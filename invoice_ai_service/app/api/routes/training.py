"""
Training API Routes
====================
POST /api/v1/train   — Re-learn patterns from all uploaded training documents.
GET  /api/v1/train   — Show current learned pattern statistics.

Whenever you upload new invoices to training_data/raw/ and run OCR on them,
calling POST /api/v1/train will automatically discover all field patterns,
column layouts, amount labels, and doc-type signals from those documents.
The extraction engine immediately uses the updated patterns for new invoices.
"""
import logging
import threading
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from app.api.deps import verify_train_post_secret
from app.config.settings import settings

logger = logging.getLogger(__name__)
router = APIRouter()

_ml_train_lock = threading.Lock()
_ml_train_running = False


@router.post(
    "/train",
    summary="Re-learn extraction patterns from all training data",
    dependencies=[Depends(verify_train_post_secret)],
)
async def trigger_training():
    """
    Re-reads every document in training_data/ocr_cache/ and learns:
    - How field labels appear (Invoice Date, Due Date, GSTIN, etc.)
    - What column keywords exist in tables (HSN, Rate, Amount, etc.)
    - Which keywords distinguish sales invoices from registers/reports
    - How amount labels are written (Grand Total, Net Amount, CGST @9%, etc.)

    Run this every time you upload new training documents.
    """
    try:
        from app.services.training.pattern_learner import learn_from_all_training_data
        import app.services.training.pattern_learner as pl

        logger.info("Training triggered via API")
        start = datetime.now()
        learned = learn_from_all_training_data()

        # Clear cache so next extraction uses fresh patterns
        pl._PATTERNS_CACHE = None

        elapsed = (datetime.now() - start).total_seconds()
        meta = learned.get("meta", {})
        field_labels = learned.get("field_labels", {})
        doc_signals = learned.get("doc_type_signals", {})

        return JSONResponse({
            "status": "success",
            "message": f"Pattern learning complete in {elapsed:.1f}s",
            "trained_on_documents": meta.get("trained_on_docs", 0),
            "trained_at": meta.get("trained_at"),
            "fields_learned": list(field_labels.keys()),
            "doc_types_found": list(doc_signals.keys()),
            "doc_names": meta.get("doc_names", []),
            "top_patterns": {
                field: labels[:3]
                for field, labels in field_labels.items()
            },
        })

    except Exception as e:
        logger.error(f"Training failed: {e}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": str(e)}
        )


@router.get("/train", summary="Show current learned pattern statistics")
async def get_training_status():
    """Show statistics about the currently loaded learned patterns."""
    try:
        from app.services.training.pattern_learner import load_learned_patterns, LEARNED_FILE

        patterns = load_learned_patterns()
        meta = patterns.get("meta", {})
        field_labels = patterns.get("field_labels", {})
        col_headers = patterns.get("column_headers", {})
        doc_signals = patterns.get("doc_type_signals", {})
        amount_labels = patterns.get("amount_labels", {})

        return JSONResponse({
            "status": "ready",
            "patterns_file": str(LEARNED_FILE),
            "trained_on_documents": meta.get("trained_on_docs", 0),
            "trained_at": meta.get("trained_at", "never"),
            "doc_names": meta.get("doc_names", []),
            "fields_with_patterns": list(field_labels.keys()),
            "column_headers_discovered": len(col_headers),
            "doc_types_learned": list(doc_signals.keys()),
            "amount_fields_learned": list(amount_labels.keys()),
            "field_pattern_counts": {
                field: len(labels) for field, labels in field_labels.items()
            },
        })

    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": str(e)}
        )


@router.post(
    "/train/ml",
    summary="Train XGBoost routing model from labels.json (background)",
    dependencies=[Depends(verify_train_post_secret)],
)
async def trigger_ml_training():
    """
    Runs scripts/train_model.py pipeline in a background thread.
    Requires annotated labels in training_data/annotated/labels.json and PDFs in training_data/raw/.
  """
    global _ml_train_running

    if _ml_train_running:
        return JSONResponse(
            status_code=409,
            content={"status": "busy", "message": "ML training already in progress"},
        )

    def _run():
        global _ml_train_running
        try:
            from app.services.training.retraining_manager import RetrainingManager

            mgr = RetrainingManager(
                data_dir="training_data/raw",
                labels_file="training_data/annotated/labels.json",
                output_dir=settings.ML_MODEL_DIR,
            )
            mgr.run_training_pipeline()
            logger.info("ML training completed")
        except Exception as e:
            logger.error(f"ML training failed: {e}", exc_info=True)
        finally:
            with _ml_train_lock:
                _ml_train_running = False

    with _ml_train_lock:
        _ml_train_running = True
    threading.Thread(target=_run, daemon=True).start()

    return JSONResponse({
        "status": "started",
        "message": f"ML training started; output → {settings.ML_MODEL_DIR}",
        "note": "XGBoost provides routing/HITL signals only, not field values.",
    })


@router.get("/train/ml/status")
async def ml_training_status():
    """Whether background ML training is running and model pack exists."""
    from pathlib import Path

    model_dir = Path(settings.ML_MODEL_DIR)
    return {
        "training_in_progress": _ml_train_running,
        "model_pack_exists": (model_dir / "model.pkl").exists(),
        "model_dir": str(model_dir),
    }
