# Invoice AI Service — System Documentation (Handoff)

**Audience:** Engineers, operators, and LLMs that need to understand this repository **from scratch** without prior context.

**Companion docs:** `ARCHITECTURE_AND_TRAINING_PLAN.md` (flow + training policy), `END_TO_END_GUIDE.md` (operational workflow), `scripts/README.md` (scripts index).

---

## 1. What this system is

This is a **Python FastAPI microservice** focused on **Indian GST-style invoices** (textile/wholesale layouts: Muskan, Gayatri, multi-invoice PDFs, etc.). It:

1. Accepts uploaded files (PDF, images, Excel, DOCX).
2. **Extracts text** (PDF text layer, OCR, or format-specific paths).
3. **Classifies** whether the document should be processed as a commercial invoice (vs register, balance sheet, random photos).
4. **Extracts structured fields and line items** using **learned label patterns**, **regex**, **format-specific profiles**, and optional **PDF table parsing**.
5. Runs a **post-processing pipeline**: cleaning → normalization → GST compliance hints → validation → confidence → **ERP-shaped JSON**.
6. Optionally attaches **ML “signals”** from an **XGBoost pack** (`models/v1`): these support **routing and HITL**; they do **not** replace field extraction today.

---

## 2. What this system is not (important for LLMs)

- **Not a generic “production ERP” deployment by default:** infra like PostgreSQL, Redis, Celery, MinIO may be referenced in settings, but **the main upload path is synchronous** and can run with **local disk + optional MinIO** (see `storage_service`).
- **e-Invoice / IRP integration:** compliance code may *mention* e-invoice applicability; there is **no live `app/services/einvoice/` package** in this tree. Treat e-invoice as **future / partial / documentation drift** unless reintroduced in code.
- **XGBoost does not extract values:** it predicts **invoice type** and **field presence** probabilities. **All buyer names, GSTINs, totals, and line items** come from **rules + patterns + formats** unless you add a separate value model later.

---

## 3. End-to-end story: from “zero” to “current behavior”

### 3.1 Bootstrap (developer)

| Step | What happens |
|------|----------------|
| Install | `pip install -r requirements.txt` (heavy: PaddleOCR stack, PDF libs, ML libs). Optional: `.venv`. |
| Configure | Copy `.env.example` → `.env`. Key toggles in `app/config/settings.py` (also env-overridable). |
| Run API | `uvicorn app.main:app --reload --host 0.0.0.0 --port 8000` |
| Patterns at startup | `app/main.py` lifespan calls **`load_learned_patterns()`** so `app/config/learned_patterns.json` is ready before traffic. |

### 3.2 Training data lifecycle (offline improvement)

Abbreviated pipeline:

```
training_data/raw/*.pdf          # Source PDFs
        ↓
training_data/ocr_cache/*.json   # Cached OCR / extracted text payloads
        ↓
POST /api/v1/train               # Re-learns patterns → learned_patterns.json
        ↓
python scripts/train_model.py    # Optional: builds XGBoost pack → models/v1/
```

- **`labels.json`** (`training_data/annotated/`) is used for **supervised ML training** (XGBoost path), not for directly driving pattern learning. Pattern learning scans **OCR cache text** for recurring label phrases.
- **`AUTO_LEARN_ON_UPLOAD`** (default `false`): when `true`, successful uploads can **append OCR cache** and **background-refresh** patterns (dev convenience; see `upload.py`).

### 3.3 Runtime: one upload (`POST /api/v1/upload`)

Implemented in **`app/api/routes/upload.py`**. High-level ordering:

```
Client file bytes
    → Size / MIME / basic malicious scan (`file_detector`, constants)
    → Optional duplicate short-circuit (`duplicate_detector` + in-memory/cache)
    → Storage upload (`storage_service` — MinIO if available, else local fallback)
    → universal_extractor.extract_text(...)     # OCR / PDF extraction
    → [optional] compute_ml_signals_sync(...)   # XGBoost hints if ML_SIGNALS_ON_UPLOAD && models/v1
    → document_classifier.classify(...)       # should_process gate
    → invoice_splitter.detect_and_split(...)  # multi-invoice PDF sections
    Per section:
        → field_extractor.extract_fields(...) # patterns + universal_structure + format_registry
        → table_extractor + format_enhancer   # line items (PDF tables vs text)
        → merge best line-item source
        → pipeline_orchestrator.process_fields(...)  # clean → normalize → compliance → validate → confidence → erp_schema
        → hybrid_scorer.build_hybrid_review(...)   # merges rule confidence + ml_signals
    → UploadResponse(extracted_data=...)
```

**Primary ERP output location in JSON:**  
`extracted_data.pipeline.erp_schema` (single invoice) or, for multi-invoice responses, each element under `extracted_data.invoices[]` carries the same per-invoice structure.

---

## 4. Repository layout (what lives where)

Root folder: `invoice_ai_service/`

```
invoice_ai_service/
├── app/
│   ├── main.py                 # FastAPI app, routers, middleware, lifespan (pattern preload)
│   ├── api/
│   │   ├── deps.py             # Optional API keys: verify_upload_api_key, verify_train_post_secret
│   │   └── routes/
│   │       ├── health.py       # Liveness-style endpoints
│   │       ├── upload.py       # Main extraction pipeline (sync)
│   │       ├── training.py     # POST/GET train, POST /train/ml (XGBoost retrain hook)
│   │       └── system.py       # Status / metrics for ops
│   ├── config/
│   │   ├── settings.py         # Pydantic-settings; all major toggles
│   │   └── learned_patterns.json   # Active pattern pack (generated, committed or rebuilt)
│   ├── core/                   # Exceptions, constants, logging
│   ├── models/                 # Pydantic response & domain models
│   └── services/
│       ├── extraction/         # OCR, PDF, fields, tables, formats, classifier, splitter
│       ├── training/           # pattern_learner, model_trainer, registry, retraining_manager, …
│       ├── orchestration/      # pipeline_orchestrator (main post-extraction chain)
│       ├── cleaning/           # Field cleaning
│       ├── normalization/      # Field / line-item normalization
│       ├── compliance/         # Indian GST-oriented checks and metadata
│       ├── validation/         # Business-rule validation
│       ├── mapping/            # ERP JSON schema assembly
│       ├── confidence/         # Field confidence + hybrid_review (with ML)
│       ├── intelligence/       # ML feature / signal helpers (if present)
│       └── utils/              # storage_service, file_detector, duplicate_detector, audit_logger, …
├── models/v1/                  # Trained XGBoost pack (routing/HITL), not source code
├── training_data/
│   ├── raw/                    # PDFs
│   ├── ocr_cache/              # JSON caches of extracted text
│   ├── annotated/labels.json # Ground truth for ML training (quality varies)
│   ├── exports/                # Optional export artifacts
│   └── models/                 # Optional training outputs / copies
├── scripts/                    # Operational & validation scripts (see scripts/README.md)
├── tests/                      # pytest; integration marked separately
├── frontend/                   # Static upload UI (mounted at /frontend)
├── storage/                    # Local upload fallback area
├── requirements.txt
├── pytest.ini
├── README.md                   # High-level; some bullets may predate code — trust this file + source
└── ARCHITECTURE_AND_TRAINING_PLAN.md
```

---

## 5. Code map: main modules and responsibilities

| Area | Key files | Role |
|------|-----------|------|
| HTTP entry | `app/main.py` | Routers, CORS, rate limit, exception handling, static frontend |
| Upload | `app/api/routes/upload.py` | Full sync pipeline; multi-invoice; auto-learn hook |
| Training API | `app/api/routes/training.py` | Pattern re-learn; ML retrain endpoints |
| System | `app/api/routes/system.py` | Operational visibility |
| Text in | `universal_extractor.py`, `pdf_extractor.py`, `image_extractor.py`, `paddle_ocr_extractor.py`, `docx_extractor.py` | Route bytes → text; engine selection |
| Understand doc | `document_classifier.py` | Accept/reject document types |
| Split | `invoice_splitter.py` | Multiple invoices in one PDF |
| Structure | `field_extractor.py`, `universal_structure_extractor.py`, `format_registry.py`, `format_enhancer.py` | Headers, amounts, items, vendor-specific fixes |
| Tables | `table_extractor.py` | pdfplumber / camelot / text fallbacks |
| Post-process | `pipeline_orchestrator.py` | Clean → normalize → compliance → validate → confidence → `erp_schema` |
| Hybrid HITL | `confidence/hybrid_scorer.py` | Combine rule-based scores with `ml_signals` |
| Patterns | `training/pattern_learner.py` | Build `learned_patterns.json` from `ocr_cache` |
| XGBoost | `training/model_trainer.py`, `retraining_manager.py`, `model_registry.py`, `scripts/train_model.py` | Train/serve routing pack under `models/v1` |
| Storage | `utils/storage_service.py` | MinIO with filesystem fallback |

---

## 6. Configuration (environment)

Defined in **`app/config/settings.py`** (reads `.env`). Especially important:

| Variable | Typical default | Meaning |
|----------|-----------------|--------|
| `API_V1_PREFIX` | `/api/v1` | All versioned routes |
| `DEFAULT_OCR_ENGINE` | `paddleocr` | Fallback cascades may still use PDF text / Tesseract depending on path |
| `AUTO_LEARN_ON_UPLOAD` | `false` | Save `ocr_cache` + background pattern refresh on upload |
| `ML_SIGNALS_ON_UPLOAD` | `true` | Attach XGBoost-derived `ml_signals` when model dir exists |
| `ML_MODEL_DIR` | `models/v1` | XGBoost pack location |
| `TRAIN_API_SECRET` | optional | If set, training POSTs need `X-Training-Secret` |
| `UPLOAD_API_KEY` | optional | If set, upload needs `X-API-Key` |

Database/Redis/Celery/MinIO URLs exist for **future** or **optional** integrations; **`upload` remains synchronous`** in this codebase snapshot.

---

## 7. Web frontend (static UI)

The app **mounts** the `frontend/` folder in **`app/main.py`** as static files:

| URL | What you get |
|-----|----------------|
| **http://localhost:8000/frontend/** or **.../frontend/index.html** | Invoice upload page (primary UI) |
| **http://localhost:8000/** | Small JSON with `docs` and `frontend` links |

**Files on disk:**

```
frontend/
├── index.html          # Page layout, inline JS (upload + results table + modals)
├── static/css/styles.css
└── static/js/app.js    # Placeholder; real logic is in index.html <script>
```

**Behavior:**

- **`POST /api/v1/upload`** with `multipart/form-data`: fields **`file`** (required) and **`ocr_engine`** (optional dropdown: `google_vision`, `paddleocr`, `tesseract`). Same as API; see **`upload_invoice`** in `app/api/routes/upload.py`.
- Uses **relative** `fetch('/api/v1/upload', ...)`, so the page must be served from the **same origin** as the API (open via the URLs above). Opening `index.html` as `file://` will fail CORS/origin-wise.
- While upload is in flight, the loading modal **cycles generic stages** (reading file → OCR → classify → …). **Exact** steps appear after the response returns in **`processing_log`** (sync API — no live SSE yet). The page has a **Processing log** `<pre>` showing those lines.
- If **`UPLOAD_API_KEY`** is set in `.env`, the frontend **does not** send `X-API-Key`; use curl/Postman or extend the JS to pass the header. For unsecured dev servers, uploads from the UI work without the header.

---

## 8. REST API endpoints (reference)

Unless you change **`API_V1_PREFIX`** in `.env`, **`{prefix}`** = **`/api/v1`**.

### 8.1 Core & documentation (no version prefix on these)

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/` | Service name, version, links to `/docs` and frontend |
| GET | `/docs` | Swagger UI (interactive API) |
| GET | `/redoc` | ReDoc |

### 8.2 Health & readiness (`{prefix}`)

| Method | Path | Purpose |
|--------|------|---------|
| GET | `{prefix}/health` | Liveness-style check; probes MinIO, Redis, DB, Tesseract and returns dependency map (failures logged; overall still often 200 — see `health.py`) |
| GET | `{prefix}/ready` | Simple `{"status":"ready"}` for k8s-style readiness |

### 8.3 Upload & extraction (`{prefix}`)

| Method | Path | Purpose |
|--------|------|---------|
| POST | `{prefix}/upload` | **Main pipeline:** file upload → OCR → classify → extract → pipeline → ERP JSON. **Form:** `file` (required), `force_reprocess` (optional bool), `ocr_engine` (optional: e.g. `paddleocr`, `tesseract`, `google_vision`). **Header (optional):** `X-API-Key` if `UPLOAD_API_KEY` is set — see `app/api/deps.py`. |
| GET | `{prefix}/upload/test` | Static JSON confirming the upload route is registered |

### 8.4 Training & patterns (`{prefix}`)

| Method | Path | Purpose |
|--------|------|---------|
| POST | `{prefix}/train` | Re-learn **`app/config/learned_patterns.json`** from all **`training_data/ocr_cache/*.json`**. **Header (optional):** `X-Training-Secret` matching `TRAIN_API_SECRET`. |
| GET | `{prefix}/train` | Read-only stats: trained doc counts, field keys, column headers, doc-type signals (`training.py`). |
| POST | `{prefix}/train/ml` | Starts **background** XGBoost retrain via **`RetrainingManager`** → **`models/v1/`**. Returns 409 if already running. **Header (optional):** `X-Training-Secret` when `TRAIN_API_SECRET` is set. |
| GET | `{prefix}/train/ml/status` | `{ training_in_progress, model_pack_exists, model_dir }` |

### 8.5 System / ops (`{prefix}`)

| Method | Path | Purpose |
|--------|------|---------|
| GET | `{prefix}/system/status` | Config flags, training_data counts, pattern meta, **`xgboost_pack_exists`**, phase checklist |
| GET | `{prefix}/system/metrics` | e.g. duplicate-cache size, HITL threshold (`system.py`) |

**Response models and exact JSON fields:** **`app/models/response.py`** and OpenAPI at **`/docs`**.

---

## 9. Testing and validation scripts

| Command / script | What it verifies |
|------------------|------------------|
| `pytest tests/ -m "not integration"` | Fast suite: routers, classifier, hybrid, golden OCR-cache extractions |
| `scripts/run_tests.sh` | Creates/uses `.venv`, installs deps, pytest + eval + e2e |
| `scripts/e2e_validate.py` | pytest + OpenAPI routes + golden caches + optional PDF smoke |
| `scripts/eval_ocr_cache.py` | Batch quality table over cached OCR JSONs |
| `scripts/build_ocr_cache.py` | Populate `ocr_cache` from `raw/` |

---

## 10. Typical response shape (single invoice)

**Top-level `UploadResponse`** also includes **`processing_log`**: an ordered list of short human-readable strings (OCR → classify → split → fields/items → pipeline). The static frontend shows this in the **Processing log** panel after each upload.

`UploadResponse.extracted_data` is a dict-like payload. Important nested keys:

- **`invoice_data`** — raw-ish extracted fields (buyer, supplier, taxes, items, …).
- **`pipeline`** — `erp_schema`, `confidence`, `validation`, `compliance`, normalized fields mirror.
- **`ml_signals`** — optional; routing / presence probs.
- **`hybrid_review`** — merged guidance for human review thresholds.

Multi-invoice responses wrap **`invoices`** array at the top of `extracted_data` plus shared metadata (`invoice_count`, …).

---

## 11. How to onboard an LLM in one paragraph (paste-worthy)

“This repo is a **FastAPI service** (`app/main.py`) that processes invoice files in **`upload.py`**: extract text (`services/extraction/*`), classify and split invoices, extract fields/items via **`learned_patterns.json`** and **format rules**, then **`pipeline_orchestrator.process_fields`** produces **`pipeline.erp_schema`**. **`models/v1` XGBoost** only adds **`ml_signals`** for HITL/routing. Training: put PDFs in **`training_data/raw`**, OCR JSON in **`training_data/ocr_cache`**, call **`POST /api/v1/train`** for patterns; use **`scripts/train_model.py`** for ML. **`ARCHITECTURE_AND_TRAINING_PLAN.md`** describes the same flow in shorter form.”

---

## 12. Drift checklist (when README vs code disagrees)

If something below appears in **`README.md`** but not in code, assume **README is stale**:

- Dedicated `app/services/einvoice/` package.
- Guaranteed async job queue for every upload (Celery path may not be wired to `/upload`).
- “Production” without securing `UPLOAD_API_KEY` / `TRAIN_API_SECRET`.

**Truth order:** runnable code → this document → `ARCHITECTURE_AND_TRAINING_PLAN.md` → `README.md`.

---

## 13. Suggested next work (product / engineering)

- Expand **golden tests** per vendor layout (not only 188 / 184-185).
- Clean **`labels.json`** before trusting ML metrics.
- **Value extraction model** (NER / layout LM) if XGBoost should ever drive amounts.
- Lock down **optional auth headers** for any exposed deployment.

---

*Document generated for repository handoff. Update sections 2 and 11 when major modules (e.g. e-invoice) are added or removed.*
http://localhost:8001/frontend/