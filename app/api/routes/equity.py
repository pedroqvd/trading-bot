"""GET /equity — equity-curve series."""
from __future__ import annotations

from fastapi import APIRouter, Query
from sqlalchemy import select

from app.api.dependencies import period_to_since
from app.api.schemas import EquityPoint, EquityResponse, Period
from app.database import session_scope
from app.database.models import EquitySnapshot

router = APIRouter(tags=["equity"])


@router.get("/equity", response_model=EquityResponse)
def equity(period: Period = Query("24h")) -> EquityResponse:
    since = period_to_since(period)
    with session_scope() as session:
        stmt = select(EquitySnapshot).order_by(EquitySnapshot.ts.asc())
        if since is not None:
            stmt = stmt.where(EquitySnapshot.ts >= since.replace(tzinfo=None))
        rows = session.execute(stmt).scalars().all()
        points = [
            EquityPoint(
                time=r.ts,
                equity=float(r.equity_usd),
                cash=float(r.cash_usd),
                unrealized=float(r.unrealized_usd),
            )
            for r in rows
        ]
    return EquityResponse(period=period, points=points)
