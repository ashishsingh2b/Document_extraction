# Phase 5: Data Cleaning & Normalization

## Goal
Improve extraction accuracy from 60-75% to 90%+ for Indian GST invoices

## Tasks

### 1. Improve Table Extraction ⏳
- [ ] Better Camelot configuration for Indian invoice tables
- [ ] Fallback to pdfplumber for borderless tables
- [ ] Handle multi-page tables
- [ ] Extract line items with HSN, Qty, Rate, Amount

### 2. Improve Field Extraction ⏳
- [ ] Better regex patterns for Indian formats
- [ ] Extract supplier name from header (not table borders)
- [ ] Extract all tax components (CGST, SGST, IGST, Cess)
- [ ] Calculate taxable amount from line items if missing
- [ ] Extract place of supply, state codes

### 3. Data Normalization ⏳
- [ ] Standardize date formats (DD/MM/YYYY, DD-MM-YYYY, etc.)
- [ ] Clean amount formats (remove commas, handle decimals)
- [ ] Normalize GSTIN format (15 characters, uppercase)
- [ ] Standardize party names (trim, title case)

### 4. Data Validation ⏳
- [ ] Validate GSTIN format (2 digits + 10 chars + 3 chars)
- [ ] Validate HSN codes (4-8 digits)
- [ ] Validate tax calculations (CGST + SGST = Total GST for intra-state)
- [ ] Validate amounts (taxable + tax = total)

### 5. Confidence Scoring ⏳
- [ ] Field-level confidence scores
- [ ] Overall extraction confidence
- [ ] Flag low-confidence fields for HITL review

## Current Status
Starting Phase 5 implementation...
