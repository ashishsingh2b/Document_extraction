"""File type detection service."""

import logging
from typing import Tuple

from app.core.exceptions import UnsupportedFormatError
from app.core.constants import SUPPORTED_FORMATS

logger = logging.getLogger(__name__)

_EXT_TO_MIME = {
    ".pdf": "application/pdf",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


class FileDetector:
    """File type detector using magic bytes, with extension fallback."""

    def detect_file_type(self, file_data: bytes, filename: str) -> Tuple[str, str]:
        file_extension = f".{filename.rsplit('.', 1)[-1].lower()}" if "." in filename else ""

        mime_type = self._detect_mime(file_data, file_extension)

        if mime_type not in SUPPORTED_FORMATS:
            for supported_mime, extensions in SUPPORTED_FORMATS.items():
                if file_extension in extensions:
                    mime_type = supported_mime
                    break
            else:
                raise UnsupportedFormatError(f"File type {mime_type} is not supported")

        logger.info(f"Detected file type: {mime_type}, extension: {file_extension}")
        return mime_type, file_extension

    def _detect_mime(self, file_data: bytes, file_extension: str) -> str:
        try:
            import magic

            mime = magic.Magic(mime=True)
            return mime.from_buffer(file_data)
        except ImportError:
            logger.debug("python-magic not installed; using extension fallback")
        except Exception as e:
            logger.warning(f"magic.from_buffer failed: {e}; using extension fallback")

        if file_extension in _EXT_TO_MIME:
            return _EXT_TO_MIME[file_extension]
        if file_data[:4] == b"%PDF":
            return "application/pdf"
        raise UnsupportedFormatError(
            f"Could not determine file type (extension={file_extension or 'unknown'})"
        )

    def get_extractor_type(self, mime_type: str) -> str:
        if mime_type == "application/pdf":
            return "pdf"
        if mime_type in ["image/jpeg", "image/png"]:
            return "image"
        if mime_type == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet":
            return "excel"
        if mime_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
            return "docx"
        raise UnsupportedFormatError(f"No extractor for MIME type: {mime_type}")


file_detector = FileDetector()
