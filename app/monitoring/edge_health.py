"""Per-strategy edge-health tracking.

Detects when a strategy's edge is breaking by computing rolling statistics
(win rate, expectancy, drawdown) over its closed positions. Returns a verdict
the runner can act on:

  HEALTHY   → trade normally
  WATCH     → expectancy positive but trending weak
  IMPAIRED  → recent win rate or expectancy collapsed → reduce capital
  DISABLED  → rolling expectancy < 0 or strategy DD exceeds threshold → halt
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Sequence

from sqlalchemy import desc, select

from app.config import settings
from app.database import session_scope
from app.database.models import Position, PositionStatus, RiskEvent
from app.monitoring.alerts import send_alert
from app.monitoring.logger import get_logger

log = get_logger(__name__)


class HealthState(str, Enum):
    HEALTHY = "HEALTHY"
    WATCH = "WATCH"
    IMPAIRED = "IMPAIRED"
    DISABLED = "DISABLED"


@dataclass(frozen=True)
class EdgeVerdict:
    strategy: str
    state: HealthState
    trades: int
    win_rate: float
    expectancy_usd: float
    cumulative_pnl_usd: float
    drawdown_pct: float
    reason: str = ""


_LAST_DISABLED_ALERTS: dict[str, str] = {}


class EdgeHealth:
    """Compute per-strategy verdicts and emit alerts on transitions."""

    def __init__(self, lookback_trades: int = 30) -> None:
        self.lookback_trades = lookback_trades

    def evaluate(self, strategy: str) -> EdgeVerdict:
        with session_scope() as session:
            recent = session.execute(
                select(Position)
                .where(
                    Position.strategy == strategy,
                    Position.status != PositionStatus.OPEN,
                    Position.realized_pnl_usd.is_not(None),
                )
                .order_by(desc(Position.closed_at))
                .limit(self.lookback_trades)
            ).scalars().all()
            session.expunge_all()

        return self._verdict(strategy, list(recent))

    def evaluate_and_alert(self, strategy: str) -> EdgeVerdict:
        verdict = self.evaluate(strategy)
        prior = _LAST_DISABLED_ALERTS.get(strategy)
        if verdict.state == HealthState.DISABLED and prior != HealthState.DISABLED.value:
            send_alert(
                title=f"Strategy '{strategy}' disabled",
                message=verdict.reason,
                severity="warning",
            )
            with session_scope() as session:
                session.add(RiskEvent(
                    kind="STRATEGY_DISABLED",
                    severity="WARNING",
                    message=f"{strategy}: {verdict.reason}",
                    details={
                        "strategy": strategy,
                        "win_rate": verdict.win_rate,
                        "expectancy": verdict.expectancy_usd,
                        "drawdown_pct": verdict.drawdown_pct,
                        "trades": verdict.trades,
                    },
                ))
            _LAST_DISABLED_ALERTS[strategy] = verdict.state.value
        elif verdict.state != HealthState.DISABLED:
            _LAST_DISABLED_ALERTS.pop(strategy, None)
        return verdict

    # -----------------------------------------------------------------------
    def _verdict(self, strategy: str, positions: Sequence[Position]) -> EdgeVerdict:
        trades = len(positions)
        if trades == 0:
            return EdgeVerdict(strategy, HealthState.HEALTHY, 0, 0.0, 0.0, 0.0, 0.0)

        pnls = [float(p.realized_pnl_usd or 0.0) for p in positions]
        wins = [p for p in pnls if p > 0]
        win_rate = len(wins) / trades
        expectancy = sum(pnls) / trades
        cumulative = sum(pnls)

        # DD against best running cumulative on the rolling window
        running = 0.0
        peak = 0.0
        worst_dd = 0.0
        for pnl in reversed(pnls):  # oldest → newest
            running += pnl
            if running > peak:
                peak = running
            dd = running - peak
            if dd < worst_dd:
                worst_dd = dd
        # express drawdown as a fraction of the peak (capped) or as raw $ if peak is 0
        drawdown_pct = (worst_dd / peak) if peak > 0 else 0.0

        # ---- Verdict logic ----
        if trades < settings.edge_health_min_trades:
            return EdgeVerdict(strategy, HealthState.HEALTHY, trades, win_rate,
                               expectancy, cumulative, drawdown_pct,
                               reason="not enough trades for verdict")

        if expectancy < settings.edge_health_min_expectancy_usd:
            return EdgeVerdict(strategy, HealthState.DISABLED, trades, win_rate,
                               expectancy, cumulative, drawdown_pct,
                               reason=f"expectancy ${expectancy:.2f} negative over last {trades} trades")

        if abs(drawdown_pct) >= settings.edge_health_max_drawdown_pct:
            return EdgeVerdict(strategy, HealthState.DISABLED, trades, win_rate,
                               expectancy, cumulative, drawdown_pct,
                               reason=(f"strategy DD {drawdown_pct:.2%} exceeds "
                                       f"{settings.edge_health_max_drawdown_pct:.0%}"))

        if win_rate < 0.40 or expectancy < settings.edge_health_min_expectancy_usd * 1.5 + 0.01:
            return EdgeVerdict(strategy, HealthState.IMPAIRED, trades, win_rate,
                               expectancy, cumulative, drawdown_pct,
                               reason="win rate / expectancy degraded — capital reduced")

        if win_rate < 0.50:
            return EdgeVerdict(strategy, HealthState.WATCH, trades, win_rate,
                               expectancy, cumulative, drawdown_pct,
                               reason="watching — win rate below 50%")

        return EdgeVerdict(strategy, HealthState.HEALTHY, trades, win_rate,
                           expectancy, cumulative, drawdown_pct)


def health_multiplier(state: HealthState) -> float:
    """Capital multiplier based on health state."""
    return {
        HealthState.HEALTHY: 1.0,
        HealthState.WATCH: 0.75,
        HealthState.IMPAIRED: 0.4,
        HealthState.DISABLED: 0.0,
    }[state]
