"""AI-based field extraction from invoice text."""

import logging
import json
import re
from typing import Dict, Optional, List, Tuple
from datetime import datetime

logger = logging.getLogger(__name__)

INDIAN_STATES = {
    'ANDHRA PRADESH', 'ARUNACHAL PRADESH', 'ASSAM', 'BIHAR', 'CHHATTISGARH',
    'GOA', 'GUJARAT', 'HARYANA', 'HIMACHAL PRADESH', 'JHARKHAND', 'KARNATAKA',
    'KERALA', 'MADHYA PRADESH', 'MAHARASHTRA', 'MANIPUR', 'MEGHALAYA', 'MIZORAM',
    'NAGALAND', 'ODISHA', 'PUNJAB', 'RAJASTHAN', 'SIKKIM', 'TAMIL NADU',
    'TELANGANA', 'TRIPURA', 'UTTAR PRADESH', 'UTTARAKHAND', 'WEST BENGAL',
    'DELHI', 'PUDUCHERRY', 'JAMMU AND KASHMIR', 'LADAKH',
}

GSTIN_PATTERN = r'\b(\d{2}[A-Z]{5}\d{4}[A-Z]{1}[A-Z\d]{1}[Z]{1}[A-Z\d]{1})\b'

COMPANY_KEYWORDS = (
    'FASHION', 'COLLECTION', 'TRADERS', 'INTERNATIONAL', 'SAREE', 'TEXTILES',
    'INDUSTRIES', 'CORPORATION', 'COMPANY', 'LTD', 'LIMITED', 'PVT', 'MUSKAN',
    'ALAKH', 'ENTERPRISES', 'ENTERPRISE', 'EXPORT', 'IMPORT', 'GARMENTS', 'FABRICS',
    'GAYATRI', 'PALACE', 'AGENCY', 'CREATION', 'PRINTS', 'PRINTS.', 'DESIGNER',
    'DESIGN', 'SUPPLIER', 'MANUFACTURER', 'SHIVALAXMI', 'CHANDRALOK', 'KOMAL',
    'SHREE', 'SHR', 'M/S', 'SUSWAANI', 'MAHADEV', 'MUSKAN', 'PARASMAL',
    'GAYATRI', 'SAGAS', 'SHIVAM', 'FANCY', 'MILLS', 'WEAVING', 'DYEING',
)

ADDRESS_SKIP_KEYWORDS = (
    'SHOP', 'FLOOR', 'ROAD', 'MARKET', 'STREET', 'GSTIN', 'MOBILE', 'EMAIL',
    'PHONE', 'PIN', 'RING', 'PARKIN', 'CAR PARK', 'NAMAH', 'GANESHAYA',
    'COLONY', 'BLOCK', 'SECTOR', 'PLOT', 'NAGAR', 'GANDHINAGAR',
)

# Minimum word length for a standalone word to be a company indicator
_COMPANY_MIN_WORD = 4


class FieldExtractor:
    """Extract structured fields from invoice text using pattern matching and AI."""
    
    def __init__(self):
        """Initialize field extractor."""
        pass    
    
    def extract_fields(self, text: str) -> Dict[str, any]:
        """
        Extract fields from any document format — fully dynamic.

        Pipeline (priority order — later layers win):
          0. Learned patterns     — discovered from your uploaded training data
          1. Universal extractor  — auto-detects doc type, columns, grand total
          2. Regex baseline       — specific patterns for known field formats
          3. Format handler       — per-format fine-tuning (highest priority)
          4. Tax inference        — fill missing tax fields from available data
        """
        try:
            from app.services.extraction.format_registry import detect_invoice_format
            from app.services.extraction.format_enhancer import enhance_fields
            from app.services.extraction.universal_structure_extractor import extract_all as universal_extract
            from app.services.training.pattern_learner import extract_with_learned_patterns

            # ── Layer 0: Learned patterns from your uploaded training data ──
            # These are discovered automatically from all documents you uploaded.
            # Every time you retrain, new patterns are learned and used here.
            learned = extract_with_learned_patterns(text)
            logger.info(f"Learned patterns: found {len([v for v in learned.values() if v])} fields")

            # ── Layer 1: Universal structure extractor ──
            universal = universal_extract(text)
            logger.info(
                f"Universal extractor: doc_type={universal.get('_doc_type')} "
                f"conf={universal.get('_doc_type_confidence')} "
                f"cols={list(universal.get('_col_map', {}).keys())} "
                f"items={len(universal.get('items', []))}"
            )

            # ── Layer 2: Format-profile detection ──
            format_id, format_conf, format_label = detect_invoice_format(text)
            logger.info(f"Format profile: {format_id} (conf={format_conf})")

            # ── Layer 3: Regex baseline (specific patterns) ──
            # Run robust party name & GSTIN resolution first
            robust_parties = self._extract_parties_robust(text)
            
            supplier_gstin = robust_parties.get("supplier_gstin") or self._extract_gstin(text, 'supplier')
            supplier_name  = robust_parties.get("supplier_name") or self._extract_supplier_name(text)
            
            raw_buyer      = robust_parties.get("buyer_name") or self._extract_buyer_name(text, supplier_name)
            buyer_name     = self._guard_same_party(raw_buyer, supplier_name, text)
            
            buyer_gstin    = robust_parties.get("buyer_gstin") or self._extract_buyer_gstin(text, supplier_gstin)

            fields = {
                'invoice_number':  self._extract_invoice_number(text),
                'invoice_date':    self._extract_date(text, 'invoice'),
                'due_date':        self._extract_date(text, 'due'),
                'supplier_name':   supplier_name,
                'supplier_gstin':  supplier_gstin,
                'buyer_name':      buyer_name,
                'buyer_gstin':     buyer_gstin,
                'total_amount':    self._extract_amount(text, 'total'),
                'taxable_amount':  self._extract_amount(text, 'taxable'),
                'cgst_amount':     self._extract_amount(text, 'cgst'),
                'sgst_amount':     self._extract_amount(text, 'sgst'),
                'igst_amount':     self._extract_amount(text, 'igst'),
                'items':           self._extract_line_items(text),
            }

            # ── Merge Layer 0 (learned) → fills anything regex didn't get ──
            LEARNED_AMOUNT_FIELDS = {'total_amount', 'taxable_amount', 'cgst_amount', 'sgst_amount', 'igst_amount'}
            for key, lval in learned.items():
                if key.startswith('_'):
                    continue
                if lval is not None and not fields.get(key):
                    # For amount fields, try to cast to float
                    if key in LEARNED_AMOUNT_FIELDS:
                        try:
                            fields[key] = float(str(lval).replace(',', ''))
                        except ValueError:
                            pass
                    else:
                        fields[key] = lval

            # ── Merge Layer 1 (universal) → fills remaining gaps ──
            for key, uval in universal.items():
                if key.startswith('_') or key in ('items',):
                    continue
                if uval is not None and not fields.get(key):
                    fields[key] = uval

            # Universal line items: use only when regex found none
            if not fields.get('items'):
                fields['items'] = universal.get('items', [])

            # Always carry universal metadata through
            fields['_gst_total']           = universal.get('_gst_total')
            fields['_no_cgst_sgst']        = universal.get('_no_cgst_sgst', False)
            fields['_doc_type']            = universal.get('_doc_type')
            fields['_doc_type_confidence'] = universal.get('_doc_type_confidence')
            fields['report_from_date']     = universal.get('report_from_date')
            fields['report_to_date']       = universal.get('report_to_date')

            # ── Layer 4: Format-specific handler — always wins (highest priority) ──
            fields = enhance_fields(text, fields, format_id)

            # ── Layer 5: Tax inference — skipped for reports/registers ──
            fields = self._fill_missing_tax_fields(fields, text)

            fields['detected_format']  = format_id
            fields['format_label']     = format_label
            fields['format_confidence'] = format_conf

            return {
                'fields': fields,
                'extraction_confidence': self._calculate_confidence(fields),
                'detected_format': format_id,
                'format_label':    format_label,
                'format_confidence': format_conf,
                'success': True,
            }

        except Exception as e:
            logger.error(f"Field extraction failed: {str(e)}", exc_info=True)
            return {
                'fields': {},

                'error':  str(e),
                'success': False,
            }

    
    def _extract_invoice_number(self, text: str) -> Optional[str]:
        """Extract invoice number."""
        patterns = [
            # Combined Pattern: "Invoice # BPXINV-00550" or "Invoice No: 184"
            r'Invoice\s*(?:#|Number|No\.?)\s*[:\-]?\s*([A-Z0-9\-/]+)',
            r'Bill\s*No[\s\S]{0,120}?:\s*(\d{1,6})\b',
            r'Bill\s*No\s*:\s*(\d{1,6})',
            # Pattern 1: "Invoice No. : 184" (with period and colon)
            r'Invoice\s*No\.?\s*:\s*([A-Z0-9\-/]+)',
            # Pattern 2: "Invoice Number : 184"
            r'Invoice\s*(?:Number|#)\s*:\s*([A-Z0-9\-/]+)',
            # Pattern 3: "Invoice No 184" (no colon)
            r'Invoice\s*No\.?\s+([A-Z0-9\-/]+)',
            # Pattern 4: Standalone pattern like "G/1292"
            r'\b([A-Z]{1,3}[/-]\d{3,6})\b',
            # Pattern 5: Just number after "Invoice"
            r'Invoice\s*:\s*([A-Z0-9\-/]+)',
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
            if match:
                inv_num = match.group(1).strip()
                # Bill numbers are short; reject IRN/Ack-style long numeric strings
                if re.search(r'\d', inv_num) and 1 < len(inv_num) <= 16:
                    return inv_num
        
        return None
    
    def _extract_date(self, text: str, date_type: str) -> Optional[str]:
        """Extract dates supporting DD/MM/YYYY, DD-MM-YYYY and DD-Mon-YY formats."""
        # Normalize text month-name dates like '22-Apr-25' → keep as-is but match them
        MONTH_RE = r'(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)'

        if date_type == "invoice":
            patterns = [
                # DD-Mon-YY or DD-Mon-YYYY  e.g. 22-Apr-25
                rf'[Ii]nvoice\s*[Dd]ate[\s:]+([0-3]?\d[-/]{MONTH_RE}[-/]\d{{2,4}})',
                rf'[Ii]nvoice\s*[Dd]ate[\s:]+([0-3]?\d\s+{MONTH_RE}\s+\d{{2,4}})',
                r'invoice\s+detail[\s\S]{0,600}?:\s*\d+[\s\S]{0,120}?:\s*(\d{1,2}[-/]\d{1,2}[-/]\d{2,4})',
                r'bill\s*no[\s\S]{0,200}?date[\s\S]{0,80}?:\s*(\d{1,2}[-/]\d{1,2}[-/]\d{2,4})',
                r'invoice\s*date[\s:]*(\d{1,2}[-/]\d{1,2}[-/]\d{2,4})',
                r'date[\s:]*(\d{1,2}[-/]\d{1,2}[-/]\d{2,4})',
                r'dated[\s:]*(\d{1,2}[-/]\d{1,2}[-/]\d{2,4})',
            ]
        else:  # due date
            patterns = [
                # DD-Mon-YY format
                rf'[Dd]ue\s*[Dd]ate[\s:]+([0-3]?\d[-/]{MONTH_RE}[-/]\d{{2,4}})',
                rf'[Dd]ue\s*[Dd]ate[\s:]+([0-3]?\d\s+{MONTH_RE}\s+\d{{2,4}})',
                r'due\s*date[\s\S]{0,60}?:\s*(\d{1,2}[-/]\d{1,2}[-/]\d{2,4})',
                r'due\s*date[\s:]*(\d{1,2}[-/]\d{1,2}[-/]\d{2,4})',
                r'payment\s*due[\s:]*(\d{1,2}[-/]\d{1,2}[-/]\d{2,4})',
            ]

        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1).strip()

        # Fallback for invoice date: first date pattern in the first 2000 characters
        if date_type == "invoice":
            # Try Mon-name format first
            MONTH_RE = r'(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)'
            fb = re.search(rf'\b([0-3]?\d[-/]{MONTH_RE}[-/]\d{{2,4}})\b', text[:2000], re.I)
            if fb:
                return fb.group(1).strip()
            fallback_match = re.search(r'\b(\d{1,2}[-/]\d{1,2}[-/]\d{2,4})\b', text[:2000])
            if fallback_match:
                return fallback_match.group(1).strip()

        return None
    
    def _extract_text_section(
        self, text: str, start_markers: tuple, end_markers: tuple, max_len: int = 2500
    ) -> str:
        """Extract text between markers (supports multiple invoice layouts)."""
        text_lower = text.lower()
        start = 0
        for marker in start_markers:
            pos = text_lower.find(marker.lower())
            if pos >= 0:
                start = pos
                break

        end = len(text)
        for marker in end_markers:
            pos = text_lower.find(marker.lower(), start + 5)
            if pos >= 0:
                end = min(end, pos)

        return text[start : min(end, start + max_len)]

    def _extract_gstin(self, text: str, party_type: str) -> Optional[str]:
        """Extract supplier GSTIN from header (before Billed To / product table)."""
        if party_type != "supplier":
            return None
        text_lower = text.lower()
        end = len(text)
        for marker in ('billed to', 'details of consignee', 'name of product', 'broker'):
            pos = text_lower.find(marker)
            if pos > 0:
                end = min(end, pos)
        section = text[:end]
        
        # Use lenient pattern to find candidates
        candidates = re.findall(r'\b([A-Z\d]{15})\b', section, re.IGNORECASE)
        from app.services.cleaning.data_cleaner import clean_gstin
        from app.services.compliance.compliance_engine import validate_gstin
        
        # First pass: look for a strictly valid one (after OCR correction)
        for cand in candidates:
            cleaned = clean_gstin(cand)
            if cleaned:
                is_valid, _ = validate_gstin(cleaned)
                if is_valid:
                    return cleaned
                    
        # Second pass: fallback to the first corrected candidate
        for cand in candidates:
            cleaned = clean_gstin(cand)
            if cleaned:
                return cleaned
                
        return None
    
    def _is_valid_party_name(self, name: str) -> bool:
        """Validate extracted party name."""
        if not name or len(name) < 5 or len(name) > 100:
            return False
        upper = name.upper().strip()
        if upper in INDIAN_STATES:
            return False
        if any(char in name for char in ['├', '─', '│', '┬', '┤', '|']):
            return False
        skip = (
            'DETAILS', 'CONSIGNEE', 'RECEIVER', 'SHOP', 'FLOOR', 'ROAD', 'ADDRESS',
            'INVOICE', 'GSTIN', 'STATE NAME', 'TRANSPORT', 'ORIGINAL', 'DUPLICATE',
            'CHALLAN', 'ORDER NO', 'L.R.', 'E-WAY', 'TRANSPORT', 'FREIGHT',
            # Additional invalid fragments often picked up by fallback heuristics
            'SUBJECT TO', 'JURISDICTION', 'GOODS DESPATCHED', 'GOODS DISPATCH',
            'ADD COMPANY', 'ADD NAME', 'COMPANY NAME', 'AUTHORISED', 'SIGNATURE',
            'TAX INVOICE', 'SALES INVOICE', 'PURCHASE INVOICE', 'PROFORMA',
            'BILLED TO', 'SHIPPED TO', 'BILLING DETAIL', 'SHIPPING DETAIL',
            'PLACE OF SUPPLY', 'REVERSE CHARGE', 'E-WAY BILL', 'IRN',
            'DEBIT', 'CREDIT', 'MEMO', 'NOTE',
        )
        return not any(kw in upper for kw in skip)

    def _normalize_party_name(self, name: str) -> str:
        name = re.sub(r'\s+', ' ', name.strip())
        upper = name.upper()
        if ' PALACE' in upper and ' COMPLEX' in upper:
            name = name[: upper.find(' COMPLEX')].strip()
        if ' SAREE' in upper and ' COMPLEX' in upper and 'PALACE' not in upper:
            parts = name.split()
            if 'COMPLEX' in parts:
                idx = parts.index('COMPLEX')
                if idx > 0:
                    name = ' '.join(parts[:idx])
        for cut in (
            r'\s+Challan\b.*', r'\s+Invoice\b.*', r'\s+Date\b.*', r'\s+Order\b.*',
            r'\s+Place\s+Of\b.*', r'\s+L\.?\s*R\.?\b.*', r'\s+Transport\b.*',
            r'\s+No\.\s*:.*', r'\s*:\s*\d+.*$',
        ):
            name = re.sub(cut, '', name, flags=re.IGNORECASE).strip()
        return name.strip(' :|-')

    def _get_buyer_section(self, text: str) -> str:
        """Text block for buyer (Billed To / Consignee) — stops before product table."""
        text_lower = text.lower()
        for start_marker in (
            'billed to', 'details of consignee', 'details of receiver', 'shipped to',
            'buyer:', 'buyer',
        ):
            pos = text_lower.find(start_marker)
            if pos < 0:
                continue
            end = len(text)
            for end_marker in (
                'name of product', 'description of goods', 'broker', 'haste',
                'trans.id', 'e-way bill', 'sr.no', 'sr no',
            ):
                epos = text_lower.find(end_marker, pos + 10)
                if epos > 0:
                    end = min(end, epos)
            # Also stop at product line "1 SAREE" / "1|SAREE"
            product_match = re.search(
                r'(?:^|\n)\s*1\s*[|│\.]?\s*SAREE', text[pos:end], re.IGNORECASE | re.MULTILINE
            )
            if product_match:
                end = min(end, pos + product_match.start())
            return text[pos:end]
        return ""

    def _extract_buyer_gstin(self, text: str, supplier_gstin: Optional[str]) -> Optional[str]:
        """Buyer GSTIN must differ from supplier when both appear in document."""
        buyer_section = self._get_buyer_section(text)
        from app.services.cleaning.data_cleaner import clean_gstin
        
        if not buyer_section:
            buyer_section = text[text.lower().find('buyer'):] if 'buyer' in text.lower() else text

        for line in buyer_section.split('\n'):
            line_lower = line.lower()
            if 'gstin' in line_lower and 'trans' not in line_lower:
                for cand in re.findall(r'\b([A-Z\d]{15})\b', line, re.IGNORECASE):
                    gstin = clean_gstin(cand)
                    if gstin and gstin != (supplier_gstin or '').upper():
                        return gstin

        # Fallback to buyer section candidates generally
        if buyer_section:
            for cand in re.findall(r'\b([A-Z\d]{15})\b', buyer_section, re.IGNORECASE):
                gstin = clean_gstin(cand)
                if gstin and gstin != (supplier_gstin or '').upper():
                    return gstin

        # Fallback to entire text
        all_cands = re.findall(r'\b([A-Z\d]{15})\b', text, re.IGNORECASE)
        for cand in all_cands:
            gstin = clean_gstin(cand)
            if gstin and gstin != (supplier_gstin or '').upper():
                return gstin
        return None

    def _looks_like_company(self, line: str) -> bool:
        """Return True if line looks like a business/company name.

        More lenient than strict keyword matching — also accepts:
        - ALL-CAPS lines with 2+ meaningful words and no address/digit noise
        - Lines containing any COMPANY_KEYWORDS substring
        - Lines with typical Indian business suffixes (M/s., Shri., etc.)
        """
        line_clean = line.strip()
        if len(line_clean) < 4:
            return False
        upper = line_clean.upper()

        # Hard blockers: skip addresses, emails, phone numbers
        if any(kw in upper for kw in ADDRESS_SKIP_KEYWORDS):
            return False
        if re.search(r'\d{4,}', line_clean):   # long digit sequences = address/pin/phone
            return False
        if '@' in line_clean or 'www.' in line_clean.lower():
            return False
        if re.match(r'^\s*[-|:=]{2,}', line_clean):   # separator lines
            return False

        # Explicit company keyword match (most reliable)
        if any(kw in upper for kw in COMPANY_KEYWORDS):
            return True

        # All-caps multi-word line with no numbers → likely a company name
        # e.g. 'SHREE SUSWAANLENTERPRISE', 'FANCY SAREE CENTRE'
        words = [w for w in upper.split() if len(w) >= 3]
        if len(words) >= 2 and upper == upper.upper() and line_clean == line_clean.upper():
            # Exclude lines that are purely document labels
            DOC_LABELS = {'TAX INVOICE', 'SALES INVOICE', 'DEBIT MEMO', 'CREDIT NOTE',
                          'ORIGINAL', 'DUPLICATE', 'TRIPLICATE', 'QUOTATION',
                          'DELIVERY CHALLAN', 'PURCHASE ORDER', 'STATE CODE', 'STATE NAME',
                          'PAN NO', 'PLACE OF SUPPLY', 'GSTIN NO', 'INVOICE NO',
                          'MANUFACTURE & TRADERS', 'MANUFACTURE AND TRADERS'}
            # Extra: skip lines that are addresses (contain city/pincode/bazar patterns)
            ADDR_PATTERNS = ('BAZAR', 'DIST.', 'DIST ', 'TALUKA', 'TEHSIL', 'UDHYAM',
                             'VYARA', 'SURAT', 'MUMBAI', 'AHMEDABAD', 'DELHI', 'GANDHINAGAR',
                             'RING ROAD', 'TEXTILE MARKET', 'SUBJECT TO', 'JURISDICTION')
            if upper.strip() in DOC_LABELS:
                return False
            if any(ap in upper for ap in ADDR_PATTERNS):
                return False
            return True

        # Title-case company name (e.g. 'Komal Prints.', 'Max Enterprises')
        if re.match(r'^[A-Z][a-z]+(?:\s+[A-Z][a-z.]+){1,5}$', line_clean):
            if not any(kw in upper for kw in ('INVOICE', 'DATE', 'BILL', 'TOTAL', 'TAX')):
                return True

        return False

    def _clean_company_candidate(self, line: str) -> Optional[str]:
        line_clean = line.strip()
        if len(line_clean) < 3:
            return None
            
        # Strip common prefixes including roles (handles spacing-agnostic colons)
        MIS_PREFIXES = re.compile(
            r'^(?:M/[Ss]\.?\s*|Shri\.?\s*|Smt\.?\s*|s\.\s*|mr\.?\s*|mrs\.?\s*|For,?\s*|For:\s*|M/s\s+|Buyer\s*(?::|\b)\s*|Consignee\s*(?::|\b)\s*|Seller\s*(?::|\b)\s*|Name\s*(?::|\b)\s*)', 
            re.IGNORECASE
        )
        name = MIS_PREFIXES.sub('', line_clean).strip()
        
        upper = name.upper()
        sep_idx = len(name)
        
        # Separators
        for char in (',', ';', '|', '│', '┬', '┤', '├', '─'):
            idx = name.find(char)
            if idx >= 0:
                sep_idx = min(sep_idx, idx)
                
        # Multiple spaces or tabs
        m_space = re.search(r'\s{2,}', name)
        if m_space:
            sep_idx = min(sep_idx, m_space.start())
            
        # Address keywords (only truncate if NOT at the very beginning of the name)
        addr_keywords = [
            r'\bSHOP\b', r'\bPLOT\b', r'\bBLOCK\b', r'\bFLOOR\b', r'\bROAD\b', 
            r'\bMARKET\b', r'\bCOLONY\b', r'\bBAZAR\b', r'\bBBAZAR\b', r'\bBUILDING\b', 
            r'\bCOMPLEX\b', r'\bPLAZA\b', r'\bTOWER\b', r'\bDIST\b', r'\bTALUKA\b', 
            r'\bTEHSIL\b', r'\bNEAR\b', r'\bOPPOSITE\b', r'\bOPP\b', r'\bBEGUMWADI\b', 
            r'\bSALABATPURA\b', r'\bTAPI\b', r'\bVYARA\b', r'\bSURAT\b', r'\bGUJARAT\b',
            r'\bSTATE\b', r'\bCODE\b', r'\bGSTIN\b', r'\bGST\b', r'\bPAN\b', 
            r'\bPHONES\b', r'\bPHONE\b', r'\bMOBILE\b', r'\bEMAIL\b', r'\bPIN\b'
        ]
        for kw_pat in addr_keywords:
            m_kw = re.search(kw_pat, upper)
            if m_kw:
                if m_kw.start() > 2:
                    sep_idx = min(sep_idx, m_kw.start())
                    
        # 3+ digits
        m_digits = re.search(r'\b\d{3,}\b', name)
        if m_digits:
            if m_digits.start() > 0:
                sep_idx = min(sep_idx, m_digits.start())
                
        cleaned_name = name[:sep_idx].strip()
        cleaned_name = re.sub(r'^[\s\-:./|]+', '', cleaned_name).strip()
        cleaned_name = re.sub(r'[\s\-:./|]+$', '', cleaned_name).strip()
        
        if len(cleaned_name) < 4:
            return None
            
        return cleaned_name

    def _is_valid_company_name(self, name: str) -> bool:
        if not name or len(name) < 4 or len(name) > 80:
            return False
        upper = name.upper().strip()
        
        if upper in INDIAN_STATES:
            return False
            
        # Skip page headers / indicators
        if 'PAGE' in upper:
            return False
            
        # Skip religious invocations
        religious_keywords = (
            'GANESHAYA', 'GANESHAY', 'GANESHA', 'NAMAH', 'JAISHREE', 'JAI SHREE', 
            'KRISHNA', 'SHIVAY', 'SHIVAYA', 'OM ', 'BISMILLAH', 'ALHAMDULILLAH'
        )
        if any(rk in upper for rk in religious_keywords):
            return False
            
        if any(char in name for char in ['├', '─', '│', '┬', '┤', '|']):
            return False
            
        # Check if name starts with a digit pattern that indicates address
        if re.match(r'^\d{2,}', name):
            return False
            
        # Word-level blockers: block names containing standalone address/city terms
        word_blocks = {
            'ROAD', 'STREET', 'MARKET', 'BAZAR', 'SHOP', 'PLOT', 'BLOCK', 'FLOOR', 'BUILDING',
            'COMPLEX', 'TOWER', 'PLAZA', 'NEAR', 'OPP', 'OPPOSITE', 'COLONY', 'NAGAR', 'STATE',
            'CODE', 'GSTIN', 'GST', 'PAN', 'MOBILE', 'PHONE', 'PHONES', 'EMAIL', 'FAX', 'PIN',
            'SURAT', 'VYARA', 'RING', 'TEXTILE', 'GANDHINAGAR', 'GUJARAT', 'MUMBAI', 'DELHI', 
            'AHMEDABAD', 'TAPI', 'TALUKA', 'TEHSIL', 'UDYAM', 'UDHYAM'
        }
        words = upper.split()
        if any(w in word_blocks for w in words):
            return False
            
        exact_blocks = {
            'TAX INVOICE', 'SALES INVOICE', 'PURCHASE INVOICE', 'DEBIT MEMO', 'CREDIT NOTE',
            'ORIGINAL', 'DUPLICATE', 'TRIPLICATE', 'QUOTATION', 'DELIVERY CHALLAN', 
            'PURCHASE ORDER', 'STATE CODE', 'STATE NAME', 'PAN NO', 'PLACE OF SUPPLY', 
            'GSTIN NO', 'INVOICE NO', 'BILL NO', 'CHALLAN NO', 'ORDER NO', 'DATE OF SUPPLY',
            'INVOICE DATE', 'DUE DATE', 'DATE', 'BILL', 'CHALLAN', 'ORDER', 'INVOICE',
            'DESCRIPTION', 'PARTICULARS', 'HSN/SAC', 'HSN CODE', 'QTY', 'RATE', 'AMOUNT',
            'PCS QUANTITY', 'QUANTITY', 'UNIT', 'SR NO', 'S.NO', 'SR.NO.', 'S.NO.',
            'BANK DETAILS', 'ACCOUNT NO', 'IFSC CODE', 'BRANCH', 'TOTAL', 'SUB TOTAL',
            'NET AMOUNT', 'GRAND TOTAL', 'RUPEES', 'ROUNDED OFF', 'ROUND OFF',
            'TERMS & CONDITIONS', 'TERMS AND CONDITIONS', 'AUTHORISED SIGNATORY',
            'PREPARED BY', 'RECEIVED BY', 'CHECKED BY', 'DELIVERED BY', 'SIGNATURE',
            'E. & O. E.', 'E.&.O.E', 'SUBJECT TO SURAT JURISDICTION', 'SUBJECT TO VYARA JURISDICTION',
            'JURISDICTION ONLY', 'GOODS DESPATCHED', 'GOODS DISPATCHED', 'GOODS DISPATCH',
            'SELLER', 'BUYER', 'CONSIGNEE', 'RECEIVER', 'TRANSPORTER', 'BROKER', 'AGENT',
            'TRANSPORT', 'L. R. NO', 'L.R. NO', 'L. R. NO.', 'L.R. NO.', 'L.R.', 'L. R.'
        }
        if upper in exact_blocks:
            return False
            
        substring_blocks = [
            'INVOICE', 'BILL NO', 'CHALLAN', 'ORDER NO', 'DATE', 'PHONE', 'MOBILE',
            'EMAIL', 'GSTIN', 'STATE CODE', 'PAN NO', 'BANK DETAILS', 'A/C NO',
            'IFSC', 'ROUNDED', 'ROUND OFF', 'RUPEES', 'TERMS', 'JURISDICTION',
            'SIGNATORY', 'PREPARED', 'RECEIVED', 'CHECKED', 'DELIVERED', 'E.&', 'E. &',
            'GOODS DISPATCH', 'GOODS DESPATCH', 'PCS QUANTITY', 'TOTAL RS', 'NET RATE',
            'SHOP', 'PLOT', 'BLOCK', 'FLAT', 'FLOOR', 'ROAD', 'STREET', 'MARKET', 'TOWER', 
            'BUILDING', 'COMPLEX', 'PLAZA', 'COLONY', 'NAGAR', 'BAZAR', 'NEAR', 'OPP', 'OPPOSITE',
            'BEGUMWADI', 'SALABATPURA', 'RING ROAD', 'TEXTILE MARKET', 'DIST.', 'TALUKA', 'GUJARAT',
            'RECEIVER', 'CONSIGNEE', 'BILLED', 'SHIPPED', 'CUSTOMER', 'BUYER', 'STATE NAME',
            'STATE CODE', 'CHALLAN NO', 'CAR PARKIN', 'DELIVERY AT', 'AGENT NAME', 'UDYAM', 'UDHYAM',
            'SUBJECT TO', 'ORIGINAL FOR', 'DUPLICATE FOR', 'TRIPLICATE FOR', 'COPY FOR', 'PAGE ', 'PAGE-',
            'L.R. NO', 'L. R. NO', 'L.R. NO.', 'L. R. NO.', 'L.R.', 'L. R.', 'TRANSPORT'
        ]
        if any(kw in upper for kw in substring_blocks):
            return False
            
        # Block address numbers like A-57, S-3020, L/5, 3RD, etc.
        if re.search(r'\d', name):
            if len(name) <= 8 or re.search(r'\b\d{1,4}[A-Za-z]?\b', name) or re.search(r'\b[A-Za-z][\s\-]?\d+\b', name):
                return False
                
        return True

    def _extract_candidates_from_lines(self, region_lines: List[Tuple[int, str]]) -> List[str]:
        candidates = []
        current_group = []
        
        for idx, text in region_lines:
            clean = self._clean_company_candidate(text)
            if clean and self._is_valid_company_name(clean):
                if current_group and idx == current_group[-1][0] + 1:
                    # Deduplicate identical consecutive lines
                    if clean.upper() != current_group[-1][1].upper():
                        current_group.append((idx, clean))
                    else:
                        current_group[-1] = (idx, current_group[-1][1])
                else:
                    if current_group:
                        joined = " ".join([c[1] for c in current_group])
                        if self._is_valid_company_name(joined):
                            candidates.append(joined)
                    current_group = [(idx, clean)]
            else:
                if current_group:
                    joined = " ".join([c[1] for c in current_group])
                    if self._is_valid_company_name(joined):
                        candidates.append(joined)
                    current_group = []
                    
        if current_group:
            joined = " ".join([c[1] for c in current_group])
            if self._is_valid_company_name(joined):
                candidates.append(joined)
                
        return candidates

    def _score_company_name(self, name: str, index_in_region: int) -> float:
        upper = name.upper()
        score = 0.0
        
        for kw in COMPANY_KEYWORDS:
            if kw in upper:
                score += 15.0
                
        for kw in ('LTD', 'LIMITED', 'PVT', 'PRIVATE', 'M/S', 'CORP', 'CO'):
            if kw in upper:
                score += 10.0
                
        word_count = len(name.split())
        if word_count >= 2:
            score += 5.0
            
        if name == name.upper():
            score += 5.0
            
        score -= index_in_region * 2.0
        
        return score

    def _is_buyer_marker_line(self, line: str, idx: int) -> bool:
        line_lower = line.lower().strip()
        if any(kw in line_lower for kw in ('original', 'duplicate', 'triplicate', 'copy', 'transporter', 'seller', 'carrier')):
            return False
            
        # M/s is only a buyer marker if it appears after the top header (e.g. line index >= 3)
        if idx >= 3 and (line_lower.startswith('m/s.') or line_lower.startswith('m/s ')):
            return True
            
        explicit_markers = (
            'billed to', 'consignee', 'shipped to', 'buyer', 'billed details',
            'shipping details', 'details of receiver', 'details of consignee', 'details of customer',
            'customer details',
        )
        if any(m in line_lower for m in explicit_markers):
            return True
            
        if re.search(r'\bbuyer\b', line_lower):
            return True
            
        return False

    def _extract_parties_robust(self, text: str) -> Dict[str, Optional[str]]:
        """
        Extract supplier and buyer names and GSTINs dynamically and robustly.
        Guarantees that:
          1. Supplier is always from the top/header section.
          2. Supplier and Buyer names are distinct.
          3. Matches GSTINs to the correct party based on spatial context/proximity.
        """
        lines = [line.strip() for line in text.split('\n')]
        
        buyer_start_idx = len(lines)
        table_start_idx = len(lines)
        
        table_markers = ('description', 'particulars', 'particular', 'item name', 'items name', 'product name', 'hsn/sac', 'hsn code', 'hsn', 'sr.no', 'sr no', 's.no', 's no')
        
        # Find markers
        for idx, line in enumerate(lines):
            if buyer_start_idx == len(lines) and self._is_buyer_marker_line(line, idx):
                buyer_start_idx = idx
            if table_start_idx == len(lines) and any(m in line.lower() for m in table_markers):
                table_start_idx = idx
                
        # Fallback bounds if markers not found
        if buyer_start_idx == len(lines):
            buyer_start_idx = min(12, len(lines))
        if table_start_idx == len(lines):
            table_start_idx = min(35, len(lines))
            
        # Regions
        supplier_lines = [(i, lines[i]) for i in range(0, buyer_start_idx)]
        buyer_lines = [(i, lines[i]) for i in range(buyer_start_idx, table_start_idx)]
        
        # Extract candidates
        supplier_candidates = self._extract_candidates_from_lines(supplier_lines)
        buyer_candidates = self._extract_candidates_from_lines(buyer_lines)
        
        # Score candidates
        scored_suppliers = [(self._score_company_name(name, i), name) for i, name in enumerate(supplier_candidates)]
        scored_buyers = [(self._score_company_name(name, i), name) for i, name in enumerate(buyer_candidates)]
        
        scored_suppliers.sort(key=lambda x: -x[0])
        scored_buyers.sort(key=lambda x: -x[0])
        
        supplier_name = scored_suppliers[0][1] if scored_suppliers else None
        buyer_name = None
        
        # Same party guard: ensure buyer name is different from supplier name
        if scored_buyers:
            if not supplier_name:
                buyer_name = scored_buyers[0][1]
            else:
                s_clean = re.sub(r'^(?:M/[Ss]\.?\s*|Shri\.?\s*|Smt\.?\s*|s\.\s*|mr\.?\s*|mrs\.?\s*|For,?\s*|For:\s*)', '', supplier_name, flags=re.I).strip().upper()
                
                # Find first buyer candidate that doesn't match supplier
                found_buyer = False
                for score, b_name in scored_buyers:
                    b_clean = re.sub(r'^(?:M/[Ss]\.?\s*|Shri\.?\s*|Smt\.?\s*|s\.\s*|mr\.?\s*|mrs\.?\s*|For,?\s*|For:\s*)', '', b_name, flags=re.I).strip().upper()
                    
                    if s_clean == b_clean or s_clean in b_clean or b_clean in s_clean:
                        continue
                    buyer_name = b_name
                    found_buyer = True
                    break
                    
                if not found_buyer:
                    buyer_name = None
                    
        # GSTIN extraction and regional mapping
        gstin_re = re.compile(r'\b(\d{2}[A-Z]{5}\d{4}[A-Z][A-Z\d]Z[A-Z\d])\b')
        gstin_hits = []
        for idx, line in enumerate(lines):
            for m in gstin_re.finditer(line):
                gstin_hits.append((idx, m.group(1).upper()))
                
        seen_gstins = set()
        unique_gstins = []
        for idx, gstin in gstin_hits:
            if gstin not in seen_gstins:
                seen_gstins.add(gstin)
                unique_gstins.append((idx, gstin))
                
        supplier_gstin = None
        buyer_gstin = None
        
        for idx, gstin in unique_gstins:
            if idx < buyer_start_idx:
                if not supplier_gstin:
                    supplier_gstin = gstin
            elif idx < table_start_idx:
                if not buyer_gstin:
                    buyer_gstin = gstin
                    
        # Apply strict same-party guard for GSTINs or align them if mismatched/incomplete
        if len(unique_gstins) >= 2:
            gstin_vals = [g[1] for g in unique_gstins]
            if supplier_gstin == buyer_gstin or not supplier_gstin or not buyer_gstin:
                if buyer_gstin in gstin_vals:
                    buyer_gstin = buyer_gstin
                    other_gstins = [g for g in gstin_vals if g != buyer_gstin]
                    if other_gstins:
                        supplier_gstin = other_gstins[0]
                elif supplier_gstin in gstin_vals:
                    supplier_gstin = supplier_gstin
                    other_gstins = [g for g in gstin_vals if g != supplier_gstin]
                    if other_gstins:
                        buyer_gstin = other_gstins[0]
                else:
                    supplier_gstin = gstin_vals[0]
                    buyer_gstin = gstin_vals[1]
        elif len(unique_gstins) == 1:
            if not supplier_gstin and not buyer_gstin:
                supplier_gstin = unique_gstins[0][1]
            elif buyer_gstin and not supplier_gstin:
                pass
            elif supplier_gstin and not buyer_gstin:
                pass
                
        return {
            "supplier_name": supplier_name,
            "supplier_gstin": supplier_gstin,
            "buyer_name": buyer_name,
            "buyer_gstin": buyer_gstin
        }

    def _extract_party_names_from_gstins(self, text: str):
        """GSTIN-anchored party name extraction (primary method for all invoices).

        Indian GST law requires every invoice to show:
          - Supplier GSTIN + supplier name (always in the TOP/HEADER of the invoice)
          - Buyer GSTIN + buyer name (in the consignee/billing section)

        Strategy:
          1. Find ALL GSTINs in the document.
          2. For each GSTIN, scan the 6 lines BEFORE it — the company name is always
             directly above the GSTIN line.
          3. First GSTIN context  → Supplier name
          4. Second GSTIN context → Buyer name
          5. If second GSTIN is a repeat of the first (multi-page), skip to next unique GSTIN.

        Returns: (supplier_name, buyer_name) or (None, None) if not found.
        """
        lines = text.split('\n')
        gstin_re = re.compile(r'\b(\d{2}[A-Z]{5}\d{4}[A-Z][A-Z\d]Z[A-Z\d])\b')

        # Find each GSTIN and its line number
        gstin_hits = []  # (line_idx, gstin_value)
        for i, line in enumerate(lines):
            for m in gstin_re.finditer(line):
                gstin_hits.append((i, m.group(1)))

        if not gstin_hits:
            return None, None

        # Labels to skip when looking for a company name
        SKIP_LABELS = {
            'TAX INVOICE', 'SALES INVOICE', 'PURCHASE INVOICE', 'DEBIT MEMO',
            'CREDIT NOTE', 'PROFORMA INVOICE', 'ORIGINAL COPY', 'DUPLICATE COPY',
            'TRIPLICATE COPY', 'BILL', 'RECEIPT', 'ORIGINAL', 'DUPLICATE',
            'TRIPLICATE', 'INVOICE', 'ADD LOGO', 'ADD ADDRESS', 'ADD COMPANY NAME',
            '--- PAGE 1 ---', '--- PAGE 2 ---', 'GSTIN', 'STATE CODE', 'STATE NAME',
            'PAN NO', 'PAN NO.', 'M/S.', 'M/S', 'DELIVERY CHALLAN',
        }
        # Prefixes that introduce the company name (e.g. "M/s. MAHADEV FASHION")
        MIS_PREFIXES = re.compile(r'^(?:M/[Ss]\.?|Shri\.?|Smt\.?|s\.\s+|m/s\.?\s+)', re.IGNORECASE)

        def _best_name_before_gstin(gstin_line_idx: int) -> Optional[str]:
            """Scan up to 8 lines before this GSTIN line, return best company name."""
            candidates = []
            for j in range(gstin_line_idx - 1, max(-1, gstin_line_idx - 9), -1):
                raw = lines[j].strip()
                if not raw:
                    continue
                # Strip M/s. prefixes
                clean = MIS_PREFIXES.sub('', raw).strip()
                upper = clean.upper()
                if upper in SKIP_LABELS:
                    continue
                if not self._is_valid_party_name(clean):
                    continue
                if self._looks_like_company(clean):
                    candidates.append(clean)
            # Return the first (closest above GSTIN) valid company name
            return self._normalize_party_name(candidates[0]) if candidates else None

        # Deduplicate GSTINs while preserving first-seen order
        seen_gstins = []
        unique_gstin_hits = []
        for (li, gv) in gstin_hits:
            if gv not in seen_gstins:
                seen_gstins.append(gv)
                unique_gstin_hits.append((li, gv))

        supplier_name = None
        buyer_name    = None

        if len(unique_gstin_hits) >= 1:
            supplier_name = _best_name_before_gstin(unique_gstin_hits[0][0])
            logger.info(f"GSTIN-anchor supplier: GSTIN={unique_gstin_hits[0][1]} name={supplier_name}")

        if len(unique_gstin_hits) >= 2:
            buyer_name = _best_name_before_gstin(unique_gstin_hits[1][0])
            logger.info(f"GSTIN-anchor buyer: GSTIN={unique_gstin_hits[1][1]} name={buyer_name}")

        return supplier_name, buyer_name

    def _extract_supplier_name(self, text: str) -> Optional[str]:
        """Extract supplier/seller name from invoice header.

        Priority:
          S0 – GSTIN-anchored (company just before first GSTIN)  ← primary
          S1 – Explicit label  (Seller / From / Supplier)
          S2 – Known brand patterns in header area
          S3 – Header scan fallback
        """
        text_lower = text.lower()

        # ── S1: Explicit label ───────────────────────────────────────────────
        for label_pat in [
            r'(?:^|\n)\s*(?:Seller|From|Supplier)[\s:]*\n+\s*([A-Za-z][A-Za-z0-9\s&\.\-]{3,60}?)(?=\n|GSTIN|State|Mobile)',
            r'(?:^|\n)\s*(?:Seller|From|Supplier)\s*:\s*([A-Za-z][A-Za-z0-9\s&\.\-]{3,60}?)(?=\n|GSTIN)',
        ]:
            m = re.search(label_pat, text, re.IGNORECASE | re.MULTILINE | re.DOTALL)
            if m:
                name = self._normalize_party_name(m.group(1))
                if self._is_valid_party_name(name):
                    logger.info(f"Supplier from label: {name}")
                    return name

        # ── S2: Company-like line JUST BEFORE the first GSTIN in the doc ────
        gstin_pat = r'\b(\d{2}[A-Z]{5}\d{4}[A-Z][A-Z\d]Z[A-Z\d])\b'
        all_gstins = list(re.finditer(gstin_pat, text))
        if all_gstins:
            first_gstin = all_gstins[0]
            # Look at the 400 chars before the first GSTIN
            before = text[max(0, first_gstin.start() - 400):first_gstin.start()]
            candidate_lines = [l.strip() for l in before.split('\n') if l.strip()]
            # Walk backwards — first company-like line wins
            SKIP_BEFORE = {
                'TAX INVOICE', 'SALES INVOICE', 'PURCHASE INVOICE', 'PROFORMA INVOICE',
                'ORIGINAL COPY', 'DUPLICATE COPY', 'TRIPLICATE COPY', 'BILL', 'RECEIPT',
                'GSTIN', 'STATE CODE', 'PAGE NO', 'ADD LOGO', 'ADD ADDRESS', 'ADD COMPANY NAME',
                '--- PAGE 1 ---', '--- PAGE 2 ---',
            }
            for line in reversed(candidate_lines):
                if line.upper() in SKIP_BEFORE:
                    continue
                if not self._is_valid_party_name(line):
                    continue
                if self._looks_like_company(line):
                    name = self._normalize_party_name(line)
                    logger.info(f"Supplier from pre-GSTIN line: {name}")
                    return name

        # ── S3: Known brand patterns ─────────────────────────────────────────
        # Limit search to header (text before first buyer-section marker)
        header_end = len(text)
        for marker in ('billed to', 'details of consignee', 'name of product', 'particulars'):
            pos = text_lower.find(marker)
            if pos > 0:
                header_end = min(header_end, pos)
        header = text[:header_end]

        for pattern in [
            r'(GAYATRI\s+SAREE(?:\s+HOUSE)?)',
            r'(MUSKAN\s+COLLECTION)',
            r'(SAGAS\s+COLLECTION)',
            r'([A-Za-z][A-Za-z\s&\.\-]{2,40}\s+SAREE(?:\s+HOUSE)?)',
            r'([A-Za-z][A-Za-z\s&\.\-]{2,40}\s+COLLECTION)',
            r'([A-Za-z][A-Za-z\s&\.\-]{2,40}\s+(?:TEXTILES|FASHION|TRADERS|ENTERPRISES|INDUSTRIES))',
        ]:
            m = re.search(pattern, header, re.IGNORECASE)
            if m:
                name = self._normalize_party_name(m.group(1))
                if self._is_valid_party_name(name):
                    logger.info(f"Supplier from brand pattern: {name}")
                    return name.upper() if name.isupper() else name

        # ── S4: Header scan (fallback) ───────────────────────────────────────
        gstin_match = all_gstins[0] if all_gstins else None
        gstin_label_m = re.search(r'GSTIN\s*[-:]\s*([A-Z0-9]{15})', text)
        if gstin_label_m and not gstin_match:
            gstin_match = gstin_label_m

        end_pos = gstin_match.start() if gstin_match else min(
            text.upper().find('TAX INVOICE') if 'TAX INVOICE' in text.upper() else len(text), 800,
        )
        header_text = text[:end_pos] if end_pos > 0 else text[:800]

        SUPPLIER_SKIP = {
            'TAX INVOICE', 'SALES INVOICE', 'PURCHASE INVOICE', 'PROFORMA INVOICE',
            'ORIGINAL COPY', 'DUPLICATE COPY', 'TRIPLICATE COPY', 'INVOICE', 'BILL',
            'RECEIPT', 'ADD LOGO', 'ADD ADDRESS', 'ADD COMPANY NAME', '--- PAGE 1 ---',
        }
        for line in header_text.split('\n'):
            line_clean = line.strip()
            if line_clean.upper() in SUPPLIER_SKIP:
                continue
            if self._looks_like_company(line_clean) and self._is_valid_party_name(line_clean):
                logger.info(f"Supplier from header scan: {line_clean}")
                return self._normalize_party_name(line_clean)

        return None
    
    def _extract_buyer_name(self, text: str, supplier_name: Optional[str] = None) -> Optional[str]:
        """Extract buyer/customer name.

        After extraction, validates that result != supplier_name (same-party guard).
        """
        # Strategy -1: Duplicate company line right after Billed To / Shipped To (Muskan-style OCR)
        dup = re.search(
            r'(?:Details\s*of\s*Consignee\s*[|｜]?\s*Shipped\s*To'
            r'|Details\s*of\s*Receiver\s*[|｜]?\s*Billed\s*To)\s*:\s*\n'
            r'\s*([A-Za-z0-9][A-Za-z0-9\s&.\-]{3,65}?)\s*\n\s*\1\s*\n',
            text,
            re.IGNORECASE | re.MULTILINE,
        )
        if dup:
            name = self._normalize_party_name(dup.group(1))
            if name.upper() not in INDIAN_STATES and self._is_valid_party_name(name):
                logger.info(f"Found buyer (duplicate line after ship/bill headers): {name}")
                return name

        # Strategy 0a: Explicit "Buyer: NAME  BILL NO." pattern (KOMAL PRINTS layout)
        buyer_label = re.search(
            r'(?:^|\n)Buyer:\s*([A-Za-z][A-Za-z\s&.\-]{3,60}?)(?:\s{2,}|\s+BILL\s|\s+CHALLAN\s|\n)',
            text,
            re.IGNORECASE | re.MULTILINE,
        )
        if buyer_label:
            name = self._normalize_party_name(buyer_label.group(1))
            if self._is_valid_party_name(name):
                logger.info(f"Found buyer (Buyer: label): {name}")
                return name

        # Strategy 0b: Explicit pattern right after Billed To
        direct = re.search(
            r'Billed\s+To[^\n]*\n\s*([A-Za-z][A-Za-z\s&\.\-]{3,60}?(?:PALACE|SAREE\s+PALACE|INTERNATIONAL|COLLECTION))',
            text,
            re.IGNORECASE,
        )
        if direct:
            name = self._normalize_party_name(direct.group(1))
            if self._is_valid_party_name(name):
                logger.info(f"Found buyer (direct Billed To): {name}")
                return name

        block = self._get_buyer_section(text)
        if block:
            candidates = []
            for line_idx, line in list(enumerate(block.split('\n')[:8])):
                line_clean = self._normalize_party_name(line)
                if not line_clean or len(line_clean) < 5:
                    continue
                upper = line_clean.upper()
                if 'BILLED TO' in upper:
                    continue
                if any(kw in upper for kw in ('GSTIN', 'STATE', 'CODE', 'PLACE OF', 'UTTAR', 'PRADESH')):
                    continue
                if re.search(r'\d{5,}', line_clean):
                    continue
                if upper.startswith('OPPOSITE') or 'BANK OF' in upper or 'GORAKHPUR' in upper:
                    continue
                if not self._is_valid_party_name(line_clean):
                    continue
                score = sum(2 for kw in ('PALACE', 'SAREE', 'INTERNATIONAL', 'COLLECTION') if kw in upper)
                score += sum(1 for kw in COMPANY_KEYWORDS if kw in upper)
                if 'COMPLEX' in upper and 'PALACE' not in upper and 'SAREE' not in upper:
                    score -= 2
                score += max(0, 5 - line_idx)
                candidates.append((score, line_clean))

            if candidates:
                candidates.sort(key=lambda x: (-x[0], -len(x[1])))
                logger.info(f"Found buyer from Billed To block: {candidates[0][1]}")
                return candidates[0][1]

        # Strategy 1: "Name :" on its own line — NOT "State Name :" (Tesseract matches GUJARAT otherwise)
        for match in re.finditer(
            r'(?:^|\n)\s*Name\s*:\s*:?\s*([A-Za-z][A-Za-z0-9\s&\.\-]+?)(?=\n|$)',
            text,
            re.IGNORECASE | re.MULTILINE,
        ):
            name = self._normalize_party_name(match.group(1))
            if self._is_valid_party_name(name):
                logger.info(f"Found buyer from 'Name :' field: {name}")
                return name
            if name.upper() in INDIAN_STATES:
                logger.info(f"Skipping state in 'Name :' field: {name}")

        # Strategy 2: Known buyer patterns
        for pattern in [
            r'(SURAT\s+SAREE\s+PALACE)',
            r'(ALAKH\s+INTERNATIONAL)',
            r'([A-Za-z][A-Za-z\s&\.\-]{2,40}\s+PALACE)',
            r'([A-Za-z][A-Za-z\s&\.\-]{2,40}\s+INTERNATIONAL)',
        ]:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                name = self._normalize_party_name(match.group(1))
                if self._is_valid_party_name(name):
                    return name

        # Strategy 3: Consignee / Billed To sections
        section_patterns = [
            r'Details\s*of\s*Consignee[^\n]*\n(?:[^\n]+\n){0,6}?Name\s*:\s*([A-Za-z][A-Za-z0-9\s&\.\-]+?)(?=\n|GSTIN|State)',
            r'Details\s*of\s*Consignee[\s:]*\n+\s*:?\s*([A-Za-z][A-Za-z0-9\s&\.\-]+?)(?=\n|GSTIN|State|Mobile)',
            r'(?:Details\s*of\s*Receiver|Billed\s*To|Shipped\s*To)[^\n]*\n(?:[^\n]+\n){0,4}?Name\s*:\s*([A-Za-z][A-Za-z0-9\s&\.\-]+?)(?=\n)',
            r'(?:Details\s*of\s*Receiver|Billed\s*To)[\s:]*\n+\s*([A-Za-z][A-Za-z0-9\s&\.\-]+?)(?=\n|GSTIN)',
        ]
        for pattern in section_patterns:
            match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE | re.DOTALL)
            if match:
                name = self._normalize_party_name(match.group(1))
                if self._is_valid_party_name(name):
                    return name

        # Strategy 4: Company-like line before second GSTIN
        gstins = list(re.finditer(
            r'\b\d{2}[A-Z]{5}\d{4}[A-Z]{1}[A-Z\d]{1}[Z]{1}[A-Z\d]{1}\b', text
        ))
        if len(gstins) >= 2:
            search_start = max(gstins[0].end(), gstins[1].start() - 400)
            block = text[search_start:gstins[1].start()]
            for line in reversed(block.split('\n')):
                line_clean = line.strip()
                if self._looks_like_company(line_clean) and self._is_valid_party_name(line_clean):
                    return self._normalize_party_name(line_clean)

        return None

    def _guard_same_party(self, buyer, supplier, text):
        """If buyer == supplier (exact or fuzzy), try to find a different name.
        Returns buyer if clearly different, or None if same and no alternative found."""
        if not buyer or not supplier:
            return buyer

        # Strip common prefixes before comparison (M/s., Shri., s., etc.)
        import re as _re
        _prefix_re = _re.compile(r'^(?:M/[Ss]\.?\s*|Shri\.?\s*|Smt\.?\s*|s\.\s*|mr\.?\s*|mrs\.?\s*)', _re.IGNORECASE)
        b_clean = _prefix_re.sub('', buyer).strip().upper()
        s_clean = _prefix_re.sub('', supplier).strip().upper()

        # Exact match after prefix-stripping
        exact_same = (b_clean == s_clean)
        # Containment: one is a substring of the other
        contained  = (b_clean in s_clean or s_clean in b_clean) and min(len(b_clean), len(s_clean)) >= 6

        if exact_same or contained:
            reason = "exact match" if exact_same else f"containment"
            logger.warning(f"Buyer\u2248Supplier ({reason}) buyer={buyer!r} supplier={supplier!r} — scanning for alternative")
            buyer_section = self._get_buyer_section(text)
            for line in (buyer_section or '').split('\n'):
                line_clean = line.strip()
                if not line_clean or len(line_clean) < 5:
                    continue
                norm = self._normalize_party_name(line_clean)
                norm_clean = _prefix_re.sub('', norm).strip().upper()
                if not self._is_valid_party_name(norm):
                    continue
                if norm_clean == s_clean or norm_clean in s_clean or s_clean in norm_clean:
                    continue
                if self._looks_like_company(norm):
                    logger.info(f"Same-party guard: found alternative buyer '{norm}'")
                    return norm
            logger.warning("Same-party guard: no distinct alternative buyer found, returning None")
            return None

        return buyer

    def _extract_amount(self, text: str, amount_type: str) -> Optional[float]:
        """Extract various amounts with better patterns for Indian invoices."""
        patterns = []
        
        if amount_type == "total":
            patterns = [
                r'(?:Net\s+Amount|Grand\s+Total\s*\/\s*Net\s+Amount)[\s:]*(?:rs\.?|₹|inr)?\s*([\d,]+\.?\d*)',
                r'Net\s+Amount\s*\n\s*(?:rs\.?|₹|inr)?\s*([\d,]+\.?\d*)',
                # Most specific first: labeled total lines
                r'Total\s+Amt\s+After\s+Tax\s*([\d,]+\.?\d*)',
                r'(?:Net\s+Amount|Grand\s*Total|Invoice\s+Value|Amount\s+Payable)[\s:]*(?:rs\.?|₹|inr)?\s*([\d,]+\.?\d*)',
                r'(?:Total\s+Amount)(?!\s*Before)(?!\s*After)[\s:]*(?:rs\.?|₹|inr)?\s*([\d,]+\.?\d*)',
                # Standalone "Total" line followed by amount (including Indian format 1,16,800)
                r'(?:^|\n)\s*Total\s+([\d,]+\.?\d*)\s*$',
            ]
        elif amount_type == "taxable":
            patterns = [
                r'DISCOUNT\s+[\d.]+%\s*([\d,]+\.?\d*)',
                r'(?:Taxable\s*(?:Amount|Value)|Taxable\s*Value)[\s:]*(?:rs\.?|₹|inr)?\s*([\d,]+\.?\d*)',
                r'(?:Gross\s*Amount|Assessable\s*Value)[\s:]*(?:rs\.?|₹|inr)?\s*([\d,]+\.?\d*)',
                r'(?:Sub\s*Total|Subtotal)(?!\s*(?:Amount|Invoice))[\s:]*(?:rs\.?|₹|inr)?\s*([\d,]+\.?\d*)',
                r'(?:Total\s*Before\s*Tax|Amount\s*Before\s*Tax|Total\s+Amt\s+Before\s+Tax)[\s:]*(?:rs\.?|₹|inr)?\s*([\d,]+\.?\d*)',
                r'Total\.{2,}[^\d\n]*([\d,]+\.?\d{2})(?=\s*(?:\n|$|[+\-]|IGST|CGST))',
                # "Sale @18% = 100000.00"  — sale base before GST
                r'Sale\s*@\d+(?:\.\d+)?%\s*=\s*([\d,]+\.?\d*)',
                # "Total Sale = 100000.00"
                r'Total\s+Sale\s*=\s*([\d,]+\.?\d*)',
            ]
        elif amount_type == "cgst":
            patterns = [
                # Pattern 1: "CGST Amount : 13518.85" (most specific)
                r'CGST\s*(?:Amount|Value)[\s:]*(?:rs\.?|₹|inr)?\s*([\d,]+\.?\d*)',
                # Pattern 2: "Central GST : 13518.85"
                r'Central\s*GST[\s:]*(?:rs\.?|₹|inr)?\s*([\d,]+\.?\d*)',
                # Pattern 3: In tax table - "2.5% 13518.85" (rate followed by amount)
                r'(?:CGST|Central\s*GST).*?[\d.]+%[\s]*(?:rs\.?|₹|inr)?\s*([\d,]+\.?\d+)',
                # Pattern 4: "CGST (2.50%) + 2874.38" or "CGST (2.50%) 2874.38"
                r'CGST\s*\([\d.]+%\)[\s+:]*(?:rs\.?|₹|inr)?\s*([\d,]+\.?\d+)',
                # Pattern 5: "CGST @ 2.50% : 2874.38"
                r'CGST[\s@]*[\d.]+%[\s:]*(?:rs\.?|₹|inr)?\s*([\d,]+\.?\d+)',
                # Pattern 6: "CGST 2.50 2874.38" (space-separated)
                r'CGST[\s]+[\d.]+[\s]+([\d,]+\.?\d+)',
                # Pattern 7: Just "CGST" followed by amount on same or next line
                r'CGST\s*[\d.]+%?\s*([\d,]+\.?\d{2,})',
                r'CGST[\s\n:]*(?:rs\.?|₹|inr)?\s*([\d,]+\.?\d+)',
            ]
        elif amount_type == "sgst":
            patterns = [
                # Pattern 1: "SGST Amount : 13518.85" (most specific)
                r'SGST\s*(?:Amount|Value)[\s:]*(?:rs\.?|₹|inr)?\s*([\d,]+\.?\d*)',
                # Pattern 2: "State GST : 13518.85"
                r'State\s*GST[\s:]*(?:rs\.?|₹|inr)?\s*([\d,]+\.?\d*)',
                # Pattern 3: In tax table - "2.5% 13518.85" (rate followed by amount)
                r'(?:SGST|State\s*GST).*?[\d.]+%[\s]*(?:rs\.?|₹|inr)?\s*([\d,]+\.?\d+)',
                # Pattern 4: "SGST (2.50%) + 2874.38" or "SGST (2.50%) 2874.38"
                r'SGST\s*\([\d.]+%\)[\s+:]*(?:rs\.?|₹|inr)?\s*([\d,]+\.?\d+)',
                # Pattern 5: "SGST @ 2.50% : 2874.38"
                r'SGST[\s@]*[\d.]+%[\s:]*(?:rs\.?|₹|inr)?\s*([\d,]+\.?\d+)',
                # Pattern 6: "SGST 2.50 2874.38" (space-separated)
                r'SGST[\s]+[\d.]+[\s]+([\d,]+\.?\d+)',
                # Pattern 7: Just "SGST" followed by amount on same or next line
                r'SGST\s*[\d.]+%?\s*([\d,]+\.?\d{2,})',
                r'SGST[\s\n:]*(?:rs\.?|₹|inr)?\s*([\d,]+\.?\d+)',
            ]
        elif amount_type == "igst":
            patterns = [
                # "+ IGST 5.00% 3192.00" (GAYATRI format)
                r'[+\-]?\s*IGST\s+[\d.]+\s*%\s*([\d,]+\.?\d*)',
                r'IGST\s*\([\d.]+%\)[\s+:]*(?:rs\.?|₹|inr)?\s*([\d,]+\.?\d*)',
                r'IGST[\s@]*[\d.]+%[\s:]*(?:rs\.?|₹|inr)?\s*([\d,]+\.?\d*)',
                r'IGST\s*(?:Amount|Value)[\s:]*(?:rs\.?|₹|inr)?\s*([\d,]+\.?\d*)',
                r'Integrated\s*GST[\s:]*(?:rs\.?|₹|inr)?\s*([\d,]+\.?\d*)',
                # "IGST = 18000.00" or "IGST: 18000.00"
                r'\bIGST\s*[=:]\s*([\d,]+\.?\d*)',
                # "Sale @18% = 100000.00, IGST = 18000.00"
                r'IGST\s*=\s*([\d,]+\.?\d*)',
            ]
        else:
            return None
        
        for pattern in patterns:
            matches = re.finditer(pattern, text, re.IGNORECASE | re.MULTILINE)
            amounts_found = []
            
            for match in matches:
                amount_str = match.group(1).replace(',', '').replace(' ', '')
                try:
                    amount = float(amount_str)
                    # Sanity check - amounts should be reasonable
                    # For tax rates, reject values less than 10 (likely percentages like 2.5%)
                    if amount_type in ["cgst", "sgst", "igst"]:
                        if 10 <= amount < 100000000:  # Tax amounts should be at least 10
                            amounts_found.append(amount)
                    elif amount_type == "taxable" and amount < 100:
                        continue
                    elif 0 < amount < 100000000:  # Less than 10 crore
                        amounts_found.append(amount)
                except ValueError:
                    continue
            
            # Return first match if found
            if amounts_found:
                if amount_type == "total":
                    return max(amounts_found)  # Return largest for total
                else:
                    return amounts_found[0]
        
        # Special handling for total amount: look for largest amount near "Total" keywords
        if amount_type == "total":
            keywords = [
                "total invoice amount", "net amount", "grand total", "total amount", 
                "invoice total", "net total", "net amt", "invoice value", 
                "amount payable", "total payable", "total due"
            ]
            candidates = []
            
            # Find all keyword positions
            for kw in keywords:
                for match in re.finditer(r'\b' + re.escape(kw) + r'\b', text, re.IGNORECASE):
                    start, end = match.span()
                    # Look before the keyword
                    before_start_idx = max(0, start - 60)
                    before_text = text[before_start_idx:start]
                    for num_match in re.finditer(r'([\d,]+\.?\d{2})', before_text):
                        try:
                            val = float(num_match.group(1).replace(',', ''))
                            if 1000 < val < 100000000:
                                if num_match.start() == 0 and before_start_idx > 0 and text[before_start_idx - 1].isdigit():
                                    continue
                                candidates.append(val)
                        except ValueError:
                            pass
                    # Look after the keyword
                    after_text = text[end:min(len(text), end + 60)]
                    for num_match in re.finditer(r'([\d,]+\.?\d{2})', after_text):
                        try:
                            val = float(num_match.group(1).replace(',', ''))
                            if 1000 < val < 100000000:
                                if end + num_match.end() < len(text) and text[end + num_match.end()].isdigit():
                                    continue
                                candidates.append(val)
                        except ValueError:
                            pass
            
            # Standalone "total" keyword
            for match in re.finditer(r'\btotal\b(?!\s*(?:gst|tax|payable|due|cgst|sgst|igst|round|perc))', text, re.IGNORECASE):
                start, end = match.span()
                before_start_idx = max(0, start - 60)
                before_text = text[before_start_idx:start]
                for num_match in re.finditer(r'([\d,]+\.?\d{2})', before_text):
                    try:
                        val = float(num_match.group(1).replace(',', ''))
                        if 1000 < val < 100000000:
                            if num_match.start() == 0 and before_start_idx > 0 and text[before_start_idx - 1].isdigit():
                                continue
                            candidates.append(val)
                    except ValueError:
                        pass
                after_text = text[end:min(len(text), end + 60)]
                for num_match in re.finditer(r'([\d,]+\.?\d{2})', after_text):
                    try:
                        val = float(num_match.group(1).replace(',', ''))
                        if 1000 < val < 100000000:
                            if end + num_match.end() < len(text) and text[end + num_match.end()].isdigit():
                                continue
                            candidates.append(val)
                    except ValueError:
                        pass
                        
            if candidates:
                return max(candidates)
            
            # Strategy 2: Look in last 30% of document for largest amount (excluding small values)
            last_section = text[int(len(text) * 0.7):]
            
            # Find all amounts in last section
            amount_pattern = r'(?:rs\.?|₹|inr)?\s*([\d,]+\.?\d{2})'
            matches = re.finditer(amount_pattern, last_section, re.IGNORECASE)
            
            amounts_in_footer = []
            for match in matches:
                amount_str = match.group(1).replace(',', '').replace(' ', '')
                try:
                    amount = float(amount_str)
                    # Filter out tax amounts (typically < 1000) and percentages
                    if 1000 < amount < 100000000:  # Reasonable invoice total (> 1k)
                        amounts_in_footer.append(amount)
                except ValueError:
                    continue
            
            # Return the largest amount found in footer (likely the total)
            if amounts_in_footer:
                return max(amounts_in_footer)
        
        return None
    
    def _extract_line_items(self, text: str) -> list:
        """
        Generic line item extractor for any tabular invoice format.

        Supports:
          • Sr | Item Description | HSN/SAC | Qty | Unit | List Price | Tax% | Amount
          • Sr | Description | HSN | Pcs | Mts | Rate | Amount  (fabric invoices)
          • Sr | Description | HSN | Qty | Rate | Amount       (simple 3-col)
        """
        items = []
        seen = set()

        # ── Pattern A: Sr  Description  HSN(6-8 digits)  Qty  Unit  Price  [Disc]  Tax%  Amount ──
        # Handles: empty Disc column, extra whitespace, Indian-format amounts
        pat_a = re.compile(
            r'(?:^|\n)\s*(\d{1,3})\s+'           # Sr no
            r'([A-Za-z][A-Za-z0-9\s\-,./]{2,60}?)\s{2,}'  # Description (2+ spaces before HSN)
            r'(\d{4,8})\s+'                       # HSN/SAC code
            r'([\d.]+)\s+'                         # Qty
            r'([A-Za-z]{1,10})\s+'                 # Unit
            r'([\d,]+\.?\d*)\s+'                   # List Price
            r'(?:[\d,]*\.?\d*\s+)?'               # Optional Disc (may be empty/missing)
            r'([\d]{1,3}(?:\.\d+)?)\s+'           # Tax %  (1-3 digit number like 18.00)
            r'([\d,]+\.?\d*)',                     # Amount
            re.MULTILINE
        )
        for m in pat_a.finditer(text):
            desc = m.group(2).strip()
            key = desc.upper()[:30]
            if key in seen:
                continue
            # Skip if description IS a column header label (exact or nearly exact)
            desc_upper = desc.upper().strip()
            HEADER_LABELS = {
                'DESCRIPTION', 'ITEM DESCRIPTION', 'ITEM', 'PARTICULARS',
                'HSN', 'HSN/SAC', 'QTY', 'QUANTITY', 'UNIT', 'PRICE',
                'AMOUNT', 'SR', 'SR.', 'SR NO', 'S.NO',
            }
            if desc_upper in HEADER_LABELS:
                continue
            seen.add(key)
            items.append({
                'sr_no':       m.group(1),
                'description': desc,
                'hsn_code':    m.group(3),
                'quantity':    float(m.group(4).replace(',', '')),
                'unit':        m.group(5),
                'rate':        float(m.group(6).replace(',', '')),
                'tax_pct':     float(m.group(7)),
                'amount':      float(m.group(8).replace(',', '')),
            })

        if items:
            return items

        # ── Pattern B: Vertical-cell OCR (cells on separate lines) ─────────────
        # Triggered when header contains PARTICULAR/DESCRIPTION + HSN + PCS/QTY on separate lines.
        # Each data cell is on its own line; groups are delimited by serial-number lines.
        B_STOP = {'central gst','state gst','cgst','sgst','igst','net total','grand total',
                  'taxable','amount in words','bank','declaration','terms','total :',
                  'total amount','sub total','total qty','total quantity'}
        UNIT_WORDS = {'p', 'box', 'pcs', 'mtr', 'nos', 'kg', 'kgs', 'set', 'per', 'mts', 'l'}

        # Order-agnostic header detection: scan windows of consecutive lines for
        # presence of Description/Particular + HSN/SAC + Qty/Rate/Amount keywords
        def _find_b_header_end(txt):
            lns = txt.split('\n')
            WIN = 18
            for i in range(len(lns) - WIN + 1):
                window_text = ' '.join(l.strip().lower() for l in lns[i:i+WIN])
                has_desc = any(k in window_text for k in ('particular','description','item'))
                has_hsn  = any(k in window_text for k in ('hsn','sac'))
                has_qty  = any(k in window_text for k in ('pcs','qty','quantity','rate','amount','unit'))
                if has_desc and has_hsn and has_qty:
                    return sum(len(l)+1 for l in lns[:i+WIN])
            return None

        b_header_re = re.compile(
            r'(?:PARTICULAR|PARTICULARS|DESCRIPTION\s+OF\s+GOODS|DESCRIPTION|ITEM\s+DESCRIPTION)[\s\S]{0,200}?'
            r'(?:HSN|SAC)[\s\S]{0,200}?'
            r'(?:PCS|QTY|QUANTITY|RATE|AMOUNT)',
            re.IGNORECASE | re.DOTALL
        )
        hdr_m = b_header_re.search(text)
        if not hdr_m:
            hdr_end = _find_b_header_end(text)
            if hdr_end:
                class _FM:
                    def __init__(self, e): self._e = e
                    def end(self): return self._e
                hdr_m = _FM(hdr_end)
        if hdr_m:
            after = text[hdr_m.end():]
            lines_b = [l.strip() for l in after.split('\n')]

            def _is_sr_line(s):
                m = re.match(r'^(\d{1,3})[\.]\ *$', s)
                if m: return m.group(1), ''
                m = re.match(r'^(\d{1,3})\s+([A-Za-z].+)$', s)
                if m: return m.group(1), m.group(2).strip()
                return None, None

            # Pre-collect all data lines (stop at footer)
            all_data = []
            for lb in lines_b:
                if not lb: continue
                low = lb.lower()
                if any(kw in low for kw in B_STOP): break
                all_data.append(lb)

            # Build groups delimited by serial-number lines
            groups = []
            cur_sr, cur_desc, cur_lines = None, '', []
            pre_lines = []   # lines before the first serial number
            for lb in all_data:
                sr, desc_hint = _is_sr_line(lb)
                if sr:
                    if cur_sr is None and pre_lines:
                        # lines that came before the first sr — treat as group 0
                        groups.append(('1', '', pre_lines))
                        pre_lines = []
                    elif cur_sr is not None:
                        groups.append((cur_sr, cur_desc, cur_lines))
                    cur_sr, cur_desc, cur_lines = sr, desc_hint, []
                else:
                    if cur_sr is None:
                        pre_lines.append(lb)
                    else:
                        cur_lines.append(lb)
            if cur_sr is not None:
                # If no lines collected for last sr, use pre_lines
                lines_to_use = cur_lines if cur_lines else pre_lines
                groups.append((cur_sr, cur_desc, lines_to_use))
            elif pre_lines and not groups:
                groups.append(('1', '', pre_lines))

            for (sr, desc_hint, grp_lines) in groups:
                desc_cand = desc_hint or None
                hsn_cand  = None
                amounts   = []
                for dl in grp_lines:
                    dl_up = dl.upper().strip()
                    if re.match(r'^\d{4,8}$', dl):
                        if not hsn_cand:
                            hsn_cand = dl
                    elif dl_up in {u.upper() for u in UNIT_WORDS}:
                        continue
                    elif re.match(r'^[A-Za-z][A-Za-z0-9 \(\)\-/&,\.]{2,60}$', dl) and not re.search(r'\d{4,}', dl):
                        if not desc_cand:
                            desc_cand = dl
                    elif re.match(r'^[\d,]+\.?\d*$', dl):
                        try:
                            amounts.append(float(dl.replace(',', '')))
                        except ValueError:
                            pass

                if not desc_cand or not amounts:
                    continue
                key = desc_cand.upper()[:30]
                if key in seen:
                    continue
                seen.add(key)
                pos_amounts = [a for a in amounts if a > 0]
                item = {
                    'sr_no':       sr,
                    'description': desc_cand.strip(),
                    'hsn_code':    hsn_cand or '',
                    'amount':      pos_amounts[-1] if pos_amounts else (amounts[-1] if amounts else None),
                }
                if len(pos_amounts) >= 2:
                    item['rate'] = pos_amounts[-2]
                if len(pos_amounts) >= 3:
                    item['quantity'] = pos_amounts[0]
                items.append(item)
                logger.info(f"Pattern B item: sr={sr} desc={desc_cand[:30]} hsn={hsn_cand} amt={item.get('amount')}")

        if items:
            return items

        # ── Pattern C: Line-by-line flexible parser ──
        all_lines = text.split('\n')
        for line_idx, line in enumerate(all_lines):
            line = line.strip()
            if not line:
                continue
            sr_m = re.match(r'^(\d{1,3})\s+', line)
            if not sr_m:
                continue
            sr = sr_m.group(1)
            rest = line[sr_m.end():]

            hsn_m = re.search(r'\b(\d{4,8})\b', rest)
            hsn = hsn_m.group(1) if hsn_m else None
            if not hsn:
                for peek_line in all_lines[line_idx + 1: line_idx + 4]:
                    peek = peek_line.strip()
                    if peek and re.match(r'^\d{4,8}$', peek):
                        hsn = peek
                        break
                if not hsn:
                    continue

            desc = rest[:hsn_m.start()].strip() if hsn_m else rest.strip()
            if not desc or len(desc) < 3:
                continue
            desc_upper = desc.upper().strip()
            HEADER_LABELS = {
                'DESCRIPTION', 'ITEM DESCRIPTION', 'ITEM', 'PARTICULARS',
                'HSN', 'HSN/SAC', 'QTY', 'QUANTITY', 'UNIT', 'PRICE',
                'AMOUNT', 'SR', 'SR.', 'SR NO', 'S.NO',
            }
            if desc_upper in HEADER_LABELS:
                continue

            after_pos = hsn_m.end() if hsn_m else len(rest)
            after_hsn = rest[after_pos:]
            nums = re.findall(r'[\d,]+\.?\d*', after_hsn)
            nums = [float(n.replace(',', '')) for n in nums
                    if n.replace(',', '').replace('.', '').isdigit() or '.' in n]
            nums = [n for n in nums if n > 0]

            if len(nums) < 1:
                continue

            key = desc.upper()[:30]
            if key in seen:
                continue
            seen.add(key)

            item = {
                'sr_no':       sr,
                'description': desc,
                'hsn_code':    hsn,
                'amount':      nums[-1],
            }
            if len(nums) >= 3:
                item['rate'] = nums[-3]
                item['quantity'] = nums[0]
            elif len(nums) >= 2:
                item['rate'] = nums[-2]
            items.append(item)

        return items


    def _fill_missing_tax_fields(self, fields: Dict, text: str) -> Dict:
        """Infer CGST/SGST when patterns miss but totals or tax lines exist in text.
        
        NOTE: If the format handler sets _no_cgst_sgst=True, skip ALL CGST/SGST
        inference — those fields are explicitly absent from the source document.
        """
        # Respect the format handler's explicit decision not to infer CGST/SGST
        skip_cgst_sgst = fields.get('_no_cgst_sgst', False)

        if not skip_cgst_sgst:
            if fields.get("cgst_amount") and float(fields["cgst_amount"]) < 10:
                fields["cgst_amount"] = None
            if fields.get("sgst_amount") and float(fields["sgst_amount"]) < 10:
                fields["sgst_amount"] = None
            if not fields.get("cgst_amount"):
                fields["cgst_amount"] = self._extract_tax_from_summary_block(text, "cgst")
            if not fields.get("sgst_amount"):
                fields["sgst_amount"] = self._extract_tax_from_summary_block(text, "sgst")

        total = fields.get("total_amount")
        taxable = fields.get("taxable_amount")

        # Wrong taxable: often equals grand total when subtotal was missed
        if total and taxable and abs(total - taxable) < 1:
            alt_taxable = self._find_taxable_in_summary(text, total)
            if alt_taxable and abs(total - alt_taxable) > 1:
                taxable = alt_taxable
                fields["taxable_amount"] = alt_taxable

        if not skip_cgst_sgst and total and taxable:
            total_tax = round(total - taxable, 2)
            if (
                not fields.get("cgst_amount")
                and not fields.get("sgst_amount")
                and not fields.get("igst_amount")
                and total_tax > 0
            ):
                fields["cgst_amount"] = round(total_tax / 2, 2)
                fields["sgst_amount"] = round(total_tax / 2, 2)
                logger.info(f"Calculated CGST/SGST from total - taxable: {total_tax}")

        # Intra-state only: mirror CGST/SGST when IGST is not applicable
        if not fields.get("igst_amount"):
            if fields.get("cgst_amount") and not fields.get("sgst_amount"):
                fields["sgst_amount"] = fields["cgst_amount"]
                logger.info(f"Mirrored SGST from CGST: {fields['sgst_amount']}")
            if fields.get("sgst_amount") and not fields.get("cgst_amount"):
                fields["cgst_amount"] = fields["sgst_amount"]
                logger.info(f"Mirrored CGST from SGST: {fields['cgst_amount']}")

        # Taxable from total - tax when IGST present
        if not fields.get("taxable_amount") and total and fields.get("igst_amount"):
            fields["taxable_amount"] = round(total - fields["igst_amount"], 2)
            logger.info(f"Calculated taxable from total - IGST: {fields['taxable_amount']}")

        # Intra-state: taxable = net − CGST − SGST
        if not fields.get("taxable_amount") and total and fields.get("cgst_amount") and fields.get("sgst_amount"):
            inferred = round(total - fields["cgst_amount"] - fields["sgst_amount"], 2)
            if inferred > 1000:
                fields["taxable_amount"] = inferred
                logger.info(f"Calculated taxable from net - CGST - SGST: {inferred}")

        return fields

    def _find_taxable_in_summary(self, text: str, grand_total: float) -> Optional[float]:
        """Find taxable/subtotal that is less than grand total (avoids picking invoice total)."""
        candidates = []
        for pattern in [
            r'(?:Taxable\s*(?:Amount|Value)|Taxable\s*Value)[\s:]*(?:rs\.?|₹|inr)?\s*([\d,]+\.?\d*)',
            r'(?:Sub\s*Total|Subtotal)[\s:]*(?:rs\.?|₹|inr)?\s*([\d,]+\.?\d*)',
            r'(?:Total\s*Before\s*Tax)[\s:]*(?:rs\.?|₹|inr)?\s*([\d,]+\.?\d*)',
            r'Total\.{2,}[^\d\n]*([\d,]+\.?\d{2})',
        ]:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                try:
                    val = float(match.group(1).replace(",", ""))
                    if 100 < val < grand_total - 1:
                        candidates.append(val)
                except ValueError:
                    continue
        return max(candidates) if candidates else None

    def _extract_tax_from_summary_block(self, text: str, tax_type: str) -> Optional[float]:
        """Extract CGST/SGST from tax summary lines (handles OCR spacing)."""
        label = "CGST" if tax_type == "cgst" else "SGST"
        # Stacked amounts above CGST (...) when OCR puts figures before labels (Muskan 188 layout)
        stacked = re.search(
            r'([\d,]+\.\d{2})\s*\n\s*([\d,]+\.\d{2})\s*\n'
            r'(?:[^\n]*\n){0,4}?CGST\s*\(',
            text,
            re.IGNORECASE | re.MULTILINE,
        )
        if stacked:
            try:
                a = float(stacked.group(1).replace(",", ""))
                b = float(stacked.group(2).replace(",", ""))
                if abs(a - b) < 0.1 and 10 <= a <= 10_000_000:
                    return a
            except ValueError:
                pass
        patterns = [
            rf'{label}\s*\(?\s*[\d.]+\s*%?\s*\)?\s*[+\-]?\s*(?:rs\.?|₹|inr)?\s*([\d,]+\.?\d{{2}})',
            rf'{label}\s*(?:amount|value)?\s*[:\-]?\s*(?:rs\.?|₹|inr)?\s*([\d,]+\.?\d{{2}})',
            rf'{label}[^\d]{{0,30}}([\d,]+\.?\d{{2}})(?!\s*%)',
        ]
        for pattern in patterns:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                try:
                    amount = float(match.group(1).replace(",", ""))
                    if 10 <= amount < 100_000_000:
                        return amount
                except ValueError:
                    continue
        return None
    
    def _calculate_confidence(self, fields: Dict) -> float:
        """Weighted score — header fields alone should not show 100%."""
        weights = {
            "invoice_number": 12,
            "invoice_date": 10,
            "supplier_name": 12,
            "supplier_gstin": 10,
            "buyer_name": 12,
            "buyer_gstin": 10,
            "total_amount": 12,
            "taxable_amount": 8,
            "cgst_amount": 7,
            "sgst_amount": 7,
            "line_items": 10,
        }
        score = 0.0
        for field, weight in weights.items():
            if field == "line_items":
                if fields.get("items"):
                    score += weight
            elif fields.get(field):
                score += weight
        return round(score, 2)


# Global instance
field_extractor = FieldExtractor()
