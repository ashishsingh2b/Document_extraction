#!/usr/bin/env python3
"""Quick extraction report over training_data/ocr_cache/*.json (no PDF/OCR needed)."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.extraction.field_extractor import field_extractor


def main():
    cache_dir = Path(__file__).resolve().parents[1] / "training_data" / "ocr_cache"
    paths = sorted(cache_dir.glob("*.json"))
    if not paths:
        print("No OCR cache files found.")
        return 1

    ok = 0
    print(f"{'File':<45} {'Buyer':<22} {'Total':>12} {'CGST':>10} {'Items':>5}")
    print("-" * 100)

    for path in paths:
        try:
            data = json.load(open(path, encoding="utf-8"))
            text = data.get("ocr_result", {}).get("text", "")
            if len(text) < 80:
                continue
            out = field_extractor.extract_fields(text)
            if not out.get("success"):
                print(f"{path.name:<45} ERROR {out.get('error', '')[:40]}")
                continue
            f = out["fields"]
            buyer = (f.get("buyer_name") or "")[:20]
            total = f.get("total_amount")
            cgst = f.get("cgst_amount")
            n_items = len(f.get("items") or [])
            if buyer and total:
                ok += 1
            print(
                f"{path.name:<45} {buyer:<22} "
                f"{total if total else '—':>12} "
                f"{cgst if cgst else '—':>10} "
                f"{n_items:>5}"
            )
        except Exception as e:
            print(f"{path.name:<45} EXC {e}")

    print("-" * 100)
    print(f"With buyer+total: {ok}/{len(paths)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
