"""API key authentication dependency.

If ``API_KEY`` is set in config every request must supply the matching value
in the ``X-API-Key`` header.  When ``API_KEY`` is empty/unset the dependency
is a no-op so local / dry-run setups work without configuration.
"""
from __future__ import annotations

from fastapi import Header, HTTPException, status

from app.config import settings
from app.monitoring.logger import get_logger

log = get_logger(__name__)

_warned = False


def require_api_key(x_api_key: str | None = Header(default=None, alias="X-API-Key")) -> None:
    """FastAPI dependency — inject with ``Depends(require_api_key)``."""
    global _warned
    configured = settings.api_key

    if not configured:
        if not _warned:
            log.warning("api.auth_disabled", reason="API_KEY not set — all endpoints are open")
            _warned = True
        return  # auth disabled

    if x_api_key != configured:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing X-API-Key header",
        )
