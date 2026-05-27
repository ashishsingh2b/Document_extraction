"""Image text extraction using OCR."""

import logging
import os
from typing import Dict
from PIL import Image
import pytesseract
import io
from app.services.extraction.paddle_ocr_extractor import paddle_ocr_extractor

logger = logging.getLogger(__name__)


class ImageExtractor:
    """Extract text from images using OCR."""
    
    def __init__(self):
        """Initialize image extractor."""
        from app.config.settings import settings
        self.default_ocr_engine = settings.DEFAULT_OCR_ENGINE
    
    def extract_text(self, image_data: bytes, ocr_engine: str = None) -> Dict[str, any]:
        """
        Extract text from image using OCR.
        
        Args:
            image_data: Image file as bytes
            ocr_engine: OCR engine to use ('tesseract', 'google_vision', or 'paddleocr')
            
        Returns:
            Dictionary with extracted text and metadata
        """
        try:
            # Determine which OCR engine to use
            if ocr_engine is None:
                ocr_engine = self.default_ocr_engine
            
            logger.info(f"Using OCR engine: {ocr_engine} for image")
            
            if ocr_engine == 'paddleocr':
                # Use PaddleOCR
                result = paddle_ocr_extractor.extract_text(image_data)
                if result.get('success'):
                    return result
                else:
                    # Fallback to Tesseract if PaddleOCR fails
                    logger.warning("PaddleOCR failed, falling back to Tesseract")
                    return self._extract_with_tesseract(image_data)
            else:
                # Use Tesseract
                return self._extract_with_tesseract(image_data)
            
        except Exception as e:
            logger.error(f"Image OCR extraction failed: {str(e)}")
            return {
                "text": "",
                "extraction_method": "failed",
                "error": str(e),
                "success": False
            }
    
    def _extract_with_tesseract(self, image_data: bytes) -> Dict[str, any]:
        """Extract text using Tesseract OCR."""
        # Open image
        image = Image.open(io.BytesIO(image_data))
        
        # Convert to RGB if needed
        if image.mode != 'RGB':
            image = image.convert('RGB')
        
        logger.info(f"Running Tesseract OCR on image ({image.size[0]}x{image.size[1]})")
        
        # Run OCR
        text = pytesseract.image_to_string(
            image,
            lang='eng',
            config='--psm 6 --oem 3'  # Assume uniform block of text, LSTM OCR
        )
        
        return {
            "text": text,
            "extraction_method": "tesseract",
            "text_length": len(text),
            "image_size": f"{image.size[0]}x{image.size[1]}",
            "success": True
        }


# Global instance
image_extractor = ImageExtractor()
