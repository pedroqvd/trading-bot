"""GET /positions — open + recently-closed positions."""
from __future__ import annotations

from fastapi import APIRouter, Query
from sqlalchemy import desc, select

from app.api.schemas import PositionResponse
from app.database import session_scope
from app.database.models import Market, Position, PositionStatus

router = APIRouter(tags=["positions"])


@router.get("/positions", response_model=list[PositionResponse])
def list_positions(
    status: str = Query("all"),
    limit: int = Query(100, ge=1, le=500),
) -> list[PositionResponse]:
    with session_scope() as session:
        stmt = (
            select(Position, Market)
            .join(Market, Market.id == Position.market_id)
            .order_by(desc(Position.opened_at))
            .limit(limit)
        )
        if status.lower() == "open":
            stmt = stmt.where(Position.status == PositionStatus.OPEN)
        elif status.lower() == "closed":
            stmt = stmt.where(Position.status != PositionStatus.OPEN)
        rows = session.execute(stmt).all()
        return [
            PositionResponse(
                id=p.id,
                market_question=m.question,
                market_slug=m.slug,
                strategy=p.strategy,
                side=p.side.value,
                status=p.status.value,
                entry_price=float(p.entry_price),
                entry_size_usd=float(p.entry_size_usd),
                shares=float(p.shares),
                take_profit=float(p.take_profit) if p.take_profit is not None else None,
                stop_loss=float(p.stop_loss) if p.stop_loss is not None else None,
                opened_at=p.opened_at,
                closed_at=p.closed_at,
                exit_price=float(p.exit_price) if p.exit_price is not None else None,
                realized_pnl_usd=(
                    float(p.realized_pnl_usd) if p.realized_pnl_usd is not None else None
                ),
            )
            for p, m in rows
        ]
