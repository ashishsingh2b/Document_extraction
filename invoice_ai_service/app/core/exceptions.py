"""Custom exceptions for the application."""

class InvoiceServiceException(Exception):
    """Base exception for invoice service."""
    def __init__(self, message: str, error_code: str = "INTERNAL_ERROR"):
        self.message = message
        self.error_code = error_code
        super().__init__(self.message)


class FileSizeExceededError(InvoiceServiceException):
    """Raised when uploaded file exceeds size limit."""
    def __init__(self, message: str = "File size exceeds maximum limit"):
        super().__init__(message, "FILE_SIZE_EXCEEDED")


class UnsupportedFormatError(InvoiceServiceException):
    """Raised when file format is not supported."""
    def __init__(self, message: str = "File format not supported"):
        super().__init__(message, "UNSUPPORTED_FORMAT")


class MaliciousFileError(InvoiceServiceException):
    """Raised when file contains malicious content."""
    def __init__(self, message: str = "File contains malicious content"):
        super().__init__(message, "MALICIOUS_FILE")


class ExtractionError(InvoiceServiceException):
    """Raised when extraction fails."""
    def __init__(self, message: str = "Failed to extract data from file"):
        super().__init__(message, "EXTRACTION_ERROR")


class ValidationError(InvoiceServiceException):
    """Raised when validation fails."""
    def __init__(self, message: str, errors: list = None):
        super().__init__(message, "VALIDATION_ERROR")
        self.errors = errors or []


class GSTINValidationError(ValidationError):
    """Raised when GSTIN validation fails."""
    def __init__(self, message: str = "Invalid GSTIN"):
        super().__init__(message, [])
        self.error_code = "INVALID_GSTIN"


class HSNValidationError(ValidationError):
    """Raised when HSN/SAC validation fails."""
    def __init__(self, message: str = "Invalid HSN/SAC code"):
        super().__init__(message, [])
        self.error_code = "INVALID_HSN_SAC"


class IRNGenerationError(InvoiceServiceException):
    """Raised when IRN generation fails."""
    def __init__(self, message: str = "Failed to generate IRN"):
        super().__init__(message, "IRN_GENERATION_ERROR")


class IRPIntegrationError(InvoiceServiceException):
    """Raised when IRP portal integration fails."""
    def __init__(self, message: str = "IRP portal integration failed"):
        super().__init__(message, "IRP_INTEGRATION_ERROR")
