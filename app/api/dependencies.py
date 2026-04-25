"""Period parsing helper used by every read endpoint."""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from app.utils.time_utils import utcnow

PERIOD_TO_DAYS = {
    "24h": 1,
    "7d": 7,
    "30d": 30,
    "all": None,
}


def period_to_since(period: str) -> Optional[datetime]:
    days = PERIOD_TO_DAYS.get(period)
    if days is None:
        return None
    return utcnow() - timedelta(days=days)
