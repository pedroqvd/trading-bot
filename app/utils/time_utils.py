"""Timezone-aware time helpers."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def minutes_ago(minutes: float) -> datetime:
    return utcnow() - timedelta(minutes=minutes)


def parse_iso(s: str) -> datetime:
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    return datetime.fromisoformat(s)
