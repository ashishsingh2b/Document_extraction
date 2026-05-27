"""Health check endpoints."""

from fastapi import APIRouter, status
from app.models.response import HealthResponse
from app.config.settings import settings
import logging

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/health", response_model=HealthResponse)
async def health_check():
    """
    Health check endpoint.
    
    Returns HTTP 200 when all dependencies are available,
    HTTP 503 when any critical dependency is unavailable.
    """
    dependencies = {}
    all_healthy = True
    
    # Check MinIO
    try:
        from minio import Minio
        client = Minio(
            settings.MINIO_ENDPOINT,
            access_key=settings.MINIO_ACCESS_KEY,
            secret_key=settings.MINIO_SECRET_KEY,
            secure=settings.MINIO_SECURE
        )
        # Try to check if bucket exists
        bucket_exists = client.bucket_exists(settings.MINIO_BUCKET_NAME)
        dependencies["minio"] = "healthy" if bucket_exists else "bucket_missing"
        if not bucket_exists:
            logger.warning("MinIO bucket does not exist")
            # Don't mark as unhealthy, just warn
    except Exception as e:
        logger.error(f"MinIO health check failed: {str(e)}")
        dependencies["minio"] = "unavailable"
        # Don't fail health check if MinIO is down
    
    # Check Redis
    try:
        import redis
        r = redis.from_url(settings.REDIS_URL)
        r.ping()
        dependencies["redis"] = "healthy"
    except Exception as e:
        logger.error(f"Redis health check failed: {str(e)}")
        dependencies["redis"] = "unavailable"
        # Don't fail health check if Redis is down
    
    # Check Database
    try:
        from sqlalchemy import create_engine, text
        engine = create_engine(settings.DATABASE_URL)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        dependencies["database"] = "healthy"
    except Exception as e:
        logger.error(f"Database health check failed: {str(e)}")
        dependencies["database"] = "unavailable"
        # Don't fail health check if database is down
    
    # Check Tesseract OCR
    try:
        import pytesseract
        version = pytesseract.get_tesseract_version()
        dependencies["tesseract_ocr"] = f"healthy (v{version})"
    except Exception as e:
        logger.warning(f"Tesseract OCR check failed: {str(e)}")
        dependencies["tesseract_ocr"] = "unavailable"
        # OCR is not critical for all operations
    
    response_status = "healthy" if all_healthy else "unhealthy"
    status_code = status.HTTP_200_OK if all_healthy else status.HTTP_503_SERVICE_UNAVAILABLE
    
    return HealthResponse(
        status=response_status,
        version=settings.APP_VERSION,
        dependencies=dependencies
    )


@router.get("/ready")
async def readiness_check():
    """
    Readiness check endpoint for Kubernetes probes.
    
    Returns HTTP 200 when application is ready to serve requests.
    """
    return {"status": "ready"}
