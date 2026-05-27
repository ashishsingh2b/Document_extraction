"""API response models."""

from typing import Optional, Any, Dict, List
from pydantic import BaseModel


class APIResponse(BaseModel):
    """Standard API response."""
    status: str
    message: Optional[str] = None
    data: Optional[Any] = None
    request_id: Optional[str] = None


class ErrorResponse(BaseModel):
    """Error response."""
    status: str = "error"
    error_message: str
    error_code: str
    request_id: Optional[str] = None
    details: Optional[Dict[str, Any]] = None


class UploadResponse(BaseModel):
    """File upload response."""
    status: str
    job_id: str
    message: str
    file_name: str
    file_size: int
    request_id: Optional[str] = None
    extracted_data: Optional[Dict[str, Any]] = None
    # Human-readable extraction steps (returned to UI / API clients for progress visibility)
    processing_log: Optional[List[str]] = None


class HealthResponse(BaseModel):
    """Health check response."""
    status: str
    version: str
    dependencies: Dict[str, str]
