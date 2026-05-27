"""Evaluate field extraction accuracy against annotated labels."""

import os
import json
import logging
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.services.extraction.field_extractor import field_extractor
from app.services.training.annotation_manager import AnnotationManager

logging.basicConfig(level=logging.WARNING)

def test_accuracy():
    labels_file = "training_data/annotated/labels.json"
    cache_dir = "training_data/ocr_cache"
    
    with open(labels_file) as f:
        labels = json.load(f)
        
    fields = [
        "invoice_number", "invoice_date", "vendor_gstin", "buyer_gstin",
        "taxable_amount", "cgst_amount", "sgst_amount", "igst_amount", "total_amount"
    ]
    
    total_annotated_values = {field: 0 for field in fields}
    correct_extractions = {field: 0 for field in fields}
    total_parsed_fields = {field: 0 for field in fields}
    
    total_files = 0
    skipped_files = 0
    
    for file_id, annot in labels.items():
        cache_file = os.path.join(cache_dir, f"{file_id}.json")
        if not os.path.exists(cache_file):
            skipped_files += 1
            continue
            
        total_files += 1
        with open(cache_file) as cf:
            cache_data = json.load(cf)
            
        ocr_text = cache_data.get('ocr_result', {}).get('text', '')
        if not ocr_text:
            continue
            
        # Run extractor
        result = field_extractor.extract_fields(ocr_text)
        extracted = result.get('fields', {})
        
        # Map label fields to extractor outputs if they differ
        extractor_field_map = {
            "vendor_gstin": "supplier_gstin",
        }
        
        for field in fields:
            annot_val = annot.get(field, "").strip()
            ext_field = extractor_field_map.get(field, field)
            ext_raw = extracted.get(ext_field)
            
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
                if ext_float is not None:
                    total_parsed_fields[field] += 1
            else:
                # Text fields
                annot_clean = annot_val.replace(" ", "").replace("-", "").replace("/", "").lower()
                ext_val = str(ext_raw).strip() if ext_raw is not None else ""
                ext_clean = ext_val.replace(" ", "").replace("-", "").replace("/", "").lower()
                
                if annot_val:
                    total_annotated_values[field] += 1
                    if ext_clean and (annot_clean == ext_clean or annot_clean in ext_clean or ext_clean in annot_clean):
                        correct_extractions[field] += 1
                if ext_clean:
                    total_parsed_fields[field] += 1

    print(f"Evaluation Summary ({total_files} files evaluated, {skipped_files} skipped):")
    print(f"{'Field Name':20s} | {'Annotated':10s} | {'Correct':10s} | {'Accuracy %':12s} | {'Parsed Count':12s}")
    print("-" * 75)
    
    overall_annotated = 0
    overall_correct = 0
    
    for field in fields:
        ann = total_annotated_values[field]
        corr = correct_extractions[field]
        parsed = total_parsed_fields[field]
        acc = (corr / ann * 100) if ann > 0 else 100.0
        print(f"{field:20s} | {ann:10d} | {corr:10d} | {acc:10.1f}% | {parsed:12d}")
        
        overall_annotated += ann
        overall_correct += corr
        
    overall_acc = (overall_correct / overall_annotated * 100) if overall_annotated > 0 else 0.0
    print("-" * 75)
    print(f"{'OVERALL':20s} | {overall_annotated:10d} | {overall_correct:10d} | {overall_acc:10.1f}%")

if __name__ == "__main__":
    test_accuracy()
