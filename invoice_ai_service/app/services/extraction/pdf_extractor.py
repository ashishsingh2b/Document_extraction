"""PDF text extraction with OCR support using PyMuPDF."""

import logging
import os
from typing import Dict, List, Tuple
import io
from PIL import Image
import pytesseract
import pdf2image
import fitz  # PyMuPDF
from app.services.extraction.paddle_ocr_extractor import paddle_ocr_extractor

logger = logging.getLogger(__name__)


class PDFExtractor:
    """Extract text from PDF files with OCR fallback."""
    
    def __init__(self):
        """Initialize PDF extractor."""
        self.dpi = 300  # High DPI for better OCR accuracy
        self.min_text_threshold = 50  # Minimum characters to consider digital PDF
        from app.config.settings import settings
        self.default_ocr_engine = settings.DEFAULT_OCR_ENGINE
        
    def extract_text(self, pdf_data: bytes, ocr_engine: str = None) -> Dict[str, any]:
        """
        Extract text from PDF using OCR.
        
        Strategy: Use OCR (Tesseract, Google Vision, or PaddleOCR) as primary method for better accuracy.
        
        Args:
            pdf_data: PDF file as bytes
            ocr_engine: OCR engine to use ('tesseract', 'google_vision', or 'paddleocr'). 
                       If None, uses DEFAULT_OCR_ENGINE from env.
            
        Returns:
            Dictionary with extracted text and metadata
        """
        try:
            # Determine which OCR engine to use
            if ocr_engine is None:
                ocr_engine = self.default_ocr_engine
            
            logger.info(f"Using OCR engine: {ocr_engine}")
            
            # Strategy 1: Try OCR first (better for invoices with tables)
            if ocr_engine == 'paddleocr':
                text = self._extract_text_paddleocr(pdf_data)
            else:
                text = self._extract_text_tesseract(pdf_data)
            
            if text and len(text.strip()) >= self.min_text_threshold:
                logger.info(f"{ocr_engine} extraction successful, extracted {len(text)} characters")
                return {
                    "text": text,
                    "extraction_method": ocr_engine,
                    "text_length": len(text),
                    "success": True
                }
            
            # Strategy 2: Fallback to PyMuPDF if OCR fails
            logger.warning(f"{ocr_engine} extraction failed or insufficient text, trying PyMuPDF")
            text, has_selectable_text = self._extract_with_pymupdf(pdf_data)
            
            if has_selectable_text and len(text.strip()) >= self.min_text_threshold:
                logger.info(f"PyMuPDF extraction successful, extracted {len(text)} characters")
                return {
                    "text": text,
                    "extraction_method": "pymupdf",
                    "text_length": len(text),
                    "success": True
                }
            else:
                # Return whatever we got
                logger.warning(f"Both methods produced limited text ({len(text)} chars)")
                return {
                    "text": text,
                    "extraction_method": f"{ocr_engine}_limited",
                    "text_length": len(text),
                    "success": True
                }
            
        except Exception as e:
            logger.error(f"PDF extraction failed: {str(e)}")
            # Try to decode as text in case it's a misnamed text file
            try:
                decoded_text = pdf_data.decode('utf-8', errors='ignore')
                if decoded_text and len(decoded_text.strip()) >= self.min_text_threshold:
                    logger.info("Fallback: Decoded misnamed PDF file as raw text")
                    return {
                        "text": decoded_text,
                        "extraction_method": "text_fallback",
                        "text_length": len(decoded_text),
                        "success": True
                    }
            except Exception as decode_err:
                logger.error(f"Text fallback decoding failed: {str(decode_err)}")
                
            return {
                "text": "",
                "extraction_method": "failed",
                "error": str(e),
                "success": False
            }
    
    def _extract_with_pymupdf(self, pdf_data: bytes) -> Tuple[str, bool]:
        """
        Extract text using PyMuPDF with layout preservation.
        
        Returns:
            Tuple of (text, has_selectable_text)
        """
        try:
            doc = fitz.open(stream=pdf_data, filetype="pdf")
            text_parts = []
            has_text = False
            
            for page_num in range(len(doc)):
                page = doc[page_num]
                
                # Extract text with layout preservation
                page_text = page.get_text("text", sort=True)
                
                if page_text and len(page_text.strip()) > 10:
                    has_text = True
                    text_parts.append(f"--- Page {page_num + 1} ---\n{page_text}")
            
            doc.close()
            
            full_text = "\n\n".join(text_parts)
            return full_text, has_text
            
        except Exception as e:
            logger.warning(f"PyMuPDF extraction failed: {str(e)}")
            return "", False
    
    def _extract_text_tesseract(self, pdf_data: bytes) -> str:
        """Extract text using Tesseract OCR - optimized for Indian invoices."""
        try:
            # Convert PDF to images with high DPI for better accuracy
            logger.info(f"Converting PDF to images at {self.dpi} DPI for Tesseract")
            images = pdf2image.convert_from_bytes(
                pdf_data,
                dpi=self.dpi,
                fmt='png'  # PNG for better quality
            )
            
            text_parts = []
            for page_num, image in enumerate(images):
                logger.info(f"Running Tesseract OCR on page {page_num + 1}/{len(images)}")
                
                # Preprocess image for better OCR
                # Convert to grayscale for better contrast
                image = image.convert('L')
                
                # Run OCR with optimized config for invoices
                # PSM 6: Assume uniform block of text (good for invoices)
                # OEM 3: Use both legacy and LSTM OCR engines
                page_text = pytesseract.image_to_string(
                    image,
                    lang='eng',
                    config='--psm 6 --oem 3'
                )
                
                if page_text and len(page_text.strip()) > 10:
                    text_parts.append(f"--- Page {page_num + 1} ---\n{page_text}")
                    logger.info(f"Page {page_num + 1}: Extracted {len(page_text)} characters")
                else:
                    logger.warning(f"Page {page_num + 1}: No text extracted")
            
            full_text = "\n\n".join(text_parts)
            logger.info(f"Tesseract OCR complete: Total {len(full_text)} characters from {len(images)} pages")
            return full_text
            
        except Exception as e:
            logger.error(f"Tesseract OCR extraction failed: {str(e)}")
            raise
    

    def _extract_text_paddleocr(self, pdf_data: bytes) -> str:
        """Extract text using PaddleOCR - better for tables and structured data."""
        try:
            # Convert PDF to images
            logger.info(f"Converting PDF to images at {self.dpi} DPI for PaddleOCR")
            images = pdf2image.convert_from_bytes(
                pdf_data,
                dpi=self.dpi,
                fmt='png'
            )
            
            text_parts = []
            for page_num, image in enumerate(images):
                logger.info(f"Running PaddleOCR on page {page_num + 1}/{len(images)}")
                
                # Convert PIL Image to bytes
                img_byte_arr = io.BytesIO()
                image.save(img_byte_arr, format='PNG')
                img_bytes = img_byte_arr.getvalue()
                
                # Call PaddleOCR
                result = paddle_ocr_extractor.extract_text(img_bytes)
                
                if result.get('success') and result.get('text'):
                    page_text = result['text']
                    text_parts.append(f"--- Page {page_num + 1} ---\n{page_text}")
                    logger.info(f"Page {page_num + 1}: Extracted {len(page_text)} characters with {result.get('confidence', 0):.1f}% confidence")
                else:
                    logger.warning(f"Page {page_num + 1}: No text extracted")
            
            full_text = "\n\n".join(text_parts)
            logger.info(f"PaddleOCR complete: Total {len(full_text)} characters from {len(images)} pages")
            return full_text
            
        except Exception as e:
            logger.error(f"PaddleOCR extraction failed: {str(e)}")
            raise


# Global instance
pdf_extractor = PDFExtractor()
