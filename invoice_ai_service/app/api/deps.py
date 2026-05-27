"""Shared FastAPI dependencies."""

import secrets as std_secrets
from typing import Annotated, Optional

from fastapi import Header, HTTPException, status

from app.config.settings import settings


def _check_secret(header_value: Optional[str], expected: str, header_name: str) -> None:
    if not header_value or len(header_value) != len(expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid or missing {header_name} header",
        )
    if not std_secrets.compare_digest(header_value.encode("utf-8"), expected.encode("utf-8")):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid or missing {header_name} header",
        )


async def verify_train_post_secret(
    x_training_secret: Annotated[Optional[str], Header()] = None,
) -> None:
    """When TRAIN_API_SECRET is set, POST /train requires matching X-Training-Secret."""
    expected = settings.TRAIN_API_SECRET
    if expected:
        _check_secret(x_training_secret, expected, "X-Training-Secret")


async def verify_upload_api_key(
    x_api_key: Annotated[Optional[str], Header()] = None,
) -> None:
    """When UPLOAD_API_KEY is set, POST /upload requires matching X-API-Key."""
    expected = settings.UPLOAD_API_KEY
    if expected:
        _check_secret(x_api_key, expected, "X-API-Key")
