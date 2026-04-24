"""Daily / drawdown circuit breakers that kill trading when tripped."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from enum import Enum

from sqlalchemy import select

from app.config import settings
from app.database import session_scope
from app.database.models import EquitySnapshot, RiskEvent
from app.monitoring.alerts import send_alert
from app.monitoring.logger import get_logger
from app.monitoring.metrics import CIRCUIT_BREAKER_TRIPS
from app.utils.time_utils import utcnow

log = get_logger(__name__)


class BreakerState(str, Enum):
    OK = "OK"
    DAILY_LOSS = "DAILY_LOSS"
    MAX_DRAWDOWN = "MAX_DRAWDOWN"


@dataclass
class BreakerVerdict:
    state: BreakerState
    reason: str = ""
    daily_pnl_pct: float = 0.0
    drawdown_pct: float = 0.0

    @property
    def tripped(self) -> bool:
        return self.state is not BreakerState.OK


class CircuitBreaker:
    """Evaluates daily loss and peak-to-trough drawdown against thresholds."""

    def evaluate(self, current_equity_usd: float) -> BreakerVerdict:
        with session_scope() as session:
            start_of_day = utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
            day_opening = session.execute(
                select(EquitySnapshot)
                .where(EquitySnapshot.ts >= start_of_day)
                .order_by(EquitySnapshot.ts.asc())
                .limit(1)
            ).scalar_one_or_none()

            peak = session.execute(
                select(EquitySnapshot)
                .order_by(EquitySnapshot.equity_usd.desc())
                .limit(1)
            ).scalar_one_or_none()

        daily_pnl_pct = 0.0
        if day_opening and day_opening.equity_usd > 0:
            daily_pnl_pct = (current_equity_usd - day_opening.equity_usd) / day_opening.equity_usd

        drawdown_pct = 0.0
        if peak and peak.equity_usd > 0:
            drawdown_pct = min(0.0, (current_equity_usd - peak.equity_usd) / peak.equity_usd)

        if daily_pnl_pct <= -settings.max_daily_loss_pct:
            verdict = BreakerVerdict(
                BreakerState.DAILY_LOSS,
                f"Daily PnL {daily_pnl_pct:.2%} breached limit -{settings.max_daily_loss_pct:.2%}",
                daily_pnl_pct, drawdown_pct,
            )
            self._log_trip(verdict)
            return verdict

        if drawdown_pct <= -settings.max_drawdown_pct:
            verdict = BreakerVerdict(
                BreakerState.MAX_DRAWDOWN,
                f"Drawdown {drawdown_pct:.2%} breached limit -{settings.max_drawdown_pct:.2%}",
                daily_pnl_pct, drawdown_pct,
            )
            self._log_trip(verdict)
            return verdict

        return BreakerVerdict(BreakerState.OK, "", daily_pnl_pct, drawdown_pct)

    @staticmethod
    def _log_trip(verdict: BreakerVerdict) -> None:
        CIRCUIT_BREAKER_TRIPS.labels(kind=verdict.state.value).inc()
        log.error("risk.circuit_breaker_tripped", state=verdict.state.value, reason=verdict.reason)
        with session_scope() as session:
            session.add(RiskEvent(
                kind=verdict.state.value,
                severity="CRITICAL",
                message=verdict.reason,
                details={
                    "daily_pnl_pct": verdict.daily_pnl_pct,
                    "drawdown_pct": verdict.drawdown_pct,
                },
            ))
        send_alert("Circuit breaker tripped", verdict.reason, severity="critical")


def is_recent_breaker(within_minutes: int = 60) -> bool:
    cutoff = utcnow() - timedelta(minutes=within_minutes)
    with session_scope() as session:
        row = session.execute(
            select(RiskEvent)
            .where(RiskEvent.ts >= cutoff)
            .where(RiskEvent.kind.in_([s.value for s in BreakerState if s != BreakerState.OK]))
            .order_by(RiskEvent.ts.desc())
            .limit(1)
        ).scalar_one_or_none()
    return row is not None
