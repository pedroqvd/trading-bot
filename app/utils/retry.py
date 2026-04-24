"""Retry helpers for network/API resilience."""
from __future__ import annotations

from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)


def api_retry(max_attempts: int = 4):
    """Retry transient failures with exponential backoff."""
    return retry(
        reraise=True,
        stop=stop_after_attempt(max_attempts),
        wait=wait_exponential(multiplier=1, min=2, max=16),
        retry=retry_if_exception_type((ConnectionError, TimeoutError, OSError)),
    )
