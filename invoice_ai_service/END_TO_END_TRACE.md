# End-to-end call trace (upload → ERP JSON)

Use the **server terminal** (stdout from `uvicorn`) or **`logs/app.log`**— every step is echoed as **`[E2E] …`** from `app/api/routes/upload.py` (`_progress` and the SSE header loop).

Legend: **▶ CALL** = entering · **✓ DONE** / **✓** = finished · **⊘ SKIP** = not run (config) · **▶ DECISION** / **▶ MODE** = branch · **── PHASE ──** = stage boundary.

---

## Response modes

| Mode | How to request | Trace output |
|------|----------------|----------------|
| **Default (JSON)** | `POST /api/v1/upload` (multipart) | **`[E2E]`** lines only on **server terminal / app.log** (bundled web UI uses this) |
| **SSE stream** | `POST .../upload?stream=true` | Same **`[E2E]`** on terminal **plus** `text/event-stream` events for programmatic clients |

Filter logs: **`grep '[E2E]' logs/app.log`**

---

## Phase 0 — HTTP handler (`upload_invoice`)

| Order | Function | When |
|-------|----------|------|
| 1 | `file_detector.detect_file_type` | Always |
| 2 | `file_detector.get_extractor_type` | Validates MIME is supported |
| 3 | `duplicate_detector.calculate_hash` | Always |
| 4 | `duplicate_detector.check_duplicate` | Unless `force_reprocess=true` |
| 5 | `storage_service.upload_file` | Cache miss only (MinIO or `storage/uploads/`) |
| 6 | `audit_logger.log_upload` | Cache miss only |
| 7 | `_process_invoice_sync` or SSE worker | Cache miss only |

**Config shown in banner:** `ocr_engine`, `ML_SIGNALS_ON_UPLOAD`, `AUTO_LEARN_ON_UPLOAD`, `response_mode`.

---

## Phase 1 — Text extraction (`_process_invoice_sync`)

| Order | Function | Notes |
|-------|----------|-------|
| 1 | `universal_extractor.extract_text` | Routes to PDF/image/Excel/DOCX extractors; uses `ocr_engine` form field or `.env` `DEFAULT_OCR_ENGINE` |
| 2 | `universal_extractor.compute_ml_signals_sync` | **Only if** `ML_SIGNALS_ON_UPLOAD=true` — routing/HITL, **not** field values |
| 3 | `document_classifier.classify` | **Rejects** registers, balance sheets, etc. (`should_process=false` → error) |
| 4 | `invoice_splitter.detect_and_split` | 1 section = single invoice; N>1 = multi-invoice loop |

---

## Phase 5 — Per invoice (`_process_single_invoice`)

Runs once (single PDF) or N times (multi-invoice).

| Order | Function | Notes |
|-------|----------|-------|
| 1 | `field_extractor.extract_fields` | `learned_patterns.json` + `format_registry` + regex |
| 2 | `table_extractor.parse_line_items_from_text` | OCR text line patterns |
| 3 | `table_extractor.extract_tables` | PDF only — pdfplumber/camelot |
| 4 | `table_extractor.parse_line_items` | From PDF tables if found |
| 5 | `format_enhancer.enhance_line_items` | If format profile detected |
| 6 | Merge decision | More items wins: table/text vs `field_extractor` regex |
| 7 | `field_extractor._calculate_confidence` | Header field confidence % |
| 8 | `pipeline_orchestrator.process_fields` | See Phase 6 |
| 9 | `build_hybrid_review` | Rules + optional ML presence probs |

---

## Phase 6 — Pipeline (`pipeline_orchestrator.process_fields`)

Internal order (same thread, not separate SSE lines today):

1. `DataCleaner.clean_extracted_fields`
2. `FieldMapper.normalize_fields` + `normalize_line_item`
3. `ComplianceEngine.validate` (GST hints)
4. `InvoiceValidator.validate`
5. `FieldConfidenceScorer.score_fields`
6. `ERPMapper.erp_schema_from_fields` → **`extracted_data.pipeline.erp_schema`**

---

## Optional post-upload (`AUTO_LEARN_ON_UPLOAD`)

| Function | When |
|----------|------|
| `_auto_save_and_learn` | `AUTO_LEARN_ON_UPLOAD=true` only |
| → write `training_data/ocr_cache/{filename}.json` | |
| → `pattern_learner.learn_from_all_training_data` | Background thread |

---

## Quick verification checklist

After one upload you should see **in order**:

1. E2E banner with `job_id`, `response_mode`, `ocr_engine`, flags  
2. `▶ CALL universal_extractor.extract_text` → `✓ DONE` with char count  
3. ML block: either `▶ CALL compute_ml_signals_sync` or `⊘ SKIP`  
4. `document_classifier.classify` → `should_process=True`  
5. `invoice_splitter` → section count  
6. `field_extractor.extract_fields` → format id (e.g. `muskan_glued`)  
7. Table path and/or `▶ DECISION merge items`  
8. `pipeline_orchestrator.process_fields` → confidence + valid + hitl  
9. `══ COMPLETE ══`

If anything is **missing** or **out of order**, compare to this doc and the source in `app/api/routes/upload.py`.
