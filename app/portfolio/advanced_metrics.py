"""Sharpe, Sortino, MAE, MFE — strategy-aware.

Sharpe / Sortino consume the equity curve (snapshots).
MAE / MFE consume per-position adverse / favorable excursions, which we
approximate from the persisted Quote history walked between open and close.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional, Sequence

from sqlalchemy import select

from app.database import session_scope
from app.database.models import EquitySnapshot, Position, PositionStatus, Quote, Side
from app.utils.time_utils import utcnow


@dataclass
class AdvancedReport:
    sharpe: float
    sortino: float
    avg_mae_usd: float
    avg_mfe_usd: float
    worst_mae_usd: float
    best_mfe_usd: float
    samples: int


def _sharpe(returns: Sequence[float], periods_per_year: int = 365 * 48) -> float:
    if not returns:
        return 0.0
    mean = sum(returns) / len(returns)
    var = sum((r - mean) ** 2 for r in returns) / max(1, len(returns) - 1)
    std = math.sqrt(var)
    if std == 0:
        return 0.0
    return (mean / std) * math.sqrt(periods_per_year)


def _sortino(returns: Sequence[float], periods_per_year: int = 365 * 48) -> float:
    if not returns:
        return 0.0
    mean = sum(returns) / len(returns)
    downside = [r for r in returns if r < 0]
    if not downside:
        return float("inf") if mean > 0 else 0.0
    dd_var = sum(r ** 2 for r in downside) / len(downside)
    dd_std = math.sqrt(dd_var)
    if dd_std == 0:
        return 0.0
    return (mean / dd_std) * math.sqrt(periods_per_year)


def equity_returns(since: Optional[datetime] = None) -> list[float]:
    with session_scope() as session:
        stmt = select(EquitySnapshot).order_by(EquitySnapshot.ts.asc())
        if since is not None:
            stmt = stmt.where(EquitySnapshot.ts >= since)
        snaps = session.execute(stmt).scalars().all()
    returns: list[float] = []
    for prev, cur in zip(snaps[:-1], snaps[1:]):
        if prev.equity_usd > 0:
            returns.append((cur.equity_usd - prev.equity_usd) / prev.equity_usd)
    return returns


def _aware(dt):
    if dt is None:
        return None
    if dt.tzinfo is None:
        from datetime import timezone
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _mae_mfe_for_position(pos: Position, quotes: Sequence[Quote]) -> tuple[float, float]:
    """Return (MAE, MFE) in *USD* for `pos`, using mid-prices on the held leg."""
    opened = _aware(pos.opened_at)
    closed = _aware(pos.closed_at) or utcnow()
    inside = [q for q in quotes if _aware(q.ts) and opened <= _aware(q.ts) <= closed]
    if not inside:
        return 0.0, 0.0
    entry = float(pos.entry_price)
    shares = float(pos.shares)
    mae = 0.0  # most negative unrealised
    mfe = 0.0  # most positive unrealised
    for q in inside:
        mid = q.yes_mid if pos.side == Side.YES else q.no_mid
        if mid is None:
            continue
        upnl = (float(mid) - entry) * shares
        if upnl < mae:
            mae = upnl
        if upnl > mfe:
            mfe = upnl
    return mae, mfe


def advanced_report(lookback_days: int = 30, strategy: Optional[str] = None) -> AdvancedReport:
    since = utcnow() - timedelta(days=lookback_days)
    returns = equity_returns(since=since)
    sharpe = _sharpe(returns)
    sortino = _sortino(returns)

    with session_scope() as session:
        stmt = (
            select(Position)
            .where(
                Position.status != PositionStatus.OPEN,
                Position.realized_pnl_usd.is_not(None),
                Position.closed_at >= since,
            )
            .order_by(Position.closed_at.asc())
        )
        if strategy:
            stmt = stmt.where(Position.strategy == strategy)
        positions = session.execute(stmt).scalars().all()
        # Quotes: pull the relevant slice once per market to keep N+1 cost low.
        market_ids = {p.market_id for p in positions}
        quotes_by_market: dict[int, list[Quote]] = {mid: [] for mid in market_ids}
        if market_ids:
            qstmt = select(Quote).where(
                Quote.market_id.in_(market_ids),
                Quote.ts >= since,
            )
            for q in session.execute(qstmt).scalars():
                quotes_by_market.setdefault(q.market_id, []).append(q)
        session.expunge_all()

    maes: list[float] = []
    mfes: list[float] = []
    for pos in positions:
        mae, mfe = _mae_mfe_for_position(pos, quotes_by_market.get(pos.market_id, []))
        maes.append(mae)
        mfes.append(mfe)

    return AdvancedReport(
        sharpe=sharpe,
        sortino=sortino,
        avg_mae_usd=(sum(maes) / len(maes)) if maes else 0.0,
        avg_mfe_usd=(sum(mfes) / len(mfes)) if mfes else 0.0,
        worst_mae_usd=min(maes) if maes else 0.0,
        best_mfe_usd=max(mfes) if mfes else 0.0,
        samples=len(positions),
    )
