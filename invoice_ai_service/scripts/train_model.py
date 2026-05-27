import os
import sys
import argparse
import logging
import json
import numpy as np

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.services.training.retraining_manager import RetrainingManager
from app.services.training.model_registry import ModelRegistry
from app.services.extraction.universal_extractor import universal_extractor
from app.services.training.feature_extractor import FeatureExtractor

from app.core.logging_config import setup_logging
setup_logging()
logger = logging.getLogger(__name__)

def evaluate_only(output_dir):
    logger.info("Running evaluation mode")
    registry = ModelRegistry(output_dir)
    model, vectorizer, label_encoder, field_models, feature_names, metadata = registry.load_model()
    if not model:
        logger.error("No model found to evaluate")
        return
    logger.info(f"Loaded model metadata: {json.dumps(metadata, indent=2)}")

def predict(file_path: str, output_dir: str):
    logger.info(f"Predicting for file {file_path}")
    registry = ModelRegistry(output_dir)
    model, vectorizer, label_encoder, field_models, feature_names, metadata = registry.load_model()
    if not model:
        logger.error("No model found for prediction")
        return

    try:
        with open(file_path, 'rb') as f:
            file_data = f.read()
        mime_type = 'application/pdf' if file_path.lower().endswith('.pdf') else 'image/jpeg'
        ocr_result = universal_extractor.extract_text(file_data, mime_type)
        text = ocr_result.get('text', '')
        
        feature_ext = FeatureExtractor()
        feature_ext.vectorizer = vectorizer
        feature_ext.is_fitted = True
        
        text_feats = feature_ext.extract_text_features(text)
        layout_feats = feature_ext.extract_layout_features(ocr_result)
        gst_feats = feature_ext.extract_gst_features(text)
        
        combined_feats = {}
        combined_feats.update(text_feats)
        combined_feats.update(layout_feats)
        combined_feats.update(gst_feats)
        
        # Dense features based on saved feature_names (excluding tfidf)
        dense_names = [f for f in feature_names if not f.startswith('tfidf_')]
        dense_array = [combined_feats.get(k, 0.0) for k in dense_names]
        
        tfidf_features = feature_ext.transform_tfidf([text])[0]
        
        X = np.hstack((dense_array, tfidf_features)).reshape(1, -1)
        
        # Predict type
        y_pred = model.predict(X)[0]
        invoice_type = label_encoder.inverse_transform([y_pred])[0]
        
        print(f"Predicted Invoice Type: {invoice_type}")
        
        # Predict field confidences
        # Note: the scaler in pipeline is applied to X before classification, but field_models 
        # were trained on processed X. So we need to process X with pipeline steps.
        X_processed = model.named_steps['imputer'].transform(X)
        X_processed = model.named_steps['scaler'].transform(X_processed)
        
        print("\nField Confidences:")
        for field, f_model in field_models.items():
            if f_model:
                try:
                    prob = f_model.predict_proba(X_processed)[0][1]
                    print(f"  {field}: {prob:.4f}")
                except Exception as e:
                    print(f"  {field}: N/A ({e})")
            else:
                print(f"  {field}: N/A (No model)")
                
    except Exception as e:
        logger.error(f"Prediction failed: {e}")

def main():
    parser = argparse.ArgumentParser(description="Train or evaluate invoice ML model")
    parser.add_argument("--data-dir", type=str, default="training_data/raw", help="Directory with raw invoices")
    parser.add_argument("--labels", type=str, default="training_data/annotated/labels.json", help="Path to labels")
    parser.add_argument("--output-dir", type=str, default="models/v1", help="Output directory for model")
    parser.add_argument("--force-rebuild-features", action="store_true", help="Force rebuild features")
    parser.add_argument("--evaluate-only", action="store_true", help="Only run evaluation on existing model")
    parser.add_argument("--predict", action="store_true", help="Run prediction on a single file")
    parser.add_argument("--file", type=str, help="File to predict on")
    
    args = parser.parse_args()

    if args.evaluate_only:
        evaluate_only(args.output_dir)
    elif args.predict:
        if not args.file:
            logger.error("Must provide --file with --predict")
            return
        predict(args.file, args.output_dir)
    else:
        manager = RetrainingManager(args.data_dir, args.labels, args.output_dir)
        manager.run_training_pipeline()

if __name__ == "__main__":
    main()
