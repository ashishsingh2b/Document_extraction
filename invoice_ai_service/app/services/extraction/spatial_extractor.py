import logging
import io
from typing import Optional
import pdfplumber
import pdf2image
import pytesseract
from PIL import Image
import numpy as np

logger = logging.getLogger(__name__)

class SpatialExtractor:
    """Extract fields using geometric bounding boxes (x0, y0, x1, y1) instead of regex."""

    def __init__(self):
        pass

    def _get_pdf_words(self, pdf_data: bytes) -> list:
        """Extract words with bounding boxes from PDF using pdfplumber."""
        words = []
        try:
            with pdfplumber.open(io.BytesIO(pdf_data)) as pdf:
                for page_num, page in enumerate(pdf.pages):
                    page_words = page.extract_words(keep_blank_chars=True)
                    for w in page_words:
                        w['page'] = page_num
                        w['y0'] = w['top']
                        w['y1'] = w['bottom']
                        words.append(w)
            return words
        except Exception as e:
            logger.error(f"pdfplumber spatial extraction failed: {e}")
            return []

    def _get_image_words(self, file_data: bytes, mime_type: str) -> list:
        """Extract words with bounding boxes from images using pytesseract."""
        words = []
        try:
            if mime_type == 'application/pdf':
                images = pdf2image.convert_from_bytes(file_data, dpi=300)
            else:
                images = [Image.open(io.BytesIO(file_data))]

            for page_num, img in enumerate(images):
                img = img.convert('L')
                data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)
                
                n_boxes = len(data['text'])
                for i in range(n_boxes):
                    text = data['text'][i].strip()
                    if int(data['conf'][i]) > 10 and text:
                        x, y, w, h = data['left'][i], data['top'][i], data['width'][i], data['height'][i]
                        words.append({
                            'text': text,
                            'x0': x,
                            'y0': y,
                            'x1': x + w,
                            'y1': y + h,
                            'page': page_num
                        })
            return words
        except Exception as e:
            logger.error(f"pytesseract spatial extraction failed: {e}")
            return []

    def get_spatial_words(self, file_data: bytes, mime_type: str) -> list:
        """Attempt pdfplumber first for PDFs, fallback to Tesseract."""
        if mime_type == 'application/pdf':
            words = self._get_pdf_words(file_data)
            if words: return words
        
        return self._get_image_words(file_data, mime_type)

    def find_right_of(self, label: str, words: list, y_tolerance: float = 8.0) -> Optional[str]:
        """
        Find text immediately to the right of a label token on the same line (page-aware).
        Used for tax/total fields in annotation helper and spatial fallback.
        """
        label_lower = label.lower().strip()
        if not label_lower:
            return None

        for i, w in enumerate(words):
            token = (w.get("text") or "").strip()
            if not token or label_lower not in token.lower():
                continue

            page = w.get("page", 0)
            y_mid = (w.get("y0", 0) + w.get("y1", 0)) / 2
            x_right = w.get("x1", 0)

            candidates = []
            for j, other in enumerate(words):
                if j == i or other.get("page", 0) != page:
                    continue
                oy_mid = (other.get("y0", 0) + other.get("y1", 0)) / 2
                if abs(oy_mid - y_mid) > y_tolerance:
                    continue
                if other.get("x0", 0) >= x_right - 2:
                    candidates.append(other)

            if not candidates:
                continue

            candidates.sort(key=lambda o: o.get("x0", 0))
            parts = []
            for c in candidates[:6]:
                t = (c.get("text") or "").strip()
                if t:
                    parts.append(t)
            if parts:
                return " ".join(parts)

        return None

    def extract_all(self, file_data: bytes, mime_type: str) -> dict:
        """Run full spatial heuristics."""
        words = self.get_spatial_words(file_data, mime_type)
        if not words:
            return {}

        results = {}
        
        # Taxes & Totals typically sit at the bottom right.
        results['cgst_amount'] = self.find_right_of("cgst", words) or self.find_right_of("central", words)
        results['sgst_amount'] = self.find_right_of("sgst", words) or self.find_right_of("state", words)
        results['igst_amount'] = self.find_right_of("igst", words)
        results['taxable_amount'] = self.find_right_of("taxable", words) or self.find_right_of("net total", words)
        results['total_amount'] = self.find_right_of("grand", words) or self.find_right_of("total", words)
        
        # Clean up outputs
        for k, v in results.items():
            if v:
                cleaned = ''.join(c for c in v if c.isdigit() or c == '.')
                results[k] = cleaned

        return results

spatial_extractor = SpatialExtractor()
