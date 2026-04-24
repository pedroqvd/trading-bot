"""Performance metrics: expectancy, ROI, Sharpe, drawdown, profit factor."""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Sequence

from sqlalchemy import select

from app.config import settings
from app.database import session_scope
from app.database.models import EquitySnapshot, Position, PositionStatus


@dataclass
class PerformanceReport:
    trades: int
    wins: int
    losses: int
    win_rate: float
    avg_win_usd: float
    avg_loss_usd: float
    expectancy_usd: float
    roi_pct: float
    profit_factor: float
    sharpe: float
    max_drawdown_pct: float


class PortfolioMetrics:
    @staticmethod
    def closed_positions(since: datetime | None = None) -> list[Position]:
        with session_scope() as session:
            stmt = select(Position).where(Position.status.in_([
                PositionStatus.CLOSED, PositionStatus.LIQUIDATED,
            ]))
            if since is not None:
                stmt = stmt.where(Position.closed_at >= since)
            rows = session.execute(stmt).scalars().all()
            session.expunge_all()
            return list(rows)

    @staticmethod
    def equity_curve(since: datetime | None = None) -> list[EquitySnapshot]:
        with session_scope() as session:
            stmt = select(EquitySnapshot).order_by(EquitySnapshot.ts.asc())
            if since is not None:
                stmt = stmt.where(EquitySnapshot.ts >= since)
            rows = session.execute(stmt).scalars().all()
            session.expunge_all()
            return list(rows)

    def compute(self, lookback_days: int = 30) -> PerformanceReport:
        since = datetime.utcnow() - timedelta(days=lookback_days)
        positions = self.closed_positions(since=since)
        pnls = [float(p.realized_pnl_usd or 0.0) for p in positions]
        wins = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p < 0]
        trades = len(pnls)
        win_rate = (len(wins) / trades) if trades else 0.0
        avg_win = (sum(wins) / len(wins)) if wins else 0.0
        avg_loss = (sum(losses) / len(losses)) if losses else 0.0
        expectancy = (sum(pnls) / trades) if trades else 0.0

        gross_win = sum(wins)
        gross_loss = abs(sum(losses))
        profit_factor = (gross_win / gross_loss) if gross_loss > 0 else (math.inf if gross_win > 0 else 0.0)

        # Sharpe from equity snapshots (per-snapshot returns)
        curve = self.equity_curve(since=since)
        if len(curve) > 2:
            returns: list[float] = []
            for prev, cur in zip(curve[:-1], curve[1:]):
                if prev.equity_usd > 0:
                    returns.append((cur.equity_usd - prev.equity_usd) / prev.equity_usd)
            sharpe = _sharpe(returns)
        else:
            sharpe = 0.0

        max_dd = _max_drawdown([s.equity_usd for s in curve])
        roi_pct = 0.0
        if curve and curve[0].equity_usd > 0:
            roi_pct = (curve[-1].equity_usd - curve[0].equity_usd) / curve[0].equity_usd

        return PerformanceReport(
            trades=trades,
            wins=len(wins),
            losses=len(losses),
            win_rate=win_rate,
            avg_win_usd=avg_win,
            avg_loss_usd=avg_loss,
            expectancy_usd=expectancy,
            roi_pct=roi_pct,
            profit_factor=profit_factor,
            sharpe=sharpe,
            max_drawdown_pct=max_dd,
        )


def _sharpe(returns: Sequence[float], risk_free: float = 0.0, periods_per_year: int = 365 * 48) -> float:
    """Annualised Sharpe assuming ~48 snapshots/day (30-min cadence). Tuned to config."""
    if not returns:
        return 0.0
    mean = sum(returns) / len(returns)
    variance = sum((r - mean) ** 2 for r in returns) / max(1, len(returns) - 1)
    std = math.sqrt(variance)
    if std == 0:
        return 0.0
    return ((mean - risk_free) / std) * math.sqrt(periods_per_year)


def _max_drawdown(equity: Sequence[float]) -> float:
    if not equity:
        return 0.0
    peak = equity[0]
    max_dd = 0.0
    for e in equity:
        if e > peak:
            peak = e
        if peak > 0:
            dd = (e - peak) / peak
            if dd < max_dd:
                max_dd = dd
    return max_dd
