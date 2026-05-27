# Multi-Invoice PDF Implementation

## Status: IN PROGRESS

## What's Implemented:

✅ **invoice_splitter.py** - Created
- Detects invoice boundaries by finding "Invoice No" changes
- Splits text into separate invoice sections
- Returns array of invoice sections with metadata

## What Needs to be Done:

### 1. Update upload.py Processing Logic

**Current Behavior:**
- Processes entire PDF as single invoice
- Mixes data from multiple invoices

**Required Behavior:**
- Detect invoice boundaries (DONE in invoice_splitter.py)
- Process each invoice section separately
- Return array of invoices

**Changes Needed in `_process_invoice_sync()`:**

```python
# After Step 2 (classification), add:

# Step 2.5: Detect and split multi-invoice PDFs
invoice_sections = invoice_splitter.detect_and_split(extracted_text)

if len(invoice_sections) > 1:
    logger.info(f"Multi-invoice PDF: {len(invoice_sections)} invoices")

# Step 3: Extract ALL line items from PDF
all_line_items = table_extractor.parse_line_items_from_text(extracted_text)

# Step 4: Process EACH invoice section separately
invoices_data = []

for idx, section in enumerate(invoice_sections):
    invoice_text = section['text']
    invoice_num = section['invoice_number']
    
    # Extract fields for THIS invoice only
    field_result = field_extractor.extract_fields(invoice_text)
    extracted_fields = field_result['fields']
    
    # Assign line items to THIS invoice
    # Simple: divide items equally
    items_per_inv = len(all_line_items) // len(invoice_sections)
    start = idx * items_per_inv
    end = start + items_per_inv if idx < len(invoice_sections)-1 else len(all_line_items)
    line_items = all_line_items[start:end]
    
    extracted_fields['items'] = line_items
    
    invoices_data.append({
        "invoice_number": invoice_num,
        "invoice_data": extracted_fields,
        "line_items_count": len(line_items)
    })

# Return array of invoices
return UploadResponse(
    extracted_data={
        "invoice_count": len(invoices_data),
        "invoices": invoices_data,  # ARRAY of invoices
        "is_multi_invoice": len(invoice_sections) > 1
    }
)
```

### 2. Update Frontend to Display Multiple Invoices

**Current:** Shows single invoice schema

**Required:** 
- Show invoice count
- Display each invoice separately
- Add tabs or accordion for multiple invoices

### 3. Fix Invoice Number Extraction

**Pattern to add in field_extractor.py:**

```python
# Current patterns miss "Invoice No. : 184" format
patterns = [
    r'Invoice\s*(?:No\.?|Number|#)[\s:]*([A-Z0-9\-/]+)',  # Add this
    r'(?:^|\n)Invoice[\s:]+([A-Z0-9\-/]+)',  # And this
]
```

### 4. Fix Supplier/Buyer Name Extraction

**Issue:** Extracting addresses instead of company names

**Fix in field_extractor.py:**

```python
def _extract_supplier_name(self, text: str) -> Optional[str]:
    # Look for company name in first 10 lines BEFORE first GSTIN
    gstin_pos = text.find('GSTIN')
    if gstin_pos > 0:
        header = text[:gstin_pos]
        lines = header.split('\n')
        
        for line in lines[:10]:
            # Skip addresses (contain numbers, "SHOP", "FLOOR")
            if re.search(r'\d{3,}', line):  # Has 3+ digits
                continue
            if any(kw in line.upper() for kw in ['SHOP', 'FLOOR', 'ROAD', 'MARKET']):
                continue
            
            # Look for company name (ALL CAPS, has "COLLECTION", "TRADERS", etc.)
            if line.isupper() and len(line) > 5:
                if any(kw in line for kw in ['COLLECTION', 'TRADERS', 'INTERNATIONAL', 'SAREE']):
                    return line.strip()
```

### 5. Fix CGST/SGST Extraction

**Pattern to add in field_extractor.py:**

```python
# Current patterns miss "CGST (2.50%) 2874.38" format
patterns = [
    r'CGST\s*\([\d.]+%\)[\s:]*(?:rs\.?|₹|inr)?\s*([\d,]+\.?\d*)',  # Add this
    r'SGST\s*\([\d.]+%\)[\s:]*(?:rs\.?|₹|inr)?\s*([\d,]+\.?\d*)',  # Add this
]
```

## Expected Output Format:

### Single Invoice:
```json
{
  "invoice_count": 1,
  "is_multi_invoice": false,
  "invoices": [
    {
      "invoice_number": "184",
      "invoice_data": {
        "invoice_number": "184",
        "invoice_date": "10/02/2025",
        "supplier_name": "MUSKAN COLLECTION",
        "buyer_name": "ALAKH INTERNATIONAL",
        "items": [...]
      },
      "line_items_count": 1
    }
  ]
}
```

### Multi-Invoice:
```json
{
  "invoice_count": 2,
  "is_multi_invoice": true,
  "invoices": [
    {
      "invoice_number": "184",
      "invoice_data": {
        "invoice_number": "184",
        "invoice_date": "10/02/2025",
        "supplier_name": "MUSKAN COLLECTION",
        "buyer_name": "ALAKH INTERNATIONAL",
        "items": [
          {
            "description": "WETLESS",
            "hsn_code": "5407",
            "quantity": "365",
            "amount": "114975.00"
          }
        ]
      },
      "line_items_count": 1
    },
    {
      "invoice_number": "185",
      "invoice_data": {
        "invoice_number": "185",
        "invoice_date": "12/02/2025",
        "supplier_name": "MUSKAN COLLECTION",
        "buyer_name": "ALAKH INTERNATIONAL",
        "items": [
          {
            "description": "WETLESS",
            "hsn_code": "5407",
            "quantity": "375",
            "amount": "118125.00"
          }
        ]
      },
      "line_items_count": 1
    }
  ]
}
```

## Testing:

1. Upload "MUSKAN COLLECTION ALL BILLS.pdf"
2. Should see: `"invoice_count": 2`
3. Should see 2 separate invoice schemas
4. Each invoice should have correct:
   - Invoice number (184, 185)
   - Invoice date (10/02/2025, 12/02/2025)
   - Line items (1 item each, not mixed)
   - Amounts (114975.00, 118125.00)

## Priority:

1. **HIGH**: Update upload.py to process multiple invoices
2. **HIGH**: Fix invoice number extraction
3. **MEDIUM**: Fix supplier/buyer name extraction
4. **MEDIUM**: Fix CGST/SGST extraction
5. **LOW**: Update frontend to display multiple invoices

## Files to Modify:

1. ✅ `app/services/extraction/invoice_splitter.py` - DONE
2. ⏳ `app/api/routes/upload.py` - IN PROGRESS (need to update _process_invoice_sync)
3. ⏳ `app/services/extraction/field_extractor.py` - Need pattern fixes
4. ⏳ `frontend/index.html` - Need multi-invoice display

## Next Step:

Manually update `upload.py` to implement the multi-invoice processing logic shown above.
