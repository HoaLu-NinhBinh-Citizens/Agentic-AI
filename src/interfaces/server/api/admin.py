"""Admin API endpoints for Phase 2D.1.

Provides runtime configuration and monitoring endpoints.
"""

from __future__ import annotations

import logging
import os
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, status

from shared.logging import get_current_log_level, set_log_level


router = APIRouter(prefix="/admin", tags=["admin"])

ADMIN_TOKEN_ENV = os.getenv("ADMIN_API_TOKEN", "changeme")


async def verify_admin_token(
    x_admin_token: Annotated[str, Header()],
) -> str:
    """Verify admin token from header.

    Args:
        x_admin_token: Admin token from X-Admin-Token header.

    Returns:
        The verified token.

    Raises:
        HTTPException: If token is invalid.
    """
    if x_admin_token != ADMIN_TOKEN_ENV:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid admin token",
        )
    return x_admin_token


@router.post("/loglevel")
async def change_log_level(
    level: str,
    token: Annotated[str, Depends(verify_admin_token)],
) -> dict:
    """Change the logging level at runtime.

    Args:
        level: New log level (DEBUG, INFO, WARNING, ERROR, CRITICAL).
        token: Verified admin token.

    Returns:
        Status confirmation with new level.

    Raises:
        HTTPException: If level is invalid.
    """
    level_upper = level.upper()

    if level_upper not in ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid log level: {level}. Must be one of: DEBUG, INFO, WARNING, ERROR, CRITICAL",
        )

    new_level = set_log_level(level_upper)
    logger = logging.getLogger(__name__)
    logger.info("Log level changed to %s by admin", new_level)

    return {
        "status": "ok",
        "level": new_level,
    }


@router.get("/loglevel")
async def get_log_level() -> dict:
    """Get the current logging level.

    Returns:
        Current log level.
    """
    current = get_current_log_level()
    return {
        "level": current,
    }


@router.get("/status")
async def get_admin_status(
    token: Annotated[str, Depends(verify_admin_token)],
) -> dict:
    """Get admin API status.

    Args:
        token: Verified admin token.

    Returns:
        Admin API status.
    """
    return {
        "status": "ok",
        "version": "1.0.0",
        "endpoints": [
            "/admin/loglevel (GET, POST)",
            "/admin/status (GET)",
        ],
    }
