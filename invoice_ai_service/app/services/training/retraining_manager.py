import logging
from .dataset_builder import DatasetBuilder
from .model_trainer import ModelTrainer
from .model_evaluator import ModelEvaluator
from .model_registry import ModelRegistry

logger = logging.getLogger(__name__)

class RetrainingManager:
    def __init__(self, data_dir: str, labels_file: str, output_dir: str):
        self.dataset_builder = DatasetBuilder(data_dir, labels_file)
        self.trainer = ModelTrainer()
        self.evaluator = ModelEvaluator()
        self.registry = ModelRegistry(output_dir)

    def run_training_pipeline(self):
        logger.info("Starting ML Retraining Pipeline")
        X, y_type, y_fields, feature_names = self.dataset_builder.build_dataset()
        
        logger.info(f"Dataset shape: {X.shape}")
        
        # Train
        type_model, field_models, label_encoder = self.trainer.train(X, y_type, y_fields)
        imputer, scaler = self.trainer.get_pipeline_components()
        
        # Preprocess X for evaluation
        X_processed = imputer.transform(X)
        X_processed = scaler.transform(X_processed)
        y_type_encoded = label_encoder.transform(y_type)
        
        # Evaluate
        metrics = self.evaluator.evaluate(type_model, X_processed, y_type_encoded, feature_names)
        
        # Construct pipeline object to save
        from sklearn.pipeline import Pipeline
        full_model = Pipeline([
            ('imputer', imputer),
            ('scaler', scaler),
            ('classifier', type_model)
        ])
        
        metadata = {
            "version": "1.0",
            "dataset_size": len(X),
            "accuracy": metrics["accuracy"],
            "f1_score": metrics["f1_score"],
            "top_features": metrics["top_features"]
        }
        
        self.registry.save_model(
            model=full_model,
            vectorizer=self.dataset_builder.feature_extractor.vectorizer,
            label_encoder=label_encoder,
            field_models=field_models,
            feature_names=feature_names,
            metadata=metadata
        )
        logger.info("Training pipeline completed successfully.")
