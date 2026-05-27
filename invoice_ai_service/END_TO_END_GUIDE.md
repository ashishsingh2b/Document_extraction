# End-to-end guide — Invoice AI service

Complete flow from **your training PDFs** → **ERP JSON** on upload.

---

## Architecture (all phases)

```
training_data/raw/*.pdf
        │
        ▼  python scripts/build_ocr_cache.py
training_data/ocr_cache/*.json
        │
        ├── POST /api/v1/train          → learned_patterns.json
        └── POST /api/v1/train/ml       → models/v1/ (XGBoost routing)

Person uploads PDF
        │
        ▼
   OCR / PDF text
        │
        ▼
   Classify (reject balance sheet / register)
        │
        ▼
   Extract fields (patterns + regex + formats)
        │
        ▼
   ml_signals (XGBoost — routing only)
        │
        ▼
   hybrid_review (rules + ML → HITL flags)
        │
        ▼
   Clean → GST → Validate → ERP schema
        │
        ▼
   JSON response (pipeline.erp_schema)
```

---

## Phase checklist

| Phase | What | Status |
|-------|------|--------|
| **0** | Clean codebase, config flags, docs, smoke tests | Done |
| **1** | Extraction quality, golden tests, `eval_ocr_cache.py` | Done (ongoing tuning) |
| **2** | `hybrid_review` on every upload | Done |
| **3** | `POST /train/ml` + CLI `train_model.py` | Done |
| **4** | `UPLOAD_API_KEY`, `TRAIN_API_SECRET`, `/system/status` | Done |
| **Future** | NER/layout model for field **values** | Planned |

---

## Setup (once)

```bash
cd invoice_ai_service
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
docker-compose up -d   # optional: MinIO, Redis, Postgres
cp .env.example .env   # edit secrets if needed
```

---

## Training workflow (your data)

### 1. Put PDFs in `training_data/raw/`

You already have OCR cache for many files; add new PDFs to `raw/` when needed.

### 2. Build / refresh OCR cache

```bash
python scripts/build_ocr_cache.py
```

### 3. Learn patterns (layout labels)

```bash
curl -X POST http://localhost:8000/api/v1/train \
  -H "X-Training-Secret: YOUR_SECRET"   # if TRAIN_API_SECRET set
```

### 4. Train XGBoost (routing / HITL)

```bash
# Fix labels in training_data/annotated/labels.json first
python scripts/train_model.py

# Or via API (background):
curl -X POST http://localhost:8000/api/v1/train/ml \
  -H "X-Training-Secret: YOUR_SECRET"
curl http://localhost:8000/api/v1/train/ml/status
```

### 5. Evaluate

```bash
python scripts/eval_ocr_cache.py
python scripts/test_accuracy.py
pytest tests/ -q -m "not integration"
```

---

## Run API

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

| URL | Purpose |
|-----|---------|
| http://localhost:8000/docs | Swagger |
| http://localhost:8000/frontend/index.html | Upload UI |
| GET /api/v1/system/status | Phase + data counts |
| POST /api/v1/upload | Extract invoice |

### Upload example

```bash
curl -X POST http://localhost:8000/api/v1/upload \
  -H "X-API-Key: YOUR_KEY" \
  -F "file=@training_data/raw/traininngtestdata.pdf" \
  -F "ocr_engine=paddleocr"
```

### Response keys

| Key | Meaning |
|-----|---------|
| `extracted_data.invoice_data` | Raw fields |
| `extracted_data.pipeline.erp_schema` | **ERP output** |
| `extracted_data.ml_signals` | XGBoost type + field presence probs |
| `extracted_data.hybrid_review` | Combined confidence + `review_fields` for HITL |

---

## Environment (.env)

| Variable | Default | Purpose |
|----------|---------|---------|
| `AUTO_LEARN_ON_UPLOAD` | `false` | Do not retrain patterns on every upload |
| `ML_SIGNALS_ON_UPLOAD` | `true` | Attach XGBoost signals |
| `ML_MODEL_DIR` | `models/v1` | Model pack path |
| `TRAIN_API_SECRET` | empty | Protect POST `/train` and `/train/ml` |
| `UPLOAD_API_KEY` | empty | Protect POST `/upload` |

---

## What XGBoost does **not** do

It does **not** replace regex/patterns for invoice number, amounts, or line items. It only helps **routing and HITL** until a value model (Phase 3 future) is added.

---

## Related docs

- `ARCHITECTURE_AND_TRAINING_PLAN.md` — design + XGBoost role  
- `PHASED_EXECUTION_PLAN.md` — file map + phase backlog  
