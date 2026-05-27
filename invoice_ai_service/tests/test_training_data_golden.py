"""Golden checks using real OCR cache under training_data/ocr_cache/."""

import json
from pathlib import Path

import pytest

BASE = Path(__file__).resolve().parents[1]
OCR_CACHE = BASE / "training_data" / "ocr_cache"


def _load_text(cache_name: str) -> str:
    path = OCR_CACHE / cache_name
    if not path.exists():
        pytest.skip(f"Missing OCR cache: {path}")
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return data.get("ocr_result", {}).get("text", "") or ""


@pytest.mark.training_data
def test_188_buyer_total_and_tax_from_cache():
    """Muskan-style bill: buyer ALAKH INTERNATIONAL, net total, CGST/SGST stacked above labels."""
    text = _load_text("188.pdf.json")
    if len(text) < 500:
        pytest.skip("No OCR text")

    from app.services.extraction.field_extractor import field_extractor

    out = field_extractor.extract_fields(text)
    assert out.get("success"), out.get("error")
    fields = out["fields"]

    buyer = (fields.get("buyer_name") or "").upper()
    assert "ALAKH" in buyer and "GUJARAT" not in buyer.replace(" ", "")

    assert fields.get("total_amount") == pytest.approx(127969.0, rel=1e-3)
    assert fields.get("taxable_amount") == pytest.approx(121875.0, rel=1e-3)

    cgst = fields.get("cgst_amount") or 0
    sgst = fields.get("sgst_amount") or 0
    assert cgst > 100 and sgst > 100
    assert abs(cgst - sgst) < 1.0
