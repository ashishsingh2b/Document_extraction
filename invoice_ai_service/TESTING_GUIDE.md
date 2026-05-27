# Testing Guide - Invoice Intelligence Microservice

## 🚀 Quick Start

### 1. Start the Application

```bash
cd invoice_ai_service

# Start infrastructure (PostgreSQL, Redis, MinIO)
docker-compose up -d

# Wait for services to be ready (30 seconds)
sleep 30

# Install dependencies
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt

# Install system dependencies (if not already installed)
# Ubuntu/Debian:
sudo apt-get install -y tesseract-ocr libmagic1

# macOS:
brew install tesseract libmagic

# Start the application
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 2. Verify Services are Running

Open your browser and check:

- ✅ **Application**: http://localhost:8000
- ✅ **API Docs**: http://localhost:8000/docs
- ✅ **Health Check**: http://localhost:8000/api/v1/health
- ✅ **Frontend**: http://localhost:8000/frontend/index.html
- ✅ **MinIO Console**: http://localhost:9001 (login: minioadmin/minioadmin)

### 3. Test Health Check

```bash
curl http://localhost:8000/api/v1/health
```

Expected response:
```json
{
  "status": "healthy",
  "version": "1.0.0",
  "dependencies": {
    "minio": "healthy",
    "redis": "healthy",
    "database": "healthy",
    "tesseract_ocr": "healthy (v5.x.x)"
  }
}
```

## 📤 Testing File Upload

### Method 1: Using the Web Interface

1. Go to http://localhost:8000/frontend/upload.html
2. Drag & drop or select a file:
   - PDF invoice
   - Image (JPG/PNG)
   - Excel (XLSX)
   - DOCX
3. Click "Upload & Process"
4. Note the Job ID returned
5. Click "Check Status" to view processing status

### Method 2: Using cURL

#### Upload a PDF
```bash
curl -X POST "http://localhost:8000/api/v1/upload" \
  -H "Content-Type: multipart/form-data" \
  -F "file=@/path/to/invoice.pdf"
```

#### Upload an Image
```bash
curl -X POST "http://localhost:8000/api/v1/upload" \
  -H "Content-Type: multipart/form-data" \
  -F "file=@/path/to/invoice.jpg"
```

#### Upload with Force Reprocess
```bash
curl -X POST "http://localhost:8000/api/v1/upload?force_reprocess=true" \
  -H "Content-Type: multipart/form-data" \
  -F "file=@/path/to/invoice.pdf"
```

Expected response:
```json
{
  "status": "accepted",
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "message": "File uploaded successfully. Processing started.",
  "file_name": "invoice.pdf",
  "file_size": 245678,
  "request_id": "abc123..."
}
```

### Method 3: Using Python

```python
import requests

url = "http://localhost:8000/api/v1/upload"
files = {"file": open("invoice.pdf", "rb")}

response = requests.post(url, files=files)
print(response.json())
```

## 🧪 Test Scenarios

### Scenario 1: Single Invoice PDF (1 page)
**File**: `invoice_single.pdf`
**Expected**: 1 invoice extracted

### Scenario 2: Multi-Invoice PDF (5-6 pages)
**File**: `invoices_merged.pdf` (5 invoices from same party)
**Expected**: 5 separate invoices extracted
**Pages**:
- Invoice 1: Page 1
- Invoice 2: Page 2
- Invoice 3: Pages 3-4 (overflow items)
- Invoice 4: Page 5
- Invoice 5: Page 6

### Scenario 3: Scanned Image Invoice
**File**: `invoice_scan.jpg`
**Expected**: OCR extraction, confidence score

### Scenario 4: Excel Invoice
**File**: `invoice.xlsx`
**Expected**: Structured data extraction

### Scenario 5: Large File (>5MB)
**File**: `large_invoice.pdf` (>5MB)
**Expected**: Async processing, job queued

### Scenario 6: Duplicate File
**File**: Upload same file twice
**Expected**: Second upload returns cached result

### Scenario 7: Unsupported Format
**File**: `document.txt`
**Expected**: HTTP 400 error, unsupported format

### Scenario 8: File Too Large (>50MB)
**File**: `huge_file.pdf` (>50MB)
**Expected**: HTTP 400 error, file size exceeded

## 🔍 Checking Job Status

### Using Web Interface
1. Go to http://localhost:8000/frontend/status.html
2. Enter Job ID
3. Click "Check Status"

### Using cURL
```bash
curl http://localhost:8000/api/v1/jobs/{job_id}
```

### Using API Docs
1. Go to http://localhost:8000/docs
2. Find `GET /api/v1/jobs/{job_id}`
3. Click "Try it out"
4. Enter Job ID
5. Click "Execute"

## 📊 Monitoring MinIO Storage

1. Open http://localhost:9001
2. Login: `minioadmin` / `minioadmin`
3. Navigate to "Buckets" → "invoice-uploads"
4. View uploaded files

## 🐛 Troubleshooting

### Issue: Health check shows MinIO unhealthy
**Solution**:
```bash
docker-compose restart minio
# Wait 10 seconds
docker-compose ps
```

### Issue: Health check shows database unhealthy
**Solution**:
```bash
docker-compose restart postgres
# Wait 10 seconds
```

### Issue: "ModuleNotFoundError: No module named 'magic'"
**Solution**:
```bash
# Install system library
# Ubuntu/Debian:
sudo apt-get install libmagic1

# macOS:
brew install libmagic

# Reinstall Python package
pip install python-magic
```

### Issue: Tesseract not found
**Solution**:
```bash
# Ubuntu/Debian:
sudo apt-get install tesseract-ocr

# macOS:
brew install tesseract

# Windows: Download from
# https://github.com/UB-Mannheim/tesseract/wiki
```

### Issue: Upload fails with "bucket not found"
**Solution**:
```bash
# Restart MinIO init container
docker-compose up -d minio-init

# Or create bucket manually in MinIO console
```

## 📝 Sample Test Data

### Create Test Invoices

You can create test PDFs using:
1. **Online tools**: https://www.sejda.com/html-to-pdf
2. **Python**: Use `reportlab` or `fpdf`
3. **LibreOffice**: Create invoice in Writer, export as PDF

### Sample Invoice Structure
```
ABC STEEL INDUSTRIES
GSTIN: 27AAPFU0939F1ZV

Invoice No: INV-1001
Date: 15/01/2024
Place of Supply: Maharashtra (27)

Items:
- Steel Pipe 12MM | HSN: 7306 | Qty: 10 | Rate: 500 | Amount: 5000

Subtotal: 5000
CGST @ 9%: 450
SGST @ 9%: 450
Grand Total: 5900
```

## 🎯 Expected Behavior

### Current Implementation (Phase 3 Complete)
✅ File upload to MinIO
✅ File type detection
✅ Security scanning
✅ Duplicate detection
✅ Job ID generation
✅ Audit logging

### Coming Soon (Phases 4-12)
⏳ PDF/Image/Excel/DOCX extraction
⏳ Multi-invoice separation
⏳ Indian GST compliance validation
⏳ e-Invoice IRN generation
⏳ Confidence scoring
⏳ HITL review queue
⏳ Complete ERP schema output

## 📞 Support

If you encounter issues:
1. Check logs: `tail -f logs/audit.log`
2. Check Docker logs: `docker-compose logs`
3. Verify all services: `docker-compose ps`
4. Check health endpoint: `curl http://localhost:8000/api/v1/health`

---

**Ready to test!** 🚀

Start with uploading a simple PDF invoice and verify it appears in MinIO storage.
