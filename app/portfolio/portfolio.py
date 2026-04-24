"""Portfolio accounting: cash, positions, equity snapshots."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Iterable

from sqlalchemy import func, select

from app.config import settings
from app.data.schemas import MarketQuote
from app.database import session_scope
from app.database.models import (
    EquitySnapshot,
    Position,
    PositionStatus,
    Side,
    Trade,
    TradeStatus,
)
from app.execution.orders import ExecutionResult, OrderRequest
from app.monitoring.logger import get_logger
from app.monitoring.metrics import (
    CASH_USD,
    DAILY_PNL_USD,
    DRAWDOWN_PCT,
    EQUITY_USD,
    OPEN_POSITIONS,
)
from app.utils.time_utils import utcnow

log = get_logger(__name__)


@dataclass
class EquitySummary:
    cash_usd: float
    unrealized_usd: float
    equity_usd: float
    realized_today_usd: float
    open_positions: int
    peak_equity_usd: float
    drawdown_pct: float


class Portfolio:
    """Derives current cash + equity from persistent trades and snapshots it."""

    def __init__(self) -> None:
        self.starting_capital_usd = settings.capital_usd

    # -----------------------------------------------------------------------
    # Cash & equity
    # -----------------------------------------------------------------------
    def cash_usd(self) -> float:
        """Cash = starting capital - outstanding position entry cost + realized PnL."""
        with session_scope() as session:
            open_cost = session.execute(
                select(func.coalesce(func.sum(Position.entry_size_usd), 0.0))
                .where(Position.status == PositionStatus.OPEN)
            ).scalar_one() or 0.0
            realized = session.execute(
                select(func.coalesce(func.sum(Position.realized_pnl_usd), 0.0))
                .where(Position.status != PositionStatus.OPEN)
            ).scalar_one() or 0.0
        return float(self.starting_capital_usd - open_cost + realized)

    def unrealized_usd(self, quotes: Iterable[MarketQuote]) -> float:
        """Mark-to-market sum for open positions using best bids."""
        mark_by_condition = {}
        for q in quotes:
            mark_by_condition[q.condition_id] = q

        total = 0.0
        with session_scope() as session:
            open_positions = session.execute(
                select(Position).where(Position.status == PositionStatus.OPEN)
            ).scalars().all()
            for pos in open_positions:
                from app.database.models import Market  # avoid cycle
                market = session.get(Market, pos.market_id)
                if market is None:
                    continue
                q = mark_by_condition.get(market.condition_id)
                if q is None:
                    continue
                mark = q.yes_bid if pos.side == Side.YES else q.no_bid
                if mark is None:
                    mark = q.yes_mid if pos.side == Side.YES else q.no_mid
                if mark is None:
                    continue
                total += (mark - pos.entry_price) * pos.shares
        return total

    def summary(self, quotes: Iterable[MarketQuote]) -> EquitySummary:
        cash = self.cash_usd()
        unreal = self.unrealized_usd(quotes)
        equity = cash + self._open_cost() + unreal  # cash already excludes open cost → add back entry value then unrealised
        realized_today = self._realized_today_usd()
        peak = self._peak_equity_usd() or equity
        drawdown = min(0.0, (equity - peak) / peak) if peak > 0 else 0.0
        with session_scope() as session:
            open_count = session.execute(
                select(func.count(Position.id)).where(Position.status == PositionStatus.OPEN)
            ).scalar_one()
        return EquitySummary(
            cash_usd=cash,
            unrealized_usd=unreal,
            equity_usd=equity,
            realized_today_usd=realized_today,
            open_positions=int(open_count or 0),
            peak_equity_usd=peak,
            drawdown_pct=drawdown,
        )

    # -----------------------------------------------------------------------
    # Position creation after a fill
    # -----------------------------------------------------------------------
    def record_entry(self, request: OrderRequest, result: ExecutionResult) -> int | None:
        """Persist a new Position for an approved + filled entry order."""
        if result.status not in (TradeStatus.FILLED, TradeStatus.PARTIAL):
            return None
        if result.filled_shares <= 0:
            return None

        with session_scope() as session:
            pos = Position(
                market_id=request.market_id,
                strategy=request.strategy,
                side=request.market_side,
                status=PositionStatus.OPEN,
                entry_price=result.filled_price,
                entry_size_usd=result.filled_shares * result.filled_price,
                shares=result.filled_shares,
                take_profit=request.take_profit,
                stop_loss=request.stop_loss,
                max_hold_until=request.max_hold_until,
                details={
                    "client_order_id": request.client_order_id,
                    "strategy_metadata": request.metadata,
                },
            )
            session.add(pos)
            session.flush()
            # Link the trade row to this position
            trade = session.execute(
                select(Trade).where(Trade.client_order_id == request.client_order_id)
            ).scalar_one_or_none()
            if trade is not None:
                trade.position_id = pos.id
            return pos.id

    # -----------------------------------------------------------------------
    # Snapshots
    # -----------------------------------------------------------------------
    def snapshot(self, quotes: Iterable[MarketQuote]) -> EquitySummary:
        summary = self.summary(quotes)
        with session_scope() as session:
            session.add(EquitySnapshot(
                cash_usd=summary.cash_usd,
                unrealized_usd=summary.unrealized_usd,
                equity_usd=summary.equity_usd,
                realized_today_usd=summary.realized_today_usd,
                open_positions=summary.open_positions,
            ))
        EQUITY_USD.set(summary.equity_usd)
        CASH_USD.set(summary.cash_usd)
        OPEN_POSITIONS.set(summary.open_positions)
        DAILY_PNL_USD.set(summary.realized_today_usd)
        DRAWDOWN_PCT.set(summary.drawdown_pct)
        return summary

    # -----------------------------------------------------------------------
    # Helpers
    # -----------------------------------------------------------------------
    @staticmethod
    def _open_cost() -> float:
        with session_scope() as session:
            return float(session.execute(
                select(func.coalesce(func.sum(Position.entry_size_usd), 0.0))
                .where(Position.status == PositionStatus.OPEN)
            ).scalar_one() or 0.0)

    @staticmethod
    def _realized_today_usd() -> float:
        start = utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        with session_scope() as session:
            return float(session.execute(
                select(func.coalesce(func.sum(Position.realized_pnl_usd), 0.0))
                .where(Position.closed_at >= start)
            ).scalar_one() or 0.0)

    @staticmethod
    def _peak_equity_usd() -> float:
        with session_scope() as session:
            return float(session.execute(
                select(func.coalesce(func.max(EquitySnapshot.equity_usd), 0.0))
            ).scalar_one() or 0.0)
