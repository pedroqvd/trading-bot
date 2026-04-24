"""Webhook-based alerting (Slack/Discord compatible)."""
from __future__ import annotations

import httpx

from app.config import settings
from app.monitoring.logger import get_logger

log = get_logger(__name__)


def send_alert(title: str, message: str, severity: str = "info") -> None:
    """Fire-and-forget alert; never raises."""
    url = settings.alert_webhook_url
    if not url:
        log.info("alert.local_only", title=title, severity=severity, message=message)
        return
    payload = {"text": f"[{severity.upper()}] {title}\n{message}"}
    try:
        with httpx.Client(timeout=5.0) as client:
            client.post(url, json=payload)
    except Exception as exc:  # noqa: BLE001
        log.warning("alert.dispatch_failed", error=str(exc))
