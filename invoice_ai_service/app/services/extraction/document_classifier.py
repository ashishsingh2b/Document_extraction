"""Document type classifier to identify invoice vs non-invoice documents."""

import logging
import re
from typing import Dict, Tuple

logger = logging.getLogger(__name__)


class DocumentClassifier:
    """Classify document type from extracted text."""
    
    # Document type keywords
    INVOICE_KEYWORDS = [
        'tax invoice', 'sales invoice', 'purchase invoice', 'invoice no', 'bill no',
        'invoice date', 'bill date', 'gstin', 'place of supply', 'invoice',
        'sale bill', 'purchase bill', 'proforma invoice', 'credit note', 'debit note'
    ]
    
    REGISTER_KEYWORDS = [
        'register', 'ledger', 'purchase register', 'sales register', 'broker register',
        'job register', 'packing register', 'expense register', 'dying and printing register',
        'grey purchase register', 'finish purchase register'
    ]
    
    BALANCE_SHEET_KEYWORDS = [
        'balance sheet', 'trading and pl', 'profit and loss', 'p&l', 'p & l',
        'provisional balance sheet', 'trading account', 'balance sheet as on'
    ]
    
    REPORT_KEYWORDS = [
        'report', 'summary', 'statement', 'all bills', 'consolidated'
    ]
    
    def __init__(self):
        """Initialize document classifier."""
        pass
    
    def classify(self, text: str, filename: str = "") -> Dict[str, any]:
        """
        Classify document type.
        
        Args:
            text: Extracted text from document
            filename: Original filename
            
        Returns:
            Dictionary with classification result
        """
        text_lower = text.lower()
        filename_lower = filename.lower()
        
        # Check filename first (faster)
        doc_type, confidence, reason = self._classify_by_filename(filename_lower)
        
        if confidence < 0.8:
            # Check content if filename is not conclusive
            doc_type, confidence, reason = self._classify_by_content(text_lower)
        
        is_invoice = doc_type in ['sales_invoice', 'purchase_invoice']
        should_process = is_invoice

        if doc_type in ('balance_sheet', 'register', 'report'):
            should_process = False
            reason = f"{reason} — not a single tax/sales invoice (rejected for ERP upload)"

        logger.info(
            f"Document classified as: {doc_type} (confidence: {confidence:.2f}) "
            f"should_process={should_process} — {reason}"
        )

        return {
            'document_type': doc_type,
            'is_invoice': is_invoice,
            'confidence': confidence,
            'reason': reason,
            'should_process': should_process,
        }
    
    def _classify_by_filename(self, filename: str) -> Tuple[str, float, str]:
        """Classify based on filename."""
        
        # Balance sheet / Financial statements
        if any(kw in filename for kw in ['balance sheet', 'trading and pl', 'p&l', 'p & l']):
            return 'balance_sheet', 0.95, 'Filename contains balance sheet keywords'
        
        # Registers / Ledgers
        if 'register' in filename or 'ledger' in filename:
            return 'register', 0.95, 'Filename contains register/ledger'
        
        # Multi-invoice PDFs (ALL BILLS) - treat as sales invoice, will extract first invoice
        # Note: These are merged invoices from same party, not reports
        if 'all bills' in filename or 'all bill' in filename:
            return 'sales_invoice', 0.60, 'Multi-invoice PDF (will extract first invoice)'
        
        # Sales invoices
        if any(kw in filename for kw in ['sale bill', 'sales bill', 'salesbill', 'sales invoice', 'inv_']):
            return 'sales_invoice', 0.85, 'Filename indicates sales invoice'
        
        # Purchase invoices
        if 'purchase' in filename and 'register' not in filename:
            return 'purchase_invoice', 0.80, 'Filename indicates purchase invoice'
        
        # Generic invoice patterns
        if re.search(r'(bn-|ssp-|inv[_-]?\d+)', filename):
            return 'sales_invoice', 0.75, 'Filename has invoice number pattern'
        
        return 'unknown', 0.3, 'Could not determine from filename'
    
    def _classify_by_content(self, text: str) -> Tuple[str, float, str]:
        """Classify based on document content."""
        
        # Count keyword matches
        invoice_score = sum(1 for kw in self.INVOICE_KEYWORDS if kw in text)
        register_score = sum(1 for kw in self.REGISTER_KEYWORDS if kw in text)
        balance_sheet_score = sum(1 for kw in self.BALANCE_SHEET_KEYWORDS if kw in text)
        
        # Check for multiple invoices (multi-invoice PDF vs consolidated report)
        invoice_count = len(re.findall(r'invoice\s*(?:no|number|#)[\s:]*[A-Z0-9\-/]+', text, re.IGNORECASE))
        
        # Determine document type
        if balance_sheet_score > 2:
            return 'balance_sheet', 0.90, 'Balance sheet keywords found'
        
        if register_score > 2:
            return 'register', 0.90, 'Register/ledger keywords found'
        
        # Multi-invoice PDFs (2-10 invoices) - treat as sales invoice, extract first one
        # More than 10 invoices is likely a report/register
        if 2 <= invoice_count <= 10:
            return 'sales_invoice', 0.75, f'Multi-invoice PDF with {invoice_count} invoices (will extract first)'
        elif invoice_count > 10:
            return 'register', 0.85, f'Too many invoices ({invoice_count}), likely a register'
        
        # Check for invoice type
        if invoice_score >= 2:
            # Determine if sales or purchase
            has_sales = any(kw in text for kw in ['sale bill', 'sales invoice', 'sold to', 'buyer'])
            has_purchase = any(kw in text for kw in ['purchase invoice', 'purchase order', 'vendor'])
            
            if has_sales:
                return 'sales_invoice', 0.80, 'Sales invoice keywords found'
            elif has_purchase:
                return 'purchase_invoice', 0.80, 'Purchase invoice keywords found'
            else:
                return 'sales_invoice', 0.70, 'Generic invoice keywords found (assuming sales)'
        
        return 'unknown', 0.4, 'Could not classify document'


# Global instance
document_classifier = DocumentClassifier()
