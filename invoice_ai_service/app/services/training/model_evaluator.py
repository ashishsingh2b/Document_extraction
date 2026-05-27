import logging
from typing import Dict, Any
import numpy as np
from sklearn.metrics import accuracy_score, f1_score
from sklearn.model_selection import StratifiedKFold, cross_val_predict

logger = logging.getLogger(__name__)

class ModelEvaluator:
    def __init__(self):
        pass

    def evaluate(self, model, X: np.ndarray, y: np.ndarray, feature_names: list) -> Dict[str, Any]:
        logger.info("Evaluating model")
        
        if len(np.unique(y)) < 2:
            logger.warning("Not enough classes to evaluate.")
            return {"accuracy": 1.0, "f1_score": 1.0, "top_features": []}
            
        cv = StratifiedKFold(n_splits=min(5, len(y)))
        try:
            y_pred = cross_val_predict(model, X, y, cv=cv)
            acc = accuracy_score(y, y_pred)
            f1 = f1_score(y, y_pred, average='weighted')
        except ValueError as e:
            logger.warning(f"Cross-validation failed: {e}. Using training data for evaluation.")
            y_pred = model.predict(X)
            acc = accuracy_score(y, y_pred)
            f1 = f1_score(y, y_pred, average='weighted')
            
        top_features = []
        if hasattr(model, 'feature_importances_'):
            importances = model.feature_importances_
            indices = np.argsort(importances)[::-1]
            for i in range(min(10, len(feature_names))):
                top_features.append({
                    "feature": feature_names[indices[i]],
                    "importance": float(importances[indices[i]])
                })
                
        return {
            "accuracy": float(acc),
            "f1_score": float(f1),
            "top_features": top_features
        }
