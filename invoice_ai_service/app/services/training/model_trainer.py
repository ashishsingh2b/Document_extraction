import logging
from typing import Dict, Any, List
import numpy as np
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler, LabelEncoder
from sklearn.impute import SimpleImputer
from sklearn.model_selection import StratifiedKFold, cross_val_predict
try:
    from imblearn.over_sampling import SMOTE
    HAS_SMOTE = True
except ImportError:
    HAS_SMOTE = False

logger = logging.getLogger(__name__)

class ModelTrainer:
    def __init__(self):
        self.type_model = None
        self.field_models = {}
        self.label_encoder = LabelEncoder()
        
    def train(self, X: np.ndarray, y_type: np.ndarray, y_fields: Dict[str, np.ndarray]):
        logger.info("Starting model training pipeline")
        
        # Preprocessing
        self.imputer = SimpleImputer(strategy='mean')
        self.scaler = StandardScaler()
        
        X_processed = self.imputer.fit_transform(X)
        X_processed = self.scaler.fit_transform(X_processed)
        
        # Encode labels
        y_type_encoded = self.label_encoder.fit_transform(y_type)
        
        # Handle imbalance
        if HAS_SMOTE and len(np.unique(y_type_encoded)) > 1:
            logger.info("Applying SMOTE")
            smote = SMOTE(random_state=42, k_neighbors=min(5, len(X_processed)-1))
            try:
                X_resampled, y_resampled = smote.fit_resample(X_processed, y_type_encoded)
            except ValueError:
                # Fallback if too few samples
                X_resampled, y_resampled = X_processed, y_type_encoded
        else:
            X_resampled, y_resampled = X_processed, y_type_encoded
            
        # Train Stage 1: Invoice Type
        logger.info("Training invoice type model (Stage 1) using XGBoost")
        try:
            from xgboost import XGBClassifier
            self.type_model = XGBClassifier(
                n_estimators=300,
                max_depth=6,
                learning_rate=0.05,
                subsample=0.8,
                colsample_bytree=0.8,
                eval_metric='mlogloss',
                random_state=42
            )
        except ImportError:
            logger.warning("XGBoost not installed. Falling back to HistGradientBoostingClassifier.")
            from sklearn.ensemble import HistGradientBoostingClassifier
            self.type_model = HistGradientBoostingClassifier(
                max_iter=300,
                max_depth=6,
                learning_rate=0.05,
                random_state=42
            )

        self.type_model.fit(X_resampled, y_resampled)
        
        # Train Stage 2: Field models
        logger.info("Training field confidence models (Stage 2) using XGBoost")
        
        try:
            from xgboost import XGBClassifier
            model_class = XGBClassifier
            model_kwargs = {
                'n_estimators': 150,
                'learning_rate': 0.1,
                'max_depth': 4,
                'eval_metric': 'logloss',
                'random_state': 42
            }
        except ImportError:
            from sklearn.ensemble import HistGradientBoostingClassifier
            model_class = HistGradientBoostingClassifier
            model_kwargs = {
                'max_iter': 150,
                'learning_rate': 0.1,
                'max_depth': 4,
                'random_state': 42
            }

        for field, y_field in y_fields.items():
            logger.info(f"Training model for field: {field}")
            # Ensure multiple classes
            if len(np.unique(y_field)) > 1:
                model = model_class(**model_kwargs)
                model.fit(X_processed, y_field)
                self.field_models[field] = model
            else:
                logger.warning(f"Field {field} has only one class, skipping training.")
                self.field_models[field] = None
                
        return self.type_model, self.field_models, self.label_encoder

    def get_pipeline_components(self):
        return self.imputer, self.scaler
