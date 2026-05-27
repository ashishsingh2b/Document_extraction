"""Indian GST Compliance Engine — validates, calculates, and classifies."""

import json
import logging
import os
import re
from typing import Dict, Any, List, Optional, Tuple
from decimal import Decimal, ROUND_HALF_UP

from app.core.constants import (
    GST_RATES, TDS_THRESHOLD_INR, TCS_THRESHOLD_INR,
    TDS_RATE, TCS_RATE, EINVOICE_TURNOVER_THRESHOLD,
    InvoiceType,
)
from app.models.invoice import ComplianceData

logger = logging.getLogger(__name__)

STATE_CODES_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "config", "state_codes.json")
HSN_SAC_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "config", "hsn_sac_master.json")


def _load_json(path: str) -> Dict:
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.warning(f"Failed to load {path}: {e}")
        return {}


_STATE_DATA = _load_json(STATE_CODES_PATH)
_HSN_SAC_DATA = _load_json(HSN_SAC_PATH)

GSTIN_PATTERN = re.compile(r"^(\d{2})([A-Z]{5})(\d{4})([A-Z])([A-Z\d])([Z])([A-Z\d])$")


def validate_gstin(gstin: Optional[str]) -> Tuple[bool, str]:
    if not gstin:
        return False, "GSTIN is empty"
    gstin = gstin.upper().strip()
    match = GSTIN_PATTERN.match(gstin)
    if not match:
        return False, "Invalid GSTIN format"
    state_code, pan, _entity, _alpha, _check, _z, _last = match.groups()
    if state_code not in _STATE_DATA.get("states", {}):
        return False, f"Invalid state code: {state_code}"
    if _z != "Z":
        return False, "Invalid GSTIN: position 16 must be Z"
    return True, "Valid GSTIN"


def get_state_from_code(code: str) -> Optional[str]:
    return _STATE_DATA.get("states", {}).get(code)


def get_state_code(gstin: str) -> Optional[str]:
    if not gstin:
        return None
    match = GSTIN_PATTERN.match(gstin.upper().strip())
    if match:
        return match.group(1)
    return None


def get_state_name_from_gstin(gstin: str) -> Optional[str]:
    code = get_state_code(gstin)
    if code:
        return get_state_from_code(code)
    return None


def validate_hsn_sac(code: Optional[str]) -> Tuple[bool, str, str]:
    if not code:
        return False, "", "Code is empty"
    code = re.sub(r"[^0-9A-Za-z]", "", str(code).upper())
    if code in _HSN_SAC_DATA.get("hsn_codes", {}):
        return True, "hsn", _HSN_SAC_DATA["hsn_codes"][code]
    if code in _HSN_SAC_DATA.get("sac_codes", {}):
        return True, "sac", _HSN_SAC_DATA["sac_codes"][code]
    return False, "", "Code not found in master data"


def determine_place_of_supply(supplier_gstin: Optional[str], buyer_gstin: Optional[str]) -> Dict[str, Any]:
    supplier_state = get_state_code(supplier_gstin) if supplier_gstin else None
    buyer_state = get_state_code(buyer_gstin) if buyer_gstin else None
    supplier_state_name = get_state_from_code(supplier_state) if supplier_state else None
    buyer_state_name = get_state_from_code(buyer_state) if buyer_state else None

    if supplier_state and buyer_state:
        if supplier_state == buyer_state:
            tax_type = "CGST+SGST"
        else:
            tax_type = "IGST"
    elif supplier_state and not buyer_state:
        tax_type = "CGST+SGST"
    else:
        tax_type = "IGST"

    return {
        "supplier_state_code": supplier_state,
        "supplier_state_name": supplier_state_name,
        "buyer_state_code": buyer_state,
        "buyer_state_name": buyer_state_name,
        "tax_type": tax_type,
        "intra_state": tax_type == "CGST+SGST",
        "inter_state": tax_type == "IGST",
    }


def find_gst_rate(taxable_amount: Optional[float], cgst_amount: Optional[float],
                  sgst_amount: Optional[float], igst_amount: Optional[float]) -> Optional[float]:
    if taxable_amount and taxable_amount > 0:
        if cgst_amount and cgst_amount > 0:
            rate_pct = round((cgst_amount / taxable_amount) * 100, 2)
            combined_rate = round(rate_pct * 2, 0)
            if combined_rate in GST_RATES:
                return combined_rate
        if sgst_amount and sgst_amount > 0:
            rate_pct = round((sgst_amount / taxable_amount) * 100, 2)
            combined_rate = round(rate_pct * 2, 0)
            if combined_rate in GST_RATES:
                return combined_rate
        if igst_amount and igst_amount > 0:
            rate_pct = round((igst_amount / taxable_amount) * 100, 2)
            if rate_pct in GST_RATES:
                return rate_pct
    return None


def calculate_tax(taxable_amount: float, gst_rate: float, tax_type: str = "CGST+SGST") -> Dict[str, float]:
    if tax_type == "IGST":
        igst = round(taxable_amount * gst_rate / 100, 2)
        return {"igst_amount": igst, "cgst_amount": 0, "sgst_amount": 0}
    else:
        half_rate = gst_rate / 2
        cgst = round(taxable_amount * half_rate / 100, 2)
        sgst = round(taxable_amount * half_rate / 100, 2)
        return {"cgst_amount": cgst, "sgst_amount": sgst, "igst_amount": 0}


def check_tds_applicable(total_amount: Optional[float]) -> Tuple[bool, float]:
    if total_amount and total_amount >= TDS_THRESHOLD_INR:
        tds = round(total_amount * TDS_RATE, 2)
        return True, tds
    return False, 0


def check_tcs_applicable(total_amount: Optional[float]) -> Tuple[bool, float]:
    if total_amount and total_amount >= TCS_THRESHOLD_INR:
        tcs = round(total_amount * TCS_RATE, 2)
        return True, tcs
    return False, 0


def detect_rcm(text: str) -> Tuple[bool, str]:
    text_lower = text.lower()
    rcm_keywords = [
        "reverse charge", "rcm applicable", "rcm",
        "reverse charge mechanism", "tax payable under reverse charge",
        "unregistered dealer", "composition dealer",
    ]
    for kw in rcm_keywords:
        if kw in text_lower:
            return True, f"RCM detected via keyword: {kw}"
    return False, "RCM not applicable"


def classify_invoice(text: str, fields: Dict[str, Any]) -> str:
    text_lower = text.lower()
    if "debit note" in text_lower or "debit note" in text_lower:
        return InvoiceType.DEBIT_NOTE
    if "credit note" in text_lower or "credit note" in text_lower:
        return InvoiceType.CREDIT_NOTE
    if "export" in text_lower and "invoice" in text_lower:
        return InvoiceType.EXPORT_INVOICE
    if "bill of supply" in text_lower:
        return InvoiceType.BILL_OF_SUPPLY
    if fields.get("igst_amount") and fields["igst_amount"] > 0:
        return InvoiceType.TAX_INVOICE
    if fields.get("cgst_amount") and fields["cgst_amount"] > 0:
        return InvoiceType.TAX_INVOICE
    if "tax invoice" in text_lower:
        return InvoiceType.TAX_INVOICE
    return InvoiceType.TAX_INVOICE


def check_einvoice_applicable(total_amount: Optional[float]) -> bool:
    if total_amount and total_amount >= EINVOICE_TURNOVER_THRESHOLD:
        return True
    return False


class ComplianceEngine:
    def validate(self, normalized_fields: Dict[str, Any], raw_text: str = "") -> Dict[str, Any]:
        supplier_gstin = normalized_fields.get("supplier_gstin")
        buyer_gstin = normalized_fields.get("buyer_gstin")
        total_amount = normalized_fields.get("total_amount")
        taxable_amount = normalized_fields.get("taxable_amount")
        cgst = normalized_fields.get("cgst_amount")
        sgst = normalized_fields.get("sgst_amount")
        igst = normalized_fields.get("igst_amount")

        gstin_valid, gstin_msg = validate_gstin(supplier_gstin)
        buyer_gstin_valid, buyer_gstin_msg = validate_gstin(buyer_gstin)

        pos_result = determine_place_of_supply(supplier_gstin, buyer_gstin)

        gst_rate = find_gst_rate(taxable_amount, cgst, sgst, igst)

        tds_applicable, tds_amount = check_tds_applicable(total_amount)
        tcs_applicable, tcs_amount = check_tcs_applicable(total_amount)
        rcm_applicable, rcm_reason = detect_rcm(raw_text)

        invoice_type = classify_invoice(raw_text, normalized_fields)
        einvoice_applicable = check_einvoice_applicable(total_amount)

        line_item_validations = []
        items = normalized_fields.get("items", [])
        for item in items:
            hsn = item.get("hsn_code")
            hsn_valid, hsn_type, hsn_desc = validate_hsn_sac(hsn)
            line_item_validations.append({
                "description": item.get("description", ""),
                "hsn_code": hsn,
                "hsn_valid": hsn_valid,
                "hsn_type": hsn_type,
                "hsn_description": hsn_desc,
            })

        hsn_valid_overall = all(v["hsn_valid"] for v in line_item_validations) if line_item_validations else False

        compliance_data = ComplianceData(
            gstin_valid=gstin_valid,
            hsn_sac_valid=hsn_valid_overall,
            place_of_supply_code=pos_result["buyer_state_code"] or pos_result["supplier_state_code"],
            tax_type=pos_result["tax_type"],
            tds_applicable=tds_applicable,
            tcs_applicable=tcs_applicable,
            rcm_applicable=rcm_applicable,
            einvoice_applicable=einvoice_applicable,
        )

        return {
            "compliance_data": compliance_data,
            "gstin_validation": {
                "supplier_gstin": supplier_gstin,
                "supplier_valid": gstin_valid,
                "supplier_message": gstin_msg,
                "buyer_gstin": buyer_gstin,
                "buyer_valid": buyer_gstin_valid,
                "buyer_message": buyer_gstin_msg,
            },
            "place_of_supply": pos_result,
            "gst_rate_detected": gst_rate,
            "tds": {"applicable": tds_applicable, "amount": tds_amount},
            "tcs": {"applicable": tcs_applicable, "amount": tcs_amount},
            "rcm": {"applicable": rcm_applicable, "reason": rcm_reason},
            "invoice_type": invoice_type,
            "einvoice_applicable": einvoice_applicable,
            "line_item_validations": line_item_validations,
        }


compliance_engine = ComplianceEngine()
