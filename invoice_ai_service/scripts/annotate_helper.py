import os
import sys
import argparse
import glob
import re

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.services.extraction.universal_extractor import universal_extractor
from app.services.extraction.spatial_extractor import spatial_extractor
from app.services.training.annotation_manager import AnnotationManager

def extract_prefill(text: str) -> dict:
    prefill = {
        'invoice_type': 'tax_invoice',
        'invoice_number': '',
        'invoice_date': '',
        'vendor_gstin': '',
        'buyer_gstin': '',
        'taxable_amount': '',
        'cgst_amount': '',
        'sgst_amount': '',
        'igst_amount': '',
        'total_amount': ''
    }
    
    # invoice number (improved)
    inv_match = re.search(r'(?i)(?:inv|invoice|bill|challan)[\s\-\:]*(?:no|num|number|#)[\s\-\:]*([A-Za-z0-9\-\/\\]+)', text)
    if inv_match:
        prefill['invoice_number'] = inv_match.group(1)
        
    # date (improved)
    date_match = re.search(r'\b(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\b', text)
    if date_match:
        prefill['invoice_date'] = date_match.group(1)
        
    # gstins
    gstins = re.findall(r'\d{2}[A-Z]{5}\d{4}[A-Z]{1}[A-Z\d]{1}[Z]{1}[A-Z\d]{1}', text)
    if len(gstins) > 0:
        prefill['vendor_gstin'] = gstins[0]
    if len(gstins) > 1:
        prefill['buyer_gstin'] = gstins[1]
        
    # amounts (rough prefill by looking at last amounts or after labels)
    amounts = [float(a.replace(',', '')) for a in re.findall(r'\b\d{1,9}(?:,\d{2,3})*\.\d{2}\b', text)]
    if amounts:
        prefill['total_amount'] = str(max(amounts))

    # taxes
    for line in text.split('\n'):
        line_lower = line.lower()
        nums = re.findall(r'\b\d{1,9}(?:,\d{2,3})*\.\d{2}\b', line)
        if not nums:
            continue
        
        last_num = nums[-1]
        if 'cgst' in line_lower or 'central gst' in line_lower:
            prefill['cgst_amount'] = last_num
        elif 'sgst' in line_lower or 'state gst' in line_lower:
            prefill['sgst_amount'] = last_num
        elif 'igst' in line_lower or 'integrated gst' in line_lower:
            prefill['igst_amount'] = last_num
        elif 'taxable' in line_lower or 'net total' in line_lower or 'sub total' in line_lower or 'subtotal' in line_lower:
            prefill['taxable_amount'] = last_num

    return prefill

def main():
    parser = argparse.ArgumentParser(description="Annotate raw invoices for ML training")
    parser.add_argument("--data-dir", type=str, default="training_data/raw", help="Directory with raw invoices")
    parser.add_argument("--labels", type=str, default="training_data/annotated/labels.json", help="Path to save labels")
    args = parser.parse_args()

    annotation_manager = AnnotationManager(args.labels)
    all_files = glob.glob(os.path.join(args.data_dir, "**/*.*"), recursive=True)
    valid_files = [f for f in all_files if f.lower().endswith(('.pdf', '.jpg', '.jpeg', '.png'))]
    
    print(f"Found {len(valid_files)} valid invoices to annotate.")
    
    for file_path in valid_files:
        file_id = os.path.basename(file_path)
        existing = annotation_manager.get_annotation(file_id)
        if existing:
            print(f"[{file_id}] Already annotated. Skipping.")
            continue
            
        print(f"\nProcessing: {file_path}")
        
        try:
            with open(file_path, 'rb') as f:
                file_data = f.read()
            mime_type = 'application/pdf' if file_path.lower().endswith('.pdf') else 'image/jpeg'
            
            print(f"Extracting OCR text...")
            ocr_result = universal_extractor.extract_text(file_data, mime_type)
            text = ocr_result.get('text', '')
            
            print(f"Running Spatial Bounding Box Extraction...")
            spatial_results = spatial_extractor.extract_all(file_data, mime_type)
            
            prefill = extract_prefill(text)
            
            # Overlay spatial bounds over regex
            for k, v in spatial_results.items():
                if v and not prefill.get(k):
                    prefill[k] = v
            
            print("\nAuto-detected fields:")
            for k, v in prefill.items():
                print(f"  {k}: {v}")
                
            print("\nOptions: [a] Accept all, [s] Skip, [e] Edit")
            choice = input("Choice: ").strip().lower()
            
            if choice == 's':
                continue
            elif choice == 'a':
                annotation_manager.add_annotation(file_id, prefill)
                print("Saved.")
            elif choice == 'e':
                edited = {}
                for k, v in prefill.items():
                    new_val = input(f"  {k} [{v}]: ").strip()
                    edited[k] = new_val if new_val else v
                annotation_manager.add_annotation(file_id, edited)
                print("Saved.")
            else:
                print("Invalid choice, skipping.")
                
        except Exception as e:
            print(f"Error processing {file_path}: {e}")

if __name__ == "__main__":
    main()
