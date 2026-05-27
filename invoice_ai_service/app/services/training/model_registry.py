import os
import json
import pickle
import logging
from typing import Dict, Any, Tuple
from datetime import datetime

logger = logging.getLogger(__name__)

class ModelRegistry:
    def __init__(self, model_dir: str = "models/v1"):
        self.model_dir = model_dir
        os.makedirs(self.model_dir, exist_ok=True)

    def save_model(self, model, vectorizer, label_encoder, field_models, feature_names, metadata: Dict[str, Any]):
        try:
            with open(os.path.join(self.model_dir, 'model.pkl'), 'wb') as f:
                pickle.dump(model, f)
            with open(os.path.join(self.model_dir, 'vectorizer.pkl'), 'wb') as f:
                pickle.dump(vectorizer, f)
            with open(os.path.join(self.model_dir, 'label_encoder.pkl'), 'wb') as f:
                pickle.dump(label_encoder, f)
            with open(os.path.join(self.model_dir, 'field_models.pkl'), 'wb') as f:
                pickle.dump(field_models, f)
            
            with open(os.path.join(self.model_dir, 'feature_names.json'), 'w') as f:
                json.dump(feature_names, f, indent=4)
            
            # Add timestamps and versions
            import sklearn
            import platform
            metadata.update({
                "trained_at": datetime.utcnow().isoformat(),
                "python_version": platform.python_version(),
                "sklearn_version": sklearn.__version__
            })
            with open(os.path.join(self.model_dir, 'metadata.json'), 'w') as f:
                json.dump(metadata, f, indent=4)
            logger.info(f"Successfully saved all models to {self.model_dir}")
        except Exception as e:
            logger.error(f"Failed to save models: {e}")
            raise

    def load_model(self) -> Tuple[Any, Any, Any, Any, Any, Any]:
        try:
            with open(os.path.join(self.model_dir, 'model.pkl'), 'rb') as f:
                model = pickle.load(f)
            with open(os.path.join(self.model_dir, 'vectorizer.pkl'), 'rb') as f:
                vectorizer = pickle.load(f)
            with open(os.path.join(self.model_dir, 'label_encoder.pkl'), 'rb') as f:
                label_encoder = pickle.load(f)
            with open(os.path.join(self.model_dir, 'field_models.pkl'), 'rb') as f:
                field_models = pickle.load(f)
            with open(os.path.join(self.model_dir, 'feature_names.json'), 'r') as f:
                feature_names = json.load(f)
            with open(os.path.join(self.model_dir, 'metadata.json'), 'r') as f:
                metadata = json.load(f)
            return model, vectorizer, label_encoder, field_models, feature_names, metadata
        except Exception as e:
            logger.error(f"Failed to load models from {self.model_dir}: {e}")
            return None, None, None, None, None, None
