#!/usr/bin/env python3
"""Build training_data/ocr_cache/*.json from PDFs/images in training_data/raw/."""

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config.settings import settings
from app.services.extraction.universal_extractor import universal_extractor


def main():
    raw_dir = Path(__file__).resolve().parents[1] / "training_data" / "raw"
    cache_dir = Path(__file__).resolve().parents[1] / "training_data" / "ocr_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)

    files = sorted(
        list(raw_dir.glob("*.pdf"))
        + list(raw_dir.glob("*.jpg"))
        + list(raw_dir.glob("*.jpeg"))
        + list(raw_dir.glob("*.png"))
    )
    if not files:
        print(f"No files in {raw_dir}")
        return 1

    built = 0
    for path in files:
        cache_path = cache_dir / f"{path.name}.json"
        data = path.read_bytes()
        mime = "application/pdf" if path.suffix.lower() == ".pdf" else "image/jpeg"
        result = universal_extractor.extract_text(data, mime, settings.DEFAULT_OCR_ENGINE)
        payload = {
            "file_size": len(data),
            "mtime": path.stat().st_mtime,
            "ocr_result": result,
        }
        cache_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        built += 1
        ok = "ok" if result.get("success") else "FAIL"
        print(f"{ok:4} {path.name} → {cache_path.name} ({result.get('text_length', len(result.get('text', '')))} chars)")

    print(f"\nBuilt {built} OCR cache files in {cache_dir}")
    print("Next: POST /api/v1/train  OR  python -m app.services.training.pattern_learner")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
