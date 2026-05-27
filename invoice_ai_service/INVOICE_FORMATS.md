# Indian GST Invoice Format Registry

The extraction pipeline uses a **single output schema** for all invoice layouts. Input layouts vary; detection picks the best profile and applies format-specific patterns.

## Output schema (always the same)

| Field | Description |
|-------|-------------|
| `invoice_number`, `invoice_date`, `due_date` | Header |
| `supplier_name`, `supplier_gstin` | Seller (header, before Billed To) |
| `buyer_name`, `buyer_gstin` | Buyer (Billed To / Consignee / M/s.) |
| `items[]` | Line items: description, hsn, qty, rate, amount |
| `taxable_amount`, `cgst_amount`, `sgst_amount`, `igst_amount` | Tax |
| `total_amount` | Grand / Net amount |

## How it works

```
Upload → OCR → Detect format → Universal extract → Format enhance → JSON
```

1. **Detect** — `format_registry.detect_invoice_format(text)` scores signals in `app/config/invoice_format_profiles.json`
2. **Universal** — `field_extractor.py` + `table_extractor.py` (works for most invoices)
3. **Enhance** — `format_enhancer.py` fills gaps using the detected profile

## Supported profiles (v1)

| ID | Example supplier | Layout hints |
|----|------------------|--------------|
| `gayatri_box` | GAYATRI SAREE | Billed To column, Name of Product, IGST |
| `komal_prints` | KOMAL PRINTS | Buyer:, BILL NO, CGST @ on Taxable |
| `muskan_glued` | MUSKAN COLLECTION | Glued OCR, Details of Consignee |
| `shivam_fashion` | SHIVAM FASHION | Seller/Buyer, PARTICULAR, Central/State GST |
| `mr_fashion_chandni` | M.R FASHION | Chandni app, SALE TAX INVOICE |
| `suswaani_debit` | SHREE SUSWAANI | Debit Memo, Sub Total |
| `gayatri_traders` | GAYATRI TRADERS | Vyara, Kgs, dashed lines |
| `sagas_collection` | SAGAS COLLECTION | Description Of Goods, Cut/Pcs/Mts |
| `balkrishna_debit` | SHREE BALKRUSHNA | Debit Memo, M/s., Central Tax 9% |
| `shivalaxmi_grid` | SHIVALAXMI | Multi-column tax grid |
| `alakh_supplier_invoice` | ALAKH INTERNATIONAL | Supplier issues invoice, IGST |
| `universal` | (fallback) | Generic patterns |

## Adding a new format (3 steps)

### Step 1 — Register signals (`invoice_format_profiles.json`)

```json
{
  "id": "my_new_vendor",
  "label": "My Vendor Layout",
  "signals": ["my vendor name", "unique header text", "special column name"],
  "tax_type": "cgst_sgst"
}
```

### Step 2 — Add field patterns (`format_enhancer.py`)

Add a handler function and register in `_HANDLERS`:

```python
def _my_new_vendor(text: str, f: Dict) -> Dict:
    f["supplier_name"] = f.get("supplier_name") or _first_str([r"(MY VENDOR)"], text)
    f["taxable_amount"] = f.get("taxable_amount") or _first_float([r"Subtotal\s*([\d,]+)"], text)
    return f

_HANDLERS["my_new_vendor"] = _my_new_vendor
```

### Step 3 — Add line item patterns (optional)

Register in `_LINE_HANDLERS` if the table layout is unique.

Restart the server and test with a sample PDF.

## Metadata in API response

```json
"metadata": {
  "detected_format": "gayatri_box",
  "format_label": "GAYATRI SAREE box layout...",
  "format_confidence": 0.85
}
```

## Training samples

Reference OCR samples: `traininngtestdata.txt`
