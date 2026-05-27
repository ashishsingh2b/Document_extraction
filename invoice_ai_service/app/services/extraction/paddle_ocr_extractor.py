"""PaddleOCR extraction for better table recognition."""

import logging
import io
from typing import Dict
from PIL import Image
import numpy as np

logger = logging.getLogger(__name__)


class PaddleOCRExtractor:
    """Extract text from images/PDFs using PaddleOCR."""
    
    def __init__(self):
        """Initialize PaddleOCR extractor."""
        self.ocr = None
        self._initialize_ocr()
    
    def _initialize_ocr(self):
        """Lazy initialization of PaddleOCR."""
        try:
            from paddleocr import PaddleOCR
            
            # Initialize PaddleOCR with English language
            # use_angle_cls=True helps with rotated text
            # use_gpu=False for CPU (set to True if GPU available)
            self.ocr = PaddleOCR(
                use_angle_cls=True,
                lang='en',
                use_gpu=False,
                show_log=False
            )
            logger.info("PaddleOCR initialized successfully")
        except ImportError:
            logger.error("PaddleOCR not installed. Install with: pip install paddleocr paddlepaddle")
            self.ocr = None
        except Exception as e:
            logger.error(f"Failed to initialize PaddleOCR: {str(e)}")
            self.ocr = None
    
    def extract_text(self, image_data: bytes) -> Dict[str, any]:
        """
        Extract text using PaddleOCR.
        
        Args:
            image_data: Image file as bytes (PNG, JPG, or PDF page as image)
            
        Returns:
            Dictionary with extracted text and metadata
        """
        try:
            if not self.ocr:
                raise Exception("PaddleOCR not initialized")
            
            # Convert bytes to PIL Image
            image = Image.open(io.BytesIO(image_data))
            
            # Convert to RGB if needed
            if image.mode != 'RGB':
                image = image.convert('RGB')
            
            # Convert PIL Image to numpy array
            img_array = np.array(image)
            
            # Run OCR
            logger.info("Running PaddleOCR...")
            result = self.ocr.ocr(img_array, cls=True)
            
            # Extract text from results
            # PaddleOCR returns: [[[bbox], (text, confidence)], ...]
            extracted_lines = []
            total_confidence = 0
            count = 0
            
            if result and len(result) > 0:
                for line in result[0]:  # result[0] contains the detection results
                    if line:
                        bbox, (text, confidence) = line
                        extracted_lines.append(text)
                        total_confidence += confidence
                        count += 1
            
            # Join all lines with newlines
            extracted_text = '\n'.join(extracted_lines)
            avg_confidence = (total_confidence / count * 100) if count > 0 else 0
            
            logger.info(f"PaddleOCR extracted {len(extracted_text)} characters with {avg_confidence:.1f}% confidence")
            
            return {
                "text": extracted_text,
                "extraction_method": "paddleocr",
                "text_length": len(extracted_text),
                "confidence": avg_confidence,
                "lines_detected": count,
                "success": True
            }
            
        except Exception as e:
            logger.error(f"PaddleOCR extraction failed: {str(e)}")
            return {
                "text": "",
                "extraction_method": "paddleocr",
                "error": str(e),
                "success": False
            }


# Global instance
paddle_ocr_extractor = PaddleOCRExtractor()
