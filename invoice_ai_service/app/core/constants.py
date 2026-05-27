"""Application constants."""

# File size limits
MAX_FILE_SIZE_MB = 50
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024

# Supported file formats
SUPPORTED_FORMATS = {
    "application/pdf": [".pdf"],
    "image/jpeg": [".jpg", ".jpeg"],
    "image/png": [".png"],
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": [".xlsx"],
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": [".docx"],
}

# Confidence thresholds
CONFIDENCE_THRESHOLD_HITL = 70  # Below this goes to HITL queue

# Indian GST rates
GST_RATES = [0, 5, 12, 18, 28]

# TDS/TCS thresholds
TDS_THRESHOLD_INR = 5000000  # ₹50 lakh
TCS_THRESHOLD_INR = 5000000  # ₹50 lakh
TDS_RATE = 0.001  # 0.1%
TCS_RATE = 0.001  # 0.1%

# e-Invoice thresholds
EINVOICE_TURNOVER_THRESHOLD = 50000000  # ₹5 crore
EINVOICE_UPLOAD_DAYS_LIMIT = 30  # 30 days for ₹10 crore+ turnover

# Invoice types
class InvoiceType:
    TAX_INVOICE = "Tax Invoice"
    BILL_OF_SUPPLY = "Bill of Supply"
    EXPORT_INVOICE = "Export Invoice"
    DEBIT_NOTE = "Debit Note"
    CREDIT_NOTE = "Credit Note"
