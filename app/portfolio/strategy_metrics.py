"""Per-strategy performance breakdown.

The original `PortfolioMetrics.compute()` aggregates everything; you couldn't
tell whether the overreaction model was carrying the bot or sinking it. This
module slices the same trade history by strategy.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Sequence

from sqlalchemy import select

from app.database import session_scope
from app.database.models import Position, PositionStatus
from app.utils.time_utils import utcnow


@dataclass
class StrategyReport:
    strategy: str
    trades: int
    wins: int
    losses: int
    win_rate: float
    avg_win_usd: float
    avg_loss_usd: float
    expectancy_usd: float
    total_pnl_usd: float
    profit_factor: float
    avg_hold_minutes: float
    max_drawdown_usd: float


def per_strategy_report(lookback_days: int = 30) -> list[StrategyReport]:
    since = utcnow() - timedelta(days=lookback_days)
    with session_scope() as session:
        rows = session.execute(
            select(Position)
            .where(
                Position.status != PositionStatus.OPEN,
                Position.realized_pnl_usd.is_not(None),
                Position.closed_at >= since,
            )
            .order_by(Position.closed_at.asc())
        ).scalars().all()
        session.expunge_all()

    by_strategy: dict[str, list[Position]] = {}
    for p in rows:
        # The position manager opens close orders with `<strategy>:close` strategy.
        # Roll those back into the parent strategy so the slice is meaningful.
        key = p.strategy.split(":", 1)[0]
        by_strategy.setdefault(key, []).append(p)

    return [_summarise(strategy, positions) for strategy, positions in by_strategy.items()]


def _summarise(strategy: str, positions: Sequence[Position]) -> StrategyReport:
    pnls = [float(p.realized_pnl_usd or 0.0) for p in positions]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]
    trades = len(pnls)
    win_rate = (len(wins) / trades) if trades else 0.0
    avg_win = (sum(wins) / len(wins)) if wins else 0.0
    avg_loss = (sum(losses) / len(losses)) if losses else 0.0
    expectancy = (sum(pnls) / trades) if trades else 0.0
    total = sum(pnls)
    gross_win = sum(wins)
    gross_loss = abs(sum(losses))
    profit_factor = (gross_win / gross_loss) if gross_loss > 0 else (
        math.inf if gross_win > 0 else 0.0
    )

    holds: list[float] = []
    for p in positions:
        if p.opened_at and p.closed_at:
            holds.append((p.closed_at - p.opened_at).total_seconds() / 60.0)
    avg_hold = (sum(holds) / len(holds)) if holds else 0.0

    cumulative = 0.0
    peak = 0.0
    max_dd = 0.0
    for pnl in pnls:
        cumulative += pnl
        if cumulative > peak:
            peak = cumulative
        dd = cumulative - peak
        if dd < max_dd:
            max_dd = dd

    return StrategyReport(
        strategy=strategy,
        trades=trades,
        wins=len(wins),
        losses=len(losses),
        win_rate=win_rate,
        avg_win_usd=avg_win,
        avg_loss_usd=avg_loss,
        expectancy_usd=expectancy,
        total_pnl_usd=total,
        profit_factor=profit_factor,
        avg_hold_minutes=avg_hold,
        max_drawdown_usd=max_dd,
    )
