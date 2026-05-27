# OCR-First Extraction Strategy

## Date: May 22, 2026

## Change Summary

Switched from PyMuPDF-first to **Tesseract OCR-first** extraction strategy for better accuracy with Indian invoices.

---

## Why OCR First?

### Problems with PyMuPDF:
1. **Missing table data** - PyMuPDF often skips table content
2. **Poor layout preservation** - Loses column structure in invoices
3. **Incomplete extraction** - Misses important fields in complex layouts
4. **Table borders interfere** - Box drawing characters (├─┬┤) confuse text extraction

### Benefits of OCR First:
1. **Better table detection** - Sees the actual rendered content
2. **Layout preservation** - Maintains spatial relationships
3. **Handles all formats** - Works with both digital and scanned PDFs
4. **More complete extraction** - Captures all visible text

---

## New Extraction Flow

### Primary Method: Tesseract OCR
```
PDF → Convert to Images (300 DPI) → Grayscale → Tesseract OCR → Text
```

**Configuration:**
- DPI: 300 (high quality)
- PSM: 6 (uniform block of text - good for invoices)
- OEM: 3 (LSTM + Legacy engines)
- Language: English
- Format: PNG (better quality than JPEG)

### Fallback Method: PyMuPDF
Only used if OCR fails or produces insufficient text (< 50 chars)

---

## Expected Improvements

### Line Items Extraction:
- **Before**: 0% (PyMuPDF missed table data)
- **After**: 70-80% (OCR sees rendered tables)

### Party Names:
- **Before**: Extracting table borders (├─┬┤)
- **After**: Clean company names from OCR

### Tax Fields:
- **Before**: Missing CGST/SGST breakdown
- **After**: Complete tax information visible in OCR

### Invoice Numbers:
- **Before**: Partial extraction ("OICE" instead of "G/1292")
- **After**: Full invoice numbers

---

## Performance Considerations

### Speed:
- **OCR**: Slower (~2-5 seconds per page)
- **PyMuPDF**: Faster (~0.1 seconds per page)

**Trade-off**: Accuracy > Speed for invoice processing

### Resource Usage:
- **CPU**: Higher (image processing + OCR)
- **Memory**: Higher (image conversion)

**Mitigation**: Process one invoice at a time (current synchronous approach)

---

## Multi-Invoice PDF Handling

### Current Behavior:
- Extracts ALL pages with OCR
- Processes first invoice found
- Logs all invoice numbers detected

### Future Enhancement (Phase 4):
- Detect invoice boundaries (invoice number changes)
- Split into separate invoices
- Process each invoice individually
- Return array of invoices

---

## Testing Instructions

1. **Upload Test Invoice**:
   ```
   http://localhost:8000/frontend/index.html
   ```

2. **Watch Terminal Logs**:
   ```
   [STEP 1] Using OCR as primary extraction method
   Converting PDF to images at 300 DPI
   Running OCR on page 1/1
   Page 1: Extracted XXXX characters
   OCR complete: Total XXXX characters from 1 pages
   ```

3. **Verify Extraction**:
   - Line items count > 0
   - Clean party names (no table borders)
   - Complete tax breakdown
   - Full invoice numbers

---

## Troubleshooting

### If OCR Fails:
1. Check Tesseract installation: `tesseract --version`
2. Check pdf2image dependencies: `pdftoppm --version`
3. Check Python packages: `pip list | grep -E "pytesseract|pdf2image|Pillow"`

### If Extraction is Slow:
- Reduce DPI from 300 to 200 (faster but less accurate)
- Process only first page for testing
- Consider async processing (Phase 10)

### If Text Quality is Poor:
- Increase DPI to 400 (slower but more accurate)
- Try different PSM modes (1-13)
- Add image preprocessing (threshold, denoise)

---

## Libraries Used

### Current Stack:
1. **Tesseract OCR** (PRIMARY) - Text extraction from images
2. **pdf2image** - Convert PDF pages to images
3. **Pillow (PIL)** - Image preprocessing
4. **pytesseract** - Python wrapper for Tesseract
5. **PyMuPDF (fitz)** (FALLBACK) - Digital PDF text extraction
6. **pdfplumber** - Table extraction
7. **Camelot** - Table extraction fallback

---

## Next Steps

### Immediate:
1. Test with "SURYA NX ALL BILLS" PDF
2. Verify line items extraction works
3. Check party names are clean
4. Validate tax field extraction

### Phase 5 Completion:
1. Add data cleaning/normalization
2. Validate extracted amounts
3. Calculate missing tax fields
4. Standardize date formats

### Phase 6 (Indian Compliance):
1. GSTIN validation
2. HSN/SAC validation
3. Tax calculation verification
4. Place of supply determination

---

## Configuration

### Current Settings (pdf_extractor.py):
```python
self.dpi = 300  # High DPI for accuracy
self.min_text_threshold = 50  # Minimum chars to consider valid
```

### Tesseract Config:
```python
config='--psm 6 --oem 3'
# PSM 6: Uniform block of text
# OEM 3: LSTM + Legacy engines
```

### To Adjust:
- Change DPI in `PDFExtractor.__init__()`
- Change PSM mode in `_extract_text_ocr()`
- Add preprocessing in `_extract_text_ocr()`

---

## Expected Results

Upload any invoice PDF and you should see:
- ✓ OCR extraction logs in terminal
- ✓ Line items extracted (count > 0)
- ✓ Clean party names
- ✓ Complete tax breakdown
- ✓ Full invoice numbers
- ✓ All table data visible

**Extraction time**: 2-5 seconds per page (acceptable for accuracy)
