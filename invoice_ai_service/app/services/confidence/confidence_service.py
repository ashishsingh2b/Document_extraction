"""Field-level confidence scoring service."""

import logging
from typing import Dict, Any, Optional
from app.core.constants import CONFIDENCE_THRESHOLD_HITL

logger = logging.getLogger(__name__)

FIELD_WEIGHTS = {
    "invoice_number": 0.15,
    "invoice_date": 0.10,
    "due_date": 0.05,
    "supplier_name": 0.12,
    "supplier_gstin": 0.10,
    "buyer_name": 0.10,
    "buyer_gstin": 0.08,
    "total_amount": 0.12,
    "taxable_amount": 0.06,
    "cgst_amount": 0.04,
    "sgst_amount": 0.04,
    "igst_amount": 0.04,
}


class FieldConfidenceScorer:
    def score_fields(self, fields: Dict[str, Any]) -> Dict[str, Any]:
        field_scores: Dict[str, float] = {}

        field_scores["invoice_number"] = self._score_invoice_number(fields.get("invoice_number"))
        field_scores["invoice_date"] = self._score_date(fields.get("invoice_date"))
        field_scores["due_date"] = self._score_date(fields.get("due_date"))
        field_scores["supplier_name"] = self._score_party_name(fields.get("supplier_name"))
        field_scores["supplier_gstin"] = self._score_gstin(fields.get("supplier_gstin"))
        field_scores["buyer_name"] = self._score_party_name(fields.get("buyer_name"))
        field_scores["buyer_gstin"] = self._score_gstin(fields.get("buyer_gstin"))
        field_scores["total_amount"] = self._score_amount(fields.get("total_amount"))
        field_scores["taxable_amount"] = self._score_amount(fields.get("taxable_amount"))
        field_scores["cgst_amount"] = self._score_amount(fields.get("cgst_amount"))
        field_scores["sgst_amount"] = self._score_amount(fields.get("sgst_amount"))
        field_scores["igst_amount"] = self._score_amount(fields.get("igst_amount"))

        items = fields.get("items", [])
        field_scores["items"] = self._score_items(items)

        overall = self._calculate_overall(field_scores, fields)

        hitl_required = overall < CONFIDENCE_THRESHOLD_HITL

        return {
            "overall": round(overall, 2),
            "field_scores": field_scores,
            "hitl_required": hitl_required,
            "fields_action": self._determine_actions(field_scores),
        }

    def _score_invoice_number(self, value: Any) -> float:
        if not value:
            return 0
        s = str(value).strip()
        if not s:
            return 0
        has_alpha = any(c.isalpha() for c in s)
        has_digit = any(c.isdigit() for c in s)
        if has_alpha and has_digit:
            return 95
        if has_digit:
            return 80
        return 60

    def _score_date(self, value: Any) -> float:
        if not value:
            return 0
        s = str(value).strip()
        if not s:
            return 0
        import re
        if re.match(r"\d{2}[-/]\d{2}[-/]\d{4}", s):
            return 95
        if re.match(r"\d{1,2}[-/]\d{1,2}[-/]\d{2}", s):
            return 85
        return 60

    def _score_party_name(self, value: Any) -> float:
        if not value:
            return 0
        s = str(value).strip()
        if not s:
            return 0
        if len(s) < 5:
            return 40
        if len(s) > 50:
            return 60
        has_company_kw = any(kw in s.upper() for kw in
                             ["SAREE", "PALACE", "COLLECTION", "TRADERS", "FASHION",
                              "TEXTILES", "INDUSTRIES", "INTERNATIONAL", "ENTERPRISES"])
        if has_company_kw:
            return 95
        if any(c.isupper() for c in s[:2]):
            return 85
        return 70

    def _score_gstin(self, value: Any) -> float:
        if not value:
            return 0
        s = str(value).strip().upper()
        import re
        if re.match(r"^\d{2}[A-Z]{5}\d{4}[A-Z]{1}[A-Z\d]{1}Z[A-Z\d]{1}$", s):
            return 98
        if len(s) == 15:
            return 80
        return 40

    def _score_amount(self, value: Any) -> float:
        if value is None:
            return 0
        try:
            v = float(value)
            if v > 0:
                return 95
            return 60
        except (ValueError, TypeError):
            return 0

    def _score_items(self, items: Any) -> float:
        if not items or not isinstance(items, list):
            return 0
        if len(items) == 0:
            return 0
        scored = 0
        for item in items:
            desc = item.get("description")
            amount = item.get("amount")
            if desc and amount:
                try:
                    if float(amount) > 0:
                        scored += 1
                except (ValueError, TypeError):
                    pass
        ratio = scored / len(items) if items else 0
        return round(ratio * 100, 2)

    def _calculate_overall(self, field_scores: Dict[str, float], fields: Dict[str, Any]) -> float:
        total_weight = 0
        weighted_sum = 0
        for field, weight in FIELD_WEIGHTS.items():
            score = field_scores.get(field, 0)
            value = fields.get(field)
            if value is not None and str(value).strip():
                weighted_sum += score * weight
                total_weight += weight

        items = fields.get("items", [])
        if items:
            item_score = field_scores.get("items", 0)
            weighted_sum += item_score * 0.10
            total_weight += 0.10

        if total_weight == 0:
            return 0
        return weighted_sum / total_weight

    def _determine_actions(self, field_scores: Dict[str, float]) -> Dict[str, str]:
        actions = {}
        for field, score in field_scores.items():
            if score >= 90:
                actions[field] = "auto_approve"
            elif score >= CONFIDENCE_THRESHOLD_HITL:
                actions[field] = "auto_accept"
            else:
                actions[field] = "manual_review"
        return actions


field_confidence_scorer = FieldConfidenceScorer()
