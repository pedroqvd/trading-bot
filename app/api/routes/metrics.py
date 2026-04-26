"""GET /metrics — aggregate performance summary."""
from __future__ import annotations

from fastapi import APIRouter, Query
from sqlalchemy import func, select

from app.api.schemas import MetricsResponse, Period, StrategyBreakdown
from app.database import session_scope
from app.database.models import EquitySnapshot, Position, PositionStatus
from app.monitoring.edge_health import EdgeHealth
from app.portfolio.advanced_metrics import advanced_report
from app.portfolio.metrics import PortfolioMetrics
from app.portfolio.strategy_metrics import per_strategy_report
from app.utils.time_utils import utcnow

router = APIRouter(tags=["metrics"])


@router.get("/metrics", response_model=MetricsResponse)
def metrics(period: Period = Query("24h")) -> MetricsResponse:
    lookback_days = {"24h": 1, "7d": 7, "30d": 30, "all": 3650}[period]
    pm = PortfolioMetrics()
    perf = pm.compute(lookback_days=lookback_days)
    advanced = advanced_report(lookback_days=lookback_days)

    # Equity / cash from latest snapshot — read scalars inside the session scope
    # so the ORM objects don't become detached before we touch them.
    with session_scope() as session:
        latest_snap = session.execute(
            select(EquitySnapshot).order_by(EquitySnapshot.ts.desc()).limit(1)
        ).scalar_one_or_none()
        equity = float(latest_snap.equity_usd) if latest_snap else 0.0
        cash = float(latest_snap.cash_usd) if latest_snap else 0.0
        open_count = session.execute(
            select(func.count(Position.id)).where(Position.status == PositionStatus.OPEN)
        ).scalar_one()
        today_start = utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        realized_today = session.execute(
            select(func.coalesce(func.sum(Position.realized_pnl_usd), 0.0))
            .where(
                Position.status != PositionStatus.OPEN,
                Position.closed_at >= today_start.replace(tzinfo=None),
            )
        ).scalar_one() or 0.0

    # Per-strategy
    health = EdgeHealth()
    breakdowns: list[StrategyBreakdown] = []
    for sr in per_strategy_report(lookback_days=lookback_days):
        verdict = health.evaluate(sr.strategy)
        breakdowns.append(StrategyBreakdown(
            strategy=sr.strategy,
            trades=sr.trades,
            win_rate=sr.win_rate,
            expectancy_usd=sr.expectancy_usd,
            total_pnl_usd=sr.total_pnl_usd,
            profit_factor=sr.profit_factor if sr.profit_factor != float("inf") else 0.0,
            avg_hold_minutes=sr.avg_hold_minutes,
            state=verdict.state.value,
            reason=verdict.reason or "",
        ))

    return MetricsResponse(
        period=period,
        total_pnl_usd=sum(b.total_pnl_usd for b in breakdowns),
        realized_today_usd=float(realized_today),
        win_rate=perf.win_rate,
        total_trades=perf.trades,
        avg_ev_usd=perf.expectancy_usd,
        expectancy_usd=perf.expectancy_usd,
        profit_factor=perf.profit_factor if perf.profit_factor != float("inf") else 0.0,
        sharpe=advanced.sharpe,
        sortino=advanced.sortino if advanced.sortino != float("inf") else 0.0,
        max_drawdown_pct=perf.max_drawdown_pct,
        open_positions=int(open_count or 0),
        equity_usd=equity,
        cash_usd=cash,
        by_strategy=breakdowns,
    )
