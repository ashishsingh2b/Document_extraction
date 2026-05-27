"""
Pattern Learning Engine
========================
Reads ALL uploaded training documents, discovers how each field
(invoice_number, invoice_date, supplier_name, GSTIN, amounts, etc.)
appears in text, and saves learned patterns to a JSON file.

These learned patterns are then used automatically for extraction on
any new invoice — no hardcoding required for each new format.

Run:
    python -m app.services.training.pattern_learner

Or call learn_from_all_training_data() directly.
"""

import re
import json
import os
import logging
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ── Paths ──────────────────────────────────────────────────────────────────
BASE_DIR       = Path(__file__).resolve().parents[3]
OCR_CACHE_DIR  = BASE_DIR / "training_data" / "ocr_cache"
LEARNED_FILE   = BASE_DIR / "app" / "config" / "learned_patterns.json"

# ── Field seed patterns: used to LOCATE known field values in training docs ─
# Each seed finds a known value; we then record the context around it
# so the system can generalise to unseen documents.
FIELD_SEEDS = {
    "invoice_number": [
        r'(?:Invoice|Bill|Inv)\s*(?:No\.?|Number|#)\s*[:\-]?\s*([A-Z0-9/\-]{3,20})',
        r'(?:^|\n)\s*(?:Invoice|Bill)\s*No\.?\s*[:\-]?\s*([A-Z0-9/\-]{3,20})',
    ],
    "invoice_date": [
        r'(?:Invoice|Bill)\s*Date\s*[:\-]?\s*(\d{1,2}[-/][A-Za-z0-9]{2,3}[-/]\d{2,4})',
        r'(?:Invoice|Bill)\s*Date\s*[:\-]?\s*(\d{1,2}[-/]\d{1,2}[-/]\d{2,4})',
        r'Date\s*[:\-]?\s*(\d{1,2}[-/]\d{1,2}[-/]\d{2,4})',
    ],
    "due_date": [
        r'Due\s*Date\s*[:\-]?\s*(\d{1,2}[-/][A-Za-z0-9]{2,3}[-/]\d{2,4})',
        r'Due\s*Date\s*[:\-]?\s*(\d{1,2}[-/]\d{1,2}[-/]\d{2,4})',
        r'Payment\s*(?:Due|Within)[^\d]*(\d{1,2}[-/]\d{1,2}[-/]\d{2,4})',
    ],
    "supplier_gstin": [
        r'GSTIN\s*[:\-]?\s*(\d{2}[A-Z]{5}\d{4}[A-Z][A-Z\d]Z[A-Z\d])',
    ],
    "total_amount": [
        r'(?:Grand\s*Total|Net\s*Amount|Invoice\s*Value|Total\s*Amount|NET\s*AMOUNT)\s*[:\-]?\s*(?:Rs\.?|₹)?\s*([\d,]+\.?\d*)',
        r'(?:^|\n)\s*Total\s+([\d,]+\.?\d*)\s*$',
    ],
    "taxable_amount": [
        r'(?:Taxable\s*(?:Amount|Value)|Total\s*(?:Amount\s*)?Before\s*Tax)\s*[:\-]?\s*([\d,]+\.?\d*)',
        r'Sale\s*@\d+%\s*=\s*([\d,]+\.?\d*)',
    ],
    "cgst_amount": [
        r'CGST\s*@?\s*[\d.]+\s*%\s*[:\-+]?\s*([\d,]+\.?\d+)',
        r'CGST\s*[\d.]+\s*([\d,]+\.?\d+)',
    ],
    "sgst_amount": [
        r'SGST\s*@?\s*[\d.]+\s*%\s*[:\-+]?\s*([\d,]+\.?\d+)',
        r'SGST\s*[\d.]+\s*([\d,]+\.?\d+)',
    ],
    "igst_amount": [
        r'IGST\s*@?\s*[\d.]+\s*%?\s*[:\-+=]?\s*([\d,]+\.?\d+)',
        r'IGST\s*=\s*([\d,]+\.?\d+)',
    ],
    "hsn_code": [
        r'\b(\d{4,8})\b',   # standalone 4-8 digit code near line item
    ],
}

# ── Context window size (chars) around each found value ──────────────────
CTX_BEFORE = 80
CTX_AFTER  = 40

# ── Minimum number of training documents a pattern must appear in ─────────
MIN_DOCS = 2


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _load_ocr_texts() -> List[Tuple[str, str]]:
    """Load all (filename, text) pairs from the OCR cache."""
    results = []
    for path in sorted(OCR_CACHE_DIR.glob("*.json")):
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            text = data.get("ocr_result", {}).get("text", "")
            if text and len(text) > 100:
                results.append((path.name, text))
        except Exception as e:
            logger.warning(f"Could not load {path.name}: {e}")
    return results


def _extract_context_patterns(text: str, field: str) -> List[str]:
    """
    For a given field and text, find all occurrences of the field value
    and extract the text context (label) immediately before it.
    Returns a list of normalised 'label' strings (the key part).
    """
    patterns = FIELD_SEEDS.get(field, [])
    contexts = []
    for pat in patterns:
        for m in re.finditer(pat, text, re.I | re.M):
            start = m.start()
            before = text[max(0, start - CTX_BEFORE): start]
            # Take the last meaningful token before the value
            label_candidates = re.findall(r'[A-Za-z][\w\s\.]{2,40}', before)
            if label_candidates:
                label = label_candidates[-1].strip().lower()
                label = re.sub(r'\s+', ' ', label)
                if 3 <= len(label) <= 50:
                    contexts.append(label)
    return contexts


def _discover_label_patterns(docs: List[Tuple[str, str]]) -> Dict[str, List[str]]:
    """
    For each field, count how often each label (context prefix) appears
    across all training documents. Return the most common labels per field.
    """
    field_label_counts: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
    field_doc_counts:   Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))

    for fname, text in docs:
        for field in FIELD_SEEDS:
            seen_labels = set()
            labels = _extract_context_patterns(text, field)
            for label in labels:
                field_label_counts[field][label] += 1
                if label not in seen_labels:
                    field_doc_counts[field][label] += 1
                    seen_labels.add(label)

    # Keep labels seen in at least MIN_DOCS documents
    learned: Dict[str, List[str]] = {}
    for field, doc_counts in field_doc_counts.items():
        good = [lbl for lbl, cnt in sorted(doc_counts.items(), key=lambda x: -x[1])
                if cnt >= MIN_DOCS]
        if good:
            learned[field] = good[:20]  # top 20 labels per field
    return learned


def _discover_column_headers(docs: List[Tuple[str, str]]) -> Dict[str, int]:
    """
    Scan all training documents for lines that look like table column headers.
    Count how often each column keyword appears and record its frequency.
    Returns {keyword: frequency}.
    """
    from app.services.extraction.universal_structure_extractor import COLUMN_FIELD_MAP
    col_freq: Dict[str, int] = defaultdict(int)
    for _, text in docs:
        for line in text.split('\n')[:80]:
            line_l = line.lower()
            for col_key in COLUMN_FIELD_MAP:
                if col_key in line_l:
                    col_freq[col_key] += 1
    return dict(sorted(col_freq.items(), key=lambda x: -x[1]))


def _discover_doc_type_signals(docs: List[Tuple[str, str]]) -> Dict[str, List[str]]:
    """
    For each document, try to infer its type, then collect distinctive keyword
    signals that appear in that type but not in others.
    Returns {doc_type: [signal, ...]} sorted by discriminative power.
    """
    from app.services.extraction.universal_structure_extractor import DOC_TYPE_SIGNALS, detect_document_type

    type_word_counts: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
    type_doc_counts:  Dict[str, int] = defaultdict(int)

    for _, text in docs:
        doc_type, conf = detect_document_type(text)
        if conf < 0.15:
            doc_type = "sales_invoice"  # assume invoice for generic docs
        type_doc_counts[doc_type] += 1
        words = set(re.findall(r'\b[a-z]{3,20}\b', text.lower()))
        for w in words:
            type_word_counts[doc_type][w] += 1

    # Find words that appear in >= 60% of docs of one type but rarely elsewhere
    type_signals: Dict[str, List[str]] = {}
    all_types = list(type_word_counts.keys())

    for dtype in all_types:
        n = type_doc_counts[dtype]
        if n < 1:
            continue
        candidates = []
        for word, cnt in type_word_counts[dtype].items():
            freq_in_type = cnt / n
            # How frequent is it in OTHER types?
            other_freq = max(
                (type_word_counts[ot].get(word, 0) / max(type_doc_counts[ot], 1))
                for ot in all_types if ot != dtype
            ) if len(all_types) > 1 else 0
            discriminative = freq_in_type - other_freq
            if freq_in_type >= 0.50 and discriminative > 0.20:
                candidates.append((word, round(discriminative, 2)))
        candidates.sort(key=lambda x: -x[1])
        type_signals[dtype] = [w for w, _ in candidates[:15]]

    return type_signals


def _discover_amount_positions(docs: List[Tuple[str, str]]) -> Dict[str, List[str]]:
    """
    Discover how amounts are labeled across all training docs.
    E.g. learn that 'net amount' → total_amount, 'cgst 9.00%' → cgst_amount, etc.
    Returns {field_name: [label_pattern, ...]} discovered from real data.
    """
    amount_labels: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))

    AMOUNT_FIELD_HINTS = {
        "total_amount":    ['grand total', 'net amount', 'invoice value', 'total invoice', 'amount payable', 'net amt'],
        "taxable_amount":  ['taxable value', 'taxable amount', 'total before tax', 'amount before tax', 'sub total'],
        "cgst_amount":     ['cgst', 'central gst'],
        "sgst_amount":     ['sgst', 'state gst'],
        "igst_amount":     ['igst', 'integrated gst'],
    }

    for _, text in docs:
        text_l = text.lower()
        for field, hints in AMOUNT_FIELD_HINTS.items():
            for hint in hints:
                if hint in text_l:
                    # Find the actual label text used in this document
                    m = re.search(re.escape(hint), text_l)
                    if m:
                        raw_label = text[m.start():m.start()+60].split('\n')[0].strip()
                        norm = re.sub(r'[:\-=@%\s]+', ' ', raw_label.lower()).strip()[:40]
                        if norm:
                            amount_labels[field][norm] += 1

    return {field: sorted(lbls, key=lambda x: -lbls[x])[:10]
            for field, lbls in amount_labels.items()}


# ─────────────────────────────────────────────────────────────────────────────
# Main: learn from all training data
# ─────────────────────────────────────────────────────────────────────────────

def learn_from_all_training_data() -> Dict[str, Any]:
    """
    Master function: reads every cached OCR file, learns patterns,
    saves to learned_patterns.json, and returns the learned data.
    """
    logger.info(f"Loading training documents from {OCR_CACHE_DIR}")
    docs = _load_ocr_texts()
    logger.info(f"Loaded {len(docs)} training documents")

    if not docs:
        logger.error("No training documents found in OCR cache!")
        return {}

    learned = {}

    # 1. Label patterns for each field
    logger.info("Discovering field label patterns...")
    learned["field_labels"] = _discover_label_patterns(docs)

    # 2. Column header keywords
    logger.info("Discovering column header keywords...")
    learned["column_headers"] = _discover_column_headers(docs)

    # 3. Document type signals
    logger.info("Discovering document type signals...")
    learned["doc_type_signals"] = _discover_doc_type_signals(docs)

    # 4. Amount label patterns
    logger.info("Discovering amount label patterns...")
    learned["amount_labels"] = _discover_amount_positions(docs)

    # 5. Statistics
    learned["meta"] = {
        "trained_on_docs": len(docs),
        "doc_names": [fname for fname, _ in docs],
        "trained_at": __import__('datetime').datetime.now().isoformat(),
    }

    # Save
    LEARNED_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(LEARNED_FILE, "w", encoding="utf-8") as f:
        json.dump(learned, f, indent=2, ensure_ascii=False)

    logger.info(f"Learned patterns saved to {LEARNED_FILE}")
    logger.info(f"  Field labels discovered:    {list(learned['field_labels'].keys())}")
    logger.info(f"  Column headers discovered:  {len(learned['column_headers'])}")
    logger.info(f"  Doc types discovered:       {list(learned['doc_type_signals'].keys())}")

    return learned


def load_learned_patterns() -> Dict[str, Any]:
    """Load previously learned patterns from disk."""
    if not LEARNED_FILE.exists():
        logger.info("No learned patterns file found — running pattern learning now...")
        return learn_from_all_training_data()
    try:
        with open(LEARNED_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.warning(f"Could not load learned patterns: {e}")
        return {}


# ─────────────────────────────────────────────────────────────────────────────
# Extraction using learned patterns
# ─────────────────────────────────────────────────────────────────────────────

_PATTERNS_CACHE: Optional[Dict] = None

def get_patterns() -> Dict[str, Any]:
    """Get cached learned patterns (loads once)."""
    global _PATTERNS_CACHE
    if _PATTERNS_CACHE is None:
        _PATTERNS_CACHE = load_learned_patterns()
    return _PATTERNS_CACHE


def extract_with_learned_patterns(text: str) -> Dict[str, Any]:
    """
    Use learned patterns from training data to extract fields from any text.
    This runs BEFORE format-specific handlers as an additional intelligence layer.
    """
    patterns = get_patterns()
    result: Dict[str, Any] = {}

    # ── Apply learned field label → value patterns ──
    field_labels = patterns.get("field_labels", {})
    for field, labels in field_labels.items():
        if result.get(field):
            continue
        for label in labels:
            # Build a flexible regex from the learned label
            escaped = re.escape(label).replace(r'\ ', r'\s*')
            pat = rf'{escaped}\s*[:\-=]?\s*([A-Z0-9₹,.\-/\s]{{1,40}}?)(?:\n|$|\|)'
            m = re.search(pat, text, re.I | re.M)
            if m:
                val = m.group(1).strip().rstrip('.,:-')
                if val and len(val) >= 2:
                    result[field] = val
                    break

    # ── Apply learned amount labels ──
    amount_labels = patterns.get("amount_labels", {})
    AMOUNT_FIELDS = ["total_amount", "taxable_amount", "cgst_amount", "sgst_amount", "igst_amount"]
    for field in AMOUNT_FIELDS:
        if result.get(field):
            continue
        labels = amount_labels.get(field, [])
        for label in labels:
            escaped = re.escape(label).replace(r'\ ', r'\s*')
            pat = rf'{escaped}[^0-9\n]{{0,20}}([\d,]+\.?\d*)'
            m = re.search(pat, text, re.I | re.M)
            if m:
                try:
                    val = float(m.group(1).replace(',', ''))
                    if val > 0:
                        result[field] = val
                        break
                except ValueError:
                    pass

    # ── Use learned column headers to classify doc type ──
    col_headers = patterns.get("column_headers", {})
    text_l = text.lower()
    col_hits = sum(1 for col in col_headers if col in text_l and col_headers.get(col, 0) >= 3)
    if col_hits >= 3:
        result["_has_table"] = True

    return result


# ─────────────────────────────────────────────────────────────────────────────
# CLI entry point
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO,
                        format='%(asctime)s - %(levelname)s - %(message)s')
    print("=" * 60)
    print("PATTERN LEARNING ENGINE")
    print("=" * 60)
    learned = learn_from_all_training_data()
    print()
    print(f"Trained on {learned['meta']['trained_on_docs']} documents")
    print()
    print("Field labels learned:")
    for field, labels in learned.get("field_labels", {}).items():
        print(f"  {field:20s}: {labels[:5]}")
    print()
    print("Document types found in training data:")
    for dtype, signals in learned.get("doc_type_signals", {}).items():
        print(f"  {dtype:30s}: {signals[:5]}")
    print()
    print(f"Learned patterns saved to: {LEARNED_FILE}")
