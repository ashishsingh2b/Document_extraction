# Invoice AI — Architecture & Training Plan (Final)

For a **full repository handoff** (folder tree, every major module, API list, training vs ML, README drift): see **`SYSTEM_DOCUMENTATION.md`**.

This document is the **canonical** description of how extraction works today and how training is managed.

---

## 1. Upload flow (one person, one PDF)

```
Person → POST /api/v1/upload
           │
           ▼
      Validate file (size, type, basic scan)
           │
           ▼
      OCR / PDF text extraction
           │
           ├──► [optional] XGBoost ml_signals (routing/HITL only)
           │
           ▼
      Document classifier (invoice vs register/balance sheet)
           │
           ▼
      Multi-invoice split (if needed)
           │
           ▼
      Field + line extraction
        • learned_patterns.json (pattern pack)
        • regex + format profiles
           │
           ▼
      Pipeline: clean → normalize → GST → validate → confidence
           │
           ▼
      ERP JSON schema in response (pipeline.erp_schema)
```

**Response shape (single invoice):** `extracted_data` contains `invoice_data`, `pipeline` (with `erp_schema`), and optionally `ml_signals`.

---

## 2. What fills field values vs what XGBoost does

| Component | Fills invoice_number, GSTIN, amounts? | Role |
|-----------|----------------------------------------|------|
| Patterns + regex + formats | **Yes** (primary today) | Extraction |
| XGBoost `models/v1` | **No** | Type prediction + per-field **presence** probability |
| Pipeline rules | Validates / maps | GST checksum, ERP schema |

**XGBoost must not be treated as the main extractor** until a value model (NER/layout LM) is trained and released.

---

## 3. Configuration (.env)

| Variable | Default | Meaning |
|----------|---------|---------|
| `AUTO_LEARN_ON_UPLOAD` | `false` | Save OCR cache + refresh `learned_patterns.json` on each upload |
| `ML_SIGNALS_ON_UPLOAD` | `true` | Attach `ml_signals` to upload response when `models/v1` exists |
| `ML_MODEL_DIR` | `models/v1` | Path to XGBoost pack |

**Testing:** set `AUTO_LEARN_ON_UPLOAD=true` only when you want uploads to feed pattern learning.  
**Production:** keep `AUTO_LEARN_ON_UPLOAD=false`; train via admin steps below.

---

## 4. Training & release (managed, not automatic)

```
Collect PDFs → training_data/raw/
       │
       ▼
OCR cache → training_data/ocr_cache/  (upload with AUTO_LEARN or dataset build)
       │
       ├──► Pattern train: POST /api/v1/train  → learned_patterns.json
       │
       └──► ML train: python scripts/train_model.py
              labels: training_data/annotated/labels.json
              output: models/v1/
       │
       ▼
Test: python scripts/test_accuracy.py
       │
       ▼
Release: deploy new patterns/model dir; set ML_MODEL_DIR if versioned
```

---

## 5. Roadmap (hybrid → model-primary)

| Phase | Extraction | Training |
|-------|------------|----------|
| **Now** | Patterns + rules → ERP; XGBoost = `ml_signals` only | Manual `/train` + `train_model.py` |
| **Next** | NER/layout model proposes values; rules validate | Train on clean `labels.json` |
| **Later** | Model-primary; rules = validation only | Versioned model packs + HITL corrections |

---

## 6. API quick reference

| Endpoint | Purpose |
|----------|---------|
| `POST /api/v1/upload` | Extract invoice → ERP schema |
| `POST /api/v1/train` | Rebuild `learned_patterns.json` from OCR cache |
| `GET /api/v1/train` | Pattern pack statistics |
| `GET /api/v1/health` | Service health |
| `GET /api/v1/ready` | Readiness probe |

**Scripts (repo root `scripts/`):**

| Script | Purpose |
|--------|---------|
| `train_model.py` | Train/evaluate XGBoost (`--evaluate-only`, `--predict --file …`) |
| `test_accuracy.py` | Compare extraction vs `labels.json` |
| `generate_report.py` | Write accuracy report |
| `annotate_helper.py` | Build/edit `labels.json` |

Removed (unused): empty batch/HITL/jobs routes, root debug scripts, `scratch/`, legacy `app_models/`.

---

## 7. Files to know

| Path | Purpose |
|------|---------|
| `app/api/routes/upload.py` | Upload + hybrid flags |
| `app/services/extraction/field_extractor.py` | Pattern + regex extraction |
| `app/config/learned_patterns.json` | Active pattern pack |
| `models/v1/` | XGBoost routing pack |
| `training_data/annotated/labels.json` | Ground truth for ML |
| `app/services/orchestration/pipeline_orchestrator.py` | Clean → ERP |

---

## 8. Related docs

- **`PHASED_EXECUTION_PLAN.md`** — full file map + Phase 0–4 backlog
- **`pytest tests/test_smoke.py`** — CI smoke (training auth); full app: `pytest -m integration`

`POST /train` may require header `X-Training-Secret` when `TRAIN_API_SECRET` is set in `.env`.

---

*Last updated: hybrid upload flow with configurable auto-learn and ML signals.*
