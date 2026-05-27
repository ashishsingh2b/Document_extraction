# Invoice Intelligence Microservice - Project Structure

## Complete Directory Tree

```
invoice_ai_service/
├── app/
│   ├── __init__.py
│   ├── main.py                          # FastAPI application entry point
│   │
│   ├── api/
│   │   ├── __init__.py
│   │   ├── dependencies.py              # Shared dependencies
│   │   └── routes/
│   │       ├── __init__.py
│   │       ├── upload.py                # File upload endpoints
│   │       ├── jobs.py                  # Job status endpoints
│   │       ├── batch.py                 # Batch processing endpoints
│   │       ├── hitl.py                  # HITL review endpoints
│   │       └── health.py                # Health check endpoints
│   │
│   ├── services/
│   │   ├── __init__.py
│   │   │
│   │   ├── extraction/
│   │   │   ├── __init__.py
│   │   │   ├── pdf_extractor.py        # PDF text/table extraction
│   │   │   ├── image_extractor.py      # OCR for images
│   │   │   ├── excel_extractor.py      # Excel data extraction
│   │   │   └── docx_extractor.py       # DOCX text/table extraction
│   │   │
│   │   ├── cleaning/
│   │   │   ├── __init__.py
│   │   │   └── data_cleaner.py         # OCR error correction, formatting
│   │   │
│   │   ├── normalization/
│   │   │   ├── __init__.py
│   │   │   ├── field_mapper.py         # Field name normalization
│   │   │   └── alias_loader.py         # Load alias dictionary
│   │   │
│   │   ├── compliance/                  # ⭐ Indian GST Compliance Layer
│   │   │   ├── __init__.py
│   │   │   ├── gstin_validator.py      # GSTIN format & checksum validation
│   │   │   ├── hsn_validator.py        # HSN/SAC code validation
│   │   │   ├── place_of_supply.py      # Place of supply determination
│   │   │   ├── tax_calculator.py       # CGST/SGST/IGST calculation
│   │   │   ├── tds_tcs_calculator.py   # TDS/TCS applicability
│   │   │   └── rcm_detector.py         # Reverse Charge Mechanism
│   │   │
│   │   ├── validation/
│   │   │   ├── __init__.py
│   │   │   └── validator.py            # Business rule validation
│   │   │
│   │   ├── mapping/
│   │   │   ├── __init__.py
│   │   │   └── schema_mapper.py        # ERP schema mapping
│   │   │
│   │   ├── confidence/
│   │   │   ├── __init__.py
│   │   │   └── confidence_service.py   # Confidence scoring
│   │   │
│   │   ├── einvoice/                    # ⭐ e-Invoice Integration
│   │   │   ├── __init__.py
│   │   │   ├── irn_generator.py        # IRN generation
│   │   │   ├── irp_client.py           # IRP portal client
│   │   │   └── qr_generator.py         # QR code generation
│   │   │
│   │   ├── orchestration/
│   │   │   ├── __init__.py
│   │   │   └── pipeline_orchestrator.py # 9-layer pipeline orchestration
│   │   │
│   │   └── utils/
│   │       ├── __init__.py
│   │       ├── file_detector.py        # File type detection
│   │       ├── duplicate_detector.py   # Duplicate file detection
│   │       └── audit_logger.py         # Audit logging
│   │
│   ├── models/
│   │   ├── __init__.py
│   │   ├── schemas.py                   # Pydantic schemas
│   │   ├── invoice.py                   # Invoice data models
│   │   ├── job.py                       # Job models
│   │   └── response.py                  # API response models
│   │
│   ├── config/
│   │   ├── __init__.py
│   │   ├── settings.py                  # Application settings
│   │   ├── alias_dictionary.json        # Field name aliases
│   │   ├── hsn_sac_master.json         # HSN/SAC master data
│   │   └── state_codes.json            # Indian state codes
│   │
│   ├── core/
│   │   ├── __init__.py
│   │   ├── exceptions.py                # Custom exceptions
│   │   └── constants.py                 # Application constants
│   │
│   └── workers/
│       ├── __init__.py
│       └── job_processor.py             # Celery background workers
│
├── frontend/
│   ├── index.html                       # Landing page
│   ├── upload.html                      # Upload interface
│   ├── status.html                      # Job status viewer
│   ├── hitl.html                        # HITL review interface
│   └── static/
│       ├── css/
│       │   └── styles.css
│       └── js/
│           └── app.js
│
├── storage/
│   └── uploads/                         # Local file storage (dev only)
│
├── tests/
│   ├── __init__.py
│   ├── unit/                            # Unit tests
│   │   └── __init__.py
│   ├── integration/                     # Integration tests
│   │   └── __init__.py
│   └── property_based/                  # Property-based tests
│       └── __init__.py
│
├── requirements.txt                     # Python dependencies
├── .env.example                         # Environment variables template
├── .gitignore                          # Git ignore rules
├── docker-compose.yml                   # Infrastructure services
├── Dockerfile                           # Application container (TBD)
├── README.md                            # Project documentation
└── PROJECT_STRUCTURE.md                 # This file
```

## Module Responsibilities

### API Layer (`app/api/`)
- **routes/upload.py**: File upload, security scanning, job creation
- **routes/jobs.py**: Job status queries, result retrieval
- **routes/batch.py**: Batch upload and processing
- **routes/hitl.py**: HITL queue management, corrections submission
- **routes/health.py**: Health checks, readiness probes

### Services Layer (`app/services/`)

#### Extraction (`extraction/`)
- Multi-format data extraction (PDF, Image, Excel, DOCX)
- OCR for scanned documents
- Table structure preservation

#### Cleaning (`cleaning/`)
- OCR error correction
- Whitespace normalization
- Date/currency formatting

#### Normalization (`normalization/`)
- Field name standardization using alias dictionary
- Vendor-specific to standard field mapping

#### Compliance (`compliance/`) ⭐ **Indian GST**
- **gstin_validator.py**: 15-char format, checksum, state code validation
- **hsn_validator.py**: HSN/SAC code validation against master
- **place_of_supply.py**: State determination, CGST+SGST vs IGST logic
- **tax_calculator.py**: GST calculation, rate validation
- **tds_tcs_calculator.py**: Section 194Q, 206C(1H) detection
- **rcm_detector.py**: Reverse Charge Mechanism identification

#### Validation (`validation/`)
- Business rule validation
- GST calculation verification
- Required field checks

#### Mapping (`mapping/`)
- ERP schema generation
- Schema versioning support

#### Confidence (`confidence/`)
- Extraction quality scoring
- HITL routing decisions

#### e-Invoice (`einvoice/`) ⭐ **e-Invoice Integration**
- **irn_generator.py**: 64-char IRN hash generation
- **irp_client.py**: Government IRP portal integration
- **qr_generator.py**: Digitally signed QR codes

#### Orchestration (`orchestration/`)
- 9-layer pipeline coordination
- Error handling and retry logic

#### Utils (`utils/`)
- File type detection
- Duplicate detection
- Audit logging

### Models Layer (`app/models/`)
- Pydantic data models for validation
- Invoice, Job, Response schemas
- Indian GST field definitions

### Configuration (`app/config/`)
- Application settings (MinIO, database, Redis)
- Master data (state codes, HSN/SAC, aliases)
- Environment-based configuration

### Core (`app/core/`)
- Custom exceptions
- Application constants
- Shared utilities

### Workers (`app/workers/`)
- Celery background job processing
- Async file processing
- Retry logic

## Technology Stack

- **Framework**: FastAPI 0.109.0
- **Storage**: MinIO (S3-compatible)
- **Database**: PostgreSQL 15
- **Cache/Queue**: Redis 7
- **Task Queue**: Celery 5.3
- **OCR**: Tesseract
- **PDF**: PyMuPDF, pdfplumber
- **Excel**: openpyxl
- **DOCX**: python-docx
- **QR Codes**: qrcode

## Infrastructure Services (docker-compose.yml)

1. **PostgreSQL**: Audit logs, job metadata
2. **Redis**: Job queue, caching
3. **MinIO**: Object storage for uploaded files
4. **MinIO Init**: Auto-create buckets on startup

## Next Steps

1. ✅ Project structure created
2. ⏳ Implement FastAPI main application
3. ⏳ Implement data models and schemas
4. ⏳ Implement extraction layer
5. ⏳ Implement Indian compliance layer
6. ⏳ Implement e-Invoice integration
7. ⏳ Implement frontend
8. ⏳ Testing and deployment
