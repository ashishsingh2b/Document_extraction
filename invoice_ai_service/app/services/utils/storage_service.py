"""MinIO storage service for file management with filesystem fallback."""

import logging
from typing import Optional
import uuid
from datetime import timedelta
from pathlib import Path

from app.config.settings import settings

logger = logging.getLogger(__name__)


class StorageService:
    """Storage service with MinIO primary and filesystem fallback."""

    def __init__(self):
        self.client = None
        self.bucket_name = settings.MINIO_BUCKET_NAME
        self._initialized = False
        self._use_filesystem = False
        self._storage_dir = Path("storage/uploads")

    def _initialize(self):
        """Lazy initialization of MinIO client with filesystem fallback."""
        if self._initialized:
            return
        try:
            from minio import Minio
            from minio.error import S3Error

            self._S3Error = S3Error
            self.client = Minio(
                settings.MINIO_ENDPOINT,
                access_key=settings.MINIO_ACCESS_KEY,
                secret_key=settings.MINIO_SECRET_KEY,
                secure=settings.MINIO_SECURE,
            )
            self._ensure_bucket_exists()
            self._initialized = True
            self._use_filesystem = False
            logger.info("MinIO client initialized successfully")
        except ImportError:
            logger.warning("minio package not installed — using filesystem storage")
            self._use_filesystem = True
            self._initialized = True
            self._storage_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            logger.warning(f"MinIO unavailable, falling back to filesystem storage: {e}")
            self._use_filesystem = True
            self._initialized = True
            self._storage_dir.mkdir(parents=True, exist_ok=True)
            logger.info(f"Using filesystem storage at: {self._storage_dir.absolute()}")

    def _ensure_bucket_exists(self):
        try:
            if not self.client.bucket_exists(self.bucket_name):
                self.client.make_bucket(self.bucket_name)
                logger.info(f"Created bucket: {self.bucket_name}")
        except Exception as e:
            logger.error(f"Error ensuring bucket exists: {e}")
            raise

    def upload_file(self, file_data: bytes, original_filename: str, content_type: str) -> str:
        self._initialize()
        file_extension = original_filename.split(".")[-1]
        object_name = f"{uuid.uuid4()}.{file_extension}"

        if self._use_filesystem or self.client is None:
            path = self._storage_dir / object_name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(file_data)
            logger.info(f"Saved file to filesystem: {path}")
            return object_name

        try:
            from io import BytesIO

            self.client.put_object(
                self.bucket_name,
                object_name,
                BytesIO(file_data),
                length=len(file_data),
                content_type=content_type,
            )
            logger.info(f"Uploaded file to MinIO: {object_name}")
            return object_name
        except Exception as e:
            logger.error(f"Error uploading to MinIO: {e}")
            raise

    def download_file(self, object_name: str) -> bytes:
        self._initialize()
        if self._use_filesystem or self.client is None:
            return (self._storage_dir / object_name).read_bytes()

        response = self.client.get_object(self.bucket_name, object_name)
        try:
            return response.read()
        finally:
            response.close()
            response.release_conn()

    def get_file_path(self, object_name: str) -> str:
        self._initialize()
        if self._use_filesystem or self.client is None:
            return str((self._storage_dir / object_name).absolute())

        url = self.client.presigned_get_object(
            self.bucket_name,
            object_name,
            expires=timedelta(hours=1),
        )
        return url

    def delete_file(self, object_name: str):
        self._initialize()
        if self._use_filesystem or self.client is None:
            path = self._storage_dir / object_name
            if path.exists():
                path.unlink()
            return

        self.client.remove_object(self.bucket_name, object_name)
        logger.info(f"Deleted file: {object_name}")


storage_service = StorageService()
