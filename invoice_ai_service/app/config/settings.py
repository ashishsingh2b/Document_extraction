"""Application settings and configuration."""

from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    # Application
    APP_NAME: str = "Invoice Intelligence Microservice"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False
    
    # API
    API_V1_PREFIX: str = "/api/v1"
    
    # File Upload
    MAX_FILE_SIZE_MB: int = 50

    # MinIO Object Storage
    MINIO_ENDPOINT: str = "localhost:9000"
    MINIO_ACCESS_KEY: str = "minioadmin"
    MINIO_SECRET_KEY: str = "minioadmin"
    MINIO_BUCKET_NAME: str = "invoice-uploads"
    MINIO_SECURE: bool = False
    
    # Database
    DATABASE_URL: str = "postgresql://postgres:postgres@localhost:5432/invoice_db"
    
    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"
    
    # Celery
    CELERY_BROKER_URL: str = "redis://localhost:6379/0"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/0"
    
    # Confidence Scoring
    CONFIDENCE_THRESHOLD_HITL: int = 70
    
    # Retry Policy
    MAX_RETRIES: int = 3
    RETRY_BACKOFF_FACTOR: float = 2.0
    
    # Indian GST
    EINVOICE_TURNOVER_THRESHOLD: int = 50000000  # ₹5 crore
    TDS_THRESHOLD: int = 5000000  # ₹50 lakh
    TCS_THRESHOLD: int = 5000000  # ₹50 lakh
    
    # IRP Portal (e-Invoice)
    IRP_BASE_URL: Optional[str] = None
    IRP_USERNAME: Optional[str] = None
    IRP_PASSWORD: Optional[str] = None
    
    # Tesseract OCR
    TESSERACT_CMD: Optional[str] = None  # Path to tesseract executable
    
    # Default OCR Engine (Options: tesseract, paddleocr)
    DEFAULT_OCR_ENGINE: str = "paddleocr"

    # Hybrid extraction lifecycle — OCR→patterns/rules validate→ERP today; ML signals optional
    # Save OCR cache + background pattern refresh on each successful upload (disable for prod/staging control).
    AUTO_LEARN_ON_UPLOAD: bool = False
    # Attach XGBoost field-presence probabilities + invoice-type prediction when models/v1 exists (routing/HITL).
    ML_SIGNALS_ON_UPLOAD: bool = True
    ML_MODEL_DIR: str = "models/v1"

    # When set, POST /api/v1/train requires header X-Training-Secret with this value (constant-time compare).
    TRAIN_API_SECRET: Optional[str] = None

    # When set, POST /api/v1/upload requires header X-API-Key with this value.
    UPLOAD_API_KEY: Optional[str] = None
    
    # Logging
    LOG_LEVEL: str = "INFO"
    AUDIT_LOG_RETENTION_DAYS: int = 2555  # 7 years
    
    class Config:
        env_file = ".env"
        case_sensitive = True
        extra = "allow"  # Allow extra fields from .env


# Global settings instance
_settings = None


def get_settings() -> Settings:
    """Get settings instance with reload support."""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


def reload_settings() -> Settings:
    """Reload settings from environment variables."""
    global _settings
    _settings = Settings()
    return _settings


# Convenience accessor
settings = get_settings()
