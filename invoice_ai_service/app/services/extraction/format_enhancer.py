"""Format-specific extraction overlays — add new handlers here for new invoice layouts."""

import logging
import re
from typing import Any, Dict, List, Optional

from app.services.extraction.format_registry import get_profile

logger = logging.getLogger(__name__)

GSTIN_RE = re.compile(r"\b(\d{2}[A-Z]{5}\d{4}[A-Z]{1}[A-Z\d]{1}[Z]{1}[A-Z\d]{1})\b", re.I)


def _first_float(patterns: List[str], text: str) -> Optional[float]:
    for pat in patterns:
        m = re.search(pat, text, re.I | re.M)
        if m:
            try:
                return float(m.group(1).replace(",", "").replace(" ", ""))
            except ValueError:
                continue
    return None


def _first_str(patterns: List[str], text: str) -> Optional[str]:
    for pat in patterns:
        m = re.search(pat, text, re.I | re.M)
        if m:
            return re.sub(r"\s+", " ", m.group(1).strip())
    return None


def enhance_fields(text: str, fields: Dict[str, Any], format_id: str) -> Dict[str, Any]:
    """Apply format-specific extraction on top of universal results."""
    handler = _HANDLERS.get(format_id)
    if handler:
        try:
            fields = handler(text, fields)
        except Exception as e:
            logger.warning(f"Format handler {format_id} failed: {e}")
    return fields


def _norm_item_key(it: Dict) -> tuple:
    desc = str(it.get("description", ""))
    desc = re.sub(r"([a-z])([A-Z])", r"\1 \2", desc)
    desc = re.sub(r"\s+", " ", desc).strip().upper()[:40]
    return (desc, str(it.get("hsn_code", "")))


def enhance_line_items(text: str, items: List[Dict], format_id: str) -> List[Dict]:
    """Fill line items from format handlers; merge Mts/Cut when OCR used wrong columns."""
    handler = _LINE_HANDLERS.get(format_id, _line_items_universal)
    fmt_items = handler(text) or []
    if not fmt_items:
        return items
    if not items:
        return fmt_items

    if format_id == "mr_fashion_chandni":
        bad = any(str(i.get("rate", "")).lower() in ("mtr", "mt", "meter", "meters") for i in items)
        if bad or len(fmt_items) >= len(items):
            return fmt_items

    def _key(it: Dict) -> tuple:
        return _norm_item_key(it)

    fmt_by_key = {_key(i): i for i in fmt_items}
    merged = []
    for it in items:
        row = dict(it)
        fmt = fmt_by_key.get(_key(row))
        if fmt:
            for field in ("meters", "mts", "cut", "sr_no"):
                if fmt.get(field) and not row.get(field):
                    row[field] = fmt[field]
            if fmt.get("meters") and not row.get("mts"):
                row["mts"] = fmt["meters"]
            # Fix Pcs / Mts / Rate / Amount column swap (172 → rate, 150 → amount)
            if fmt.get("meters") and str(row.get("rate")) == str(fmt.get("meters")):
                row["rate"] = fmt.get("rate", row.get("rate"))
                row["amount"] = fmt.get("amount", row.get("amount"))
                row["quantity"] = fmt.get("quantity", row.get("quantity"))
            if str(row.get("rate", "")).lower() in ("mtr", "mt", "meter", "meters"):
                row["rate"] = fmt.get("rate", row.get("rate"))
                row["meters"] = fmt.get("meters") or fmt.get("mts") or row.get("meters")
                row["mts"] = row.get("meters")
                row["amount"] = fmt.get("amount", row.get("amount"))
        merged.append(row)

    seen = {_key(m) for m in merged}
    for fi in fmt_items:
        if _key(fi) not in seen:
            merged.append(fi)
    return merged


# --- Format-specific field handlers ---


def _gayatri_box(text: str, f: Dict) -> Dict:
    f["supplier_name"] = f.get("supplier_name") or _first_str([r"(GAYATRI\s+SAREE)"], text)
    f["buyer_name"] = f.get("buyer_name") or _first_str([
        r"Billed\s+To[^\n]*\n\s*([A-Za-z][A-Za-z\s]{3,50}?PALACE)",
        r"(SURAT\s+SAREE\s+PALACE)",
    ], text)
    f["taxable_amount"] = f.get("taxable_amount") or _first_float([
        r"Total\.{2,}[^\d\n]*([\d,]+\.?\d{2})",
    ], text)
    f["igst_amount"] = f.get("igst_amount") or _first_float([
        r"[+\-]?\s*IGST\s+[\d.]+\s*%\s*([\d,]+\.?\d*)",
    ], text)
    f["total_amount"] = f.get("total_amount") or _first_float([
        r"Net\s+Amount\s+Rs\.?\s*([\d,]+\.?\d*)",
    ], text)
    return f


def _komal_prints(text: str, f: Dict) -> Dict:
    f["supplier_name"] = f.get("supplier_name") or _first_str([r"(KOMAL\s+PRINTS)"], text)
    # Buyer name appears as "Buyer: ALAKH INTERNATIONAL  BILL NO." — stop before BILL
    f["buyer_name"] = f.get("buyer_name") or _first_str([
        r"Buyer:\s*([A-Za-z][A-Za-z\s&]+?)(?=\s{2,}|\s+BILL|\s+CHALLAN|\n)",
    ], text)
    f["invoice_number"] = f.get("invoice_number") or _first_str([r"BILL\s*NO\.?\s*:?\s*(\d+)"], text)
    f["taxable_amount"] = f.get("taxable_amount") or _first_float([
        r"SUB\s+TOTAL[^\d]*([\d,]+\.?\d*)",
        r"Taxable\s+Value\s*[:\s]*([\d,]+\.?\d*)",
    ], text)
    f["cgst_amount"] = f.get("cgst_amount") or _first_float([
        r"CGST\s*@\s*[\d.]+%\s*on\s*Taxable\s*Value\s*[\d,]+(?:\.\d+)?\s*=\s*([\d,]+\.?\d*)",
    ], text)
    f["sgst_amount"] = f.get("sgst_amount") or _first_float([
        r"SGST\s*@\s*[\d.]+%\s*on\s*Taxable\s*Value\s*[\d,]+(?:\.\d+)?\s*=\s*([\d,]+\.?\d*)",
    ], text)
    f["total_amount"] = f.get("total_amount") or _first_float([
        r"Invoice\s+Value\s*([\d,]+\.?\d*)",
    ], text)
    return f


def _muskan_glued(text: str, f: Dict) -> Dict:
    """MUSKAN / KHUSHBOO / CHANDRALOK glued OCR layout."""
    f["supplier_name"] = f.get("supplier_name") or _first_str([
        r"(CHANDRALOK\s+CREATION)",
        r"(KHUSHBOO\s+CREATION)",
        r"(MUSKAN\s+COLLECTION)",
        r"^([A-Za-z]+\s+CREATION)",
    ], text)
    f["buyer_name"] = f.get("buyer_name") or _first_str([
        r"Address\s*:\s*([A-Za-z][A-Za-z\s&]+?)(?=Place|GSTIN|State)",
        r"Name\s*:\s*:?\s*([A-Za-z][A-Za-z\s&]+?)(?=Address|GSTIN|Place)",
        r"(MUZU\s+TEX)",
        r"(ALAKH\s+INTERNATIONAL)",
    ], text)

    # Taxable: after discount or line total before tax
    f["taxable_amount"] = f.get("taxable_amount") or _first_float([
        r"DISCOUNT\s+[\d.]+%\s*([\d,]+\.?\d*)",
        r"Total\s+Amt\s+Before\s+Tax[^\d]*?([\d,]+\.?\d{2,})",
        r"Gross\s+Amount\s*([\d,]+\.?\d*)",
        r"Taxable\s+Amount\s*\+*([\d,]+\.?\d*)",
    ], text)

    # Stacked tax lines before "CGST (2.50%)" label (188.pdf layout)
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
            if abs(a - b) < 0.1 and a >= 10:
                f["cgst_amount"] = f.get("cgst_amount") or a
                f["sgst_amount"] = f.get("sgst_amount") or b
        except ValueError:
            pass

    # CGST/SGST glued: "Total Amt Before Tax+++599.85599.850.30" or amounts after CGST (2.50%) label
    before_tax = re.search(
        r"Total\s+Amt\s+Before\s+Tax\++([\d,.]+)",
        text,
        re.IGNORECASE,
    )
    if before_tax:
        amounts = re.findall(r"\d+\.\d{2}", before_tax.group(1).replace(",", ""))
        tax_parts = [float(a) for a in amounts if float(a) >= 50]
        if len(tax_parts) >= 2:
            f["cgst_amount"] = f.get("cgst_amount") or tax_parts[0]
            f["sgst_amount"] = f.get("sgst_amount") or tax_parts[1]
        elif len(tax_parts) == 1:
            f["cgst_amount"] = f.get("cgst_amount") or tax_parts[0]
            f["sgst_amount"] = f.get("sgst_amount") or tax_parts[0]

    cgst_val = _first_float([
        r"CGST\s*\([\d.]+%\)\s*\+*([\d,]+\.?\d*)",
        r"CGST\s*[\d.]+%\s+([\d,]+\.?\d{2,})",
    ], text)
    if cgst_val and cgst_val >= 10:
        f["cgst_amount"] = f.get("cgst_amount") or cgst_val
    sgst_val = _first_float([
        r"SGST\s*\([\d.]+%\)\s*\+*([\d,]+\.?\d*)",
        r"SGST\s*[\d.]+%\s+([\d,]+\.?\d{2,})",
    ], text)
    if sgst_val and sgst_val >= 10:
        f["sgst_amount"] = f.get("sgst_amount") or sgst_val

    # Total tax from "Tax Amount : GST 1199.70"
    tax_gst = _first_float([r"Tax\s+Amount\s*:\s*GST\s*([\d,]+\.?\d*)"], text)
    if tax_gst and tax_gst >= 10.0 and not f.get("cgst_amount"):
        f["cgst_amount"] = round(tax_gst / 2, 2)
        f["sgst_amount"] = round(tax_gst / 2, 2)

    # Grand total — prefer "After Tax", not tax amount
    after_tax = _first_float([
        r"Total\s+Amt\s+After\s+Tax\s*([\d,]+\.?\d*)",
        r"Net\s+Amount\s*([\d,]+\.?\d*)",
    ], text)
    if after_tax:
        f["total_amount"] = after_tax
    elif f.get("total_amount") and f["total_amount"] < 5000 and after_tax:
        f["total_amount"] = after_tax

    f["total_amount"] = f.get("total_amount") or _first_float([
        r"Total\s+Amt\s+After\s+Tax\s*([\d,]+\.?\d*)",
        r"Net\s+Amount\s*([\d,]+\.?\d*)",
    ], text)

    return f


def _shivam_fashion(text: str, f: Dict) -> Dict:
    challan = _first_str([r"Challan\s*Number\s*[:\-]?\s*(\d+)"], text)
    if challan:
        f["invoice_number"] = challan
    f["supplier_name"] = f.get("supplier_name") or _first_str([r"(SHIVAM\s+FASHION)"], text)
    f["buyer_name"] = f.get("buyer_name") or _first_str([
        r"Receiver\s*/\s*Billed\s+To\s*\n*\s*(?!Goods\s+Despatched)([A-Za-z][A-Za-z\s]+)",
        r"M/s\.\s*\n*\s*([A-Za-z][A-Za-z\s]+)",
        r"(ALAKH\s+INTERNATIONAL)",
    ], text)
    f["taxable_amount"] = f.get("taxable_amount") or _first_float([
        r"([\d,]+\.?\d{2})\s*\n\s*CENTRAL\s+GST",
        r"\bon\s+([\d,]+\.?\d{2})",
    ], text)
    f["cgst_amount"] = f.get("cgst_amount") or _first_float([
        r"CENTRAL\s+GST\s+[\d.]+\s*(?:%|PERC)?\s*\n\s*([\d,]+\.?\d{2})",
        r"Center\s+Tax\s+[\d.]+\s*%?\s*\n\s*([\d,]+\.?\d{2})",
    ], text)
    f["sgst_amount"] = f.get("sgst_amount") or _first_float([
        r"STATE\s+GST\s+[\d.]+\s*(?:%|PERC)?\s*\n\s*([\d,]+\.?\d{2})",
        r"State\s+Tax\s+[\d.]+\s*%?\s*\n\s*([\d,]+\.?\d{2})",
    ], text)
    f["total_amount"] = f.get("total_amount") or _first_float([
        r"([\d,]+\.?\d{2})[\s\n]+0\.00[\s\n]+Net\s+Total",
        r"Net\s+Total\s*[:\-]?\s*([\d,]+\.?\d{2})",
    ], text)
    return f


def _chandni_header_fields(text: str) -> Dict[str, Optional[str]]:
    """
    Parse Chandni app header — Bill No / dates on separate lines; pymupdf may reorder blocks.
    """
    out: Dict[str, Optional[str]] = {
        "invoice_number": None,
        "invoice_date": None,
        "due_date": None,
    }

    # Ignore IRN/Ack footer when searching header (Ack No is a long numeric)
    search_end = len(text)
    for marker in ("irn no", "ack no", "ack date", "f7cd07ba"):
        pos = text.lower().find(marker)
        if pos > 50:
            search_end = min(search_end, pos)
    search_text = text[:search_end]

    bill_patterns = [
        r"Bill\s*No[\s\n:.\-]{0,120}(\d{1,6})\b",
        r"Bill\s*No[\s\S]{0,400}?(\d{1,6})\b",
        r"Invoice\s+Detail[\s\S]{0,800}?Bill\s*No[\s\S]{0,400}?(\d{1,6})\b",
    ]
    for pat in bill_patterns:
        m = re.search(pat, search_text, re.IGNORECASE)
        if m:
            num = m.group(1)
            if len(num) <= 6 and int(num) < 1000000:
                out["invoice_number"] = num
                break

    block_m = re.search(
        r"Invoice\s+Detail\s*:?(.*?)(?=\bSr\s+Items\b|\bItems\s+Name\b|\d+\s+[A-Za-z]{4,})",
        search_text,
        re.IGNORECASE | re.DOTALL,
    )
    block = block_m.group(1) if block_m else ""
    if not block:
        bill_anchor = re.search(r"Bill\s*No", search_text, re.I)
        if bill_anchor:
            block = search_text[bill_anchor.start() : bill_anchor.start() + 500]

    dates: List[str] = []
    bill_candidates: List[str] = []

    for line in block.split("\n"):
        line = line.strip()
        if not line:
            continue
        dm = re.match(r"^(\d{1,2}[-/]\d{1,2}[-/]\d{2,4})$", line)
        if dm:
            dates.append(dm.group(1))
            continue
        cm = re.match(r"^:?\s*(\d{1,2}[-/]\d{1,2}[-/]\d{2,4})\s*$", line)
        if cm:
            dates.append(cm.group(1))
            continue
        for val in re.findall(r":\s*([^\n]+)", line):
            val = val.strip()
            if re.match(r"^\d{1,2}[-/]\d{1,2}[-/]\d{2,4}$", val):
                dates.append(val)
            elif re.match(r"^\d{1,6}$", val):
                bill_candidates.append(val)
        if re.match(r"^\d{1,6}$", line):
            bill_candidates.append(line)

    for val in re.findall(r":\s*([^\n:]+?)(?=\s*:|\n|$)", block):
        val = val.strip()
        if re.match(r"^\d{1,2}[-/]\d{1,2}[-/]\d{2,4}$", val):
            dates.append(val)
        elif re.match(r"^\d{1,6}$", val):
            bill_candidates.append(val)

    if bill_candidates and not out["invoice_number"]:
        out["invoice_number"] = bill_candidates[0]

    if not dates:
        dates = re.findall(r"\b(\d{1,2}[-/]\d{1,2}[-/]\d{4})\b", search_text)

    seen_dates: List[str] = []
    for d in dates:
        if d not in seen_dates:
            seen_dates.append(d)

    if seen_dates:
        out["invoice_date"] = seen_dates[0]
        out["due_date"] = seen_dates[1] if len(seen_dates) > 1 else seen_dates[0]

    if not out["invoice_date"]:
        inv_m = re.search(
            r"Invoice\s+Detail[\s\S]{0,800}?(\d{1,2}[-/]\d{1,2}[-/]\d{2,4})",
            search_text,
            re.IGNORECASE,
        )
        if inv_m:
            out["invoice_date"] = inv_m.group(1)

    if not out["due_date"]:
        due_m = re.search(
            r"Due\s*Date[\s\S]{0,120}?(\d{1,2}[-/]\d{1,2}[-/]\d{2,4})",
            search_text,
            re.IGNORECASE,
        )
        if due_m:
            out["due_date"] = due_m.group(1)

    return out


def _mr_fashion(text: str, f: Dict) -> Dict:
    """CHANDNI app — M.R FASHION (Bill No / Date on separate lines, Qnty + Mtr + Rate)."""
    f["supplier_name"] = f.get("supplier_name") or _first_str([r"(M\.?\s*R\.?\s+FASHION)"], text)
    f["buyer_name"] = f.get("buyer_name") or _first_str([
        r"Details\s+of\s+Receiver/Billed\s+to:\s*\n\s*([A-Za-z][A-Za-z\s]+)",
        r"(GAYATRI\s+SAREE)",
    ], text)

    header = _chandni_header_fields(text)
    if header.get("invoice_number"):
        f["invoice_number"] = header["invoice_number"]
    if header.get("invoice_date"):
        f["invoice_date"] = header["invoice_date"]
    if header.get("due_date"):
        f["due_date"] = header["due_date"]

    tax_m = re.search(r"Taxable\s+Amount", text, re.IGNORECASE)
    if tax_m:
        chunk = text[tax_m.end() : tax_m.end() + 350]
        net_pos = chunk.lower().find("net amount")
        if net_pos > 0:
            chunk = chunk[:net_pos]
        amounts = [
            float(x.replace(",", ""))
            for x in re.findall(r"[\d,]+\.?\d{2}", chunk)
        ]
        net_total = f.get("total_amount")
        candidates = [
            a for a in amounts
            if a >= 5000 and (not net_total or abs(a - net_total) > 100)
        ]
        if candidates:
            f["taxable_amount"] = max(candidates)

    f["cgst_amount"] = f.get("cgst_amount") or _first_float([
        r"Cgst\s*@\s*[\d.]+%[\s\S]{0,80}?([\d,]+\.?\d{2})",
    ], text)
    f["sgst_amount"] = f.get("sgst_amount") or _first_float([
        r"Sgst\s*@\s*[\d.]+%[\s\S]{0,80}?([\d,]+\.?\d{2})",
    ], text)
    if f.get("cgst_amount") and f["cgst_amount"] < 100:
        f["cgst_amount"] = None
    if f.get("sgst_amount") and f["sgst_amount"] < 100:
        f["sgst_amount"] = None
    cgst_line = re.search(r"Cgst\s*@[\s\S]{0,120}?([\d,]+\.?\d{2})", text, re.I)
    sgst_line = re.search(r"Sgst\s*@[\s\S]{0,120}?([\d,]+\.?\d{2})", text, re.I)
    if cgst_line:
        v = float(cgst_line.group(1).replace(",", ""))
        if v >= 100:
            f["cgst_amount"] = v
    if sgst_line:
        v = float(sgst_line.group(1).replace(",", ""))
        if v >= 100:
            f["sgst_amount"] = v

    f["total_amount"] = f.get("total_amount") or _first_float([r"Net\s+Amount\s*:\s*([\d,]+\.?\d*)"], text)

    # Taxable fallback: Net − CGST − SGST (Chandni PDF often omits taxable line in text layer)
    total = f.get("total_amount")
    cgst = f.get("cgst_amount")
    sgst = f.get("sgst_amount")
    if not f.get("taxable_amount") and total and cgst and sgst:
        inferred = round(float(total) - float(cgst) - float(sgst), 2)
        if inferred > 1000:
            f["taxable_amount"] = inferred

    return f


def _suswaani_debit(text: str, f: Dict) -> Dict:
    f["supplier_name"] = f.get("supplier_name") or _first_str([r"(SHREE\s+SUSWAANI[^\n]*)"], text)
    f["buyer_name"] = f.get("buyer_name") or _first_str([
        r"M/s\.\s*:?\s*([A-Za-z][A-Za-z\s]+)",
        r"(MAHADEV\s+FASHION)",
    ], text)
    f["taxable_amount"] = f.get("taxable_amount") or _first_float([r"Sub\s+Total\s*([\d,]+\.?\d*)"], text)
    f["cgst_amount"] = f.get("cgst_amount") or _first_float([r"CGST\s+[\d.]+\s*%\s*([\d,]+\.?\d*)"], text)
    f["sgst_amount"] = f.get("sgst_amount") or _first_float([r"SGST\s+[\d.]+\s*%\s*([\d,]+\.?\d*)"], text)
    f["total_amount"] = f.get("total_amount") or _first_float([
        r"Grand\s+Total\s*([\d,]+\.?\d*)",
        r"Current\s+Amt\s*:\s*([\d,]+\.?\d*)",
    ], text)
    return f


def _gayatri_traders(text: str, f: Dict) -> Dict:
    f["supplier_name"] = f.get("supplier_name") or _first_str([r"(GAYATRI\s+TRADERS)"], text)
    f["buyer_name"] = f.get("buyer_name") or _first_str([
        r"Details\s+of\s+Receiver\(Billed\s+to\)\s*Invoice[^\n]*\n\s*([A-Za-z][A-Za-z\s]+)",
        r"(MAHALAXMI\s+SAREES)",
        r"(SURYA\s+NX)",
    ], text)
    f["taxable_amount"] = f.get("taxable_amount") or _first_float([
        r"Total\s+Rs\.?\s*:?\s*([\d,]+\.?\d*)",
        r"TaxableValue\s*:\s*([\d,]+\.?\d*)",
    ], text)
    f["cgst_amount"] = f.get("cgst_amount") or _first_float([r"\+?\s*CGST\s+[\d.]+\s*%\s*([\d,]+\.?\d*)"], text)
    f["sgst_amount"] = f.get("sgst_amount") or _first_float([r"\+?\s*SGST\s+[\d.]+\s*%\s*([\d,]+\.?\d*)"], text)
    f["total_amount"] = f.get("total_amount") or _first_float([
        r"Due\s+Date[^\d]*([\d,]+\.?\d{2,})",
        r"Total\s+Rs\.[^\d]*([\d,]+\.?\d{2})\s*$",
    ], text)
    return f


def _sagas_collection(text: str, f: Dict) -> Dict:
    f["supplier_name"] = f.get("supplier_name") or _first_str([r"(SAGAS\s+COLLECTION)"], text)
    f["buyer_name"] = f.get("buyer_name") or _first_str([
        r"Billed\s+To[^\n]*\n\s*([A-Za-z][A-Za-z\s]+)",
        r"(MUSKAN\s+COLLECTION)",
    ], text)
    f["taxable_amount"] = f.get("taxable_amount") or _first_float([
        r"Total\s+Amount\s+Before\s+Tax\s*([\d,]+\.?\d*)",
    ], text)
    f["cgst_amount"] = f.get("cgst_amount") or _first_float([r"CGST\s*\([\d.]+%\)\s*([\d,]+\.?\d*)"], text)
    f["sgst_amount"] = f.get("sgst_amount") or _first_float([r"SGST\s*\([\d.]+%\)\s*([\d,]+\.?\d*)"], text)
    f["total_amount"] = f.get("total_amount") or _first_float([r"NET\s+AMOUNT\s*([\d,]+\.?\d*)"], text)
    return f


def _balkrishna_debit(text: str, f: Dict) -> Dict:
    f["supplier_name"] = _first_str([r"(SHREE\s+BALKRUSHNA\s+CREATION)"], text) or f.get("supplier_name")
    f["buyer_name"] = _first_str([
        r"M/s\.\s*:?\s*([A-Za-z][A-Za-z ]+)",
        r"(MUSKAN\s+COLLECTION)",
        r"(MAHADEV\s+FASHION)",
        r"(SUNDHAMATA\s+SAREES)",
    ], text) or f.get("buyer_name")
    f["taxable_amount"] = f.get("taxable_amount") or _first_float([r"Taxable\s+Amount\s*([\d,]+\.?\d*)"], text)
    f["cgst_amount"] = f.get("cgst_amount") or _first_float([r"Central\s+Tax\s+[\d.]+\s*%\s*([\d,]+\.?\d*)"], text)
    f["sgst_amount"] = f.get("sgst_amount") or _first_float([r"State/UT\s+Tax\s+[\d.]+\s*%\s*([\d,]+\.?\d*)"], text)
    f["total_amount"] = f.get("total_amount") or _first_float([r"Grand\s+Total\s*([\d,]+\.?\d*)"], text)
    return f


def _shivalaxmi_grid(text: str, f: Dict) -> Dict:
    f["supplier_name"] = f.get("supplier_name") or _first_str([r"(SHIVALAXMI[^\n]*)"], text)
    f["buyer_name"] = f.get("buyer_name") or _first_str([
        r"Billed\s+to\s*\(Customer\):\s*([A-Za-z][A-Za-z\s]+)",
        r"(SAMBHAV\s+TEXTILE)",
    ], text)
    f["total_amount"] = f.get("total_amount") or _first_float([r"Net\s+Amount\s+Rs\.?\s*([\d,]+\.?\d*)"], text)
    return f


def _alakh_supplier(text: str, f: Dict) -> Dict:
    f["supplier_name"] = f.get("supplier_name") or _first_str([r"(ALAKH\s+INTERNATIONAL)"], text)
    f["buyer_name"] = f.get("buyer_name") or _first_str([
        r"(SHREE\s+GANAPATHI\s+TEXTILES)",
        r"Name\s*:\s*:?\s*([A-Za-z][A-Za-z\s]+)",
    ], text)
    f["igst_amount"] = f.get("igst_amount") or _first_float([r"IGST\s+[\d.]+%\s*([\d,]+\.?\d*)"], text)
    f["total_amount"] = f.get("total_amount") or _first_float([r"NET\s+AMOUNT\s*([\d,]+\.?\d*)"], text)
    return f


def _parse_expense_register(text: str, f: Dict) -> Dict:
    """
    Common parser for ALAKH INTERNATIONAL / generic expense registers.
    Layout: Header (company name, register type, till date, type)
    then: Row Labels | TAXABLE | GST | TOTAL VALUE
    then: vendor rows, sub-totals per vendor, dates and invoice numbers.
    Grand Total line gives overall totals.
    """
    lines = text.split('\n')

    # Extract company name from first meaningful line
    company = None
    register_type = None
    till_date = None
    doc_type_label = None

    for line in lines[:20]:
        line_s = line.strip()
        if not line_s or line_s.startswith('---'):
            continue
        if not company and len(line_s) > 4 and re.match(r'^[A-Z][A-Z\s&]+$', line_s):
            company = line_s
            continue
        # "EXPENSE REGISTER    TILL 25-02-2025" or "DYING & PRINTING REGISTERS"
        m_reg = re.search(r'([\w\s&]+REGISTER[S]?)\s+(?:TILL\s+(\d{1,2}[-/]\d{1,2}[-/]\d{4}))?', line_s, re.I)
        if m_reg:
            register_type = m_reg.group(1).strip()
            if m_reg.group(2):
                till_date = m_reg.group(2)
            continue
        m_till = re.search(r'TILL\s+(\d{1,2}[-/]\d{1,2}[-/]\d{4})', line_s, re.I)
        if m_till and not till_date:
            till_date = m_till.group(1)
            continue
        m_type = re.search(r'^TYPE\s+(.+)$', line_s, re.I)
        if m_type:
            doc_type_label = m_type.group(1).strip()
            continue

    if company and not f.get('supplier_name'):
        f['supplier_name'] = company
    if company and not f.get('buyer_name'):
        f['buyer_name'] = company  # Register belongs to this company

    # Detect column order from "Row Labels  TAXABLE  GST  TOTAL VALUE" header
    # Columns may appear in any order
    col_order = ['taxable', 'gst', 'total']  # default
    header_m = re.search(r'Row\s+Labels\s+([\w\s]+)', text, re.I)
    if header_m:
        header_cols = header_m.group(1).lower()
        cols = []
        if 'taxable' in header_cols:
            cols.append('taxable')
        if 'gst' in header_cols:
            cols.append('gst')
        if 'total' in header_cols:
            cols.append('total')
        if len(cols) == 3:
            col_order = cols

    # Grand Total → overall tax summary
    # Try inline: "Grand Total  971014.56  48549.42  1019563.98"
    grand_total_m = re.search(
        r'Grand\s+Total[\s\n]+([\d,]+\.?\d*)[\s\n]+([\d,]+\.?\d*)[\s\n]+([\d,]+\.?\d*)',
        text, re.I
    )
    if grand_total_m:
        nums = sorted([
            float(grand_total_m.group(1).replace(',', '')),
            float(grand_total_m.group(2).replace(',', '')),
            float(grand_total_m.group(3).replace(',', '')),
        ])
        # In a register: GST << TAXABLE < TOTAL (GST is always the smallest)
        # total = max, gst = min, taxable = total - gst
        total = nums[2]
        gst = nums[0]
        taxable = total - gst   # taxable_amount = grand_total - total_gst

        # Grand Total has columns: TAXABLE | GST | TOTAL VALUE
        # The invoice shows a single "GST" column — NOT CGST/SGST split.
        # We must NOT fabricate CGST/SGST values that don't exist in the document.
        f['taxable_amount'] = round(taxable, 2)   # Always override — Grand Total is authoritative
        f['total_amount'] = round(total, 2)
        # Clear any cgst/sgst that generic extractor may have wrongly set —
        # this register only has a combined GST column
        f['cgst_amount'] = None
        f['sgst_amount'] = None
        f['igst_amount'] = None
        # Store raw GST total for display (not split into cgst/sgst)
        f['_gst_total'] = round(gst, 2)
        # Signal to _fill_missing_tax_fields: do NOT infer CGST/SGST for this format
        f['_no_cgst_sgst'] = True

    # Invoice date = till date if found
    if till_date and not f.get('invoice_date'):
        f['invoice_date'] = till_date

    # Register type metadata
    if register_type or doc_type_label:
        f['_register_type'] = register_type or ''
        f['_register_subtype'] = doc_type_label or ''



    return f


def _line_expense_register(text: str) -> List[Dict]:
    """
    Extract vendor summary rows from expense/broker/printing register.
    Pattern: "VENDOR NAME    taxable   gst   total_value"
    followed by date rows and invoice number rows.
    We treat each top-level vendor block as one line item.
    """
    items = []
    seen = set()

    # Match vendor header lines: ALL CAPS company name followed by 3 numbers
    # e.g. "ADITYA ENTERPRISE    5000    900    5900"
    vendor_pattern = re.compile(
        r'^([A-Z][A-Z\s&./()]+?)\s{2,}([\d,]+\.?\d*)\s+([\d,]+\.?\d*)\s+([\d,]+\.?\d*)\s*$',
        re.M
    )
    for m in vendor_pattern.finditer(text):
        vendor = m.group(1).strip()
        # Skip header row and grand total
        if re.search(r'^(ROW\s+LABELS|GRAND\s+TOTAL|TAXABLE|TYPE)', vendor, re.I):
            continue
        if len(vendor) < 4:
            continue
        key = vendor.upper()[:40]
        if key in seen:
            continue
        seen.add(key)
        taxable = float(m.group(2).replace(',', ''))
        gst = float(m.group(3).replace(',', ''))
        total = float(m.group(4).replace(',', ''))
        items.append({
            'description': vendor,
            'taxable_amount': taxable,
            'gst_amount': gst,
            'amount': total,
            'quantity': None,
            'rate': None,
            'hsn_code': None,
        })

    return items


def _alakh_expense_register(text: str, f: Dict) -> Dict:
    """Handler for ALAKH INTERNATIONAL expense/broker/printing registers."""
    return _parse_expense_register(text, f)


def _generic_expense_register(text: str, f: Dict) -> Dict:
    """Handler for generic expense/purchase registers with Row Labels layout."""
    return _parse_expense_register(text, f)


def _parse_outstanding_report(text: str, f: Dict) -> Dict:
    """
    Parser for SALE OUTSTANDING REPORT - PARTY WISE documents.

    Layout (multi-page):
      Header:   Company name, GSTIN, address, report title, period
      Columns:  BillNo | BillDate | GrossAmt | AddLess | GSTAmt | TDSAmt | PaidAmt | GRAmt | Balance | Days | Narration
      Per party: PARTY: <name> (BAL: <amount> Dr.) ... individual bill rows ... TOTAL row
      Last line: GRAND TO  <count>  <gross>  <addless>  <gst>  <tds>  <paid>  <gramt>  <balance>  <days>

    Strategy:
      1. Extract company name + GSTIN from header
      2. Extract report period from title
      3. Extract printed date
      4. Parse GRAND TO/TOTAL row for overall financials
      5. Parse each PARTY: TOTAL row as a line item
    """
    # ── 1. Company + GSTIN from header (first 10 lines)
    header_lines = text.split('\n')[:20]
    company = None
    report_gstin = None
    for line in header_lines:
        line_s = line.strip()
        if not line_s or line_s.startswith('---') or line_s.startswith('==='):
            continue
        # GSTIN line
        gstin_m = re.search(r'GSTIN\s*:\s*([A-Z0-9]{15})', line_s, re.I)
        if gstin_m:
            report_gstin = gstin_m.group(1).upper()
            continue
        # Company name = ALL CAPS line that isn't a label
        if (not company and len(line_s) > 5
                and re.match(r'^[A-Z][A-Z\s&.]+$', line_s)
                and not re.search(r'(PAN|GSTIN|REPORT|PARTY|SALE)', line_s)):
            company = line_s.strip()
            continue

    if company:
        f['supplier_name'] = company
        # Clear any wrong buyer name set by generic extractor
        f['buyer_name'] = None
        f['buyer_gstin'] = None

    if report_gstin:
        f['supplier_gstin'] = report_gstin

    # ── 2. Report period  "SALE OUTSTANDING REPORT-PARTY WISE (01/04/2025 TO 15/12/2025)"
    period_m = re.search(
        r'OUTSTANDING\s+REPORT[^(]*\((\d{2}/\d{2}/\d{4})\s+TO\s+(\d{2}/\d{2}/\d{4})\)',
        text, re.I
    )
    if period_m:
        f['report_from_date'] = period_m.group(1)
        f['report_to_date'] = period_m.group(2)
        if not f.get('invoice_date'):
            f['invoice_date'] = period_m.group(2)   # use end-date as the report date

    # ── 3. Printed On date
    printed_m = re.search(r'Printed\s+On\s*:\s*(\d{2}/\d{2}/\d{4})', text, re.I)
    if printed_m:
        f['_printed_on'] = printed_m.group(1)
        if not f.get('invoice_date'):
            f['invoice_date'] = printed_m.group(1)

    # ── 4. GRAND TOTAL row
    # "GRAND TO  107  3833915.00  -9.25  191695.75  0.00  -621102.00  99582.00  4547140.00  144"
    grand_m = re.search(
        r'GRAND\s+TO(?:TAL)?\s+(\d+)\s+([\d,]+\.?\d*)\s+([-\d,]+\.?\d*)\s+([\d,]+\.?\d*)'
        r'\s+([\d,]+\.?\d*)\s+([-\d,]+\.?\d*)\s+([-\d,]+\.?\d*)\s+([\d,]+\.?\d*)',
        text, re.I
    )
    if grand_m:
        gross_amt = float(grand_m.group(2).replace(',', ''))
        gst_amt   = float(grand_m.group(4).replace(',', ''))
        balance   = float(grand_m.group(8).replace(',', ''))
        f['taxable_amount'] = round(gross_amt, 2)
        f['_gst_total']     = round(gst_amt, 2)
        f['total_amount']   = round(balance, 2)
        f['_bill_count']    = int(grand_m.group(1))
    else:
        # Fallback: just extract the balance from GRAND TO line
        grand_simple = re.search(r'GRAND\s+TO(?:TAL)?\s+[\d\s.,-]+?([\d,]+\.\d{2})\s*$', text, re.I | re.M)
        if grand_simple:
            f['total_amount'] = float(grand_simple.group(1).replace(',', ''))

    # ── 5. Clear fields the generic extractor wrongly set
    # Invoice number gets wrongly picked from balance amounts; clear it
    wrong_inv = f.get('invoice_number')
    if wrong_inv and str(wrong_inv).replace('.', '').isdigit() and float(str(wrong_inv)) > 10000:
        f['invoice_number'] = None   # large number is a balance, not invoice number

    # Do NOT compute CGST/SGST — this report has a single GSTAmt column
    f['cgst_amount'] = None
    f['sgst_amount'] = None
    f['igst_amount'] = None
    f['_no_cgst_sgst'] = True

    return f


def _line_outstanding_report(text: str) -> List[Dict]:
    """
    Extract party-wise TOTAL rows from a Sale Outstanding Report.
    Each TOTAL row looks like:
      TOTAL  <count>  <gross>  <addless>  <gst>  <tds>  <paid>  <gramt>  <balance>  <days>
    The PARTY name is on the line above the bills block.
    """
    items = []
    seen = set()

    # Extract all PARTY: NAME blocks followed eventually by TOTAL row
    # Pattern: "PARTY: ASHAPURA CREATION (BAL : 216658.00 Dr.) ..."
    party_pattern = re.compile(
        r'PARTY:\s*([A-Z][A-Z\s\-&./()]+?)\s*\(BAL\s*:\s*([\d,]+\.?\d*)\s*(Dr\.|Cr\.)',
        re.I
    )
    # Pattern for TOTAL row in the report:
    # "TOTAL  6  206340.00  -1.00  10317.00  0.00  0.00  0.00  216658.00  127"
    total_pattern = re.compile(
        r'(?:^|\n)TOTAL\s+(\d+)\s+([\d,]+\.?\d*)\s+([-\d,]+\.?\d*)\s+([\d,]+\.?\d*)'
        r'\s+([\d,]+\.?\d*)\s+([-\d,]+\.?\d*)\s+([-\d,]+\.?\d*)\s+([\d,]+\.?\d*)',
        re.I | re.M
    )

    # Find all party names and positions
    parties = [(m.start(), m.group(1).strip(), m.group(2), m.group(3)) for m in party_pattern.finditer(text)]
    totals  = [m for m in total_pattern.finditer(text)]

    for idx, (party_pos, party_name, bal_str, bal_dir) in enumerate(parties):
        # Find the TOTAL row that comes after this party
        next_party_pos = parties[idx + 1][0] if idx + 1 < len(parties) else len(text)
        party_totals = [t for t in totals if party_pos < t.start() < next_party_pos]
        if not party_totals:
            continue
        # Use the last TOTAL row in this party's section
        t = party_totals[-1]
        key = party_name.upper()[:40]
        if key in seen:
            continue
        seen.add(key)

        gross_amt = float(t.group(2).replace(',', ''))
        gst_amt   = float(t.group(4).replace(',', ''))
        balance   = float(t.group(8).replace(',', ''))

        items.append({
            'description': party_name,
            'quantity': int(t.group(1)),     # bill count
            'amount': balance,               # outstanding balance
            'taxable_amount': gross_amt,
            'gst_amount': gst_amt,
            'hsn_code': None,
            'rate': None,
        })

    return items


def _alakh_sale_outstanding_report(text: str, f: Dict) -> Dict:
    """Handler for ALAKH INTERNATIONAL multi-page Sale Outstanding Report."""
    return _parse_outstanding_report(text, f)


def _generic_outstanding_report(text: str, f: Dict) -> Dict:
    """Handler for generic Sale/Purchase Outstanding Reports."""
    return _parse_outstanding_report(text, f)


_HANDLERS = {
    "gayatri_box": _gayatri_box,
    "komal_prints": _komal_prints,
    "muskan_glued": _muskan_glued,
    "shivam_fashion": _shivam_fashion,
    "mr_fashion_chandni": _mr_fashion,
    "suswaani_debit": _suswaani_debit,
    "gayatri_traders": _gayatri_traders,
    "sagas_collection": _sagas_collection,
    "balkrishna_debit": _balkrishna_debit,
    "shivalaxmi_grid": _shivalaxmi_grid,
    "alakh_supplier_invoice": _alakh_supplier,
    "alakh_expense_register": _alakh_expense_register,
    "generic_expense_register": _generic_expense_register,
    "alakh_sale_outstanding_report": _alakh_sale_outstanding_report,
    "generic_outstanding_report": _generic_outstanding_report,
}


# --- Line item handlers ---


def _parse_lines(patterns: List[str], text: str) -> List[Dict]:
    items = []
    seen = set()
    for pat in patterns:
        for m in re.finditer(pat, text, re.I | re.M):
            g = m.groups()
            sr_no = desc = hsn = qty = rate = amt = None
            if len(g) == 7:
                sr_no, desc, hsn, qty, meters, rate, amt = g
            elif len(g) == 6:
                sr_no, desc, hsn, qty, rate, amt = g
                meters = None
            elif len(g) == 5:
                desc, hsn, qty, rate, amt = g[0], g[1], g[2], g[3], g[4]
                sr_no, meters = None, None
            else:
                continue
            if not desc or len(desc) < 2:
                continue
            key = _norm_item_key({"description": desc, "hsn_code": hsn})
            if key in seen:
                continue
            seen.add(key)
            desc_clean = re.sub(r"([a-z])([A-Z])", r"\1 \2", desc.strip())
            row = {
                "sr_no": str(sr_no).strip() if sr_no else None,
                "description": desc_clean,
                "hsn_code": str(hsn).strip(),
                "quantity": str(qty).replace(",", "").strip(),
                "rate": str(rate).replace(",", "").strip(),
                "amount": str(amt).replace(",", "").strip(),
            }
            if meters is not None:
                row["meters"] = str(meters).replace(",", "").strip()
                row["mts"] = row["meters"]
            items.append(row)
    return items


def _line_gayatri(text: str) -> List[Dict]:
    return _parse_lines([
        r"(?:^|\n)\s*(\d+)\s*[|│]?\s*(SAREE\s+[A-Za-z0-9\-,/\.]+?)\s+(\d{6})\s+(\d+)\s+(?:[\d.]+\s+)?([\d.]+)\s+([\d.]+)",
        r"(?:^|\n)\s*(\d+)\s+(SAREE\s+[A-Za-z0-9\-,/\.]+?)\s+(\d{6})\s+(\d+)\s+(?:[\d.]+\s+)?([\d.]+)\s+([\d.]+)",
    ], text)


def _line_komal(text: str) -> List[Dict]:
    items = []
    # Match lines like:
    # 1 DIAMOND CITY                    BAG PHOT      120     6.30   756.00    380.00    45600.00
    pattern = r"(?:^|\n)\s*(\d+)\s+([A-Za-z0-9\s\-()]+?)(?:\s+(BAG\s+PHOT|BAG|PHOT|BOX|PKT|ROLL|ROLLS|LUMP|LUMPS|CASE|PCS|BUNDLE|BUNDLES))?\s+(\d+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)"
    for m in re.finditer(pattern, text, re.I):
        sr_no, desc, pack, pcs, cut, mts, rate, amt = m.groups()
        if not desc or len(desc) < 2:
            continue
        
        # Clean description
        desc_clean = re.sub(r"\s+", " ", desc.strip())
        
        # Check if next line contains description extension, like (DARK)
        post_match = text[m.end():m.end() + 200]
        next_line_match = re.match(r"^\s*\n\s*(\([A-Z\s\-]+\))", post_match, re.I)
        if next_line_match:
            desc_clean += " " + next_line_match.group(1)
            
        items.append({
            "sr_no": sr_no.strip(),
            "description": desc_clean,
            "quantity": pcs.strip(), # Quantity should be PCS (120)
            "meters": mts.strip(),
            "mts": mts.strip(),
            "rate": rate.strip(),
            "amount": amt.strip(),
        })
    return items


def _line_muskan(text: str) -> List[Dict]:
    return _parse_lines([
        # CHANDRALOK: 1. ORGANZA JAQUARD 540710 2 172.00 150.00 M25800.00
        r"(\d+)\.\s*([A-Za-z][A-Za-z\s]+?)\s+(\d{6})\s+(\d+)\s+([\d.]+)\s+([\d.]+)\s+M?([\d.]+)",
        r"(\d+)\.\s*([A-Za-z][A-Za-z0-9\-]+)\s+(\d{4})\s+([\d.]+)\s+(\d+)\s+([\d.]+)\s+([\d.]+)P?([\d.]+)",
        r"(\d+)\.\s*([A-Za-z][A-Za-z0-9\-]+)\s+(\d{4,8})\s+([\d.]+)\s+(\d+)\s+([\d.]+)",
    ], text)


def _line_shivam(text: str) -> List[Dict]:
    return _parse_lines([
        r"(?:^|\n)\s*(\d+)\s+([A-Za-z][A-Za-z0-9\s+]+?)\s+(\d{6})\s+(\d+)\s+[\d.]+\s+[\d.]+\s+\d+\s+P\s+([\d.]+)",
    ], text)


def _line_mr_fashion(text: str) -> List[Dict]:
    return _parse_lines([
        # 1 SHARMILI PRINT / SHARMILIPRINT 540710 440 2200.00 Mtr 24.50 53900.00
        r"(\d+)\s+([A-Za-z][A-Za-z0-9]+(?:\s+[A-Za-z]+)?)\s+(\d{6})\s+(\d+)\s+([\d,.]+)\s+Mtr\s+([\d,.]+)\s+([\d,.]+)",
    ], text)


def _line_suswaani(text: str) -> List[Dict]:
    return _parse_lines([
        r"(?:^|\n)\s*(\d+)\s+([A-Za-z][A-Za-z\s()]+?)\s+(\d{4})\s+([\d.]+)\s+KGS\s+([\d.]+)\s+([\d.]+)",
    ], text)


def _line_gayatri_traders(text: str) -> List[Dict]:
    return _parse_lines([
        r"(?:^|\n)\s*(\d+)\s+([A-Za-z][A-Za-z\s\-]+?)\s+(\d{4})\s+([\d.]+)\s+Kgs\s+([\d.]+)\s+([\d.]+)",
        r"(?:^|\n)\s*(\d+)\s+([A-Za-z][A-Za-z\s\-]+?)\s+(\d{4})\s+([\d.]+)\s+([\d.]+)",
    ], text)


def _line_sagas(text: str) -> List[Dict]:
    return _parse_lines([
        r"(?:^|\n)\s*(\d+)\s+(PACKING\s+[A-Za-z\s]+)\s+(\d{4})\s+([\d.]+)\s+(\d+)\s+([\d.]+)\s+([\d.]+)",
    ], text)


def _line_balkrishna(text: str) -> List[Dict]:
    # Match vertically-aligned columns sequence: sr_no, description, qty, hsn, rate, tax_pct, amount
    pattern = r"(?:^|\n)\s*(\d+)\s+([A-Za-z][A-Za-z\s]+?)\s+(\d+)\s+(\d{4,8})\s+([\d.]+)\s+[\d.]+\s+([\d.]+)"
    items = []
    seen = set()
    for m in re.finditer(pattern, text, re.I):
        g = m.groups()
        sr_no, desc, qty, hsn, rate, amt = g
        key = (desc.strip().upper(), hsn)
        if key in seen:
            continue
        seen.add(key)
        items.append({
            "sr_no": sr_no.strip(),
            "description": desc.strip(),
            "hsn_code": hsn.strip(),
            "quantity": qty.strip(),
            "rate": rate.strip(),
            "amount": amt.strip()
        })
    return items


def _line_shivalaxmi(text: str) -> List[Dict]:
    return _parse_lines([
        r"(?:^|\n)\s*(\d+)\s+([A-Za-z0-9\s\-]+?)\s+(\d{6})\s+(\d+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)",
    ], text)


def _line_items_universal(text: str) -> List[Dict]:
    return _parse_lines([
        r"(?:^|\n)\s*(\d+)\s*[|│\.]?\s*([A-Za-z][A-Za-z0-9\s\-,/\.]+?)\s+(\d{4,8})\s+(\d+)\s+[\d.]+\s+([\d,]+\.?\d+)\s+([\d,]+\.?\d+)",
        r"(SAREE\s+[A-Za-z0-9\-,/\.]+?)\s+(\d{6})\s+(\d+)\s+([\d,]+\.?\d+)\s+([\d,]+\.?\d+)",
    ], text)


_LINE_HANDLERS = {
    "gayatri_box": _line_gayatri,
    "komal_prints": _line_komal,
    "muskan_glued": _line_muskan,
    "shivam_fashion": _line_shivam,
    "mr_fashion_chandni": _line_mr_fashion,
    "suswaani_debit": _line_suswaani,
    "gayatri_traders": _line_gayatri_traders,
    "sagas_collection": _line_sagas,
    "balkrishna_debit": _line_balkrishna,
    "shivalaxmi_grid": _line_shivalaxmi,
    "alakh_expense_register": _line_expense_register,
    "generic_expense_register": _line_expense_register,
    "alakh_sale_outstanding_report": _line_outstanding_report,
    "generic_outstanding_report": _line_outstanding_report,
}
