# Current Issues and Required Fixes

## Summary of Integration Work Completed

### ✅ PaddleOCR Integration - COMPLETE
- Created `paddle_ocr_extractor.py` module
- Updated `pdf_extractor.py` to support 3 OCR engines
- Updated `image_extractor.py` to support 3 OCR engines
- Updated frontend dropdown with PaddleOCR option
- Added dependencies to `requirements.txt`
- Updated `.env` configuration

**Status**: PaddleOCR packages are installed and ready to use

---

## 🔴 Critical Issues Remaining

### Issue 1: Line Items = 0 (CRITICAL)
**Problem**: Text-based extraction patterns don't match Google Vision OCR output format

**Current Behavior**:
```
Line items extracted: 0
```

**Root Cause**: The regex patterns in `parse_line_items_from_text()` expect specific formats that don't match how Google Vision outputs the table data.

**Solution Needed**:
1. Test with PaddleOCR first (better for tables)
2. If still failing, need to see actual OCR output format and adjust patterns
3. May need to add more flexible patterns for Google Vision output

**Files to Fix**:
- `invoice_ai_service/app/services/extraction/table_extractor.py`

---

### Issue 2: Buyer Name = "GUJARAT" (HIGH PRIORITY)
**Problem**: Extracting state name instead of company name

**Current Behavior**:
```json
"buyer": {
  "name": "GUJARAT",
  "gstin": "24ASHPS2461C1ZY"
}
```

**Expected**:
```json
"buyer": {
  "name": "ALAKH INTERNATIONAL",
  "gstin": "24ASHPS2461C1ZY"
}
```

**Root Cause**: The buyer name extraction pattern is matching "State Name : GUJARAT" before finding the actual company name "Name : ALAKH INTERNATIONAL"

**Solution Needed**:
1. Update `_extract_buyer_name()` in `field_extractor.py`
2. Add state name keywords to skip list
3. Prioritize "Name :" pattern over state patterns
4. Look for buyer name after "Details of Consignee" or "Shipped To" sections

**Files to Fix**:
- `invoice_ai_service/app/services/extraction/field_extractor.py`

---

### Issue 3: CGST/SGST = null (MEDIUM PRIORITY)
**Problem**: Tax amounts not being extracted

**Current Behavior**:
```json
"tax_summary": {
  "taxable_amount": 121875,
  "cgst": null,
  "sgst": null,
  "igst": null,
  "total_tax": 0,
  "total_amount": 121875
}
```

**Expected** (based on invoice 184):
```json
"tax_summary": {
  "taxable_amount": 114975,
  "cgst": 2874.38,
  "sgst": 2874.38,
  "igst": null,
  "total_tax": 5748.76,
  "total_amount": 120724
}
```

**Root Cause**: Tax extraction patterns may not match the format in split invoice sections

**Solution Needed**:
1. Check if tax info is in the split text section
2. Update CGST/SGST patterns to handle variations
3. Add fallback: calculate from (Total - Taxable) / 2

**Files to Fix**:
- `invoice_ai_service/app/services/extraction/field_extractor.py`

---

## 📋 Recommended Action Plan

### Step 1: Test with PaddleOCR (IMMEDIATE)
```bash
# Restart server
cd invoice_ai_service
uvicorn app.main:app --reload

# Test with PaddleOCR selected in frontend
# Upload invoice 188.pdf with "PaddleOCR (Best for Tables)" option
```

**Expected Outcome**: PaddleOCR should extract line items better than Google Vision

---

### Step 2: Fix Buyer Name Extraction (IF PADDLEOCR DOESN'T SOLVE IT)

**Change Required in `field_extractor.py`**:

```python
def _extract_buyer_name(self, text: str) -> str:
    """Extract buyer/customer name."""
    patterns = [
        # Pattern 1: Look for "Name : COMPANY NAME" after buyer section
        r'(?:Details\s+of\s+Consignee|Shipped\s+To|Billed\s+To|Buyer)[:\s]+.*?Name\s*:\s*([A-Z][A-Za-z\s&\.\-,]+?)(?:\n|GSTIN|Address|Place|State|$)',
        # Pattern 2: Direct "Name : COMPANY" pattern (prioritize this)
        r'Name\s*:\s*([A-Z][A-Za-z\s&\.\-,]+?)(?:\n|GSTIN|Address|Place|State|$)',
        # Pattern 3: Buyer/Customer followed by name
        r'(?:buyer|customer|bill\s+to|billed\s+to|consignee|shipped\s+to)[:\s]+([A-Z][A-Za-z\s&\.\-,]+?)(?:\n|GSTIN|Address|Mobile|Phone|Place|State|$)',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE | re.DOTALL)
        if match:
            name = match.group(1).strip()
            # Clean up: remove trailing colons, commas
            name = re.sub(r'[:\s,]+$', '', name)
            # Skip if it's a state name or field label
            skip_keywords = ['gstin', 'address', 'mobile', 'phone', 'state', 'place', 
                            'gujarat', 'maharashtra', 'karnataka', 'tamil nadu', 'delhi', 
                            'rajasthan', 'uttar pradesh', 'code', 'name']
            if len(name) > 3 and not any(kw in name.lower() for kw in skip_keywords):
                return name
    
    return ""
```

---

### Step 3: Fix Line Items Extraction (IF PADDLEOCR DOESN'T SOLVE IT)

**Option A**: Add more flexible patterns to `parse_line_items_from_text()`

**Option B**: Request actual OCR output to see exact format and create matching patterns

**Option C**: Use PaddleOCR's table structure detection (recommended)

---

### Step 4: Fix CGST/SGST Extraction

**Change Required in `field_extractor.py`**:

Add more flexible tax patterns and fallback calculation:

```python
# In _extract_cgst_amount() and _extract_sgst_amount()
# Add patterns like:
r'CGST\s*\([\d.]+%\)\s*[+\-]?\s*([\d,]+\.?\d*)'
r'SGST\s*\([\d.]+%\)\s*[+\-]?\s*([\d,]+\.?\d*)'

# Add fallback in extract_fields():
if not cgst and not sgst and total_amount and taxable_amount:
    tax_diff = total_amount - taxable_amount
    if tax_diff > 0:
        cgst = round(tax_diff / 2, 2)
        sgst = round(tax_diff / 2, 2)
```

---

## 🎯 Next Steps

1. **IMMEDIATE**: Test with PaddleOCR - this may solve line items issue
2. **IF NEEDED**: Apply buyer name fix
3. **IF NEEDED**: Apply tax extraction fix
4. **IF NEEDED**: Debug line items with actual OCR output

---

## Testing Checklist

After fixes:
- [ ] Line items extracted correctly (count > 0)
- [ ] Buyer name = "ALAKH INTERNATIONAL" (not "GUJARAT")
- [ ] CGST and SGST values extracted
- [ ] Total amount calculation correct
- [ ] Multi-invoice PDFs work correctly
- [ ] All 3 OCR engines work (Tesseract, Google Vision, PaddleOCR)

---

## Files Modified in This Session

1. ✅ `invoice_ai_service/app/services/extraction/paddle_ocr_extractor.py` - NEW
2. ✅ `invoice_ai_service/app/services/extraction/pdf_extractor.py` - UPDATED
3. ✅ `invoice_ai_service/app/services/extraction/image_extractor.py` - UPDATED
4. ✅ `invoice_ai_service/frontend/index.html` - UPDATED
5. ✅ `invoice_ai_service/requirements.txt` - UPDATED
6. ✅ `invoice_ai_service/.env` - UPDATED
7. ⏳ `invoice_ai_service/app/services/extraction/field_extractor.py` - NEEDS UPDATE
8. ⏳ `invoice_ai_service/app/services/extraction/table_extractor.py` - MAY NEED UPDATE

---

## Contact Points for Further Debugging

If issues persist after PaddleOCR test:
1. Share the actual OCR output text for invoice 188
2. Share a sample line item row from the PDF
3. Test with different invoices to see if pattern is consistent
