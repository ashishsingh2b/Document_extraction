# Invoice Intelligence Microservice

FastAPI-based microservice for processing multi-format invoices with comprehensive Indian GST compliance.

**Full system handoff (architecture, folders, code map, API, training vs ML): see [`SYSTEM_DOCUMENTATION.md`](SYSTEM_DOCUMENTATION.md)** — use it when onboarding people or pasting context into an LLM.

## Features

- **Multi-format extraction**: PDF, Image (OCR), Excel, DOCX
- **Indian GST compliance**: GSTIN validation, HSN/SAC codes, CGST/SGST/IGST calculation
- **e-Invoice integration**: IRN generation, IRP portal integration, QR codes
- **Place of supply determination**: Automatic tax type selection
- **TDS/TCS detection**: Section 194Q and 206C(1H) compliance
- **Confidence scoring**: Automatic HITL routing for low-confidence extractions
- **Async processing**: Background job queue for large files
- **MinIO storage**: Scalable object storage for uploaded files

## Project Structure

Authoritative tree and file-level notes: **`SYSTEM_DOCUMENTATION.md`**. Sketch:

```
invoice_ai_service/
├── app/
│   ├── api/routes/          # upload, training, system, health
│   ├── services/
│   │   ├── extraction/      # OCR/PDF, fields, tables, formats, classifier
│   │   ├── training/       # pattern learning, ML train/registry
│   │   ├── orchestration/   # pipeline → ERP schema
│   │   ├── compliance/      # GST-oriented checks
│   │   └── ...
│   ├── config/              # settings, learned_patterns.json
│   └── ...
├── training_data/           # raw, ocr_cache, annotated
├── models/v1/               # XGBoost pack (routing/HITL signals)
├── scripts/                 # train, eval, e2e_validate, run_tests.sh
├── frontend/                # Static upload UI
├── tests/
└── storage/                 # Local upload fallback (dev)
```

## Prerequisites

- Python 3.11+
- PostgreSQL 14+
- Redis 7+
- MinIO (or S3-compatible storage)
- Tesseract OCR

## Installation

1. Clone the repository
2. Create virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Install Tesseract OCR:
   - Ubuntu/Debian: `sudo apt-get install tesseract-ocr`
   - macOS: `brew install tesseract`
   - Windows: Download from https://github.com/UB-Mannheim/tesseract/wiki

5. Set up environment variables:
   ```bash
   cp .env.example .env
   # Edit .env with your configuration
   ```

6. Start infrastructure services:
   ```bash
   docker-compose up -d
   ```

## Running the Application

### Development
```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Production
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
```

## API Documentation

Once running, visit:
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## Frontend

- Upload UI: http://localhost:8000/frontend/index.html
- System handoff & code map: **`SYSTEM_DOCUMENTATION.md`**
- Architecture & training policy: `ARCHITECTURE_AND_TRAINING_PLAN.md`

## Indian GST Compliance

### Supported Features
- GSTIN validation with checksum
- HSN/SAC code validation
- Place of supply determination
- CGST/SGST (intra-state) vs IGST (inter-state)
- TDS/TCS applicability (Section 194Q, 206C(1H))
- Reverse Charge Mechanism (RCM) detection
- e-Invoice IRN generation
- IRP portal integration
- QR code generation

### e-Invoice Setup
For businesses with ₹5 crore+ turnover, configure IRP credentials in .env:
```
IRP_BASE_URL=https://einvoice1.gst.gov.in
IRP_USERNAME=your_username
IRP_PASSWORD=your_password
```

## Testing

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=app --cov-report=html

# Run property-based tests
pytest tests/property_based/
```

## License

MIT License
