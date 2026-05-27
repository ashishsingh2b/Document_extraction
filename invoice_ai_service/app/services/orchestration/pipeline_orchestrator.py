"""Pipeline Orchestrator — connects all processing layers end-to-end."""

import logging
import time
from typing import Dict, Any, Optional, List

from app.models.invoice import RawExtractedData
from app.services.cleaning.data_cleaner import DataCleaner
from app.services.normalization.field_mapper import FieldMapper
from app.services.compliance.compliance_engine import ComplianceEngine
from app.services.validation.invoice_validator import InvoiceValidator
from app.services.mapping.erp_mapper import ERPMapper
from app.services.confidence.confidence_service import FieldConfidenceScorer

logger = logging.getLogger(__name__)


class PipelineOrchestrator:
    def __init__(self):
        self.data_cleaner = DataCleaner()
        self.field_mapper = FieldMapper()
        self.compliance_engine = ComplianceEngine()
        self.validator = InvoiceValidator()
        self.erp_mapper = ERPMapper()
        self.confidence_scorer = FieldConfidenceScorer()

    def process(
        self,
        extracted_text: str,
        extracted_fields: Dict[str, Any],
        line_items: List[Dict[str, Any]],
        extraction_metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        start_time = time.time()
        logger.info("=" * 80)
        logger.info("PIPELINE ORCHESTRATOR STARTING")
        logger.info("=" * 80)

        raw = RawExtractedData(
            raw_text=extracted_text,
            raw_fields=extracted_fields,
            raw_tables=line_items,
            extraction_method=extraction_metadata.get("extraction_method", "unknown") if extraction_metadata else "unknown",
        )

        # Step 1: Data Cleaning
        logger.info("[PIPELINE] Step 1/6: Data Cleaning...")
        cleaned = self.data_cleaner.clean_raw_data(raw)
        logger.info(f"[PIPELINE] ✓ Cleaned {len(cleaned.clean_fields)} fields, {len(cleaned.clean_tables)} line items")

        # Step 2: Normalization
        logger.info("[PIPELINE] Step 2/6: Field Normalization...")
        normalized = self.field_mapper.normalize(cleaned)
        logger.info(f"[PIPELINE] ✓ Normalized {len(normalized.normalized_fields)} fields, {len(normalized.normalized_items)} items")

        # Step 3: GST Compliance
        logger.info("[PIPELINE] Step 3/6: GST Compliance Check...")
        compliance_result = self.compliance_engine.validate(normalized.normalized_fields, extracted_text)
        cd = compliance_result["compliance_data"]
        logger.info(f"[PIPELINE] ✓ GSTIN valid: {cd.gstin_valid} | HSN/SAC: {cd.hsn_sac_valid} | Tax: {cd.tax_type}")
        logger.info(f"[PIPELINE] ✓ TDS: {cd.tds_applicable} | TCS: {cd.tcs_applicable} | RCM: {cd.rcm_applicable}")
        logger.info(f"[PIPELINE] ✓ Invoice Type: {compliance_result['invoice_type']}")
        logger.info(f"[PIPELINE] ✓ e-Invoice Applicable: {cd.einvoice_applicable}")

        # Step 4: Validation
        logger.info("[PIPELINE] Step 4/6: Business Rule Validation...")
        validation_result = self.validator.validate(normalized.normalized_fields, compliance_result)
        validation_dict = {
            "is_valid": validation_result.is_valid,
            "errors": [e.model_dump() for e in validation_result.errors],
            "warnings": [w.model_dump() for w in validation_result.warnings],
        }
        logger.info(f"[PIPELINE] ✓ Valid: {validation_result.is_valid} | Errors: {len(validation_result.errors)} | Warnings: {len(validation_result.warnings)}")

        # Step 5: Confidence Scoring
        logger.info("[PIPELINE] Step 5/6: Field-Level Confidence Scoring...")
        field_conf_scores = self.confidence_scorer.score_fields(normalized.normalized_fields)
        logger.info(f"[PIPELINE] ✓ Overall Confidence: {field_conf_scores['overall']}%")
        logger.info(f"[PIPELINE] ✓ HITL Required: {field_conf_scores['hitl_required']}")

        # Step 6: ERP Schema Mapping
        logger.info("[PIPELINE] Step 6/6: ERP Schema Mapping...")
        erp_schema = self.erp_mapper.map_to_erp_schema(
            normalized_fields=normalized.normalized_fields,
            compliance_result=compliance_result,
            confidence_scores={
                "overall": field_conf_scores["overall"],
                "invoice_number": field_conf_scores["field_scores"].get("invoice_number"),
                "invoice_date": field_conf_scores["field_scores"].get("invoice_date"),
                "party_name": max(
                    field_conf_scores["field_scores"].get("supplier_name", 0),
                    field_conf_scores["field_scores"].get("buyer_name", 0),
                ),
                "gstin": max(
                    field_conf_scores["field_scores"].get("supplier_gstin", 0),
                    field_conf_scores["field_scores"].get("buyer_gstin", 0),
                ),
                "items": field_conf_scores["field_scores"].get("items", 0),
                "totals": min(
                    field_conf_scores["field_scores"].get("total_amount", 0),
                    field_conf_scores["field_scores"].get("taxable_amount", 0),
                ),
            },
            validation_result=validation_result,
            extraction_metadata=extraction_metadata,
        )
        erp_dict = self.erp_mapper.to_dict(erp_schema)
        logger.info(f"[PIPELINE] ✓ ERP Schema generated (v{erp_dict['schema_version']})")

        elapsed = time.time() - start_time
        logger.info(f"[PIPELINE] Pipeline completed in {elapsed:.2f}s")
        logger.info(f"[PIPELINE] Result: {'PASS' if validation_result.is_valid else 'FAIL'} | Confidence: {field_conf_scores['overall']}%")
        logger.info("=" * 80)

        return {
            "normalized_fields": normalized.normalized_fields,
            "normalized_items": normalized.normalized_items,
            "compliance": compliance_result,
            "validation": validation_dict,
            "confidence": field_conf_scores,
            "erp_schema": erp_dict,
            "pipeline_elapsed_seconds": round(elapsed, 2),
            "overall_confidence": field_conf_scores["overall"],
            "hitl_required": field_conf_scores["hitl_required"],
            "is_valid": validation_result.is_valid,
        }

    def process_fields(
        self,
        fields: Dict[str, Any],
        raw_text: str = "",
        extraction_metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        items = fields.get("items", [])

        cleaned_fields = self.data_cleaner.clean_extracted_fields(fields)
        normalized_fields = self.field_mapper.normalize_fields(cleaned_fields)
        normalized_items = [self.field_mapper.normalize_line_item(it) for it in items]

        normalized_fields["items"] = normalized_items

        compliance_result = self.compliance_engine.validate(normalized_fields, raw_text)
        validation_result = self.validator.validate(normalized_fields, compliance_result)
        field_conf_scores = self.confidence_scorer.score_fields(normalized_fields)

        erp_dict = self.erp_mapper.erp_schema_from_fields(
            fields=normalized_fields,
            compliance_result=compliance_result,
            confidence_scores={
                "overall": field_conf_scores["overall"],
                "invoice_number": field_conf_scores["field_scores"].get("invoice_number"),
                "invoice_date": field_conf_scores["field_scores"].get("invoice_date"),
                "party_name": max(
                    field_conf_scores["field_scores"].get("supplier_name", 0),
                    field_conf_scores["field_scores"].get("buyer_name", 0),
                ),
                "gstin": max(
                    field_conf_scores["field_scores"].get("supplier_gstin", 0),
                    field_conf_scores["field_scores"].get("buyer_gstin", 0),
                ),
                "items": field_conf_scores["field_scores"].get("items", 0),
                "totals": min(
                    field_conf_scores["field_scores"].get("total_amount", 0),
                    field_conf_scores["field_scores"].get("taxable_amount", 0),
                ),
            },
        )

        return {
            "normalized_fields": normalized_fields,
            "compliance": compliance_result,
            "validation": {
                "is_valid": validation_result.is_valid,
                "errors": [e.model_dump() for e in validation_result.errors],
                "warnings": [w.model_dump() for w in validation_result.warnings],
            },
            "confidence": field_conf_scores,
            "erp_schema": erp_dict,
            "overall_confidence": field_conf_scores["overall"],
            "hitl_required": field_conf_scores["hitl_required"],
            "is_valid": validation_result.is_valid,
        }


pipeline_orchestrator = PipelineOrchestrator()
