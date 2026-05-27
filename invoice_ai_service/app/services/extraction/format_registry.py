"""Invoice format detection and profile registry for multi-layout Indian GST invoices."""

import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

_PROFILES_PATH = Path(__file__).resolve().parents[2] / "config" / "invoice_format_profiles.json"


def load_profiles() -> List[Dict[str, Any]]:
    """Load format profiles from JSON config (easy to extend without code changes)."""
    try:
        with open(_PROFILES_PATH, encoding="utf-8") as f:
            data = json.load(f)
        return data.get("profiles", [])
    except Exception as e:
        logger.warning(f"Could not load format profiles: {e}")
        return [{"id": "universal", "signals": ["tax invoice"], "tax_type": "auto"}]


def detect_invoice_format(text: str) -> Tuple[str, float, str]:
    """
    Detect which invoice layout best matches the OCR text.

    Each profile in invoice_format_profiles.json can specify:
      signals          — keywords scored by hit-ratio
      required_signals — ALL must match or profile is rejected
      exclusive_signals — if ANY of these match, profile is rejected
      supplier_signals  — bonus if found in first 800 chars
      priority         — tiebreaker (higher wins)

    Returns:
        (format_id, confidence 0-1, human label)
    """
    text_lower = text.lower()
    profiles = load_profiles()
    best_id = "universal"
    best_score = 0.0
    best_label = "Generic"
    best_priority = 0

    for profile in profiles:
        if profile["id"] == "universal":
            continue

        # ── Required signals: ALL must be present ──
        required = profile.get("required_signals", [])
        if required and not all(r.lower() in text_lower for r in required):
            continue  # skip — mandatory signal missing

        # ── Exclusive signals: if ANY present, this format is disqualified ──
        exclusive = profile.get("exclusive_signals", [])
        if exclusive and any(e.lower() in text_lower for e in exclusive):
            continue  # skip — conflicting signal found

        signals = profile.get("signals", [])
        if not signals:
            continue
        hits = sum(1 for s in signals if s.lower() in text_lower)
        score = hits / len(signals)

        supplier_signals = profile.get("supplier_signals", [])
        if supplier_signals:
            if any(s.lower() in text_lower[:800] for s in supplier_signals):
                score += 0.15

        profile_priority = profile.get("priority", 5)
        if score > best_score or (
            abs(score - best_score) <= 0.05 and profile_priority > best_priority
        ):
            best_score = score
            best_id = profile["id"]
            best_label = profile.get("label", best_id)
            best_priority = profile_priority

    # Require a meaningful match — raise threshold to avoid false positives
    confidence = min(1.0, best_score + (0.1 if best_id != "universal" else 0))
    if best_score < 0.40:
        best_id = "universal"
        best_label = "Generic fallback"
        confidence = 0.3

    logger.info(f"Detected invoice format: {best_id} (confidence: {confidence:.2f}) — {best_label}")
    return best_id, round(confidence, 2), best_label


def get_profile(format_id: str) -> Dict[str, Any]:
    for p in load_profiles():
        if p["id"] == format_id:
            return p
    return {"id": "universal", "tax_type": "auto"}
