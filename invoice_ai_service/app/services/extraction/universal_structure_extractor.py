"""
Universal Structure Extractor
==============================
Handles ANY document format dynamically — no hardcoded per-format handlers needed.

How it works:
  1. detect_document_type()   → infers type from keywords/structure
  2. detect_column_headers()  → finds table headers + their positions
  3. extract_header_block()   → company name, GSTIN, PAN, address, period
  4. extract_grand_total()    → reads any summary / grand-total row
  5. extract_party_rows()     → reads all line/party rows from the table
  6. extract_kv_fields()      → key:value pairs (invoice no, date, GSTIN, etc.)

Call extract_all(text) to get a fully structured result for any document.
"""

import re
import logging
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Column-name → standard field mapping (case-insensitive)
# ---------------------------------------------------------------------------
COLUMN_FIELD_MAP: Dict[str, str] = {
    # Invoice / bill identification
    "bill no": "invoice_number", "billno": "invoice_number",
    "invoice no": "invoice_number", "invoice number": "invoice_number",
    "sr no": "sr_no", "sr.no": "sr_no", "s.no": "sr_no",

    # Dates
    "bill date": "invoice_date", "billdate": "invoice_date",
    "invoice date": "invoice_date", "date": "invoice_date",

    # Amounts
    "gross amt": "gross_amount", "grossamt": "gross_amount", "gross amount": "gross_amount",
    "taxable": "taxable_amount", "taxable value": "taxable_amount",
    "taxable amount": "taxable_amount", "taxable amt": "taxable_amount",
    "gst amt": "gst_amount", "gstamt": "gst_amount", "gst": "gst_amount",
    "gst amount": "gst_amount",
    "cgst": "cgst_amount", "cgst amount": "cgst_amount",
    "sgst": "sgst_amount", "sgst amount": "sgst_amount",
    "igst": "igst_amount", "igst amount": "igst_amount",
    "tds amt": "tds_amount", "tdsamt": "tds_amount",
    "paid amt": "paid_amount", "paidamt": "paid_amount",
    "gr amt": "gr_amount", "gramt": "gr_amount",
    "balance": "balance_amount",
    "total value": "total_amount", "total amount": "total_amount",
    "net amount": "total_amount", "net amt": "total_amount",
    "invoice value": "total_amount",
    "add less": "add_less", "addless": "add_less",

    # Other
    "days": "days",
    "narration": "narration",
    "description": "description",
    "hsn": "hsn_code", "hsn code": "hsn_code",
    "qty": "quantity", "quantity": "quantity",
    "rate": "rate",
    "type": "doc_subtype",
    "firm name": "firm_name",
}

# Document type signals
DOC_TYPE_SIGNALS: Dict[str, List[str]] = {
    "sale_outstanding_report": [
        "sale outstanding report", "outstanding report", "party wise",
        "billno", "grossamt", "gstamt", "balance", "printed on",
    ],
    "purchase_outstanding_report": [
        "purchase outstanding", "payable report", "party wise",
        "billno", "grossamt", "balance",
    ],
    "expense_register": [
        "expense register", "dying", "printing register", "broker register",
        "row labels", "total value",
    ],
    "sales_invoice": [
        "tax invoice", "sale invoice", "bill of supply",
        "buyer:", "invoice value", "invoice no",
    ],
    "purchase_invoice": [
        "purchase invoice", "tax invoice", "supplier",
        "bill no", "taxable value",
    ],
    "debit_note": ["debit note", "debit memo"],
    "credit_note": ["credit note"],
    "ledger": ["ledger", "account statement", "opening balance", "closing balance"],
}

GSTIN_RE = re.compile(r'\b(\d{2}[A-Z]{5}\d{4}[A-Z]{1}[A-Z\d]{1}Z[A-Z\d]{1})\b', re.I)
DATE_RE  = re.compile(r'\b(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\b')
AMT_RE   = re.compile(r'([-]?\d{1,3}(?:,\d{3})*(?:\.\d+)?)')


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _to_float(s: str) -> Optional[float]:
    try:
        return float(s.replace(',', '').strip())
    except Exception:
        return None


def _norm(s: str) -> str:
    return re.sub(r'\s+', ' ', s).strip().lower()


# ---------------------------------------------------------------------------
# 1. Document type detection
# ---------------------------------------------------------------------------

def detect_document_type(text: str) -> Tuple[str, float]:
    """
    Automatically infer document type from text without any hardcoded format IDs.
    Returns (doc_type_string, confidence 0-1).
    """
    text_l = text.lower()
    scores: Dict[str, float] = {}

    for dtype, signals in DOC_TYPE_SIGNALS.items():
        hits = sum(1 for s in signals if s in text_l)
        scores[dtype] = hits / len(signals) if signals else 0

    if not scores:
        return "unknown", 0.0

    best = max(scores, key=lambda k: scores[k])
    best_score = scores[best]

    # Boost if GSTIN found (confirms it's a GST document)
    if GSTIN_RE.search(text):
        best_score = min(1.0, best_score + 0.05)

    if best_score < 0.20:
        return "unknown", best_score

    return best, round(best_score, 2)


# ---------------------------------------------------------------------------
# 2. Column header detection
# ---------------------------------------------------------------------------

def detect_column_headers(text: str) -> Dict[str, int]:
    """
    Scan text for lines that look like table column headers.
    Returns {standard_field_name: char_position} mapping.
    """
    lines = text.split('\n')
    best_line = None
    best_hits = 0
    best_pos = 0

    for line_no, line in enumerate(lines[:60]):  # headers near top
        line_l = line.lower()
        hits = 0
        for col_key in COLUMN_FIELD_MAP:
            if col_key in line_l:
                hits += 1
        if hits > best_hits:
            best_hits = hits
            best_line = line
            best_pos = line_no

    if not best_line or best_hits < 2:
        return {}

    # Parse column positions from the header line
    col_map: Dict[str, int] = {}
    line_l = best_line.lower()
    for col_key, field in COLUMN_FIELD_MAP.items():
        idx = line_l.find(col_key)
        if idx >= 0:
            col_map[field] = idx

    logger.info(f"Detected {len(col_map)} columns from header at line {best_pos}: {list(col_map.keys())}")
    return col_map


# ---------------------------------------------------------------------------
# 3. Company header extraction
# ---------------------------------------------------------------------------

def extract_header_block(text: str) -> Dict[str, Any]:
    """
    Extract company information from the document header (first ~25 lines).
    Works for any format that has a company name + GSTIN at the top.
    """
    result: Dict[str, Any] = {}
    lines = text.split('\n')

    company_found = False
    for line in lines[:25]:
        line_s = line.strip()
        if not line_s or line_s.startswith('---') or line_s.startswith('==='):
            continue

        # GSTIN
        g = GSTIN_RE.search(line_s)
        if g and 'supplier_gstin' not in result:
            result['supplier_gstin'] = g.group(1).upper()
            continue

        # PAN
        pan_m = re.search(r'\bPAN\s*(?:No\.?|:)\s*([A-Z]{5}\d{4}[A-Z])\b', line_s, re.I)
        if pan_m:
            result['pan'] = pan_m.group(1).upper()
            continue

        # Company name = first substantial ALL-CAPS line (not a label line)
        if (not company_found
                and len(line_s) > 4
                and re.match(r'^[A-Z][A-Z\s&.]+$', line_s)
                and not re.search(r'\b(PAN|GSTIN|REPORT|PARTY|SALE|PHONE|EMAIL|FAX|MOBILE)\b', line_s, re.I)):
            result['supplier_name'] = line_s
            company_found = True
            continue

        # Phone / Mobile
        phone_m = re.search(r'(?:Phone|Mobile|Ph)\s*[:\-]?\s*(\d[\d\s\-]{8,14})', line_s, re.I)
        if phone_m:
            result['phone'] = phone_m.group(1).strip()

        # Email
        email_m = re.search(r'[\w.+-]+@[\w.-]+\.\w+', line_s, re.I)
        if email_m:
            result['email'] = email_m.group(0)

    # Report period from title line
    period_m = re.search(
        r'\((\d{2}/\d{2}/\d{4})\s+TO\s+(\d{2}/\d{2}/\d{4})\)',
        text, re.I
    )
    if period_m:
        result['report_from_date'] = period_m.group(1)
        result['report_to_date']   = period_m.group(2)

    # Printed / Report date
    printed_m = re.search(r'Printed\s+On\s*:\s*(\d{2}/\d{2}/\d{4})', text, re.I)
    if printed_m:
        result['printed_on'] = printed_m.group(1)

    return result


# ---------------------------------------------------------------------------
# 4. Grand total / summary row extraction
# ---------------------------------------------------------------------------

def extract_grand_total(text: str, col_map: Dict[str, int]) -> Dict[str, Any]:
    """
    Find any Grand Total / TOTAL summary row and return field values.
    Works by matching common total row labels, then extracting numbers.
    """
    result: Dict[str, Any] = {}

    # Patterns for total rows (order matters — most specific first)
    total_patterns = [
        # "GRAND TO  107  3833915.00  -9.25  191695.75  0.00  -621102.00  99582.00  4547140.00  144"
        r'GRAND\s+TO(?:TAL)?\s+(\d+)\s+([-\d,]+\.?\d*)\s+([-\d,]+\.?\d*)\s+([-\d,]+\.?\d*)'
        r'\s+([-\d,]+\.?\d*)\s+([-\d,]+\.?\d*)\s+([-\d,]+\.?\d*)\s+([-\d,]+\.?\d*)',

        # "Grand Total  8291  1492.38  9783.38"  (register 3-col)
        r'Grand\s+Total\s+([-\d,]+\.?\d*)\s+([-\d,]+\.?\d*)\s+([-\d,]+\.?\d*)',

        # "TOTAL  2  47920.00  0.00  2396.00  ..."  (report party total)
        r'(?:^|\n)TOTAL\s+(\d+)\s+([-\d,]+\.?\d*)\s+([-\d,]+\.?\d*)\s+([-\d,]+\.?\d*)'
        r'\s+([-\d,]+\.?\d*)\s+([-\d,]+\.?\d*)\s+([-\d,]+\.?\d*)\s+([-\d,]+\.?\d*)',
    ]

    for pat in total_patterns:
        m = re.search(pat, text, re.I | re.M)
        if not m:
            continue

        nums = [_to_float(g) for g in m.groups() if g is not None]
        nums = [n for n in nums if n is not None]

        if not nums:
            continue

        # Use column map to assign values if available
        ordered_fields = _ordered_fields_from_col_map(col_map)

        if ordered_fields and len(ordered_fields) >= len(nums):
            for i, val in enumerate(nums):
                field = ordered_fields[i]
                result[field] = val
        else:
            # Fall back: largest = total, smallest = gst/tax, second-largest = taxable
            if len(nums) == 3:
                nums_s = sorted(nums)
                result['gst_amount']    = nums_s[0]
                result['taxable_amount'] = nums_s[2] - nums_s[0]
                result['total_amount']  = nums_s[2]
            elif len(nums) >= 4:
                # Treat last as balance/total
                result['total_amount']  = nums[-1]
                result['taxable_amount'] = nums[1] if len(nums) > 1 else None
                result['gst_amount']    = nums[3] if len(nums) > 3 else None

        logger.info(f"Grand total extracted: {result}")
        break  # use first matching pattern

    return result


def _ordered_fields_from_col_map(col_map: Dict[str, int]) -> List[str]:
    """Return field names ordered by their character position in the header line."""
    return [f for f, _ in sorted(col_map.items(), key=lambda x: x[1])]


# ---------------------------------------------------------------------------
# 5. Line / party row extraction
# ---------------------------------------------------------------------------

def extract_party_rows(text: str, col_map: Dict[str, int]) -> List[Dict[str, Any]]:
    """
    Dynamically extract party/line rows from any tabular document.
    Uses the detected column map to assign values per row.

    Handles:
    - Outstanding reports: PARTY: NAME ... TOTAL rows
    - Registers: VENDOR NAME   taxable   gst   total
    - Generic invoices: numbered line items
    """
    rows: List[Dict[str, Any]] = []
    seen = set()

    # --- Strategy A: PARTY: NAME ... TOTAL blocks (outstanding reports) ---
    party_pat = re.compile(
        r'PARTY:\s*([A-Z][A-Z\s\-&./()]+?)\s*\(BAL\s*:\s*([\d,]+\.?\d*)\s*(Dr\.|Cr\.)',
        re.I
    )
    total_pat = re.compile(
        r'(?:^|\n)TOTAL\s+(\d+)\s+([-\d,]+\.?\d*)\s+([-\d,]+\.?\d*)\s+([-\d,]+\.?\d*)'
        r'(?:\s+([-\d,]+\.?\d*))?(?:\s+([-\d,]+\.?\d*))?(?:\s+([-\d,]+\.?\d*))?(?:\s+([-\d,]+\.?\d*))?',
        re.I | re.M
    )

    parties = list(party_pat.finditer(text))
    if parties:
        totals = list(total_pat.finditer(text))
        for idx, pm in enumerate(parties):
            party_name = pm.group(1).strip()
            key = party_name.upper()[:40]
            if key in seen:
                continue
            seen.add(key)

            next_pos = parties[idx + 1].start() if idx + 1 < len(parties) else len(text)
            party_totals = [t for t in totals if pm.start() < t.start() < next_pos]
            if not party_totals:
                continue

            t = party_totals[-1]
            nums = [_to_float(g) for g in t.groups() if g is not None]
            nums = [n for n in nums if n is not None]

            row: Dict[str, Any] = {'description': party_name}
            ordered = _ordered_fields_from_col_map(col_map)
            # Skip first field (bill count) if it's an integer count
            if ordered and len(ordered) >= len(nums):
                for i, val in enumerate(nums):
                    if i < len(ordered):
                        row[ordered[i]] = val
            else:
                if len(nums) >= 3:
                    row['quantity']       = int(nums[0]) if nums[0] == int(nums[0]) else None
                    row['taxable_amount'] = nums[1] if len(nums) > 1 else None
                    row['gst_amount']     = nums[3] if len(nums) > 3 else None
                    row['amount']         = nums[-1]

            rows.append(row)
        if rows:
            return rows

    # --- Strategy B: ALL-CAPS vendor name + 3 numbers (expense registers) ---
    reg_pat = re.compile(
        r'^([A-Z][A-Z\s&./()]{3,50}?)\s{2,}([\d,]+\.?\d*)\s+([\d,]+\.?\d*)\s+([\d,]+\.?\d*)\s*$',
        re.M
    )
    for m in reg_pat.finditer(text):
        vendor = m.group(1).strip()
        if re.search(r'^(ROW\s+LABELS|GRAND\s+TOTAL|TAXABLE|TYPE|TOTAL)', vendor, re.I):
            continue
        key = vendor.upper()[:40]
        if key in seen:
            continue
        seen.add(key)
        nums = [_to_float(m.group(i)) for i in (2, 3, 4)]
        rows.append({
            'description':    vendor,
            'taxable_amount': nums[0],
            'gst_amount':     nums[1],
            'amount':         nums[2],
        })
    if rows:
        return rows

    # --- Strategy C: Numbered line items (standard invoices) ---
    inv_pat = re.compile(
        r'(?:^|\n)\s*(\d{1,4})\s+([A-Za-z][A-Za-z0-9\s\-,/.]+?)\s+'
        r'(\d{4,8})\s+([\d.]+)\s+([\d,.]+)\s+([\d,.]+)',
        re.M
    )
    for m in inv_pat.finditer(text):
        desc = m.group(2).strip()
        key = desc.upper()[:40]
        if key in seen:
            continue
        seen.add(key)
        rows.append({
            'sr_no':       m.group(1),
            'description': desc,
            'hsn_code':    m.group(3),
            'quantity':    _to_float(m.group(4)),
            'rate':        _to_float(m.group(5)),
            'amount':      _to_float(m.group(6)),
        })

    return rows


# ---------------------------------------------------------------------------
# 6. Key-value pair extraction (invoice number, date, party names, etc.)
# ---------------------------------------------------------------------------

KV_PATTERNS: List[Tuple[str, str, str]] = [
    # (field_name, pattern, group_index_hint)
    ('invoice_number', r'(?:Invoice|Bill|Inv)\s*(?:No\.?|Number|#)\s*[:\-]?\s*([A-Z0-9/\-#]+)', '1'),
    ('invoice_date',   r'(?:Invoice|Bill|Inv)\s*Date\s*[:\-]?\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})', '1'),
    ('due_date',       r'Due\s*Date\s*[:\-]?\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})', '1'),
    ('supplier_gstin', r'(?:Our|Seller|Supplier)\s*GSTIN\s*[:\-]?\s*([A-Z0-9]{15})', '1'),
    ('buyer_gstin',    r'(?:Buyer|Customer|Client|Recipient)\s*GSTIN\s*[:\-]?\s*([A-Z0-9]{15})', '1'),
    ('buyer_name',     r'(?:Billed\s+To|Bill\s+To|Buyer|Customer)\s*[:\-]?\s*([A-Za-z][A-Za-z\s&.]{3,60}?)(?=\n|GSTIN|Phone|Address)', '1'),
    ('total_amount',   r'(?:Grand\s+Total|Net\s+Amount|Invoice\s+Value|Total\s+Amount)\s*[:\-]?\s*([\d,]+\.?\d*)', '1'),
    ('taxable_amount', r'(?:Taxable\s+(?:Value|Amount)|Sub\s+Total)\s*[:\-]?\s*([\d,]+\.?\d*)', '1'),
    ('cgst_amount',    r'CGST\s*@?\s*[\d.]+%?\s*[:\-=]?\s*([\d,]+\.?\d*)', '1'),
    ('sgst_amount',    r'SGST\s*@?\s*[\d.]+%?\s*[:\-=]?\s*([\d,]+\.?\d*)', '1'),
    ('igst_amount',    r'IGST\s*@?\s*[\d.]+%?\s*[:\-=]?\s*([\d,]+\.?\d*)', '1'),
]


def extract_kv_fields(text: str) -> Dict[str, Any]:
    """
    Extract standard key-value fields from any document using generic patterns.
    Covers: invoice_number, dates, GSTIN, party names, amounts.
    """
    result: Dict[str, Any] = {}

    for field, pattern, _ in KV_PATTERNS:
        m = re.search(pattern, text, re.I | re.M)
        if not m:
            continue
        val = m.group(1).strip()
        if not val:
            continue
        # Convert amount fields to float
        if 'amount' in field or 'total' in field:
            fval = _to_float(val)
            if fval:
                result[field] = fval
        else:
            result[field] = val

    # All GSTINs in document
    all_gstins = list(set(g.upper() for g in GSTIN_RE.findall(text)))
    if len(all_gstins) == 1:
        result.setdefault('supplier_gstin', all_gstins[0])
    elif len(all_gstins) >= 2:
        result.setdefault('supplier_gstin', all_gstins[0])
        result.setdefault('buyer_gstin', all_gstins[1])

    return result


# ---------------------------------------------------------------------------
# 7. Master entry point
# ---------------------------------------------------------------------------

def extract_all(text: str) -> Dict[str, Any]:
    """
    Fully dynamic extraction for ANY document type.

    Returns a unified dict with:
      supplier_name, supplier_gstin, buyer_name, buyer_gstin,
      invoice_number, invoice_date,
      taxable_amount, gst_amount, total_amount,
      cgst_amount, sgst_amount, igst_amount,
      items (list),
      _doc_type, _doc_type_confidence,
      _col_map, _gst_total, _no_cgst_sgst (for register/report types)
    """
    # Step 1: Detect document type
    doc_type, type_conf = detect_document_type(text)
    logger.info(f"Universal extractor: doc_type={doc_type} conf={type_conf}")

    # Step 2: Detect column layout
    col_map = detect_column_headers(text)

    # Step 3: Extract header block (company, GSTIN, period)
    header = extract_header_block(text)

    # Step 4: Extract key-value fields
    kv = extract_kv_fields(text)

    # Step 5: Extract grand total
    grand = extract_grand_total(text, col_map)

    # Step 6: Extract line/party rows
    rows = extract_party_rows(text, col_map)

    # ── Merge: header wins > grand > kv (grand total is authoritative for amounts)
    fields: Dict[str, Any] = {}
    fields.update(kv)
    fields.update(header)
    # Grand total values override kv for amounts
    for k, v in grand.items():
        if v is not None:
            fields[k] = v

    # Remap gst_amount → _gst_total for register/report types (no cgst/sgst split)
    is_report_or_register = doc_type in (
        "expense_register", "sale_outstanding_report",
        "purchase_outstanding_report", "ledger"
    )
    if is_report_or_register:
        if 'gst_amount' in fields:
            fields['_gst_total'] = fields.pop('gst_amount')
        fields['cgst_amount'] = None
        fields['sgst_amount'] = None
        fields['igst_amount'] = None
        fields['_no_cgst_sgst'] = True

    # Normalise taxable_amount from gross_amount if needed
    if 'gross_amount' in fields and 'taxable_amount' not in fields:
        fields['taxable_amount'] = fields['gross_amount']

    # balance_amount → total_amount for reports
    if 'balance_amount' in fields and 'total_amount' not in fields:
        fields['total_amount'] = fields['balance_amount']

    # Line items
    fields['items'] = rows

    # Metadata
    fields['_doc_type']            = doc_type
    fields['_doc_type_confidence'] = type_conf
    fields['_col_map']             = col_map

    return fields
