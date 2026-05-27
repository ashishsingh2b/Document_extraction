"""Evaluate field extraction accuracy and generate a detailed report."""

import os
import json
import logging
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.services.extraction.field_extractor import field_extractor

def generate_report():
    labels_file = "training_data/annotated/labels.json"
    cache_dir = "training_data/ocr_cache"
    report_file = "logs/accuracy_report.txt"
    
    with open(labels_file) as f:
        labels = json.load(f)
        
    fields = [
        "invoice_number", "invoice_date", "vendor_gstin", "buyer_gstin",
        "taxable_amount", "cgst_amount", "sgst_amount", "igst_amount", "total_amount"
    ]
    
    extractor_field_map = {
        "vendor_gstin": "supplier_gstin",
    }
    
    total_annotated_values = {field: 0 for field in fields}
    correct_extractions = {field: 0 for field in fields}
    total_parsed_fields = {field: 0 for field in fields}
    
    report_lines = []
    report_lines.append("=== DETAILED EXTRACTION REPORT ===")
    
    for file_id, annot in labels.items():
        cache_file = os.path.join(cache_dir, f"{file_id}.json")
        if not os.path.exists(cache_file):
            continue
            
        with open(cache_file) as cf:
            cache_data = json.load(cf)
            
        ocr_text = cache_data.get('ocr_result', {}).get('text', '')
        if not ocr_text:
            continue
            
        result = field_extractor.extract_fields(ocr_text)
        extracted = result.get('fields', {})
        
        report_lines.append(f"\nFile: {file_id}")
        
        for field in fields:
            annot_val = annot.get(field, "").strip()
            ext_field = extractor_field_map.get(field, field)
            ext_raw = extracted.get(ext_field)
            
            is_correct = False
            ext_display = str(ext_raw) if ext_raw is not None else ""
            
            if field in ["taxable_amount", "cgst_amount", "sgst_amount", "igst_amount", "total_amount"]:
                try:
                    annot_float = float(annot_val) if annot_val else None
                except ValueError:
                    annot_float = None
                
                try:
                    ext_float = float(ext_raw) if ext_raw is not None else None
                except (ValueError, TypeError):
                    ext_float = None
                
                if annot_val:
                    total_annotated_values[field] += 1
                    if ext_float is not None and abs(ext_float - annot_float) < 1.0:
                        correct_extractions[field] += 1
                        is_correct = True
                if ext_float is not None:
                    total_parsed_fields[field] += 1
            else:
                annot_clean = annot_val.replace(" ", "").replace("-", "").replace("/", "").lower()
                ext_val = str(ext_raw).strip() if ext_raw is not None else ""
                ext_clean = ext_val.replace(" ", "").replace("-", "").replace("/", "").lower()
                
                if annot_val:
                    total_annotated_values[field] += 1
                    if ext_clean and (annot_clean == ext_clean or annot_clean in ext_clean or ext_clean in annot_clean):
                        correct_extractions[field] += 1
                        is_correct = True
                if ext_clean:
                    total_parsed_fields[field] += 1
                    
            if annot_val or ext_display:
                status = "PASS" if (not annot_val and not ext_display) or is_correct else "FAIL"
                # If both are empty, it is not counted in total_annotated_values but it is technically correct
                if not annot_val and not ext_display:
                    status = "PASS"
                report_lines.append(f"  {field:15s} | Annot: {annot_val:15s} | Extracted: {ext_display:15s} | {status}")

    # Write report
    os.makedirs("logs", exist_ok=True)
    with open(report_file, "w") as rf:
        rf.write("\n".join(report_lines))
        
    print(f"Report written to {report_file}")

if __name__ == "__main__":
    generate_report()
