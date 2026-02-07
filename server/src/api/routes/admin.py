"""Admin endpoints for internal operations."""

from typing import Optional
from fastapi import APIRouter, HTTPException, Header
from ...config import settings
from ...db import close_all_connections

router = APIRouter()


@router.post("/refresh-db")
async def refresh_db(x_api_key: Optional[str] = Header(None)):
    """
    Force refresh database connection pool.

    This endpoint closes all existing database connections and forces
    the pool to be recreated on next query. Used after database sync
    to ensure API sees fresh data immediately.

    Security: Requires X-API-Key header matching ADMIN_API_KEY env var.

    Args:
        x_api_key: Admin API key from request header

    Returns:
        Success message confirming pool refresh

    Raises:
        HTTPException: 500 if admin API key not configured
        HTTPException: 403 if provided API key is invalid
        HTTPException: 500 if pool refresh fails
    """
    # Validate API key configuration
    if not settings.admin_api_key:
        raise HTTPException(status_code=500, detail="Admin API key not configured")

    # Validate provided API key
    if not x_api_key or x_api_key != settings.admin_api_key:
        raise HTTPException(status_code=403, detail="Invalid API key")

    # Force dispose database pool
    try:
        await close_all_connections()
        return {
            "status": "ok",
            "message": "Database connection pool refreshed successfully",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to refresh pool: {str(e)}")
