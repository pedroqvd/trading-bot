"""Lifecycle management for open positions: exits, take-profit, stop-loss."""
from __future__ import annotations

from datetime import timedelta
from typing import Iterable

from sqlalchemy import select

from app.data.polymarket_client import PolymarketClient
from app.data.schemas import MarketQuote
from app.database import session_scope
from app.database.models import OrderSide, Position, PositionStatus, Side, TradeStatus
from app.execution.executor import Executor
from app.execution.orders import ExecutionResult, OrderRequest, new_client_order_id
from app.monitoring.logger import get_logger
from app.utils.time_utils import utcnow

log = get_logger(__name__)


class PositionManager:
    """Evaluates open positions against current quotes and triggers exits."""

    def __init__(self, client: PolymarketClient, executor: Executor) -> None:
        self.client = client
        self.executor = executor

    def reconcile(self, quotes: Iterable[MarketQuote]) -> list[ExecutionResult]:
        quote_by_condition = {q.condition_id: q for q in quotes}
        results: list[ExecutionResult] = []

        with session_scope() as session:
            open_positions = session.execute(
                select(Position).where(Position.status == PositionStatus.OPEN)
            ).scalars().all()
            session.expunge_all()

        for pos in open_positions:
            q = quote_by_condition.get(self._condition_id_for(pos.market_id))
            if q is None:
                continue
            mark = self._mark_price(pos, q)
            if mark is None:
                continue
            reason = self._exit_reason(pos, mark)
            if reason is None:
                continue

            result = self._close_position(pos, q, mark, reason)
            if result is not None:
                results.append(result)
        return results

    # -----------------------------------------------------------------------
    def _exit_reason(self, pos: Position, mark: float) -> str | None:
        if pos.take_profit is not None and mark >= pos.take_profit:
            return "take_profit"
        if pos.stop_loss is not None and mark <= pos.stop_loss:
            return "stop_loss"
        if pos.max_hold_until is not None and utcnow() >= pos.max_hold_until:
            return "time_stop"
        return None

    @staticmethod
    def _mark_price(pos: Position, q: MarketQuote) -> float | None:
        if pos.side == Side.YES:
            return q.yes_bid or q.yes_mid
        return q.no_bid or q.no_mid

    @staticmethod
    def _token_id(pos: Position, q: MarketQuote) -> str:
        return q.yes_token_id if pos.side == Side.YES else q.no_token_id

    @staticmethod
    def _condition_id_for(market_id: int) -> str:
        from app.database.models import Market  # local import to avoid cycles
        with session_scope() as session:
            m = session.get(Market, market_id)
            return m.condition_id if m else ""

    def _close_position(self, pos: Position, q: MarketQuote, mark: float, reason: str) -> ExecutionResult | None:
        request = OrderRequest(
            market_condition_id=q.condition_id,
            market_id=pos.market_id,
            token_id=self._token_id(pos, q),
            market_side=pos.side,
            order_side=OrderSide.SELL,
            price=mark,
            size_usd=pos.shares * mark,
            shares=pos.shares,
            strategy=f"{pos.strategy}:close",
            client_order_id=new_client_order_id(prefix="close"),
            metadata={"reason": reason, "position_id": pos.id},
            position_id=pos.id,
        )
        result = self.executor.execute(request)

        if result.status in (TradeStatus.FILLED, TradeStatus.PARTIAL):
            self._mark_position_closed(pos.id, result, reason)
            log.info("position.closed",
                     position_id=pos.id, reason=reason,
                     entry=pos.entry_price, exit=result.filled_price,
                     pnl=(result.filled_price - pos.entry_price) * result.filled_shares)
        else:
            log.warning("position.close_failed", position_id=pos.id, reason=reason, status=result.status.value)
        return result

    @staticmethod
    def _mark_position_closed(position_id: int, result: ExecutionResult, reason: str) -> None:
        with session_scope() as session:
            pos = session.get(Position, position_id)
            if pos is None:
                return
            pos.status = PositionStatus.CLOSED
            pos.exit_price = result.filled_price
            pos.closed_at = utcnow()
            pnl_gross = (result.filled_price - pos.entry_price) * result.filled_shares
            pnl_net = pnl_gross - result.fees_usd
            pos.realized_pnl_usd = pnl_net
            details = pos.details or {}
            details.update({"exit_reason": reason, "exit_fees": result.fees_usd})
            pos.details = details
