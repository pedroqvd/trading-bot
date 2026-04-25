"""GET /trades — recent fills and order history."""
from __future__ import annotations

from fastapi import APIRouter, Query
from sqlalchemy import desc, select

from app.api.schemas import TradeResponse
from app.database import session_scope
from app.database.models import Market, Trade

router = APIRouter(tags=["trades"])


@router.get("/trades", response_model=list[TradeResponse])
def list_trades(
    limit: int = Query(100, ge=1, le=500),
    status: str = Query("all"),
) -> list[TradeResponse]:
    with session_scope() as session:
        stmt = (
            select(Trade, Market)
            .join(Market, Market.id == Trade.market_id)
            .order_by(desc(Trade.created_at))
            .limit(limit)
        )
        if status.lower() != "all":
            from app.database.models import TradeStatus
            try:
                stmt = stmt.where(Trade.status == TradeStatus[status.upper()])
            except KeyError:
                pass
        rows = session.execute(stmt).all()
        return [
            TradeResponse(
                id=t.id,
                client_order_id=t.client_order_id,
                market_question=m.question,
                strategy=(t.details or {}).get("strategy", "") if isinstance(t.details, dict) else "",
                market_side=t.market_side.value,
                order_side=t.order_side.value,
                status=t.status.value,
                price=float(t.price),
                size_usd=float(t.size_usd),
                shares=float(t.shares),
                filled_shares=float(t.filled_shares),
                created_at=t.created_at,
                filled_at=t.filled_at,
            )
            for t, m in rows
        ]
