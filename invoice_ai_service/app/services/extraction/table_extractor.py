"""Table extraction from invoices using Camelot and pdfplumber."""

import logging
import re
from typing import List, Dict, Optional
import io
import tempfile
import os

logger = logging.getLogger(__name__)


class TableExtractor:
    """Extract tables (line items) from invoice PDFs."""
    
    def __init__(self):
        """Initialize table extractor."""
        self.min_rows = 1  # Minimum rows to consider valid table (reduced from 2)
        
    def extract_tables(self, pdf_data: bytes, pages: List[int] = None) -> Dict[str, any]:
        """
        Extract tables from PDF using pdfplumber first, then Camelot fallback.
        
        Args:
            pdf_data: PDF file as bytes
            pages: Optional list of 1-based page numbers to extract tables from
            
        Returns:
            Dictionary with extracted tables
        """
        # Try pdfplumber first (better for column detection)
        result = self._extract_with_pdfplumber(pdf_data, pages=pages)
        
        if result['table_count'] == 0:
            # Fallback to Camelot
            logger.info("pdfplumber found no tables, trying Camelot")
            result = self._extract_with_camelot(pdf_data, pages=pages)
        
        # If table extraction failed or found tables with too few columns, try text-based extraction
        if result['table_count'] == 0 or all(len(t.get('headers', [])) < 3 for t in result.get('tables', [])):
            logger.warning("Table extraction failed or insufficient columns, trying text-based extraction")
            # Note: Text-based extraction will be done in parse_line_items if needed
        
        return result
    
    def _extract_with_camelot(self, pdf_data: bytes, pages: List[int] = None) -> Dict[str, any]:
        """Extract tables using Camelot."""
        try:
            import camelot
            
            # Camelot requires file path, so write to temp file
            with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp_file:
                tmp_file.write(pdf_data)
                tmp_path = tmp_file.name
            
            try:
                extracted_tables = []
                pages_str = ','.join(map(str, pages)) if pages else 'all'
                
                # Try lattice method first (for bordered tables)
                tables = camelot.read_pdf(
                    tmp_path,
                    pages=pages_str,
                    flavor='lattice',
                    line_scale=40,
                    strip_text='\n'
                )
                
                if len(tables) == 0:
                    # Fallback to stream method (for borderless tables)
                    logger.info("Lattice method found no tables, trying stream method")
                    tables = camelot.read_pdf(
                        tmp_path,
                        pages=pages_str,
                        flavor='stream',
                        edge_tol=50,
                        row_tol=10,
                        column_tol=10
                    )
                
                for i, table in enumerate(tables):
                    if len(table.df) >= self.min_rows:
                        table_data = {
                            "table_index": i,
                            "page": table.page,
                            "accuracy": table.accuracy,
                            "data": table.df.to_dict('records'),
                            "headers": table.df.columns.tolist(),
                            "rows": len(table.df)
                        }
                        extracted_tables.append(table_data)
                        logger.info(f"Camelot extracted table {i} with {len(table.df)} rows (accuracy: {table.accuracy:.2f})")
                
                return {
                    "tables": extracted_tables,
                    "table_count": len(extracted_tables),
                    "method": "camelot",
                    "success": True
                }
                
            finally:
                # Clean up temp file
                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)
            
        except ImportError:
            logger.warning("Camelot not installed")
            return {
                "tables": [],
                "table_count": 0,
                "method": "camelot",
                "success": False,
                "error": "Camelot not installed"
            }
        except Exception as e:
            logger.error(f"Camelot extraction failed: {str(e)}")
            return {
                "tables": [],
                "table_count": 0,
                "method": "camelot",
                "success": False,
                "error": str(e)
            }
    
    def _extract_with_pdfplumber(self, pdf_data: bytes, pages: List[int] = None) -> Dict[str, any]:
        """Extract tables using pdfplumber (fallback method)."""
        try:
            import pdfplumber
            
            extracted_tables = []
            
            with pdfplumber.open(io.BytesIO(pdf_data)) as pdf:
                for page_num_0, page in enumerate(pdf.pages):
                    page_num = page_num_0 + 1
                    if pages and page_num not in pages:
                        continue
                    tables = page.extract_tables()
                    
                    for table_idx, table in enumerate(tables):
                        if not table or len(table) < self.min_rows:
                            continue
                        
                        # CRITICAL FIX: Skip invoice header rows that pdfplumber incorrectly includes
                        # Find the actual table header row (contains keywords like Description, HSN, Qty, Rate, Amount)
                        header_keywords = [
                            'description', 'particulars', 'hsn', 'sac', 'qty', 'quantity',
                            'rate', 'price', 'amount', 'total', 'sr', 'no', 'item', 'pcs',
                            'name of product', 'product',
                        ]
                        
                        header_row_idx = None
                        for idx, row in enumerate(table):
                            if not row:
                                continue
                            
                            # Check if this row contains table header keywords
                            row_text = ' '.join([str(cell).lower() if cell else '' for cell in row])
                            
                            # Skip if row is too long (likely invoice header, not table header)
                            if len(row_text) > 200:
                                logger.info(f"Skipping row {idx} - too long ({len(row_text)} chars), likely invoice header")
                                continue
                            
                            # Count how many header keywords are in this row
                            keyword_count = sum(1 for kw in header_keywords if kw in row_text)
                            
                            # If we find 2+ keywords, this is likely the table header
                            if keyword_count >= 2:
                                header_row_idx = idx
                                logger.info(f"Found table header at row {idx}: {row[:3]}... (matched {keyword_count} keywords)")
                                break
                        
                        if header_row_idx is None:
                            logger.warning(f"No table header found in table {table_idx}, skipping")
                            continue
                        
                        # Use the identified row as headers
                        headers = table[header_row_idx]
                        # Data rows start after the header
                        data_rows = table[header_row_idx + 1:]
                        
                        if not data_rows:
                            logger.info(f"No data rows after header in table {table_idx}")
                            continue
                        
                        # Convert to dict format
                        data = []
                        for row in data_rows:
                            row_dict = {}
                            for i, cell in enumerate(row):
                                header = headers[i] if i < len(headers) else f"col_{i}"
                                row_dict[header] = cell
                            data.append(row_dict)
                        
                        table_data = {
                            "table_index": len(extracted_tables),
                            "page": page_num + 1,
                            "accuracy": 1.0,
                            "data": data,
                            "headers": headers,
                            "rows": len(data)
                        }
                        extracted_tables.append(table_data)
                        logger.info(f"pdfplumber extracted table {table_idx} from page {page_num + 1} with {len(data)} rows (headers: {headers[:3]}...)")
            
            return {
                "tables": extracted_tables,
                "table_count": len(extracted_tables),
                "method": "pdfplumber",
                "success": True
            }
            
        except Exception as e:
            logger.error(f"pdfplumber extraction failed: {str(e)}")
            return {
                "tables": [],
                "table_count": 0,
                "method": "pdfplumber",
                "success": False,
                "error": str(e)
            }
    
    def parse_line_items(self, tables: List[Dict]) -> List[Dict]:
        """
        Parse line items from extracted tables.
        
        Looks for common Indian invoice table patterns:
        - Sr.No, Description, HSN, Qty, Rate, Amount
        - Item, Particulars, HSN/SAC, Quantity, Price, Total
        - Description Of Goods, HSN, Pcs, Mts, Rate, Amount
        
        Args:
            tables: List of extracted tables
            
        Returns:
            List of parsed line items
        """
        line_items = []
        
        for table_idx, table in enumerate(tables):
            logger.info(f"Processing table {table_idx}: {table.get('rows', 0)} rows, {len(table.get('headers', []))} columns")
            
            # Skip tables with too few columns (likely not line items)
            if len(table.get('headers', [])) < 3:
                logger.info(f"Skipping table {table_idx}: too few columns ({len(table.get('headers', []))})")
                continue
            
            # Try to identify column mappings
            headers = [str(h).lower().strip() if h else '' for h in table.get('headers', [])]
            
            logger.info(f"Table {table_idx} headers: {headers[:5]}...")  # Show first 5 headers
            
            # Find description column (most important) - more flexible matching
            desc_col = self._find_column(headers, [
                'description', 'particulars', 'item', 'goods', 'material',
                'description of goods', 'item description', 'product', 'name',
                'name of product', 'product name', 'name of product ',
            ])
            
            # Find other columns with more variations
            qty_col = self._find_column(headers, ['quantity', 'qty', 'qnty', 'pcs', 'pieces', 'nos', 'no', 'pc'])
            rate_col = self._find_column(headers, ['rate', 'price', 'unit price', 'unit rate', 'ratep', 'rateper'])
            unit_col = self._find_column(headers, ['unit', 'uom'])
            total_col = self._find_column(headers, ['total', 'amount', 'value', 'total amount', 'amt'])
            hsn_col = self._find_column(headers, ['hsn', 'sac', 'hsn/sac', 'hsn code', 'sac code', 'hsn/sac code', 'hsncode'])
            
            # Additional columns for Indian invoices
            mts_col = self._find_column(headers, ['mts', 'meters', 'mtrs', 'length', 'kgs', 'kg'])
            cut_col = self._find_column(headers, ['cut', 'cuts'])
            sr_col = self._find_column(headers, ['sr', 'sr.no', 'srno', 's.no', 'sno', 'serial'])
            
            logger.info(f"Column mapping for table {table_idx}: sr={sr_col}, desc={desc_col}, hsn={hsn_col}, qty={qty_col}, rate={rate_col}, total={total_col}")
            
            if desc_col is None:
                logger.warning(f"No description column found in table {table_idx}. Headers: {headers}")
                # Try to use first non-serial column as description
                if sr_col is not None and sr_col == 0 and len(headers) > 1:
                    logger.info(f"Using column 1 as description (column 0 is serial number)")
                    desc_col = 1
                elif len(headers) > 0:
                    logger.info(f"Attempting to use column 0 as description")
                    desc_col = 0
                else:
                    continue
            
            # Parse rows
            parsed_count = 0
            for row_idx, row in enumerate(table.get('data', [])):
                # Get description
                description = self._get_cell_value(row, headers, desc_col)
                
                # Skip empty rows
                if not description or len(str(description).strip()) < 2:
                    continue
                
                # Skip if description looks like a header or footer
                desc_lower = str(description).lower().strip()
                skip_keywords = [
                    'description', 'particulars', 'sr.no', 'sr no', 'serial',
                    'total', 'subtotal', 'sub total', 'grand total',
                    'taxable', 'cgst', 'sgst', 'igst', 'gst',
                    'bank detail', 'terms', 'condition', 'payment',
                    'e. & o.e', 'e.&.o.e', 'authorised', 'signature'
                ]
                if any(kw in desc_lower for kw in skip_keywords):
                    continue
                
                # Skip if description is just numbers or very short
                if desc_lower.replace('.', '').replace(' ', '').isdigit():
                    continue
                
                item = {
                    'description': str(description).strip(),
                    'hsn_code': self._get_cell_value(row, headers, hsn_col) if hsn_col is not None else '',
                    'quantity': self._get_cell_value(row, headers, qty_col) if qty_col is not None else '',
                    'rate': self._get_cell_value(row, headers, rate_col) if rate_col is not None else '',
                    'amount': self._get_cell_value(row, headers, total_col) if total_col is not None else ''
                }
                
                # Add optional fields
                if mts_col is not None:
                    mts_val = self._get_cell_value(row, headers, mts_col)
                    item['meters'] = mts_val
                    item['mts'] = mts_val
                if cut_col is not None:
                    item['cut'] = self._get_cell_value(row, headers, cut_col)
                if unit_col is not None:
                    item['unit'] = self._get_cell_value(row, headers, unit_col)
                if sr_col is not None:
                    item['sr_no'] = self._get_cell_value(row, headers, sr_col)
                if str(item.get('rate', '')).lower() in ('mtr', 'mt', 'meter', 'meters') and rate_col is not None:
                    item['rate'] = self._get_cell_value(row, headers, rate_col)
                
                # Clean and validate
                item = self._clean_line_item(item)
                
                # Only add if we have meaningful data (description + at least one numeric field)
                if item['description'] and len(item['description']) > 2:
                    if item['quantity'] or item['amount'] or item['rate']:
                        line_items.append(item)
                        parsed_count += 1
                        logger.info(f"✓ Item {parsed_count}: {item['description'][:40]}... | HSN: {item['hsn_code']} | Qty: {item['quantity']} | Rate: {item['rate']} | Amt: {item['amount']}")
            
            logger.info(f"Table {table_idx}: Parsed {parsed_count} items from {len(table.get('data', []))} rows")
        
        logger.info(f"Total line items parsed: {len(line_items)}")
        return line_items
    
    def parse_line_items_from_text(self, text: str, format_id: str = None) -> List[Dict]:
        """
        Fallback: Parse line items directly from OCR text when table extraction fails.
        
        Looks for patterns like:
        1 SAREE RAJ-TILAK-1,2 540752 24 340.00 8160.00
        2 SAREE INNOVA 540752 24 360.00 8640.00
        
        Args:
            text: OCR extracted text
            
        Returns:
            List of parsed line items
        """
        logger.info("Attempting text-based line item extraction")
        line_items = []
        if format_id == "mr_fashion_chandni":
            line_items = self._scan_mr_fashion_rows(text)
        if not line_items:
            line_items = self._scan_pcs_mts_rows(text)

        # ── Google Vision vertical-cell table reconstructor ──────────────────
        # Google Vision reads bordered PDF tables cell-by-cell (each on its own line).
        # Detect this pattern: find the table header line (Sr. / Item Description /
        # HSN/SAC / Qty / Unit / ...) then collect all following numeric/text tokens
        # and assign them to columns in sequence.
        if not line_items:
            gv_items = self._reconstruct_google_vision_table(text)
            if gv_items:
                logger.info(f"Google Vision table reconstructor found {len(gv_items)} items")
                line_items = gv_items

        seen_item_keys = {
            (str(i.get("description", ""))[:40].upper(), str(i.get("hsn_code", "")))
            for i in line_items
        }

        lines = text.split('\n')
        logger.info(f"Analyzing {len(lines)} lines of text")
        
        # Normalize OCR spacing (Google Vision often inserts extra spaces)
        def _norm_line(s: str) -> str:
            return re.sub(r'\s+', ' ', s).strip()

        # Multiple patterns to try (MUSKAN + GAYATRI SAREE layouts)
        patterns = [
            # GAYATRI: 1|SAREE MAYA-1,2 | 540752 | 48| 0.00| | 730.00| 35040.00
            r'^\s*(\d+)\s*[|│]?\s*([A-Za-z][A-Za-z0-9\s\-,/\.]+?)\s*[|│]?\s*(\d{4,8})\s*[|│]?\s*(\d+)\s*(?:[\d.]+\s+)?([\d,]+\.?\d+)\s+([\d,]+\.?\d+)',
            # GAYATRI without pipes: 1 SAREE MAYA-1,2 540752 48 0.00 730.00 35040.00
            r'^\s*(\d+)\s+([A-Za-z][A-Za-z0-9\s\-,/\.]+?)\s+(\d{6})\s+(\d+)\s+(?:[\d.]+\s+)?([\d,]+\.?\d+)\s+([\d,]+\.?\d+)',
            # MUSKAN: 1. WETLESS 5407 6.30 365 2299.50 315.00 114975.00
            r'^\s*(\d+)\.\s+([A-Za-z][A-Za-z0-9\s\-,/\.]+?)\s+(\d{4,8})\s+([\d.]+)\s+(\d+)\s+([\d.]+)\s+([\d.]+)\s*P?\s*([\d.]+)',
            r'^\s*(\d+)\.\s+([A-Za-z][A-Za-z0-9\s\-,/\.]+?)\s+(\d{4,8})\s+([\d.]+)\s+(\d+)\s+([\d.]+)\s+([\d.]+)P([\d.]+)',
            # Standard: 1 SAREE RAJ-TILAK-1,2 540752 24 340.00 8160.00
            r'^\s*(\d+)\.?\s+([A-Za-z][A-Za-z0-9\s\-,/\.]+?)\s+(\d{4,8})\s+(\d+)\s+([\d,]+\.?\d*)\s+([\d,]+\.?\d*)',
            r'^\s*(\d+)\.?\s+([A-Za-z][A-Za-z0-9\s\-,/\.]+?)\s+(\d{4,8})\s+(\d+)\s+[\d,]+\.?\d*\s+([\d,]+\.?\d*)\s+([\d,]+\.?\d*)',
            r'^\s*([A-Za-z][A-Za-z0-9\s\-,/\.]+?)\s+(\d{4,8})\s+(\d+)\s+([\d,]+\.?\d*)\s+([\d,]+\.?\d*)',
        ]
        
        # Debug: Show sample lines that might contain items
        logger.info("Sample lines from OCR text (lines with digits):")
        sample_count = 0
        for i, line in enumerate(lines):
            # Show lines with HSN codes OR lines with "WETLESS" or other product names
            if re.search(r'\d{4,8}', line) or re.search(r'[A-Z]{3,}', line):
                logger.info(f"  Line {i}: {line[:150]}")
                sample_count += 1
                if sample_count >= 15:
                    break
        
        in_items_section = False
        for line in lines:
            line = _norm_line(line)
            if not line or len(line) < 8:
                continue

            line_lower = line.lower()
            if any(kw in line_lower for kw in [
                'description of goods', 'name of product', 'particulars', 'hsn code',
            ]):
                in_items_section = True
                continue
            if any(kw in line_lower for kw in [
                'taxable', 'grand total', 'total amount', 'amount in words', 'bank detail',
                'net amount', 'payment within', 'idbi bank', 'total.....',
            ]):
                in_items_section = False
                continue

            if re.match(r'^Total\.{2,}', line_lower):
                in_items_section = False
                continue
            
            # Skip header lines (unless we're in the items table)
            if not in_items_section and any(
                kw in line_lower
                for kw in ['sr', 'description', 'hsn', 'qty', 'rate', 'amount', 'name of product', 'pcs']
            ):
                continue
            
            # Try each pattern
            for pattern_idx, pattern in enumerate(patterns):
                match = re.match(pattern, line, re.IGNORECASE)
                if match:
                    groups = match.groups()
                    item = {}

                    if pattern_idx in (0, 1):  # GAYATRI: sr, desc, hsn, qty, rate, amount
                        sr_no, description, hsn, qty, rate, amount = groups
                        item = {
                            'sr_no': sr_no.strip(),
                            'description': description.strip(),
                            'hsn_code': hsn.strip(),
                            'quantity': qty.strip(),
                            'rate': rate.replace(',', '').strip(),
                            'amount': amount.replace(',', '').strip(),
                        }
                    elif pattern_idx in (2, 3):  # MUSKAN with cut/meters
                        sr_no, description, hsn, cut, qty, meters, rate, amount = groups
                        item = {
                            'sr_no': sr_no.strip() + '.',
                            'description': description.strip(),
                            'hsn_code': hsn.strip(),
                            'cut': cut.strip(),
                            'quantity': qty.strip(),
                            'meters': meters.strip(),
                            'rate': rate.replace(',', '').strip(),
                            'amount': amount.replace(',', '').strip(),
                        }
                    elif pattern_idx in (4, 5):  # sr + desc + hsn + qty + rate + amount
                        sr_no, description, hsn, qty, rate, amount = groups
                        item = {
                            'sr_no': sr_no.strip(),
                            'description': description.strip(),
                            'hsn_code': hsn.strip(),
                            'quantity': qty.strip(),
                            'rate': rate.replace(',', '').strip(),
                            'amount': amount.replace(',', '').strip(),
                        }
                    else:  # no sr.no
                        description, hsn, qty, rate, amount = groups
                        item = {
                            'description': description.strip(),
                            'hsn_code': hsn.strip(),
                            'quantity': qty.strip(),
                            'rate': rate.replace(',', '').strip(),
                            'amount': amount.replace(',', '').strip(),
                        }

                    item = self._clean_line_item(item)
                    desc = item.get('description', '')
                    item_key = (desc[:40].upper(), str(item.get("hsn_code", "")))
                    if (
                        len(desc) > 3
                        and len(desc) < 100
                        and (item.get('quantity') or item.get('amount') or item.get('rate'))
                        and not desc.lower().startswith('total')
                        and item_key not in seen_item_keys
                    ):
                        line_items.append(item)
                        seen_item_keys.add(item_key)
                        logger.info(
                            f"✓ Text-based item {len(line_items)} (pattern {pattern_idx + 1}): "
                            f"{desc[:40]}... | HSN: {item.get('hsn_code')} | Qty: {item.get('quantity')}"
                        )
                        break
        
        # Fallback: scan full text for SAREE / product rows (messy Tesseract column merge)
        if not line_items:
            line_items = self._scan_product_rows(text)

        # Format-specific: merge Mts/Cut and fix column swaps
        if format_id:
            from app.services.extraction.format_enhancer import enhance_line_items
            line_items = enhance_line_items(text, line_items, format_id)

        logger.info(f"Text-based extraction found {len(line_items)} items")
        return line_items

    def _scan_mr_fashion_rows(self, text: str) -> List[Dict]:
        """M.R FASHION / Chandni: Qnty + meters + Mtr unit + Rate + Amount."""
        items = []
        pat = (
            r"(\d+)\s+([A-Za-z][A-Za-z0-9]+(?:\s+[A-Za-z]+)?)\s+(\d{6})\s+"
            r"(\d+)\s+([\d,.]+)\s+Mtr\s+([\d,.]+)\s+([\d,.]+)"
        )
        seen = set()
        for m in re.finditer(pat, text, re.IGNORECASE):
            sr_no, desc, hsn, qty, meters, rate, amount = m.groups()
            desc = re.sub(r"([a-z])([A-Z])", r"\1 \2", desc.strip())
            key = (desc.upper()[:40], hsn)
            if key in seen:
                continue
            seen.add(key)
            item = self._clean_line_item({
                "sr_no": sr_no.strip(),
                "description": desc,
                "hsn_code": hsn.strip(),
                "quantity": qty.strip(),
                "meters": meters.replace(",", "").strip(),
                "mts": meters.replace(",", "").strip(),
                "unit": "Mtr",
                "rate": rate.replace(",", "").strip(),
                "amount": amount.replace(",", "").strip(),
            })
            items.append(item)
            logger.info(
                f"✓ M.R FASHION row: {desc[:30]}... pcs={qty} mts={meters} rate={rate}"
            )
        return items

    def _scan_pcs_mts_rows(self, text: str) -> List[Dict]:
        """
        Textile rows with Pcs + Mts + Rate + Amount (CHANDRALOK / MUSKAN glued OCR).
        Example: 1. ORGANZA JAQUARD 540710 2 172.00 150.00 M25800.00
        """
        items = []
        pat = (
            r"(\d+)\.\s*([A-Za-z][A-Za-z\s]+?)\s+(\d{6})\s+"
            r"(\d+)\s+([\d.]+)\s+([\d.]+)\s+M?([\d.]+)"
        )
        seen = set()
        for m in re.finditer(pat, text, re.IGNORECASE):
            sr_no, desc, hsn, qty, meters, rate, amount = m.groups()
            key = (desc.strip().upper()[:40], hsn)
            if key in seen:
                continue
            seen.add(key)
            item = self._clean_line_item({
                "sr_no": sr_no.strip() + ".",
                "description": desc.strip(),
                "hsn_code": hsn.strip(),
                "quantity": qty.strip(),
                "meters": meters.strip(),
                "mts": meters.strip(),
                "rate": rate.replace(",", "").strip(),
                "amount": amount.replace(",", "").strip(),
            })
            items.append(item)
            logger.info(
                f"✓ Pcs/Mts row: {desc[:30]}... pcs={qty} mts={meters} rate={rate} amt={amount}"
            )
        return items

    def _scan_product_rows(self, text: str) -> List[Dict]:
        """Find line items when table structure is broken in OCR."""
        items = []
        # Optional middle column (0.00) between qty and rate — GAYATRI format
        row_pat = (
            r'(?:^|\n)\s*(\d+)\s*[|│]?\s*'
            r'(SAREE\s+[A-Za-z0-9\-,/\.]+?)\s+'
            r'(\d{6})\s+'
            r'(\d+)\s+'
            r'(?:[\d.]+\s+)?'  # skip optional 0.00 column
            r'([\d,]+\.?\d+)\s+'
            r'([\d,]+\.?\d+)'
        )
        seen = set()
        for match in re.finditer(row_pat, text, re.IGNORECASE | re.MULTILINE):
            sr_no, desc, hsn, qty, rate, amount = match.groups()
            desc = desc.strip()
            key = (desc.upper(), hsn)
            if key in seen or len(desc) < 4:
                continue
            try:
                rate_f = float(rate.replace(",", ""))
                amt_f = float(amount.replace(",", ""))
                if amt_f < rate_f:
                    rate_f, amt_f = amt_f, rate_f
            except ValueError:
                rate_f, amt_f = rate, amount
            seen.add(key)
            item = self._clean_line_item({
                "sr_no": sr_no.strip(),
                "description": desc,
                "hsn_code": hsn.strip(),
                "quantity": qty.replace(",", "").strip(),
                "rate": str(rate_f),
                "amount": str(amt_f),
            })
            items.append(item)
            logger.info(
                f"✓ Scanned product row: {desc[:40]}... qty={qty} rate={rate_f} amt={amt_f}"
            )
        return items
    
    def _reconstruct_google_vision_table(self, text: str) -> List[Dict]:
        """
        Reconstruct line items from Google Vision OCR output where each table cell
        appears on its own line (common for bordered PDF tables).
        """
        lines = [l.strip() for l in text.split('\n')]

        # Column header substrings to recognise
        HEADER_SUBS = ['sr', 'description', 'hsn', 'sac', 'qty', 'quantity',
                       'unit', 'price', 'rate', 'disc', 'tax', 'amount',
                       'cut', 'pcs', 'mts', 'meters', 'mtrs']
        FOOTER_KW   = {'discount', 'total', 'subtotal', 'sub total', 'grand total',
                       'taxable', 'amount in words', 'cgst', 'sgst', 'igst',
                       'bank', 'terms', 'declaration'}

        def _is_header_cell(s: str) -> bool:
            sl = s.lower()
            return any(kw in sl for kw in HEADER_SUBS) and len(s) <= 40

        # Find a run of consecutive header-like lines (the column header block)
        header_start = None
        header_end   = None
        max_run = 0
        run_start = None
        run_len = 0
        for i, line in enumerate(lines):
            if _is_header_cell(line):
                if run_start is None:
                    run_start = i
                run_len += 1
                if run_len > max_run:
                    max_run = run_len
                    header_start = run_start
                    header_end   = i
            else:
                run_start = None
                run_len   = 0

        if header_start is None or max_run < 3:
            return []

        # Get raw header cells
        raw_header_cols = [lines[i].lower().strip() for i in range(header_start, header_end + 1)]
        
        # Split merged sr/description headers if they exist
        header_cols = []
        for col in raw_header_cols:
            if ('sr' in col or 's.no' in col or 'sno' in col) and ('description' in col or 'particular' in col or 'goods' in col):
                header_cols.append('sr_no')
                header_cols.append('description')
            else:
                header_cols.append(col)

        n_cols = len(header_cols)
        logger.info(f"GV reconstructor: {n_cols}-column header at lines {header_start}-{header_end}: {header_cols}")

        # Map column positions → field names
        col_map = {}
        for j, col in enumerate(header_cols):
            if col == 'sr_no':
                col_map[j] = 'sr_no'
            elif col == 'description':
                col_map[j] = 'description'
            elif 'sr' in col or col in ('no', 's.no'):       col_map[j] = 'sr_no'
            elif 'description' in col or 'particular' in col or 'item' == col:
                                                            col_map[j] = 'description'
            elif 'hsn' in col or 'sac' in col:             col_map[j] = 'hsn_code'
            elif 'qty' in col or 'quantity' in col or col == 'pcs':        col_map[j] = 'quantity'
            elif col == 'unit':                             col_map[j] = 'unit'
            elif 'price' in col or 'rate' in col:          col_map[j] = 'rate'
            elif 'disc' in col:                             col_map[j] = 'discount'
            elif 'tax' in col:                              col_map[j] = 'tax_pct'
            elif 'amount' in col:                           col_map[j] = 'amount'
            elif col == 'cut':                              col_map[j] = 'cut'
            elif col in ('mts', 'meters', 'mtrs'):          col_map[j] = 'meters'

        if 'description' not in col_map.values() or 'amount' not in col_map.values():
            logger.info(f"GV reconstructor: missing description or amount column in {col_map}")
            return []

        # Collect data lines after header block
        # Treat empty/blank lines as empty-cell placeholders (e.g. empty Disc. column)
        raw_data = []
        for line in lines[header_end + 1:]:
            low = line.lower()
            if any(kw in low for kw in FOOTER_KW):
                break
            raw_data.append(line)   # keep empty strings as empty cell values

        # Remove trailing empty lines
        while raw_data and not raw_data[-1].strip():
            raw_data.pop()

        if not raw_data:
            return []

        logger.info(f"GV reconstructor: {len(raw_data)} raw data tokens for {n_cols} columns")

        # Group into rows of n_cols each
        items = []
        i = 0
        while i + n_cols <= len(raw_data):
            row_cells = raw_data[i: i + n_cols]
            i += n_cols

            item = {}
            for j, cell in enumerate(row_cells):
                field = col_map.get(j)
                if field and cell.strip():
                    item[field] = cell.strip()

            desc = item.get('description', '')
            amt  = item.get('amount', '')

            if not desc or len(desc) < 2:
                continue
            if not re.search(r'\d', amt):
                continue
            # Only skip if desc IS purely a column header (no digits, short)
            # Real products like 'Item Description 1' have digits — keep them
            desc_has_digit = bool(re.search(r'\d', desc))
            if not desc_has_digit and _is_header_cell(desc) and len(desc) <= 20:
                continue
            if desc.replace('.', '').isdigit():
                continue
            if any(kw == desc.lower().strip() for kw in FOOTER_KW):
                continue

            item = self._clean_line_item(item)
            if 'meters' in item:
                item['mts'] = item['meters']
            items.append(item)
            logger.info(f"✓ GV row: desc={desc[:40]} hsn={item.get('hsn_code')} qty={item.get('quantity')} rate={item.get('rate')} amt={amt}")

        return items

    def _get_cell_value(self, row: Dict, headers: List[str], col_idx: int) -> str:

        """
        Reconstruct line items from Google Vision OCR output where each table cell
        appears on its own line (common for bordered PDF tables).

        Strategy:
        1. Find the table header row (contains Sr./Description/HSN/Qty/Unit keywords)
        2. Determine the number of columns from the header
        3. Collect all lines until Discount/Total/footer
        4. Group lines into rows of N columns each
        5. Build item dicts from rows where description is text and amount is a number
        """
        lines = [l.strip() for l in text.split('\n')]

        # Identify known column header keywords
        HEADER_KW = {'sr', 'sr.', 'item', 'description', 'hsn', 'hsn/sac', 'sac',
                     'qty', 'quantity', 'unit', 'price', 'list price', 'disc', 'disc.',
                     'tax', 'tax %', 'amount', 'amount (rs', 'amount (₹'}
        FOOTER_KW = {'discount', 'total', 'subtotal', 'sub total', 'grand total',
                     'taxable', 'amount in words', 'cgst', 'sgst', 'igst',
                     'bank', 'terms', 'declaration'}

        # Find header row index
        header_idx = None
        header_cols = []
        for i, line in enumerate(lines):
            tokens = re.split(r'\s{2,}|\t', line)
            lower_tokens = [t.lower().strip() for t in tokens]
            hits = sum(1 for t in lower_tokens if any(kw in t for kw in HEADER_KW))
            if hits >= 3:
                header_idx = i
                header_cols = [t.lower().strip() for t in tokens if t.strip()]
                break
            # Also try single-word per line mode: look for 3 consecutive header kw lines
            if line.lower().strip() in HEADER_KW:
                # Check if surrounding lines are also header keywords
                window = [lines[j].lower().strip() for j in range(max(0, i-2), min(len(lines), i+5))]
                if sum(1 for w in window if w in HEADER_KW) >= 4:
                    # find start of this block
                    start = i
                    while start > 0 and lines[start-1].lower().strip() in HEADER_KW:
                        start -= 1
                    end = i
                    while end < len(lines)-1 and lines[end+1].lower().strip() in HEADER_KW:
                        end += 1
                    header_idx = start
                    header_cols = [lines[j].lower().strip() for j in range(start, end+1)]
                    break

        if header_idx is None or len(header_cols) < 3:
            return []

        n_cols = len(header_cols)
        logger.info(f"GV reconstructor: header at line {header_idx}, {n_cols} columns: {header_cols}")

        # Map column positions to field names
        col_map = {}
        for j, col in enumerate(header_cols):
            if any(k in col for k in ('sr', 'no')):        col_map[j] = 'sr_no'
            elif any(k in col for k in ('description', 'item', 'particular')): col_map[j] = 'description'
            elif any(k in col for k in ('hsn', 'sac')):    col_map[j] = 'hsn_code'
            elif any(k in col for k in ('qty', 'quantity')): col_map[j] = 'quantity'
            elif 'unit' == col:                             col_map[j] = 'unit'
            elif any(k in col for k in ('price', 'rate')): col_map[j] = 'rate'
            elif any(k in col for k in ('disc',)):          col_map[j] = 'discount'
            elif 'tax' in col:                              col_map[j] = 'tax_pct'
            elif 'amount' in col:                           col_map[j] = 'amount'

        if 'description' not in col_map.values() or 'amount' not in col_map.values():
            return []

        # Collect data lines after the header row
        data_lines = []
        for line in lines[header_idx + 1:]:
            stripped = line.strip()
            if not stripped:
                continue
            low = stripped.lower()
            if any(kw in low for kw in FOOTER_KW):
                break
            # Skip pure header keyword lines
            if stripped.lower() in HEADER_KW:
                continue
            data_lines.append(stripped)

        if not data_lines:
            return []

        logger.info(f"GV reconstructor: {len(data_lines)} data lines for {n_cols} columns")

        # Group lines into rows of n_cols each
        items = []
        for row_start in range(0, len(data_lines) - n_cols + 1, n_cols):
            row = data_lines[row_start: row_start + n_cols]
            if len(row) < n_cols:
                break

            item = {}
            for j, cell in enumerate(row):
                field = col_map.get(j)
                if field:
                    item[field] = cell

            desc = item.get('description', '')
            amt  = item.get('amount', '')

            # Validate: description must be text, amount must be a number
            if not desc or len(desc) < 2:
                continue
            if not re.search(r'\d', amt):
                continue
            if desc.lower() in HEADER_KW or desc.lower() in FOOTER_KW:
                continue
            # Skip pure-numeric descriptions (likely a serial number row)
            if desc.replace('.', '').isdigit():
                continue

            item = self._clean_line_item(item)
            items.append(item)
            logger.info(f"✓ GV row: desc={desc[:40]} hsn={item.get('hsn_code')} qty={item.get('quantity')} amt={amt}")

        return items

    def _get_cell_value(self, row: Dict, headers: List[str], col_idx: int) -> str:
        """Get cell value from row by column index."""
        if col_idx is None or col_idx >= len(headers):
            return ''
        
        header = headers[col_idx]
        
        # Try multiple strategies to get the value
        
        # Strategy 1: Exact header match (case-insensitive)
        for key in row.keys():
            if str(key).lower().strip() == header:
                value = row[key]
                return str(value).strip() if value is not None else ''
        
        # Strategy 2: Try by index if row is list-like
        try:
            if isinstance(row, dict):
                # Get values as list and access by index
                values = list(row.values())
                if col_idx < len(values):
                    value = values[col_idx]
                    return str(value).strip() if value is not None else ''
        except:
            pass
        
        # Strategy 3: Try original header (before lowercasing)
        for key in row.keys():
            if str(key).strip() == header:
                value = row[key]
                return str(value).strip() if value is not None else ''
        
        return ''
    
    def _clean_line_item(self, item: Dict) -> Dict:
        """Clean and normalize line item data."""
        # Clean numeric fields
        for field in ['quantity', 'rate', 'amount', 'meters', 'mts', 'cut']:
            if field in item and item[field]:
                # Remove commas and extra spaces
                cleaned = str(item[field]).replace(',', '').replace(' ', '').strip()
                # Remove trailing/leading characters or OCR noise (e.g. '315.00p' -> '315.00')
                m = re.search(r'([\d.]+)', cleaned)
                if m:
                    cleaned = m.group(1)
                item[field] = cleaned if cleaned else ''
        
        # Clean HSN code (remove non-alphanumeric)
        if item.get('hsn_code'):
            item['hsn_code'] = ''.join(c for c in str(item['hsn_code']) if c.isalnum())
        
        return item
    
    def _find_column(self, headers: List[str], keywords: List[str]) -> Optional[int]:
        """Find column index by matching keywords with partial matching support."""
        # First pass: exact match
        for i, header in enumerate(headers):
            for keyword in keywords:
                if header == keyword:
                    return i
        
        # Second pass: keyword is contained in header
        for i, header in enumerate(headers):
            for keyword in keywords:
                if keyword in header:
                    return i
        
        # Third pass: header is contained in keyword (for compound headers)
        for i, header in enumerate(headers):
            if not header or len(header) < 2:
                continue
            for keyword in keywords:
                if header in keyword:
                    return i
        
        return None


# Global instance
table_extractor = TableExtractor()
