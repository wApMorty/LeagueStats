"""Health check endpoint."""

from fastapi import APIRouter
from datetime import datetime
from ...config import settings
from ..models import HealthCheckResponse

router = APIRouter()


@router.get("/health", response_model=HealthCheckResponse)
async def health_check():
    """
    Health check endpoint for monitoring.

    Returns:
        HealthCheckResponse: Status information
    """
    return HealthCheckResponse(
        status="ok",
        version=settings.app_version,
        database="connected",
        timestamp=datetime.utcnow().isoformat() + "Z",
    )
