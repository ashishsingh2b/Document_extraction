"""Invoice validation layer — business rules and consistency checks."""

import logging
import re
from typing import Dict, Any, List
from datetime import datetime

from app.models.schemas import ValidationError, ValidationResult

logger = logging.getLogger(__name__)


class InvoiceValidator:
    def validate(self, normalized_fields: Dict[str, Any], compliance_result: Dict[str, Any]) -> ValidationResult:
        errors: List[ValidationError] = []
        warnings: List[ValidationError] = []

        self._validate_invoice_number(normalized_fields.get("invoice_number"), errors)
        self._validate_date(normalized_fields.get("invoice_date"), "invoice_date", errors)
        self._validate_party_name(normalized_fields.get("supplier_name"), "supplier_name", errors)
        self._validate_party_name(normalized_fields.get("buyer_name"), "buyer_name", warnings)
        self._validate_gstin_compliance(compliance_result, errors, warnings)
        self._validate_amounts(normalized_fields, errors, warnings)
        self._validate_line_items(normalized_fields.get("items", []), errors, warnings)

        return ValidationResult(is_valid=len(errors) == 0, errors=errors, warnings=warnings)

    def _validate_invoice_number(self, value: Any, errors: List[ValidationError]) -> None:
        if not value:
            errors.append(ValidationError(
                field="invoice_number",
                message="Invoice number is missing",
                error_code="MISSING_INVOICE_NUMBER",
            ))
            return
        if not isinstance(value, str) or len(str(value)) > 30:
            errors.append(ValidationError(
                field="invoice_number",
                message=f"Invalid invoice number length: {value}",
                error_code="INVALID_INVOICE_NUMBER",
            ))

    def _validate_date(self, value: Any, field: str, errors: List[ValidationError]) -> None:
        if not value:
            errors.append(ValidationError(
                field=field,
                message=f"{field} is missing",
                error_code="MISSING_DATE",
            ))
            return
        try:
            parsed = None
            for fmt in ("%d-%m-%Y", "%d/%m/%Y", "%Y-%m-%d", "%d-%b-%Y", "%d %b %Y"):
                try:
                    parsed = datetime.strptime(str(value), fmt)
                    break
                except ValueError:
                    continue
            if parsed is None:
                raise ValueError
            if parsed > datetime.now():
                errors.append(ValidationError(
                    field=field,
                    message=f"{field} is in the future: {value}",
                    error_code="FUTURE_DATE",
                ))
        except (ValueError, TypeError):
            errors.append(ValidationError(
                field=field,
                message=f"Invalid {field} format: {value}",
                error_code="INVALID_DATE_FORMAT",
            ))

    def _validate_party_name(self, value: Any, field: str, issues: List[ValidationError]) -> None:
        if not value:
            issues.append(ValidationError(
                field=field,
                message=f"{field} is missing",
                error_code="MISSING_PARTY_NAME",
            ))
        elif len(str(value)) < 3:
            issues.append(ValidationError(
                field=field,
                message=f"{field} too short: {value}",
                error_code="SHORT_PARTY_NAME",
            ))

    def _validate_gstin_compliance(self, compliance: Dict[str, Any], errors: List[ValidationError], warnings: List[ValidationError]) -> None:
        gstin = compliance.get("gstin_validation", {})
        if not gstin.get("supplier_valid"):
            errors.append(ValidationError(
                field="supplier_gstin",
                message=f"Supplier GSTIN invalid: {gstin.get('supplier_message', 'unknown')}",
                error_code="INVALID_SUPPLIER_GSTIN",
            ))
        if not gstin.get("buyer_valid"):
            warnings.append(ValidationError(
                field="buyer_gstin",
                message=f"Buyer GSTIN invalid: {gstin.get('buyer_message', 'unknown')}",
                error_code="INVALID_BUYER_GSTIN",
            ))

    def _validate_amounts(self, fields: Dict[str, Any], errors: List[ValidationError], warnings: List[ValidationError]) -> None:
        total = fields.get("total_amount")
        taxable = fields.get("taxable_amount")
        cgst = fields.get("cgst_amount")
        sgst = fields.get("sgst_amount")
        igst = fields.get("igst_amount")

        if not total:
            errors.append(ValidationError(
                field="total_amount",
                message="Total amount is missing",
                error_code="MISSING_TOTAL",
            ))

        if total and taxable and taxable > total:
            warnings.append(ValidationError(
                field="taxable_amount",
                message=f"Taxable amount ({taxable}) exceeds total ({total})",
                error_code="TAXABLE_EXCEEDS_TOTAL",
            ))

        if total and taxable:
            expected_tax = round(total - taxable, 2)
            actual_tax = (cgst or 0) + (sgst or 0) + (igst or 0)
            if actual_tax > 0 and abs(expected_tax - actual_tax) > 1:
                warnings.append(ValidationError(
                    field="tax_amount",
                    message=f"Tax mismatch: expected ~{expected_tax}, got CGST={cgst} SGST={sgst} IGST={igst}",
                    error_code="TAX_MISMATCH",
                ))

    def _validate_line_items(self, items: List[Dict[str, Any]], errors: List[ValidationError], warnings: List[ValidationError]) -> None:
        if not items:
            warnings.append(ValidationError(
                field="items",
                message="No line items extracted",
                error_code="NO_LINE_ITEMS",
            ))
            return
        for i, item in enumerate(items):
            if not item.get("description"):
                warnings.append(ValidationError(
                    field=f"items[{i}].description",
                    message=f"Item {i+1} has no description",
                    error_code="MISSING_ITEM_DESCRIPTION",
                ))
            amount = item.get("amount")
            if amount is not None:
                try:
                    if float(amount) <= 0:
                        warnings.append(ValidationError(
                            field=f"items[{i}].amount",
                            message=f"Item {i+1} has non-positive amount: {amount}",
                            error_code="INVALID_ITEM_AMOUNT",
                        ))
                except (ValueError, TypeError):
                    pass


invoice_validator = InvoiceValidator()
