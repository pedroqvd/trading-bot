"""GET /risk/events — circuit-breaker and kill-switch event log."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Query
from pydantic import BaseModel
from sqlalchemy import desc, select

from app.database import session_scope
from app.database.models import RiskEvent

router = APIRouter(tags=["risk"], prefix="/risk")


class RiskEventResponse(BaseModel):
    id: int
    ts: datetime
    kind: str
    severity: str
    message: str
    details: dict


@router.get("/events", response_model=list[RiskEventResponse])
def list_risk_events(
    limit: int = Query(100, ge=1, le=1000),
    kind: Optional[str] = Query(None, description="Filter by event kind, e.g. 'daily_loss'"),
    severity: Optional[str] = Query(None, description="Filter by severity: info | warning | critical"),
) -> list[RiskEventResponse]:
    with session_scope() as session:
        stmt = select(RiskEvent).order_by(desc(RiskEvent.ts)).limit(limit)
        if kind:
            stmt = stmt.where(RiskEvent.kind == kind)
        if severity:
            stmt = stmt.where(RiskEvent.severity == severity.lower())
        rows = session.execute(stmt).scalars().all()
        return [
            RiskEventResponse(
                id=r.id,
                ts=r.ts,
                kind=r.kind,
                severity=r.severity,
                message=r.message,
                details=r.details or {},
            )
            for r in rows
        ]
