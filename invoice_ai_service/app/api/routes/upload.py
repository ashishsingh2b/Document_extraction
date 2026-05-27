"""File upload endpoints."""

import asyncio
import json
import logging
import threading
import uuid
from pathlib import Path
from typing import Any, AsyncIterator, Callable, Dict, List, Optional, Union

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import StreamingResponse

from app.models.response import UploadResponse
from app.core.exceptions import (
    FileSizeExceededError,
    UnsupportedFormatError,
    MaliciousFileError,
)
from app.core.constants import MAX_FILE_SIZE_BYTES
from app.services.utils.storage_service import storage_service
from app.services.utils.file_detector import file_detector
from app.services.utils.duplicate_detector import duplicate_detector
from app.services.utils.audit_logger import audit_logger
from app.services.extraction.universal_extractor import universal_extractor
from app.services.extraction.field_extractor import field_extractor
from app.services.extraction.document_classifier import document_classifier
from app.services.extraction.table_extractor import table_extractor
from app.services.extraction.invoice_splitter import invoice_splitter
from app.services.orchestration.pipeline_orchestrator import pipeline_orchestrator
from app.config.settings import settings
from app.api.deps import verify_upload_api_key
from app.services.confidence.hybrid_scorer import build_hybrid_review

router = APIRouter()
logger = logging.getLogger(__name__)


def _progress(
    log: List[str],
    message: str,
    on_progress: Optional[Callable[[str], None]] = None,
) -> None:
    """Append one line to the upload log; optionally push to SSE/stream callback (same thread)."""
    log.append(message)
    if on_progress:
        try:
            on_progress(message)
        except Exception:
            logger.debug("on_progress callback failed", exc_info=True)


def _sse_data(obj: Dict[str, Any]) -> bytes:
    return f"data: {json.dumps(obj, default=str)}\n\n".encode("utf-8")


async def _upload_sse_events(
    *,
    job_id: str,
    file_data: bytes,
    mime_type: str,
    filename: str,
    ocr_engine: Optional[str],
    file_hash: str,
    duplicate_payload: Optional[Dict[str, Any]],
) -> AsyncIterator[bytes]:
    """Server-sent events: `log` lines as processing runs, then `complete` or `error`."""
    if duplicate_payload is not None:
        yield _sse_data({"type": "log", "line": "Returning cached result (duplicate file hash)."})
        yield _sse_data({"type": "complete", "payload": duplicate_payload})
        return

    loop = asyncio.get_running_loop()
    q: asyncio.Queue = asyncio.Queue(maxsize=512)
    result_holder: Dict[str, Any] = {}
    error_detail: Optional[str] = None

    def on_progress(line: str) -> None:
        asyncio.run_coroutine_threadsafe(q.put(line), loop)

    def worker() -> None:
        nonlocal error_detail
        try:
            res = _process_invoice_sync(
                job_id,
                file_data,
                mime_type,
                filename,
                ocr_engine,
                on_progress=on_progress,
            )
            result_holder["res"] = res
        except Exception as e:
            error_detail = str(e)
            logger.exception("Streaming upload pipeline failed")
        finally:
            asyncio.run_coroutine_threadsafe(q.put(None), loop)

    threading.Thread(target=worker, daemon=True).start()

    while True:
        item = await q.get()
        if item is None:
            break
        yield _sse_data({"type": "log", "line": item})

    if error_detail is not None:
        yield _sse_data({"type": "error", "detail": error_detail})
        return

    res: UploadResponse = result_holder["res"]
    duplicate_detector.store_result(file_hash, res.model_dump())

    payload = res.model_dump(mode="json")
    yield _sse_data({"type": "complete", "payload": payload})


@router.post("/upload", dependencies=[Depends(verify_upload_api_key)])
async def upload_invoice(
    request: Request,
    file: UploadFile = File(...),
    force_reprocess: bool = Form(False),
    ocr_engine: Optional[str] = Form(None),
    stream: bool = Query(
        False,
        description="If true, returns text/event-stream: log events then a complete UploadResponse payload",
    ),
) -> Union[UploadResponse, StreamingResponse]:
    """
    Upload invoice file for processing.
    
    Supports: PDF, Image (JPG/PNG), Excel (XLSX), DOCX
    Max file size: 50MB
    
    Args:
        file: Invoice file to upload
        force_reprocess: Force reprocessing even if duplicate
        ocr_engine: OCR engine to use ('tesseract' or 'paddleocr'). 
                   If not specified, uses DEFAULT_OCR_ENGINE from .env
    
    Returns:
        UploadResponse with extracted data
    """
    job_id = str(uuid.uuid4())
    request_id = getattr(request.state, "request_id", None)
    
    try:
        # Read file data
        file_data = await file.read()
        file_size = len(file_data)
        
        # Check file size
        if file_size > MAX_FILE_SIZE_BYTES:
            raise FileSizeExceededError(
                f"File size {file_size} bytes exceeds maximum {MAX_FILE_SIZE_BYTES} bytes"
            )
        
        # Security scanning (basic check for now)
        if b"<script" in file_data.lower() or b"<?php" in file_data.lower():
            raise MaliciousFileError("File contains potentially malicious content")
        
        # Detect file type
        mime_type, _file_extension = file_detector.detect_file_type(
            file_data,
            file.filename,
        )
        file_detector.get_extractor_type(mime_type)  # validates supported type

        # Check for duplicates
        file_hash = duplicate_detector.calculate_hash(file_data)
        if not force_reprocess:
            cached_result = duplicate_detector.check_duplicate(file_hash)
            if cached_result is not None:
                logger.info(f"Returning cached result for duplicate file: {file_hash}")
                if stream:
                    dup_payload = (
                        cached_result
                        if isinstance(cached_result, dict)
                        else cached_result.model_dump(mode="json")
                    )
                    return StreamingResponse(
                        _upload_sse_events(
                            job_id=job_id,
                            file_data=file_data,
                            mime_type=mime_type,
                            filename=file.filename or "upload",
                            ocr_engine=ocr_engine,
                            file_hash=file_hash,
                            duplicate_payload=dup_payload,
                        ),
                        media_type="text/event-stream",
                    )
                return cached_result

        # Upload to MinIO
        storage_service.upload_file(file_data, file.filename, mime_type)

        # Log upload event
        audit_logger.log_upload(
            job_id=job_id,
            filename=file.filename,
            file_size=file_size,
            user_id=None
        )

        logger.info(
            f"Processing job {job_id} synchronously with OCR engine: {ocr_engine or 'default'} "
            f"(stream={stream})"
        )

        if stream:
            return StreamingResponse(
                _upload_sse_events(
                    job_id=job_id,
                    file_data=file_data,
                    mime_type=mime_type,
                    filename=file.filename or "upload",
                    ocr_engine=ocr_engine,
                    file_hash=file_hash,
                    duplicate_payload=None,
                ),
                media_type="text/event-stream",
            )

        result = _process_invoice_sync(job_id, file_data, mime_type, file.filename, ocr_engine)
        duplicate_detector.store_result(file_hash, result.model_dump())
        return result
        
    except (FileSizeExceededError, UnsupportedFormatError, MaliciousFileError) as e:
        logger.error(f"Upload error for job {job_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Unexpected error for job {job_id}: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error during file upload"
        )


@router.get("/upload/test")
async def test_upload():
    """Test endpoint to verify upload route is working."""
    return {"message": "Upload endpoint is ready"}



def _process_invoice_sync(
    job_id: str,
    file_data: bytes,
    mime_type: str,
    filename: str,
    ocr_engine: str = None,
    on_progress: Optional[Callable[[str], None]] = None,
):
    """Process invoice synchronously and return UploadResponse."""
    plog: List[str] = []

    def _p(m: str) -> None:
        _progress(plog, m, on_progress)

    try:
        logger.info("=" * 80)
        logger.info(f"STARTING EXTRACTION FOR: {filename}")
        logger.info("=" * 80)
        _p(f"Starting extraction — job {job_id[:8]}… · {filename} ({mime_type})")
        
        # Step 1: Extract text from file
        logger.info(f"[STEP 1] Extracting text from file (type: {mime_type})...")
        
        effective_ocr = ocr_engine or "default"
        logger.info(f"OCR engine requested: {effective_ocr}")
        _p(f"Step 1/6: Extracting text (OCR/engine: {effective_ocr})…")
        extraction_result = universal_extractor.extract_text(file_data, mime_type, ocr_engine)
        
        if not extraction_result.get("success"):
            raise Exception(f"Text extraction failed: {extraction_result.get('error')}")
        
        extracted_text = extraction_result.get("text", "")
        logger.info(f"[STEP 1] ✓ Extracted {len(extracted_text)} characters using {extraction_result.get('extraction_method')}")
        _p(
            f"Step 1 complete: {len(extracted_text)} characters via {extraction_result.get('extraction_method')}",
        )
        logger.info(f"[STEP 1] Text Preview (first 300 chars):")
        logger.info("-" * 80)
        logger.info(extracted_text[:300])
        logger.info("-" * 80)

        ml_signals = None
        if settings.ML_SIGNALS_ON_UPLOAD:
            ml_signals = universal_extractor.compute_ml_signals_sync(
                extracted_text, extraction_result, model_dir=settings.ML_MODEL_DIR
            )
            if ml_signals:
                logger.info(f"[STEP 1b] ML signals (routing/HITL only): invoice_type_pred={ml_signals.get('invoice_type_prediction')}")
                _p(
                    f"Step 2a: ML signals — type_hint={ml_signals.get('invoice_type_prediction')!r}",
                )

        # Step 2: Classify document type
        logger.info(f"[STEP 2] Classifying document type...")
        _p("Step 2/6: Classifying document (invoice vs non-invoice)…")
        classification = document_classifier.classify(extracted_text, filename)
        
        logger.info(f"[STEP 2] ✓ Document Type: {classification['document_type']}")
        logger.info(f"[STEP 2] ✓ Confidence: {classification['confidence']:.2f}")
        logger.info(f"[STEP 2] ✓ Reason: {classification['reason']}")
        logger.info(f"[STEP 2] ✓ Should Process: {classification['should_process']}")
        
        if not classification['should_process']:
            # Not an invoice - reject
            logger.warning(f"[STEP 2] ✗ Document REJECTED - {classification['document_type']}")
            raise Exception(
                f"Document type '{classification['document_type']}' is not supported. "
                f"Only sales and purchase invoices are accepted. "
                f"Reason: {classification['reason']}"
            )
        _p(
            f"Step 2 complete: type={classification['document_type']} "
            f"confidence={classification['confidence']:.0%} proceed=yes",
        )
        
        # Step 2.5: Detect and split multi-invoice PDFs
        logger.info(f"[STEP 2.5] Detecting invoice boundaries...")
        _p("Step 3/6: Detecting invoice boundaries (single vs multi-invoice)…")
        invoice_sections = invoice_splitter.detect_and_split(extracted_text)
        
        if len(invoice_sections) > 1:
            logger.info(f"[STEP 2.5] ✓ Multi-invoice PDF: {len(invoice_sections)} invoices detected")
            _p(f"Multi-invoice PDF: {len(invoice_sections)} sections to process")
            for i, section in enumerate(invoice_sections, 1):
                logger.info(f"  Invoice {i}: #{section.get('invoice_number')} ({len(section.get('text', ''))} chars)")
            
            # Process each invoice separately
            all_invoices = []
            for i, section in enumerate(invoice_sections, 1):
                logger.info(f"\n{'='*80}")
                logger.info(f"PROCESSING INVOICE {i}/{len(invoice_sections)}: #{section.get('invoice_number')}")
                logger.info(f"{'='*80}")
                _p(f"── Invoice {i}/{len(invoice_sections)} (section chars: {len(section.get('text', '') or '')}) ──")

                invoice_text = section.get('text', '')
                invoice_data = _process_single_invoice(
                    invoice_text,
                    file_data,
                    mime_type,
                    extraction_result.get('extraction_method'),
                    ocr_engine,
                    classification,
                    i,
                    pages=section.get('pages'),
                    ml_signals=ml_signals,
                    progress_log=plog,
                    on_progress=on_progress,
                )
                all_invoices.append(invoice_data)
            
            # Return response with multiple invoices
            logger.info(f"\n{'='*80}")
            logger.info(f"[SUMMARY] Processed {len(all_invoices)} invoices from multi-invoice PDF")
            logger.info(f"{'='*80}")
            
            _maybe_auto_save_and_learn(extracted_text, filename)

            payload = {
                "extraction_method": extraction_result.get("extraction_method"),
                "document_type": classification['document_type'],
                "classification_confidence": classification['confidence'],
                "invoice_count": len(all_invoices),
                "invoices": all_invoices,
            }
            if ml_signals:
                payload["ml_signals"] = ml_signals

            _p(f"Finished: {len(all_invoices)} invoice(s) — done")
            return UploadResponse(
                status="completed",
                job_id=job_id,
                message=f"Multi-invoice PDF processed successfully: {len(all_invoices)} invoices extracted",
                file_name=filename,
                file_size=len(file_data),
                request_id=None,
                extracted_data=payload,
                processing_log=plog,
            )
        else:
            logger.info(f"[STEP 2.5] ✓ Single invoice detected")
            _p("Single invoice detected — extracting fields and line items")

            # Process single invoice
            single_section = invoice_sections[0] if invoice_sections else {}
            invoice_data = _process_single_invoice(
                extracted_text,
                file_data,
                mime_type,
                extraction_result.get('extraction_method'),
                ocr_engine,
                classification,
                1,
                pages=single_section.get('pages'),
                ml_signals=ml_signals,
                progress_log=plog,
                on_progress=on_progress,
            )

            _maybe_auto_save_and_learn(extracted_text, filename)

            _p("Finished — ERP schema ready in response.pipeline")
            return UploadResponse(
                status="completed",
                job_id=job_id,
                message="Invoice processed successfully",
                file_name=filename,
                file_size=len(file_data),
                request_id=None,
                extracted_data=invoice_data,
                processing_log=plog,
            )
        
    except Exception as e:
        logger.error("=" * 80)
        logger.error(f"[ERROR] Processing failed for {filename}")
        logger.error(f"[ERROR] {str(e)}")
        logger.error("=" * 80)
        raise Exception(f"Processing error: {str(e)}")


# ─────────────────────────────────────────────────────────────────────────────
# Internal: auto-learn helpers
# ─────────────────────────────────────────────────────────────────────────────

_OCR_CACHE = Path(__file__).resolve().parents[3] / "training_data" / "ocr_cache"
_LEARN_LOCK = threading.Lock()
_PENDING_LEARN = False


def _maybe_auto_save_and_learn(text: str, filename: str) -> None:
    """When AUTO_LEARN_ON_UPLOAD is true: cache OCR text and refresh learned_patterns (dev/testing)."""
    if not settings.AUTO_LEARN_ON_UPLOAD:
        return
    _auto_save_and_learn(text, filename)


def _auto_save_and_learn(text: str, filename: str) -> None:
    """
    1. Save the extracted OCR text to training_data/ocr_cache/ so future
       training runs include it.
    2. Trigger a background thread to refresh learned_patterns.json.
       Uses a lock so only one re-learn runs at a time; batches rapid uploads.
    """
    global _PENDING_LEARN
    try:
        # Save OCR text to cache
        _OCR_CACHE.mkdir(parents=True, exist_ok=True)
        safe_name = Path(filename).name + ".json"
        cache_path = _OCR_CACHE / safe_name
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump({"ocr_result": {"text": text}}, f, ensure_ascii=False)
        logger.info(f"[AUTO-LEARN] Saved OCR text to {cache_path.name}")
    except Exception as e:
        logger.warning(f"[AUTO-LEARN] Could not save OCR cache: {e}")

    # Schedule background re-learn (debounced: only one at a time)
    def _background_learn():
        global _PENDING_LEARN
        try:
            with _LEARN_LOCK:
                _PENDING_LEARN = False
                from app.services.training.pattern_learner import learn_from_all_training_data
                import app.services.training.pattern_learner as pl
                learn_from_all_training_data()
                pl._PATTERNS_CACHE = None  # invalidate cache so next extraction uses fresh patterns
                logger.info("[AUTO-LEARN] Pattern re-learning complete — system updated")
        except Exception as e:
            logger.warning(f"[AUTO-LEARN] Background re-learn failed: {e}")

    if not _PENDING_LEARN:
        _PENDING_LEARN = True
        t = threading.Thread(target=_background_learn, daemon=True)
        t.start()


def _extract_line_items(
    invoice_text: str,
    file_data: bytes,
    mime_type: str,
    invoice_number: int,
    format_id: str = None,
    pages: Optional[list[int]] = None,
) -> list:
    """Extract line items: PDF tables first (filtered by pages if specified), then OCR text patterns."""
    line_items = []

    text_items = table_extractor.parse_line_items_from_text(invoice_text, format_id=format_id)

    def _finalize_items(items: list) -> list:
        if format_id and items:
            from app.services.extraction.format_enhancer import enhance_line_items
            return enhance_line_items(invoice_text, items, format_id)
        return items

    if mime_type == "application/pdf" and (invoice_number == 1 or pages is not None):
        logger.info(f"[STEP 3] Trying PDF table extraction (pdfplumber/camelot) on pages {pages or 'all'}...")
        tables_result = table_extractor.extract_tables(file_data, pages=pages)
        if tables_result.get("table_count", 0) > 0:
            pdf_items = table_extractor.parse_line_items(tables_result.get("tables", []))
            if pdf_items:
                logger.info(f"[STEP 3] PDF tables yielded {len(pdf_items)} line items")
                if len(text_items) > len(pdf_items):
                    logger.info(
                        f"[STEP 3] OCR text has more items ({len(text_items)}), using text extraction"
                    )
                    return _finalize_items(text_items)
                return _finalize_items(pdf_items)
            logger.info("[STEP 3] PDF tables found but 0 line items parsed — using OCR text")

    logger.info("[STEP 3] Using text-based line item extraction...")
    return _finalize_items(text_items)


def _process_single_invoice(
    invoice_text: str,
    file_data: bytes,
    mime_type: str,
    extraction_method: str,
    ocr_engine_requested: Optional[str],
    classification: dict,
    invoice_number: int,
    pages: Optional[List[int]] = None,
    ml_signals: Optional[dict] = None,
    progress_log: Optional[List[str]] = None,
    on_progress: Optional[Callable[[str], None]] = None,
) -> dict:
    """Process a single invoice section; see upload route for caller context."""
    plog = progress_log if progress_log is not None else []
    pfx = f"[Invoice {invoice_number}] " if invoice_number > 1 else ""

    def _p(m: str) -> None:
        _progress(plog, m, on_progress)

    # Step 2.9: Detect format + extract fields (once — used for line items + header)
    _p(f"{pfx}Step 4/6: Header fields & format detection…")
    field_result = field_extractor.extract_fields(invoice_text)
    format_id = field_result.get("detected_format") if field_result.get("success") else None
    if format_id:
        _p(f"{pfx}Format profile: {format_id} ({field_result.get('format_label') or '—'})")

    # Step 3: Extract line items (PDF tables for single-invoice PDFs, else OCR text)
    logger.info(f"[STEP 3] Extracting line items...")
    _p(f"{pfx}Step 5/6: Line items (tables + text patterns)…")
    line_items = _extract_line_items(
        invoice_text, file_data, mime_type, invoice_number, format_id=format_id, pages=pages
    )
    logger.info(f"[STEP 3] ✓ Extracted {len(line_items)} line items")
    _p(f"{pfx}Line items: {len(line_items)} row(s)")
    
    if len(line_items) > 0:
        logger.info(f"[STEP 3] Line Items Preview:")
        logger.info("-" * 80)
        for i, item in enumerate(line_items[:3], 1):  # Show first 3 items
            logger.info(f"  Item {i}:")
            logger.info(f"    Description: {item.get('description', 'N/A')}")
            logger.info(f"    Pcs: {item.get('quantity', 'N/A')}")
            logger.info(f"    Mts: {item.get('mts') or item.get('meters', 'N/A')}")
            logger.info(f"    Rate: {item.get('rate', 'N/A')}")
            logger.info(f"    Amount: {item.get('amount', 'N/A')}")
            logger.info(f"    HSN: {item.get('hsn_code', 'N/A')}")
        if len(line_items) > 3:
            logger.info(f"  ... and {len(line_items) - 3} more items")
        logger.info("-" * 80)
    
    # Step 4: Use field extraction from step 2.9
    logger.info(f"[STEP 4] Extracting invoice fields...")

    if not field_result.get("success"):
        raise Exception(f"Field extraction failed: {field_result.get('error')}")
    
    extracted_fields = field_result.get("fields", {})

    # Merge line items: pick best source (most items wins)
    # Sources: (1) pdfplumber/camelot/OCR-text from _extract_line_items above
    #          (2) field_extractor regex patterns (Pattern A + Pattern C)
    fe_items = extracted_fields.get("items", [])  # from field_extractor regex
    if len(line_items) >= len(fe_items):
        extracted_fields["items"] = line_items
    else:
        logger.info(f"[STEP 4] field_extractor regex found more items ({len(fe_items)}) than table extractor ({len(line_items)}) — using regex results")
        extracted_fields["items"] = fe_items
        _p(f"{pfx}Merged items: using regex/table mix (regex won: {len(fe_items)} items)")

    line_items = extracted_fields["items"]  # keep reference in sync for logging below
    extraction_confidence = field_extractor._calculate_confidence(extracted_fields)
    
    logger.info(f"[STEP 4] ✓ Extraction Confidence: {extraction_confidence}%")
    inv = extracted_fields.get("invoice_number")
    buyer = extracted_fields.get("buyer_name") or "—"
    tot = extracted_fields.get("total_amount")
    _p(
        f"{pfx}Fields: invoice#={inv!r} buyer={str(buyer)[:48]!r} total={tot!r} · extract_conf={extraction_confidence}%",
    )
    logger.info(f"[STEP 4] Extracted Fields:")
    logger.info("=" * 80)
    logger.info("EXTRACTED DATA:")
    logger.info("=" * 80)
    
    field_mapping = {
        'invoice_number': 'Invoice Number',
        'invoice_date': 'Invoice Date',
        'due_date': 'Due Date',
        'supplier_name': 'Supplier Name',
        'supplier_gstin': 'Supplier GSTIN',
        'buyer_name': 'Buyer Name',
        'buyer_gstin': 'Buyer GSTIN',
        'total_amount': 'Total Amount',
        'taxable_amount': 'Taxable Amount',
        'cgst_amount': 'CGST Amount',
        'sgst_amount': 'SGST Amount',
        'igst_amount': 'IGST Amount'
    }
    
    for field_key, field_label in field_mapping.items():
        value = extracted_fields.get(field_key)
        status = "✓" if value else "✗"
        display_value = value if value else "NOT FOUND"
        logger.info(f"{status} {field_label:20s}: {display_value}")
    
    logger.info(f"✓ Line Items Count    : {len(line_items)}")
    logger.info("=" * 80)
    
    # Step 5: Run pipeline orchestrator (cleaning → normalization → compliance → validation → confidence → ERP)
    logger.info(f"[STEP 5] Running pipeline orchestrator...")
    _p(f"{pfx}Step 6/6: Pipeline — clean, GST, validate, ERP schema…")
    pipeline_result = pipeline_orchestrator.process_fields(
        fields=extracted_fields,
        raw_text=invoice_text,
        extraction_metadata={
            "extraction_method": extraction_method,
            "ocr_engine": ocr_engine_requested,
            "detected_format": extracted_fields.get("detected_format"),
            "document_type": classification['document_type'],
            "invoice_number": classification.get('confidence'),
        },
    )
    logger.info(f"[STEP 5] ✓ Pipeline complete: confidence={pipeline_result['overall_confidence']}%, "
                f"valid={pipeline_result['is_valid']}, hitl={pipeline_result['hitl_required']}")
    _p(
        f"{pfx}Pipeline done: overall_conf={pipeline_result['overall_confidence']}% "
        f"valid={pipeline_result['is_valid']} hitl={pipeline_result['hitl_required']}",
    )
    
    logger.info(f"[STEP 6] Processing completed successfully")
    logger.info(f"[SUMMARY] Extraction: {extraction_confidence}% | Pipeline: {pipeline_result['overall_confidence']}% | "
                f"Items: {len(line_items)} | Method: {extraction_method}")
    logger.info("=" * 80)
    
    hybrid_review = build_hybrid_review(pipeline_result, ml_signals, extracted_fields)

    return {
        "extraction_flow": "ocr → patterns+rules → ml_signals → validate → erp_schema",
        "extraction_method": extraction_method,
        "ocr_engine_requested": ocr_engine_requested,
        "detected_format": extracted_fields.get("detected_format"),
        "format_label": extracted_fields.get("format_label"),
        "format_confidence": extracted_fields.get("format_confidence"),
        "text_length": len(invoice_text),
        "document_type": classification['document_type'],
        "classification_confidence": classification['confidence'],
        "extraction_confidence": extraction_confidence,
        "invoice_data": extracted_fields,
        "line_items_count": len(line_items),
        "raw_text_preview": invoice_text[:500] + "..." if len(invoice_text) > 500 else invoice_text,
        "pipeline": pipeline_result,
        "ml_signals": ml_signals,
        "hybrid_review": hybrid_review,
    }
