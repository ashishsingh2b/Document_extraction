#!/usr/bin/env python3
"""
End-to-end validation without starting uvicorn:
- App import + OpenAPI routes
- Golden extractions from training_data/ocr_cache
- Optional live PDF read (one file from raw/)
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

FAILURES: list[str] = []


def ok(msg: str) -> None:
    print(f"  OK  {msg}")


def fail(msg: str) -> None:
    print(f"  FAIL {msg}")
    FAILURES.append(msg)


def run_pytest() -> None:
    print("\n[1] pytest")
    r = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/", "-q", "-m", "not integration", "--tb=line"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    if r.returncode == 0:
        ok(f"pytest passed\n{r.stdout.strip()}")
    else:
        fail(f"pytest exit {r.returncode}\n{r.stdout}\n{r.stderr}")


def check_app_routes() -> None:
    print("\n[2] FastAPI routes")
    try:
        from fastapi.testclient import TestClient
        from app.main import app

        client = TestClient(app)
        paths = client.get("/openapi.json").json().get("paths", {})
        for route in (
            "/api/v1/upload",
            "/api/v1/train",
            "/api/v1/train/ml",
            "/api/v1/system/status",
            "/api/v1/health",
        ):
            if route in paths:
                ok(route)
            else:
                fail(f"missing route {route}")
    except Exception as e:
        fail(f"app import: {e}")


def check_golden_extractions() -> None:
    print("\n[3] Golden OCR-cache extractions")
    from app.services.extraction.field_extractor import field_extractor

    cases = {
        "188.pdf.json": {
            "buyer_contains": "ALAKH",
            "total": 127969.0,
            "min_cgst": 100,
        },
        "184-185.pdf.json": {
            "buyer_contains": "ALAKH",
            "min_total": 100000,
        },
    }
    cache = ROOT / "training_data" / "ocr_cache"
    for name, rules in cases.items():
        path = cache / name
        if not path.exists():
            fail(f"missing {name}")
            continue
        text = json.loads(path.read_text(encoding="utf-8"))["ocr_result"]["text"]
        out = field_extractor.extract_fields(text)
        if not out.get("success"):
            fail(f"{name}: {out.get('error')}")
            continue
        f = out["fields"]
        buyer = (f.get("buyer_name") or "").upper()
        if rules.get("buyer_contains") and rules["buyer_contains"] not in buyer:
            fail(f"{name}: buyer={f.get('buyer_name')}")
            continue
        total = f.get("total_amount")
        if "total" in rules and total != rules["total"]:
            fail(f"{name}: total={total} expected {rules['total']}")
            continue
        if "min_total" in rules and (not total or total < rules["min_total"]):
            fail(f"{name}: total={total}")
            continue
        cgst = f.get("cgst_amount") or 0
        if "min_cgst" in rules and cgst < rules["min_cgst"]:
            fail(f"{name}: cgst={cgst}")
            continue
        ok(f"{name} buyer={f.get('buyer_name')!r} total={total}")


def check_optional_pdf_upload() -> None:
    print("\n[4] Optional PDF upload (sync pipeline, no HTTP)")
    raw = ROOT / "training_data" / "raw"
    pdfs = sorted(raw.glob("*.pdf"))
    if not pdfs:
        print("  SKIP no PDFs in training_data/raw")
        return
    pdf = pdfs[0]
    for candidate in raw.glob("*.pdf"):
        if "188" in candidate.name or "traininng" in candidate.name.lower():
            pdf = candidate
            break
    try:
        from app.services.extraction.universal_extractor import universal_extractor
        from app.services.extraction.document_classifier import document_classifier
        from app.services.orchestration.pipeline_orchestrator import pipeline_orchestrator

        data = pdf.read_bytes()
        ocr = universal_extractor.extract_text(data, "application/pdf")
        if not ocr.get("success"):
            fail(f"OCR failed on {pdf.name}: {ocr.get('error')}")
            return
        text = ocr.get("text", "")
        clf = document_classifier.classify(text, pdf.name)
        if not clf.get("should_process"):
            fail(f"classifier rejected {pdf.name}: {clf.get('reason')}")
            return
        from app.services.extraction.field_extractor import field_extractor

        fields_out = field_extractor.extract_fields(text)
        if not fields_out.get("success"):
            fail(f"fields failed on {pdf.name}")
            return
        fields = fields_out["fields"]
        pipe = pipeline_orchestrator.process_fields(fields=fields, raw_text=text)
        erp = pipe.get("erp_schema") or {}
        if not erp:
            fail(f"no erp_schema for {pdf.name}")
            return
        ok(f"{pdf.name} OCR={len(text)} chars ERP keys={list(erp.keys())[:6]}...")
    except ImportError as e:
        print(f"  SKIP PDF test (missing dep): {e}")
    except Exception as e:
        fail(f"PDF pipeline {pdf.name}: {e}")


def main() -> int:
    print("E2E validation")
    print(f"Python: {sys.executable}")
    run_pytest()
    check_app_routes()
    check_golden_extractions()
    check_optional_pdf_upload()

    print("\n" + "=" * 60)
    if FAILURES:
        print(f"FAILED ({len(FAILURES)} issues):")
        for f in FAILURES:
            print(f"  - {f}")
        return 1
    print("PASSED — system ready for manual upload testing")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
