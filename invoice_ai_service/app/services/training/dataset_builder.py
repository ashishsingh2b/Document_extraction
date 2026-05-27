import os
import glob
import logging
from typing import List, Dict, Any, Tuple
import numpy as np

from app.services.extraction.universal_extractor import universal_extractor
from app.services.training.feature_extractor import FeatureExtractor
from app.services.training.annotation_manager import AnnotationManager

logger = logging.getLogger(__name__)

class DatasetBuilder:
    def __init__(self, data_dir: str, labels_file: str):
        self.data_dir = data_dir
        self.annotation_manager = AnnotationManager(labels_file)
        self.feature_extractor = FeatureExtractor()

    def build_dataset(self) -> Tuple[np.ndarray, np.ndarray, Dict[str, np.ndarray], List[str]]:
        logger.info(f"Building dataset from {self.data_dir}")
        
        all_files = glob.glob(os.path.join(self.data_dir, "**/*.*"), recursive=True)
        valid_files = [f for f in all_files if f.lower().endswith(('.pdf', '.jpg', '.jpeg', '.png'))]
        
        features_list = []
        texts = []
        labels_type = []
        labels_fields = {
            'invoice_number': [],
            'invoice_date': [],
            'vendor_gstin': [],
            'buyer_gstin': [],
            'taxable_amount': [],
            'cgst_amount': [],
            'sgst_amount': [],
            'igst_amount': [],
            'total_amount': []
        }
        
        feature_names = []
        
        import json
        cache_dir = os.path.join(self.data_dir, "../ocr_cache")
        os.makedirs(cache_dir, exist_ok=True)

        for file_path in valid_files:
            file_id = os.path.basename(file_path)
            annotation = self.annotation_manager.get_annotation(file_id)
            if not annotation:
                continue
                
            try:
                file_size = os.path.getsize(file_path)
                mtime = os.path.getmtime(file_path)
                cache_file = os.path.join(cache_dir, f"{file_id}.json")
                ocr_result = None
                
                if os.path.exists(cache_file):
                    try:
                        with open(cache_file, 'r', encoding='utf-8') as cf:
                            cache_data = json.load(cf)
                        if cache_data.get('file_size') == file_size and cache_data.get('mtime') == mtime:
                            ocr_result = cache_data.get('ocr_result')
                            logger.info(f"Loaded cached OCR result for {file_id}")
                    except Exception as e:
                        logger.warning(f"Failed to read OCR cache for {file_id}: {e}")
                
                if not ocr_result:
                    with open(file_path, 'rb') as f:
                        file_data = f.read()
                    mime_type = 'application/pdf' if file_path.lower().endswith('.pdf') else 'image/jpeg'
                    ocr_result = universal_extractor.extract_text(file_data, mime_type)
                    
                    # Save to cache
                    try:
                        with open(cache_file, 'w', encoding='utf-8') as cf:
                            json.dump({
                                'file_size': file_size,
                                'mtime': mtime,
                                'ocr_result': ocr_result
                            }, cf, indent=2, ensure_ascii=False)
                        logger.info(f"Cached OCR result for {file_id}")
                    except Exception as e:
                        logger.warning(f"Failed to save OCR cache for {file_id}: {e}")
                
                text = ocr_result.get('text', '')
                if not text:
                    continue
                
                texts.append(text)
                
                # Extract features
                text_feats = self.feature_extractor.extract_text_features(text)
                layout_feats = self.feature_extractor.extract_layout_features(ocr_result)
                gst_feats = self.feature_extractor.extract_gst_features(text)
                
                combined_feats = {}
                combined_feats.update(text_feats)
                combined_feats.update(layout_feats)
                combined_feats.update(gst_feats)
                
                if not feature_names:
                    feature_names = list(combined_feats.keys())
                
                feats_array = [combined_feats[k] for k in feature_names]
                features_list.append(feats_array)
                
                # Labels
                labels_type.append(annotation.get('invoice_type', 'unknown'))
                
                for field in labels_fields.keys():
                    # for fields, label could be 1 if present/correct, 0 if not (binary classification for field confidence)
                    # or it could be the actual extracted text, but since we are predicting confidence, let's assume binary
                    # For a robust ML hybrid, we train on whether the regex extracted field matches the annotated field.
                    # Simplified for pipeline: just output 1 (valid) or 0 (invalid) if it exists.
                    val = annotation.get(field)
                    labels_fields[field].append(1 if val else 0)
                    
            except Exception as e:
                logger.error(f"Error processing {file_path}: {e}")

        if not texts:
            raise ValueError("No valid annotated data found to build dataset.")
            
        # TF-IDF
        self.feature_extractor.fit_tfidf(texts)
        tfidf_features = self.feature_extractor.transform_tfidf(texts)
        
        # Combine dense features and tfidf
        X_dense = np.array(features_list)
        X = np.hstack((X_dense, tfidf_features))
        
        # Add tfidf feature names
        vocab = self.feature_extractor.vectorizer.vocabulary_
        sorted_vocab = sorted(vocab.items(), key=lambda x: x[1])
        tfidf_names = [f"tfidf_{k}" for k, v in sorted_vocab]
        all_feature_names = feature_names + tfidf_names
        
        y_type = np.array(labels_type)
        y_fields = {k: np.array(v) for k, v in labels_fields.items()}
        
        return X, y_type, y_fields, all_feature_names
