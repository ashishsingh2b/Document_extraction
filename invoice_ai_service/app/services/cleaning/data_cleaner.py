"""Data cleaning layer for OCR error correction and text normalization."""

import logging
import re
from typing import Dict, Any, List, Optional
from app.models.invoice import RawExtractedData, CleanedData

logger = logging.getLogger(__name__)

OCR_COMMON_ERRORS = {
    "0": {"O", "o", "Q", "D"},
    "1": {"l", "I", "|"},
    "2": {"Z"},
    "5": {"S", "s"},
    "6": {"G"},
    "8": {"B"},
    "9": {"g"},
}

GSTIN_CLEAN_PATTERN = re.compile(r"[^A-Z0-9]")
AMOUNT_CLEAN_PATTERN = re.compile(r"[^\d.]")
WHITESPACE_PATTERN = re.compile(r"\s+")


def correct_gstin_ocr(gstin: str) -> str:
    gstin = gstin.upper().strip()
    if len(gstin) != 15:
        return gstin
    
    # Expected type for each position: 'D' for Digit, 'L' for Letter, 'A' for Alphanumeric
    expected_types = [
        'D', 'D',                  # State code (2 digits)
        'L', 'L', 'L', 'L', 'L',     # PAN chars (5 letters)
        'D', 'D', 'D', 'D',        # PAN digits (4 digits)
        'L',                       # PAN char (1 letter)
        'A',                       # Entity code (1 letter/digit)
        'L',                       # Z (1 letter)
        'A'                        # Checksum (1 letter/digit)
    ]
    
    chars = list(gstin)
    to_digit = {
        'S': '5', 's': '5', 'O': '0', 'o': '0', 'D': '0', 'Q': '0',
        'I': '1', 'l': '1', '|': '1', 'Z': '2', 'z': '2', 'G': '6',
        'g': '9', 'B': '8', 'A': '4'
    }
    to_letter = {
        '5': 'S', '0': 'O', '1': 'I', '2': 'Z', '6': 'G', '8': 'B', '9': 'G'
    }
    
    for i in range(15):
        exp = expected_types[i]
        char = chars[i]
        
        if exp == 'D' and not char.isdigit():
            if char in to_digit:
                chars[i] = to_digit[char]
        elif exp == 'L' and not char.isalpha():
            if i == 13:  # Position 14 must be Z
                chars[i] = 'Z'
            elif char in to_letter:
                chars[i] = to_letter[char]
            else:
                if i == 13:
                    chars[i] = 'Z'
        elif i == 13 and char != 'Z':
            chars[i] = 'Z'
            
    return "".join(chars)


def clean_gstin(raw: str) -> Optional[str]:
    raw = raw.upper().strip()
    raw = GSTIN_CLEAN_PATTERN.sub("", raw)
    if len(raw) == 15:
        # Correct OCR errors
        raw = correct_gstin_ocr(raw)
        return raw
    return None


def clean_amount(raw: Any) -> Optional[float]:
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        return float(raw)
    cleaned = AMOUNT_CLEAN_PATTERN.sub("", str(raw).replace(",", ""))
    try:
        val = float(cleaned)
        return val if val > 0 else None
    except ValueError:
        return None


def clean_invoice_number(raw: str) -> Optional[str]:
    if not raw:
        return None
    raw = raw.strip().upper()
    raw = re.sub(r"\s+", "", raw)
    if re.search(r"\d", raw) and len(raw) <= 30:
        return raw
    return None


def clean_date(raw: str) -> Optional[str]:
    if not raw:
        return None
    raw = raw.strip()
    match = re.search(r"(\d{1,2})[-/](\d{1,2})[-/](\d{2,4})", raw)
    if match:
        d, m, y = match.group(1), match.group(2), match.group(3)
        if len(y) == 2:
            y = "20" + y if int(y) <= 49 else "19" + y
        return f"{d.zfill(2)}-{m.zfill(2)}-{y}"
    return None


def clean_party_name(raw: str) -> Optional[str]:
    if not raw or len(raw) < 3:
        return None
    raw = WHITESPACE_PATTERN.sub(" ", raw.strip())
    raw = re.sub(r"[|│┬├─┤└┘]", "", raw)
    raw = re.sub(r"\s*:\s*$", "", raw)
    if len(raw) < 3:
        return None
    return raw


def clean_text_line(text: str) -> str:
    text = re.sub(r"[│┬├─┤└┘┌┐┴┼═║╒╓╔╕╖╗╘╙╚╛╜╝╞╟╠╡╢╣╤╥╦╧╨╩╪╫╬▬▭▮▯]", "", text)
    text = re.sub(r"[–—−]", "-", text)
    text = re.sub(r"[•·]", ",", text)
    text = WHITESPACE_PATTERN.sub(" ", text)
    # Fix OCR split floats (e.g. "380. 00" -> "380.00")
    text = re.sub(r'(\d+)\.\s+(\d{1,2})\b', r'\1.\2', text)
    return text.strip()


def clean_line_item(item: Dict[str, Any]) -> Dict[str, Any]:
    cleaned = {}
    for key, value in item.items():
        if isinstance(value, str):
            cleaned[key] = clean_text_line(value)
        else:
            cleaned[key] = value
    if cleaned.get("hsn_code"):
        hsn = re.sub(r"[^0-9A-Za-z]", "", str(cleaned["hsn_code"]))
        cleaned["hsn_code"] = hsn if hsn else None
    if cleaned.get("amount"):
        cleaned["amount"] = clean_amount(cleaned["amount"])
    if cleaned.get("rate"):
        cleaned["rate"] = clean_amount(cleaned["rate"])
    if cleaned.get("quantity"):
        try:
            cleaned["quantity"] = float(WHITESPACE_PATTERN.sub("", str(cleaned["quantity"])))
        except (ValueError, TypeError):
            pass
    return cleaned


class DataCleaner:
    def clean_raw_data(self, raw: RawExtractedData) -> CleanedData:
        raw_text = raw.raw_text or ""
        raw_text = clean_text_line(raw_text)

        clean_fields: Dict[str, Any] = {}
        for key, value in raw.raw_fields.items():
            if value is None:
                continue
            clean_fields[key] = self._clean_field(key, value)

        clean_tables = [clean_line_item(it) for it in raw.raw_tables]

        return CleanedData(clean_fields=clean_fields, clean_tables=clean_tables)

    def clean_extracted_fields(self, fields: Dict[str, Any]) -> Dict[str, Any]:
        cleaned = {}
        for key, value in fields.items():
            cleaned[key] = self._clean_field(key, value)
        if "items" in fields and isinstance(fields["items"], list):
            cleaned["items"] = [clean_line_item(it) for it in fields["items"]]
        return cleaned

    def _clean_field(self, key: str, value: Any) -> Any:
        if value is None or value == "":
            return None
        if key in ("supplier_gstin", "buyer_gstin"):
            return clean_gstin(str(value))
        if key in ("total_amount", "taxable_amount", "cgst_amount", "sgst_amount", "igst_amount"):
            return clean_amount(value)
        if key == "invoice_number":
            return clean_invoice_number(str(value))
        if key in ("invoice_date", "due_date"):
            return clean_date(str(value))
        if key in ("supplier_name", "buyer_name"):
            return clean_party_name(str(value))
        return value


data_cleaner = DataCleaner()
