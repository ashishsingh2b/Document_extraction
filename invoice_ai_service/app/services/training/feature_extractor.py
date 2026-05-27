import re
from typing import Dict, Any, List
from sklearn.feature_extraction.text import TfidfVectorizer

class FeatureExtractor:
    def __init__(self):
        self.vectorizer = TfidfVectorizer(
            max_features=300,
            sublinear_tf=True,
            ngram_range=(1, 2),
            min_df=2
        )
        self.is_fitted = False

    def extract_text_features(self, text: str) -> Dict[str, float]:
        lines = text.split('\n')
        words = text.split()
        
        char_count = len(text)
        word_count = len(words)
        line_count = len(lines)
        avg_words_per_line = word_count / max(1, line_count)
        
        gstin_patterns = len(re.findall(r'\d{2}[A-Z]{5}\d{4}[A-Z]{1}[A-Z\d]{1}[Z]{1}[A-Z\d]{1}', text))
        invoice_number_patterns = len(re.findall(r'(?i)(?:inv|invoice|bill)[\s\-\:]*(?:no|num|#)[\s\-\:]*([a-z0-9\-\/]+)', text))
        hsn_patterns = len(re.findall(r'\b\d{4,8}\b', text))
        date_patterns = len(re.findall(r'\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b', text))
        amount_patterns = len(re.findall(r'\b\d+\.\d{2}\b', text))
        tax_labels = len(re.findall(r'(?i)(cgst|sgst|igst|tax|gst)', text))
        reverse_charge = 1.0 if re.search(r'(?i)reverse charge', text) else 0.0
        invoice_type_keywords = len(re.findall(r'(?i)(tax invoice|bill of supply|credit note|debit note|proforma|receipt)', text))
        
        amounts = [float(a) for a in re.findall(r'\b\d+\.\d{2}\b', text)]
        amount_mean = sum(amounts) / max(1, len(amounts))
        amount_max = max(amounts) if amounts else 0.0
        
        return {
            'char_count': float(char_count),
            'word_count': float(word_count),
            'line_count': float(line_count),
            'avg_words_per_line': float(avg_words_per_line),
            'gstin_patterns': float(gstin_patterns),
            'invoice_number_patterns': float(invoice_number_patterns),
            'hsn_patterns': float(hsn_patterns),
            'date_patterns': float(date_patterns),
            'amount_patterns': float(amount_patterns),
            'tax_labels': float(tax_labels),
            'reverse_charge': reverse_charge,
            'invoice_type_keywords': float(invoice_type_keywords),
            'amount_mean': amount_mean,
            'amount_max': amount_max
        }
        
    def extract_layout_features(self, ocr_data: Dict[str, Any]) -> Dict[str, float]:
        # Assume ocr_data could provide block level info if available
        # fallback to text level estimates
        text = ocr_data.get('text', '')
        lines = text.split('\n')
        
        page_count = float(ocr_data.get('page_count', 1))
        # simplistic approximations without real bounding boxes
        table_count = float(len(re.findall(r'(?i)(qty|quantity|description|amount|total)', text[:500])))
        table_columns = 0.0
        text_blocks = float(len([l for l in lines if l.strip()]))
        header_density = float(len(" ".join(lines[:10]))) / max(1, len(text))
        footer_density = float(len(" ".join(lines[-10:]))) / max(1, len(text))
        left_region_density = 0.0
        right_region_density = 0.0
        
        return {
            'page_count': page_count,
            'table_count': table_count,
            'table_columns': table_columns,
            'text_blocks': text_blocks,
            'header_density': header_density,
            'footer_density': footer_density,
            'left_region_density': left_region_density,
            'right_region_density': right_region_density
        }

    def extract_gst_features(self, text: str) -> Dict[str, float]:
        gstins = re.findall(r'\d{2}[A-Z]{5}\d{4}[A-Z]{1}[A-Z\d]{1}[Z]{1}[A-Z\d]{1}', text)
        state_codes = [int(g[:2]) for g in gstins if g[:2].isdigit()]
        
        vendor_state_code = float(state_codes[0]) if len(state_codes) > 0 else 0.0
        buyer_state_code = float(state_codes[1]) if len(state_codes) > 1 else vendor_state_code
        interstate = 1.0 if vendor_state_code != buyer_state_code and vendor_state_code > 0 and buyer_state_code > 0 else 0.0
        gst_counts = float(len(gstins))
        
        return {
            'vendor_state_code': vendor_state_code,
            'buyer_state_code': buyer_state_code,
            'interstate_detection': interstate,
            'gst_counts': gst_counts
        }

    def fit_tfidf(self, texts: List[str]):
        if texts:
            self.vectorizer.fit(texts)
            self.is_fitted = True

    def transform_tfidf(self, texts: List[str]):
        if not self.is_fitted:
            raise ValueError("TFIDF vectorizer not fitted yet")
        return self.vectorizer.transform(texts).toarray()
