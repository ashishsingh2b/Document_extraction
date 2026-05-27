"""System status, metrics, and phase readiness."""

import json
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.config.settings import settings

router = APIRouter()

_BASE = Path(__file__).resolve().parents[3]


@router.get("/system/status")
async def system_status():
    """End-to-end pipeline status: config, training data counts, model packs."""
    ocr_cache = _BASE / "training_data" / "ocr_cache"
    raw_dir = _BASE / "training_data" / "raw"
    labels = _BASE / "training_data" / "annotated" / "labels.json"
    patterns = _BASE / "app" / "config" / "learned_patterns.json"
    model_dir = _BASE / settings.ML_MODEL_DIR

    label_count = 0
    if labels.exists():
        try:
            label_count = len(json.loads(labels.read_text(encoding="utf-8")))
        except Exception:
            pass

    pattern_meta = {}
    if patterns.exists():
        try:
            pattern_meta = json.loads(patterns.read_text(encoding="utf-8")).get("meta", {})
        except Exception:
            pass

    return {
        "service": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "extraction_flow": "ocr → patterns+rules → validate → erp_schema (+ optional ml_signals)",
        "config": {
            "auto_learn_on_upload": settings.AUTO_LEARN_ON_UPLOAD,
            "ml_signals_on_upload": settings.ML_SIGNALS_ON_UPLOAD,
            "ml_model_dir": settings.ML_MODEL_DIR,
            "train_api_secured": bool(settings.TRAIN_API_SECRET),
            "upload_api_secured": bool(settings.UPLOAD_API_KEY),
        },
        "training_data": {
            "raw_pdfs": len(list(raw_dir.glob("*.pdf"))) if raw_dir.exists() else 0,
            "ocr_cache_files": len(list(ocr_cache.glob("*.json"))) if ocr_cache.exists() else 0,
            "annotated_labels": label_count,
            "patterns_trained_on": pattern_meta.get("trained_on_docs", 0),
            "patterns_trained_at": pattern_meta.get("trained_at"),
        },
        "models": {
            "xgboost_pack_exists": (model_dir / "model.pkl").exists(),
            "path": str(model_dir),
        },
        "phases": {
            "0_stabilise": "complete",
            "1_extraction_quality": "active",
            "2_hybrid_hitl": "complete",
            "3_ml_train_api": "complete",
            "4_ops_api_keys": "complete",
        },
        "endpoints": {
            "upload": f"{settings.API_V1_PREFIX}/upload",
            "train_patterns": f"{settings.API_V1_PREFIX}/train",
            "train_ml": f"{settings.API_V1_PREFIX}/train/ml",
            "health": f"{settings.API_V1_PREFIX}/health",
        },
    }


@router.get("/system/metrics")
async def system_metrics():
    """Lightweight counters for monitoring (extend with Prometheus later)."""
    from app.services.utils.duplicate_detector import duplicate_detector

    return {
        "duplicate_cache_entries": len(getattr(duplicate_detector, "hash_cache", {})),
        "confidence_threshold_hitl": settings.CONFIDENCE_THRESHOLD_HITL,
    }
