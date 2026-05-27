"""ERP Schema Mapping — converts normalized data into ERP-ready JSON."""

import logging
from typing import Dict, Any, List, Optional
from decimal import Decimal, ROUND_HALF_UP
from datetime import datetime

from app.models.schemas import (
    PartyDetails, InvoiceItem, TaxSummary, Totals,
    DocumentDetails, ConfidenceScores, ERPSchema,
)

logger = logging.getLogger(__name__)


def _to_decimal(value: Any, default: Decimal = Decimal(0)) -> Decimal:
    if value is None:
        return default
    try:
        # Clean Indian-formatted numbers: remove commas, currency symbols, whitespace
        cleaned = str(value).strip()
        if not cleaned or cleaned in ('-', 'N/A', 'None', '—'):
            return default
        # Remove currency symbols and commas (e.g. '₹1,18,000.00' → '118000.00')
        cleaned = cleaned.replace(',', '').replace('₹', '').replace('Rs.', '').replace('Rs', '').strip()
        if not cleaned:
            return default
        return Decimal(cleaned).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except Exception:
        return default


class ERPMapper:
    def map_to_erp_schema(
        self,
        normalized_fields: Dict[str, Any],
        compliance_result: Dict[str, Any],
        confidence_scores: Dict[str, float],
        validation_result: Any = None,
        extraction_metadata: Optional[Dict[str, Any]] = None,
    ) -> ERPSchema:
        supplier_details = PartyDetails(
            party_name=normalized_fields.get("supplier_name") or "",
            gstin=normalized_fields.get("supplier_gstin"),
            state_name=compliance_result.get("place_of_supply", {}).get("supplier_state_name"),
            state_code=compliance_result.get("place_of_supply", {}).get("supplier_state_code"),
        )

        buyer_details = PartyDetails(
            party_name=normalized_fields.get("buyer_name") or "",
            gstin=normalized_fields.get("buyer_gstin"),
            state_name=compliance_result.get("place_of_supply", {}).get("buyer_state_name"),
            state_code=compliance_result.get("place_of_supply", {}).get("buyer_state_code"),
        )

        document_details = DocumentDetails(
            invoice_number=normalized_fields.get("invoice_number") or "",
            invoice_date=normalized_fields.get("invoice_date") or "",
            invoice_type=compliance_result.get("invoice_type", "Tax Invoice"),
            place_of_supply=compliance_result.get("place_of_supply", {}).get("buyer_state_name"),
            place_of_supply_code=compliance_result.get("place_of_supply", {}).get("buyer_state_code"),
            reverse_charge=compliance_result.get("rcm", {}).get("applicable", False),
        )

        items = self._build_items(normalized_fields.get("items", []), normalized_fields)

        subtotal = sum(item.line_total for item in items) if items else _to_decimal(normalized_fields.get("taxable_amount"))

        total_cgst = _to_decimal(normalized_fields.get("cgst_amount"))
        total_sgst = _to_decimal(normalized_fields.get("sgst_amount"))
        total_igst = _to_decimal(normalized_fields.get("igst_amount"))

        tax_summary = TaxSummary(
            subtotal=subtotal,
            total_cgst=total_cgst,
            total_sgst=total_sgst,
            total_igst=total_igst,
            tds_amount=_to_decimal(compliance_result.get("tds", {}).get("amount")),
            tcs_amount=_to_decimal(compliance_result.get("tcs", {}).get("amount")),
        )

        grand_total = _to_decimal(normalized_fields.get("total_amount"))
        tax_total = total_cgst + total_sgst + total_igst

        totals = Totals(
            subtotal=subtotal,
            tax_amount=tax_total,
            grand_total=grand_total,
        )

        conf_scores = ConfidenceScores(
            overall=confidence_scores.get("overall", 0),
            invoice_number=confidence_scores.get("invoice_number"),
            invoice_date=confidence_scores.get("invoice_date"),
            party_name=confidence_scores.get("party_name"),
            gstin=confidence_scores.get("gstin"),
            items=confidence_scores.get("items"),
            totals=confidence_scores.get("totals"),
        )

        return ERPSchema(
            supplier_details=supplier_details,
            buyer_details=buyer_details,
            document_details=document_details,
            items=items,
            tax_summary=tax_summary,
            totals=totals,
            confidence_scores=conf_scores,
            extraction_metadata=extraction_metadata,
        )

    def _build_items(self, raw_items: List[Dict[str, Any]], fields: Dict[str, Any]) -> List[InvoiceItem]:
        items: List[InvoiceItem] = []
        for raw in raw_items:
            line_total = _to_decimal(raw.get("amount"))
            item = InvoiceItem(
                item_name=raw.get("description") or "",
                hsn_sac_code=raw.get("hsn_code"),
                quantity=_to_decimal(raw.get("quantity")),
                unit=raw.get("unit"),
                unit_price=_to_decimal(raw.get("rate")),
                line_total=line_total,
                cgst_rate=_to_decimal(raw.get("cgst_rate")),
                cgst_amount=_to_decimal(raw.get("cgst_amount")),
                sgst_rate=_to_decimal(raw.get("sgst_rate")),
                sgst_amount=_to_decimal(raw.get("sgst_amount")),
                igst_rate=_to_decimal(raw.get("igst_rate")),
                igst_amount=_to_decimal(raw.get("igst_amount")),
            )
            items.append(item)

        if not items and fields.get("taxable_amount"):
            default_item = InvoiceItem(
                item_name="Invoice Items",
                line_total=_to_decimal(fields.get("taxable_amount")),
            )
            items.append(default_item)

        return items

    def to_dict(self, schema: ERPSchema) -> Dict[str, Any]:
        return schema.model_dump()

    def erp_schema_from_fields(
        self,
        fields: Dict[str, Any],
        compliance_result: Dict[str, Any],
        confidence_scores: Dict[str, float],
    ) -> Dict[str, Any]:
        schema = self.map_to_erp_schema(
            normalized_fields=fields,
            compliance_result=compliance_result,
            confidence_scores=confidence_scores,
        )
        return self.to_dict(schema)


erp_mapper = ERPMapper()
