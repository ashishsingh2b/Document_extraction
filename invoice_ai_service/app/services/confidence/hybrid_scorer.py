"""Merge rule-based pipeline confidence with XGBoost ml_signals for unified HITL routing."""

from typing import Any, Dict, List, Optional

from app.config.settings import settings
from app.core.constants import CONFIDENCE_THRESHOLD_HITL

# Map pipeline field_scores keys → ml_signals field_confidence keys
_ML_FIELD_MAP = {
    "invoice_number": "invoice_number",
    "invoice_date": "invoice_date",
    "supplier_gstin": "vendor_gstin",
    "buyer_gstin": "buyer_gstin",
    "taxable_amount": "taxable_amount",
    "cgst_amount": "cgst_amount",
    "sgst_amount": "sgst_amount",
    "igst_amount": "igst_amount",
    "total_amount": "total_amount",
}


def build_hybrid_review(
    pipeline_result: Dict[str, Any],
    ml_signals: Optional[Dict[str, Any]],
    extracted_fields: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Combine pipeline confidence (field presence/quality) with ML presence probabilities.

    ML does not supply values — low ML confidence on a field that rules filled flags review.
    """
    conf = pipeline_result.get("confidence") or {}
    rule_overall = float(pipeline_result.get("overall_confidence") or conf.get("overall") or 0)
    rule_scores = conf.get("field_scores") or {}
    rule_hitl = bool(pipeline_result.get("hitl_required") or conf.get("hitl_required", False))

    ml = ml_signals or {}
    ml_field = ml.get("field_confidence") or {}
    ml_low = set(ml.get("low_confidence_fields") or [])

    merged_fields: Dict[str, Dict[str, Any]] = {}
    review_fields: List[str] = []

    for pipe_key, ml_key in _ML_FIELD_MAP.items():
        r_score = float(rule_scores.get(pipe_key, 0) or 0)
        m_prob = float(ml_field.get(ml_key, 0) or 0) if ml_field else None

        # Rules dominate value quality; ML adjusts trust when present
        if m_prob is not None and settings.ML_SIGNALS_ON_UPLOAD:
            combined = round(min(100.0, r_score * 0.65 + m_prob * 100 * 0.35), 2)
            flag_ml = m_prob < 0.5
        else:
            combined = r_score
            flag_ml = False

        flag_rule = r_score < 50
        needs_review = flag_rule or flag_ml
        if needs_review and pipe_key not in review_fields:
            review_fields.append(pipe_key)

        merged_fields[pipe_key] = {
            "rule_score": r_score,
            "ml_presence_prob": round(m_prob, 4) if m_prob is not None else None,
            "combined_score": combined,
            "needs_review": needs_review,
        }

    # Party names (no direct ML keys in older models)
    for extra in ("supplier_name", "buyer_name", "items"):
        r_score = float(rule_scores.get(extra, 0) or 0)
        needs_review = r_score < 50
        merged_fields[extra] = {
            "rule_score": r_score,
            "ml_presence_prob": None,
            "combined_score": r_score,
            "needs_review": needs_review,
        }
        if needs_review and extra not in review_fields:
            review_fields.append(extra)

    merged_overall = round(
        sum(v["combined_score"] for v in merged_fields.values()) / max(len(merged_fields), 1),
        2,
    )
    hitl_required = (
        rule_hitl
        or merged_overall < CONFIDENCE_THRESHOLD_HITL
        or len(review_fields) >= 3
    )

    return {
        "overall_confidence": merged_overall,
        "hitl_required": hitl_required,
        "review_fields": review_fields,
        "field_review": merged_fields,
        "invoice_type_prediction": ml.get("invoice_type_prediction"),
        "ml_role": ml.get("role", "disabled"),
        "phase": "hybrid_v1",
    }
