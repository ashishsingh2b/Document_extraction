"""Phase 2–4 wiring tests (no heavy OCR)."""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import settings as settings_mod
from app.services.confidence.hybrid_scorer import build_hybrid_review
from app.services.extraction.document_classifier import document_classifier


def test_classifier_rejects_balance_sheet():
    r = document_classifier.classify("Assets Liabilities balance sheet as on", "Balance sheet.pdf")
    assert r["document_type"] == "balance_sheet"
    assert r["should_process"] is False


def test_classifier_accepts_sale_bill():
    r = document_classifier.classify("TAX INVOICE gstin invoice no", "SALE BILL - 188.pdf")
    assert r["should_process"] is True


def test_hybrid_review_merges_scores():
    pipeline = {
        "overall_confidence": 80,
        "hitl_required": False,
        "confidence": {"overall": 80, "field_scores": {"invoice_number": 90, "total_amount": 70}},
    }
    ml = {"field_confidence": {"invoice_number": 0.9, "total_amount": 0.2}, "role": "routing"}
    h = build_hybrid_review(pipeline, ml)
    assert "overall_confidence" in h
    assert "total_amount" in h["review_fields"] or h["hitl_required"]


def test_system_status_route():
    from app.api.routes import system as system_routes

    app = __import__("fastapi").FastAPI()
    app.include_router(system_routes.router, prefix="/api/v1")
    r = TestClient(app).get("/api/v1/system/status")
    assert r.status_code == 200
    assert r.json()["phases"]["2_hybrid_hitl"] == "complete"


@pytest.mark.training_data
def test_golden_184_from_cache():
    path = Path(__file__).resolve().parents[1] / "training_data" / "ocr_cache" / "184-185.pdf.json"
    if not path.exists():
        pytest.skip("no cache")
    text = json.loads(path.read_text())["ocr_result"]["text"]
    from app.services.extraction.field_extractor import field_extractor

    out = field_extractor.extract_fields(text)
    assert out["success"]
    f = out["fields"]
    assert f.get("buyer_name") and "ALAKH" in (f.get("buyer_name") or "").upper()
    assert f.get("total_amount")
