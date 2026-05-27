# Phased execution plan — Invoice AI service

**Status: Phases 0–4 implemented.** See `END_TO_END_GUIDE.md` for how to run everything.

---

## 1. Runtime flow

```
Client → POST /api/v1/upload → OCR → classify → extract → ml_signals → hybrid_review
      → pipeline (clean, GST, validate) → erp_schema

Admin → POST /api/v1/train (patterns) | POST /api/v1/train/ml (XGBoost)
      → GET /api/v1/system/status
```

---

## 2. Phases

### Phase 0 — Stabilise & observe ✅

- [x] Dead code removed; hybrid config; `ml_signals` on upload
- [x] `TRAIN_API_SECRET`, smoke tests, architecture docs

### Phase 1 — Extraction quality ✅ (tune ongoing)

- [x] Golden test `188.pdf.json`
- [x] `scripts/eval_ocr_cache.py`, `scripts/build_ocr_cache.py`
- [x] Muskan buyer/tax fixes; reject balance sheet / register uploads
- [ ] Expand golden tests per vendor; clean `labels.json` continuously

### Phase 2 — Hybrid HITL ✅

- [x] `app/services/confidence/hybrid_scorer.py`
- [x] `hybrid_review` on upload response

### Phase 3 — ML training path ✅

- [x] `POST /api/v1/train/ml` + `GET /api/v1/train/ml/status`
- [x] `scripts/train_model.py`
- [ ] Future: NER/layout model for field **values** on upload

### Phase 4 — Operations ✅

- [x] Optional `UPLOAD_API_KEY` on upload
- [x] `GET /api/v1/system/status`, `/system/metrics`
- [ ] Future: Redis duplicate cache, Celery async, Prometheus

---

## 3. Training data layout

| Path | Role |
|------|------|
| `training_data/raw/` | Source PDFs |
| `training_data/ocr_cache/` | Cached OCR JSON |
| `training_data/annotated/labels.json` | Ground truth for ML |
| `app/config/learned_patterns.json` | Pattern pack |
| `models/v1/` | XGBoost pack |

---

## 4. Commands

```bash
python scripts/build_ocr_cache.py
curl -X POST http://localhost:8000/api/v1/train
python scripts/train_model.py
python scripts/eval_ocr_cache.py
pytest tests/ -q -m "not integration"
curl http://localhost:8000/api/v1/system/status
```
