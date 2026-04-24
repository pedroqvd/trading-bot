"""Pre-trade risk filter + breakpoint enforcement."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from sqlalchemy import func, select

from app.config import settings
from app.database import session_scope
from app.database.models import Position, PositionStatus
from app.monitoring.logger import get_logger
from app.risk.circuit_breaker import BreakerState, CircuitBreaker

log = get_logger(__name__)


@dataclass
class RiskDecision:
    approved: bool
    size_usd: float
    reason: str = ""
    details: dict = None  # type: ignore[assignment]

    @classmethod
    def reject(cls, reason: str) -> "RiskDecision":
        return cls(False, 0.0, reason, {})

    @classmethod
    def approve(cls, size_usd: float, details: dict | None = None) -> "RiskDecision":
        return cls(True, size_usd, "", details or {})


class RiskManager:
    def __init__(self) -> None:
        self.breaker = CircuitBreaker()

    def check(
        self,
        *,
        strategy: str,
        suggested_size_usd: float,
        edge_mispricing: float,
        edge_ev: float,
        liquidity_usd: float,
        spread: Optional[float],
        current_equity_usd: float,
    ) -> RiskDecision:
        if suggested_size_usd <= 0:
            return RiskDecision.reject("Kelly size non-positive")

        if edge_mispricing < settings.min_mispricing:
            return RiskDecision.reject(
                f"Mispricing {edge_mispricing:.4f} < min {settings.min_mispricing:.4f}"
            )
        if edge_ev < settings.min_expected_value:
            return RiskDecision.reject(
                f"EV {edge_ev:.4f} < min {settings.min_expected_value:.4f}"
            )
        if liquidity_usd < settings.min_liquidity_usd:
            return RiskDecision.reject(
                f"Liquidity ${liquidity_usd:,.0f} < ${settings.min_liquidity_usd:,.0f}"
            )
        if spread is not None and spread > settings.max_spread:
            return RiskDecision.reject(f"Spread {spread:.4f} exceeds {settings.max_spread:.4f}")

        # Global exposure ceiling
        exposure = self._open_exposure_usd()
        cap = current_equity_usd * settings.max_portfolio_exposure
        if exposure + suggested_size_usd > cap:
            room = max(0.0, cap - exposure)
            if room <= 0:
                return RiskDecision.reject(
                    f"Portfolio exposure ${exposure:,.0f}/${cap:,.0f} — no room"
                )
            suggested_size_usd = min(suggested_size_usd, room)

        # Max open position count
        open_count = self._open_position_count()
        if open_count >= settings.max_open_positions:
            return RiskDecision.reject(
                f"Open positions {open_count} >= cap {settings.max_open_positions}"
            )

        # Circuit breaker
        verdict = self.breaker.evaluate(current_equity_usd)
        if verdict.tripped:
            return RiskDecision.reject(f"Circuit breaker {verdict.state.value}: {verdict.reason}")

        return RiskDecision.approve(
            size_usd=suggested_size_usd,
            details={
                "open_exposure_usd": exposure,
                "open_positions": open_count,
                "breaker_state": verdict.state.value,
                "drawdown_pct": verdict.drawdown_pct,
                "daily_pnl_pct": verdict.daily_pnl_pct,
                "strategy": strategy,
            },
        )

    # -----------------------------------------------------------------------
    # DB helpers
    # -----------------------------------------------------------------------
    @staticmethod
    def _open_exposure_usd() -> float:
        with session_scope() as session:
            total = session.execute(
                select(func.coalesce(func.sum(Position.entry_size_usd), 0.0))
                .where(Position.status == PositionStatus.OPEN)
            ).scalar_one()
        return float(total or 0.0)

    @staticmethod
    def _open_position_count() -> int:
        with session_scope() as session:
            count = session.execute(
                select(func.count(Position.id)).where(Position.status == PositionStatus.OPEN)
            ).scalar_one()
        return int(count or 0)
