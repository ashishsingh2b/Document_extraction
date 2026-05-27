"""Invoice data models for internal processing."""

from typing import Optional, List, Dict, Any
from pydantic import BaseModel
from decimal import Decimal


class RawExtractedData(BaseModel):
    """Raw data extracted from document."""
    raw_text: Optional[str] = None
    raw_fields: Dict[str, Any] = {}
    raw_tables: List[Dict[str, Any]] = []
    extraction_method: str  # pdf, ocr, excel, docx
    page_count: Optional[int] = None


class CleanedData(BaseModel):
    """Cleaned data after OCR correction."""
    clean_fields: Dict[str, Any] = {}
    clean_tables: List[Dict[str, Any]] = []


class NormalizedData(BaseModel):
    """Normalized data with standard field names."""
    normalized_fields: Dict[str, Any] = {}
    normalized_items: List[Dict[str, Any]] = []


class ComplianceData(BaseModel):
    """Indian GST compliance data."""
    gstin_valid: bool = False
    hsn_sac_valid: bool = False
    place_of_supply_code: Optional[str] = None
    tax_type: Optional[str] = None  # CGST+SGST or IGST
    tds_applicable: bool = False
    tcs_applicable: bool = False
    rcm_applicable: bool = False
    einvoice_applicable: bool = False


class ProcessingContext(BaseModel):
    """Context for pipeline processing."""
    job_id: str
    file_path: str
    file_name: str
    file_type: str
    raw_data: Optional[RawExtractedData] = None
    cleaned_data: Optional[CleanedData] = None
    normalized_data: Optional[NormalizedData] = None
    compliance_data: Optional[ComplianceData] = None
    validation_result: Optional[Dict[str, Any]] = None
    erp_schema: Optional[Dict[str, Any]] = None
    confidence_scores: Optional[Dict[str, float]] = None
