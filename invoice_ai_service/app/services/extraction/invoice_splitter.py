"""Split multi-invoice PDFs into separate invoices."""

import logging
import re
from typing import List, Dict, Tuple

logger = logging.getLogger(__name__)


class InvoiceSplitter:
    """Detect and split multi-invoice documents."""
    
    def __init__(self):
        """Initialize invoice splitter."""
        pass
    
    def detect_and_split(self, text: str) -> List[Dict[str, any]]:
        """
        Detect invoice boundaries and split text into separate invoices.
        
        Args:
            text: Full extracted text from PDF
            
        Returns:
            List of invoice sections with text and metadata
        """
        # 1. Check for page markers to perform page-aware splitting
        page_matches = list(re.finditer(r'--- Page (\d+) ---\n', text))
        
        if page_matches:
            pages = []
            for idx, pm in enumerate(page_matches):
                p_num = int(pm.group(1))
                start_pos = pm.end()
                if idx + 1 < len(page_matches):
                    end_pos = page_matches[idx + 1].start()
                else:
                    end_pos = len(text)
                pages.append({
                    'page_num': p_num,
                    'text': text[start_pos:end_pos],
                    'start_pos': pm.start(),
                    'end_pos': end_pos
                })
            
            # Find all invoice matches
            invoice_pattern = r'Invoice\s*(?:No\.?|Number|#)[\s:]*([A-Z0-9\-/]+)'
            matches = list(re.finditer(invoice_pattern, text, re.IGNORECASE))
            
            if len(matches) <= 1:
                # Single invoice
                logger.info(f"Single page-delimited invoice detected (found {len(matches)} invoice numbers)")
                return [{
                    'invoice_number': matches[0].group(1) if matches else None,
                    'text': text,
                    'start_pos': 0,
                    'end_pos': len(text),
                    'is_multi_invoice': False,
                    'pages': [p['page_num'] for p in pages]
                }]
            
            # Map each match to a page index
            match_pages = []
            for match in matches:
                match_start = match.start()
                match_page_idx = 0
                for idx, p in enumerate(pages):
                    if p['start_pos'] <= match_start < p['end_pos']:
                        match_page_idx = idx
                        break
                match_pages.append((match, match_page_idx))
                
            # Keep first match per page to identify distinct invoice pages
            unique_page_matches = []
            seen_pages = set()
            for match, page_idx in match_pages:
                if page_idx not in seen_pages:
                    seen_pages.add(page_idx)
                    unique_page_matches.append((match, page_idx))
            
            if len(unique_page_matches) <= 1:
                logger.info(f"Single page-delimited invoice after page-level grouping (found {len(unique_page_matches)} pages with invoices)")
                return [{
                    'invoice_number': unique_page_matches[0][0].group(1) if unique_page_matches else (matches[0].group(1) if matches else None),
                    'text': text,
                    'start_pos': 0,
                    'end_pos': len(text),
                    'is_multi_invoice': False,
                    'pages': [p['page_num'] for p in pages]
                }]
                
            # Multiple invoices detected
            invoices = []
            for i, (match, page_idx) in enumerate(unique_page_matches):
                invoice_num = match.group(1)
                start_page = page_idx
                
                if i + 1 < len(unique_page_matches):
                    end_page = unique_page_matches[i + 1][1]
                else:
                    end_page = len(pages)
                    
                # Combine pages for this invoice section
                invoice_text_parts = []
                for p_idx in range(start_page, end_page):
                    invoice_text_parts.append(f"--- Page {pages[p_idx]['page_num']} ---\n{pages[p_idx]['text']}")
                
                invoice_text = "".join(invoice_text_parts)
                
                invoices.append({
                    'invoice_number': invoice_num,
                    'text': invoice_text,
                    'start_pos': pages[start_page]['start_pos'],
                    'end_pos': pages[end_page - 1]['end_pos'],
                    'is_multi_invoice': True,
                    'invoice_index': i + 1,
                    'total_invoices': len(unique_page_matches),
                    'pages': [pages[p_idx]['page_num'] for p_idx in range(start_page, end_page)]
                })
                logger.info(f"Invoice {i+1}/{len(unique_page_matches)}: #{invoice_num} ({len(invoice_text)} chars, pages: {invoices[-1]['pages']})")
                
            return invoices

        # Fallback to character-position split if no page delimiters exist
        invoice_pattern = r'Invoice\s*(?:No\.?|Number|#)[\s:]*([A-Z0-9\-/]+)'
        matches = list(re.finditer(invoice_pattern, text, re.IGNORECASE))
        
        if len(matches) <= 1:
            logger.info(f"Single invoice detected (found {len(matches)} invoice numbers)")
            return [{
                'invoice_number': matches[0].group(1) if matches else None,
                'text': text,
                'start_pos': 0,
                'end_pos': len(text),
                'is_multi_invoice': False
            }]
        
        logger.info(f"Multi-invoice PDF detected (no page markers): {len(matches)} invoices found")
        invoices = []
        for i, match in enumerate(matches):
            invoice_num = match.group(1)
            start_pos = 0 if i == 0 else match.start()
            
            if i + 1 < len(matches):
                end_pos = matches[i + 1].start()
            else:
                end_pos = len(text)
            
            invoice_text = text[start_pos:end_pos]
            invoices.append({
                'invoice_number': invoice_num,
                'text': invoice_text,
                'start_pos': start_pos,
                'end_pos': end_pos,
                'is_multi_invoice': True,
                'invoice_index': i + 1,
                'total_invoices': len(matches)
            })
            logger.info(f"Invoice {i+1}/{len(matches)}: #{invoice_num} ({len(invoice_text)} chars)")
        
        return invoices
    
    def split_line_items(self, line_items: List[Dict], invoices: List[Dict]) -> Dict[str, List[Dict]]:
        """
        Assign line items to their respective invoices based on position in text.
        
        Args:
            line_items: All extracted line items
            invoices: List of invoice sections
            
        Returns:
            Dictionary mapping invoice_number to list of line items
        """
        if len(invoices) <= 1:
            # Single invoice - all items belong to it
            invoice_num = invoices[0].get('invoice_number', 'unknown')
            return {invoice_num: line_items}
        
        # Multi-invoice: need to assign items based on their position
        # For now, distribute items evenly (simple heuristic)
        # TODO: Improve by matching item position in text
        
        items_per_invoice = {}
        items_per_inv = len(line_items) // len(invoices)
        
        for i, invoice in enumerate(invoices):
            invoice_num = invoice.get('invoice_number', f'invoice_{i+1}')
            start_idx = i * items_per_inv
            
            if i == len(invoices) - 1:
                # Last invoice gets remaining items
                items_per_invoice[invoice_num] = line_items[start_idx:]
            else:
                end_idx = start_idx + items_per_inv
                items_per_invoice[invoice_num] = line_items[start_idx:end_idx]
            
            logger.info(f"Invoice #{invoice_num}: {len(items_per_invoice[invoice_num])} line items")
        
        return items_per_invoice


# Global instance
invoice_splitter = InvoiceSplitter()
