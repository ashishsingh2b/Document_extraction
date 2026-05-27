"""Audit logging service for compliance tracking."""

import logging
import json
from datetime import datetime
from typing import Optional, Dict, Any
from app.config.settings import settings

logger = logging.getLogger(__name__)


class AuditLogger:
    """Audit logger for tracking invoice processing events."""
    
    def __init__(self):
        """Initialize audit logger."""
        # Create logs directory if it doesn't exist
        import os
        os.makedirs("logs", exist_ok=True)
        
        self.logger = logging.getLogger("audit")
        self.logger.setLevel(logging.INFO)
        
        # Create audit log handler
        handler = logging.FileHandler("logs/audit.log")
        formatter = logging.Formatter(
            '{"timestamp": "%(asctime)s", "level": "%(levelname)s", '
            '"event": "%(message)s"}'
        )
        handler.setFormatter(formatter)
        self.logger.addHandler(handler)
    
    def log_upload(
        self,
        job_id: str,
        filename: str,
        file_size: int,
        user_id: Optional[str] = None
    ) -> None:
        """Log file upload event."""
        event = {
            "event_type": "upload",
            "job_id": job_id,
            "filename": filename,
            "file_size": file_size,
            "user_id": user_id,
            "timestamp": datetime.utcnow().isoformat()
        }
        self.logger.info(json.dumps(event))
    
    def log_extraction(
        self,
        job_id: str,
        extraction_method: str,
        confidence_score: float,
        fields_extracted: int
    ) -> None:
        """Log extraction completion event."""
        event = {
            "event_type": "extraction",
            "job_id": job_id,
            "extraction_method": extraction_method,
            "confidence_score": confidence_score,
            "fields_extracted": fields_extracted,
            "timestamp": datetime.utcnow().isoformat()
        }
        self.logger.info(json.dumps(event))
    
    def log_validation(
        self,
        job_id: str,
        is_valid: bool,
        errors: list,
        warnings: list
    ) -> None:
        """Log validation event."""
        event = {
            "event_type": "validation",
            "job_id": job_id,
            "is_valid": is_valid,
            "error_count": len(errors),
            "warning_count": len(warnings),
            "errors": errors,
            "warnings": warnings,
            "timestamp": datetime.utcnow().isoformat()
        }
        self.logger.info(json.dumps(event))

    
    def log_hitl_correction(
        self,
        job_id: str,
        reviewer_id: str,
        original_values: Dict[str, Any],
        corrected_values: Dict[str, Any]
    ) -> None:
        """Log HITL correction event."""
        event = {
            "event_type": "hitl_correction",
            "job_id": job_id,
            "reviewer_id": reviewer_id,
            "original_values": original_values,
            "corrected_values": corrected_values,
            "timestamp": datetime.utcnow().isoformat()
        }
        self.logger.info(json.dumps(event))
    
    def log_einvoice_generation(
        self,
        job_id: str,
        irn: str,
        irp_status: str,
        ack_number: Optional[str] = None
    ) -> None:
        """Log e-Invoice IRN generation event."""
        event = {
            "event_type": "einvoice_generation",
            "job_id": job_id,
            "irn": irn,
            "irp_status": irp_status,
            "ack_number": ack_number,
            "timestamp": datetime.utcnow().isoformat()
        }
        self.logger.info(json.dumps(event))
    
    def log_error(
        self,
        job_id: str,
        error_type: str,
        error_message: str,
        stack_trace: Optional[str] = None
    ) -> None:
        """Log error event."""
        event = {
            "event_type": "error",
            "job_id": job_id,
            "error_type": error_type,
            "error_message": error_message,
            "stack_trace": stack_trace,
            "timestamp": datetime.utcnow().isoformat()
        }
        self.logger.error(json.dumps(event))


# Global audit logger instance
audit_logger = AuditLogger()
