"""Universal text extractor that handles all file types."""

import logging
from typing import Dict, Any, Optional, List

from .pdf_extractor import pdf_extractor
from .image_extractor import image_extractor
from .docx_extractor import docx_extractor

logger = logging.getLogger(__name__)

# XGBoost field keys in models/v1 (subset may be missing if model not trained)
_ML_FIELD_KEYS = [
    "invoice_number",
    "invoice_date",
    "vendor_gstin",
    "buyer_gstin",
    "taxable_amount",
    "cgst_amount",
    "sgst_amount",
    "igst_amount",
    "total_amount",
]


class UniversalExtractor:
    """Universal text extractor for all supported file types."""

    def extract_text(
        self, file_data: bytes, mime_type: str, ocr_engine: str = None
    ) -> Dict[str, Any]:
        """
        Extract text from any supported file type.

        Returns:
            Dictionary with extracted text and metadata (includes success flag).
        """
        logger.info(f"Extracting text from file type: {mime_type}")

        try:
            if mime_type == "application/pdf":
                return pdf_extractor.extract_text(file_data, ocr_engine)

            if mime_type in ["image/jpeg", "image/png", "image/jpg"]:
                return image_extractor.extract_text(file_data, ocr_engine)

            if mime_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
                return docx_extractor.extract_text(file_data)

            logger.error(f"Unsupported MIME type: {mime_type}")
            return {
                "text": "",
                "extraction_method": "unsupported",
                "error": f"Unsupported file type: {mime_type}",
                "success": False,
            }

        except Exception as e:
            logger.error(f"Universal extraction failed: {str(e)}")
            return {
                "text": "",
                "extraction_method": "failed",
                "error": str(e),
                "success": False,
            }

    def compute_ml_signals_sync(
        self,
        text: str,
        ocr_result: Dict[str, Any],
        model_dir: str = "models/v1",
    ) -> Optional[Dict[str, Any]]:
        """
        XGBoost routing signals only — does NOT extract field values.

        Returns invoice type prediction + per-field presence probabilities for HITL/routing.
        """
        try:
            from app.services.training.model_registry import ModelRegistry
            from app.services.training.feature_extractor import FeatureExtractor
            import numpy as np

            registry = ModelRegistry(model_dir)
            model, vectorizer, label_encoder, field_models, feature_names, metadata = (
                registry.load_model()
            )

            if not model or not feature_names:
                return None

            feature_ext = FeatureExtractor()
            feature_ext.vectorizer = vectorizer
            feature_ext.is_fitted = True

            text_feats = feature_ext.extract_text_features(text)
            layout_feats = feature_ext.extract_layout_features(ocr_result)
            gst_feats = feature_ext.extract_gst_features(text)

            combined = {**text_feats, **layout_feats, **gst_feats}
            dense_names = [f for f in feature_names if not f.startswith("tfidf_")]
            dense_array = [combined.get(k, 0.0) for k in dense_names]

            tfidf_features = feature_ext.transform_tfidf([text])[0]
            X = np.hstack((dense_array, tfidf_features)).reshape(1, -1)

            X_processed = model.named_steps["imputer"].transform(X)
            X_processed = model.named_steps["scaler"].transform(X_processed)

            invoice_type_prediction = None
            try:
                y_pred = model.predict(X)[0]
                invoice_type_prediction = label_encoder.inverse_transform([y_pred])[0]
            except Exception as e:
                logger.warning(f"Invoice type prediction failed: {e}")

            field_confidence: Dict[str, float] = {}
            for field, f_model in (field_models or {}).items():
                if f_model:
                    try:
                        field_confidence[field] = round(
                            float(f_model.predict_proba(X_processed)[0][1]), 4
                        )
                    except Exception:
                        pass

            low_confidence_fields = [
                f
                for f in _ML_FIELD_KEYS
                if field_confidence.get(f, 0.0) < 0.5
            ]

            return {
                "role": "routing_and_hitl_only",
                "model_dir": model_dir,
                "model_metadata": metadata,
                "invoice_type_prediction": invoice_type_prediction,
                "field_confidence": field_confidence,
                "low_confidence_fields": low_confidence_fields,
                "note": (
                    "Field values come from patterns/rules pipeline. "
                    "XGBoost scores whether each field is likely present — not the extracted value."
                ),
            }
        except Exception as e:
            logger.warning(f"ML signals unavailable: {e}")
            return None

    async def _ml_extract(self, text: str, ocr_result: Dict[str, Any]) -> Dict[str, float]:
        """Legacy async helper — returns field_confidence map only."""
        signals = self.compute_ml_signals_sync(text, ocr_result)
        if not signals:
            return {}
        return signals.get("field_confidence", {})


# Global instance
universal_extractor = UniversalExtractor()
