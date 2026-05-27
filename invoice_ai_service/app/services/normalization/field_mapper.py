"""Field normalization layer — maps extracted keys to standard schema names."""

import json
import logging
import os
from typing import Dict, Any, List, Optional

from app.models.invoice import CleanedData, NormalizedData

logger = logging.getLogger(__name__)

ALIAS_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "config", "alias_dictionary.json")


def _load_aliases() -> Dict[str, List[str]]:
    try:
        with open(ALIAS_PATH, encoding="utf-8") as f:
            data = json.load(f)
        return data
    except Exception as e:
        logger.warning(f"Failed to load alias dictionary: {e}")
        return {}


_ALIASES: Dict[str, List[str]] = _load_aliases()

_STANDARD_TO_ALIAS: Dict[str, str] = {}
for standard, aliases in _ALIASES.items():
    for alias in aliases:
        normalized_alias = alias.lower().replace(" ", "_").replace("-", "_")
        _STANDARD_TO_ALIAS[normalized_alias] = standard

_FIELD_MAP: Dict[str, str] = {
    "invoice_no": "invoice_number",
    "inv_no": "invoice_number",
    "inv_number": "invoice_number",
    "bill_no": "invoice_number",
    "bill_number": "invoice_number",
    "inv_date": "invoice_date",
    "bill_date": "invoice_date",
    "due_date": "due_date",
    "payment_due": "due_date",
    "supplier": "supplier_name",
    "seller": "supplier_name",
    "vendor": "supplier_name",
    "seller_name": "supplier_name",
    "vendor_name": "supplier_name",
    "supplier_gst": "supplier_gstin",
    "seller_gst": "supplier_gstin",
    "vendor_gstin": "supplier_gstin",
    "buyer": "buyer_name",
    "customer": "buyer_name",
    "consignee": "buyer_name",
    "buyer_gst": "buyer_gstin",
    "customer_gstin": "buyer_gstin",
    "consignee_gstin": "buyer_gstin",
    "total": "total_amount",
    "grand_total": "total_amount",
    "net_amount": "total_amount",
    "invoice_value": "total_amount",
    "amount_payable": "total_amount",
    "taxable_value": "taxable_amount",
    "taxable_amt": "taxable_amount",
    "subtotal": "taxable_amount",
    "sub_total": "taxable_amount",
    "cgst": "cgst_amount",
    "central_gst": "cgst_amount",
    "sgst": "sgst_amount",
    "state_gst": "sgst_amount",
    "igst": "igst_amount",
    "integrated_gst": "igst_amount",
    "description": "item_name",
    "particulars": "item_name",
    "product": "item_name",
    "product_name": "item_name",
    "item": "item_name",
    "goods_description": "item_name",
    "qty": "quantity",
    "nos": "quantity",
    "pcs": "quantity",
    "pieces": "quantity",
    "units": "quantity",
    "rate": "unit_price",
    "unit_price": "unit_price",
    "price": "unit_price",
    "amount": "line_total",
    "line_total": "line_total",
    "item_total": "line_total",
    "value": "line_total",
    "hsn": "hsn_code",
    "sac": "sac_code",
    "hsn_sac": "hsn_code",
}

_LINE_ITEM_FIELD_MAP: Dict[str, str] = {
    "description": "description",
    "particulars": "description",
    "product": "description",
    "item_name": "description",
    "item": "description",
    "name": "description",
    "qty": "quantity",
    "quantity": "quantity",
    "nos": "quantity",
    "pcs": "quantity",
    "pieces": "quantity",
    "rate": "rate",
    "unit_price": "rate",
    "price": "rate",
    "amount": "amount",
    "line_total": "amount",
    "total": "amount",
    "value": "amount",
    "hsn": "hsn_code",
    "sac": "hsn_code",
    "hsn_code": "hsn_code",
    "hsn/sac": "hsn_code",
    "cgst_rate": "cgst_rate",
    "sgst_rate": "sgst_rate",
    "igst_rate": "igst_rate",
    "mts": "mts",
    "meters": "mts",
    "metres": "mts",
}


def normalize_field_name(raw_key: str) -> str:
    key = raw_key.lower().replace(" ", "_").replace("-", "_")
    if key in _STANDARD_TO_ALIAS:
        return _STANDARD_TO_ALIAS[key]
    if key in _FIELD_MAP:
        return _FIELD_MAP[key]
    return raw_key


def normalize_line_item_field(raw_key: str) -> str:
    key = raw_key.lower().replace(" ", "_").replace("-", "_")
    if key in _LINE_ITEM_FIELD_MAP:
        return _LINE_ITEM_FIELD_MAP[key]
    return raw_key


def normalize_line_item(item: Dict[str, Any]) -> Dict[str, Any]:
    normalized = {}
    for k, v in item.items():
        nk = normalize_line_item_field(k)
        normalized[nk] = v
    return normalized


class FieldMapper:
    def normalize(self, cleaned: CleanedData) -> NormalizedData:
        normalized_fields: Dict[str, Any] = {}
        for k, v in cleaned.clean_fields.items():
            nk = normalize_field_name(k)
            normalized_fields[nk] = v

        normalized_items = [normalize_line_item(it) for it in cleaned.clean_tables]

        return NormalizedData(
            normalized_fields=normalized_fields,
            normalized_items=normalized_items,
        )

    def normalize_line_item(self, item: Dict[str, Any]) -> Dict[str, Any]:
        return normalize_line_item(item)

    def normalize_fields(self, fields: Dict[str, Any]) -> Dict[str, Any]:
        normalized: Dict[str, Any] = {}
        for k, v in fields.items():
            nk = normalize_field_name(k)
            normalized[nk] = v
        if "items" in fields and isinstance(fields["items"], list):
            normalized["items"] = [normalize_line_item(it) for it in fields["items"]]
        return normalized


field_mapper = FieldMapper()
