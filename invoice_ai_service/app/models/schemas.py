"""Pydantic schemas for invoice data structures."""

from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime
from decimal import Decimal


class PartyDetails(BaseModel):
    """Party (supplier/buyer) details."""
    party_name: str
    party_address: Optional[str] = None
    gstin: Optional[str] = Field(None, min_length=15, max_length=15)
    pan: Optional[str] = Field(None, min_length=10, max_length=10)
    state_name: Optional[str] = None
    state_code: Optional[str] = Field(None, min_length=2, max_length=2)
    email: Optional[str] = None
    phone: Optional[str] = None


class InvoiceItem(BaseModel):
    """Invoice line item."""
    item_name: str
    hsn_sac_code: Optional[str] = None
    quantity: Optional[Decimal] = None
    unit: Optional[str] = None
    unit_price: Optional[Decimal] = None
    line_total: Decimal
    cgst_rate: Optional[Decimal] = None
    cgst_amount: Optional[Decimal] = None
    sgst_rate: Optional[Decimal] = None
    sgst_amount: Optional[Decimal] = None
    igst_rate: Optional[Decimal] = None
    igst_amount: Optional[Decimal] = None
    cess_rate: Optional[Decimal] = None
    cess_amount: Optional[Decimal] = None


class TaxSummary(BaseModel):
    """Tax summary with CGST/SGST/IGST breakdown."""
    subtotal: Decimal
    total_cgst: Optional[Decimal] = Decimal(0)
    total_sgst: Optional[Decimal] = Decimal(0)
    total_igst: Optional[Decimal] = Decimal(0)
    total_cess: Optional[Decimal] = Decimal(0)
    tds_amount: Optional[Decimal] = Decimal(0)
    tcs_amount: Optional[Decimal] = Decimal(0)
    discount: Optional[Decimal] = Decimal(0)


class Totals(BaseModel):
    """Invoice totals."""
    subtotal: Decimal
    tax_amount: Decimal
    grand_total: Decimal
    amount_in_words: Optional[str] = None


class DocumentDetails(BaseModel):
    """Invoice document details."""
    invoice_number: str
    invoice_date: str
    invoice_type: str = "Tax Invoice"
    place_of_supply: Optional[str] = None
    place_of_supply_code: Optional[str] = None
    reverse_charge: bool = False
    irn: Optional[str] = Field(None, min_length=64, max_length=64)
    irn_date: Optional[str] = None
    qr_code: Optional[str] = None  # Base64 encoded QR image
    eway_bill_number: Optional[str] = None
    vehicle_number: Optional[str] = None


class ConfidenceScores(BaseModel):
    """Confidence scores for extraction quality."""
    overall: float = Field(..., ge=0, le=100)
    invoice_number: Optional[float] = Field(None, ge=0, le=100)
    invoice_date: Optional[float] = Field(None, ge=0, le=100)
    party_name: Optional[float] = Field(None, ge=0, le=100)
    gstin: Optional[float] = Field(None, ge=0, le=100)
    items: Optional[float] = Field(None, ge=0, le=100)
    totals: Optional[float] = Field(None, ge=0, le=100)


class ERPSchema(BaseModel):
    """Complete ERP-ready invoice schema."""
    schema_version: str = "1.0"
    supplier_details: PartyDetails
    buyer_details: PartyDetails
    document_details: DocumentDetails
    items: List[InvoiceItem]
    tax_summary: TaxSummary
    totals: Totals
    confidence_scores: ConfidenceScores
    extraction_metadata: Optional[Dict[str, Any]] = None


class ValidationError(BaseModel):
    """Validation error details."""
    field: str
    message: str
    error_code: str


class ValidationResult(BaseModel):
    """Validation result."""
    is_valid: bool
    errors: List[ValidationError] = []
    warnings: List[ValidationError] = []
