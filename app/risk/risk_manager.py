"""Pre-trade risk filter + breakpoint enforcement.

Refactored to consult `RiskState` for adaptive controls:
  * post-loss Kelly scaling
  * per-strategy daily loss cap (pauses just that strategy)
  * per-strategy total exposure cap
  * per-market exposure cap and cooldown
in addition to the original portfolio-wide breakers.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from sqlalchemy import func, select

from app.config import settings
from app.database import session_scope
from app.database.models import Position, PositionStatus
from app.monitoring.logger import get_logger
from app.risk.circuit_breaker import CircuitBreaker
from app.risk.risk_state import (
    MarketRiskSnapshot,
    RiskState,
    StrategyRiskSnapshot,
)

log = get_logger(__name__)


@dataclass
class RiskDecision:
    approved: bool
    size_usd: float
    reason: str = ""
    details: dict = field(default_factory=dict)
    kelly_multiplier: float = 1.0
    strategy_snapshot: Optional[StrategyRiskSnapshot] = None
    market_snapshot: Optional[MarketRiskSnapshot] = None

    @classmethod
    def reject(cls, reason: str, **kw) -> "RiskDecision":
        return cls(False, 0.0, reason, **kw)

    @classmethod
    def approve(cls, size_usd: float, **kw) -> "RiskDecision":
        return cls(True, size_usd, "", **kw)


class RiskManager:
    def __init__(self) -> None:
        self.breaker = CircuitBreaker()
        self.state = RiskState()

    def check(
        self,
        *,
        strategy: str,
        condition_id: Optional[str],
        suggested_size_usd: float,
        edge_mispricing: float,
        edge_ev: float,
        liquidity_usd: float,
        spread: Optional[float],
        current_equity_usd: float,
        quality_score: Optional[float] = None,
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

        # --- Adaptive strategy checks -----------------------------------------
        strat = self.state.strategy_snapshot(strategy, current_equity_usd)
        if strat.paused:
            return RiskDecision.reject(strat.pause_reason, strategy_snapshot=strat)

        if current_equity_usd > 0:
            strategy_cap = current_equity_usd * settings.max_strategy_exposure_pct
            if strat.open_exposure_usd >= strategy_cap:
                return RiskDecision.reject(
                    f"strategy '{strategy}' exposure ${strat.open_exposure_usd:,.0f} "
                    f">= cap ${strategy_cap:,.0f}",
                    strategy_snapshot=strat,
                )
            room = max(0.0, strategy_cap - strat.open_exposure_usd)
            suggested_size_usd = min(suggested_size_usd, room)

        # Apply post-loss Kelly scaling
        if strat.kelly_multiplier < 1.0:
            suggested_size_usd *= strat.kelly_multiplier

        # --- Per-market checks ------------------------------------------------
        market_snap: Optional[MarketRiskSnapshot] = None
        if condition_id:
            market_snap = self.state.market_snapshot(condition_id)
            if market_snap.cooldown_active:
                return RiskDecision.reject(
                    f"market cooldown active "
                    f"({market_snap.minutes_since_close:.1f}m / "
                    f"{settings.market_cooldown_minutes}m)",
                    strategy_snapshot=strat,
                    market_snapshot=market_snap,
                )
            if current_equity_usd > 0:
                market_cap = current_equity_usd * settings.max_market_exposure_pct
                if market_snap.open_exposure_usd >= market_cap:
                    return RiskDecision.reject(
                        f"market exposure ${market_snap.open_exposure_usd:,.0f} "
                        f">= cap ${market_cap:,.0f}",
                        strategy_snapshot=strat,
                        market_snapshot=market_snap,
                    )
                market_room = max(0.0, market_cap - market_snap.open_exposure_usd)
                suggested_size_usd = min(suggested_size_usd, market_room)

        # --- Portfolio-wide checks --------------------------------------------
        exposure = self._open_exposure_usd()
        portfolio_cap = current_equity_usd * settings.max_portfolio_exposure
        if exposure + suggested_size_usd > portfolio_cap:
            room = max(0.0, portfolio_cap - exposure)
            if room <= 0:
                return RiskDecision.reject(
                    f"portfolio exposure ${exposure:,.0f}/${portfolio_cap:,.0f} — no room",
                    strategy_snapshot=strat,
                    market_snapshot=market_snap,
                )
            suggested_size_usd = min(suggested_size_usd, room)

        if suggested_size_usd <= 0:
            return RiskDecision.reject(
                "size collapsed to zero after layered caps",
                strategy_snapshot=strat,
                market_snapshot=market_snap,
            )

        open_count = self._open_position_count()
        if open_count >= settings.max_open_positions:
            return RiskDecision.reject(
                f"open positions {open_count} >= cap {settings.max_open_positions}",
                strategy_snapshot=strat,
                market_snapshot=market_snap,
            )

        verdict = self.breaker.evaluate(current_equity_usd)
        if verdict.tripped:
            return RiskDecision.reject(
                f"circuit breaker {verdict.state.value}: {verdict.reason}",
                strategy_snapshot=strat,
                market_snapshot=market_snap,
            )

        return RiskDecision.approve(
            size_usd=suggested_size_usd,
            details={
                "open_exposure_usd": exposure,
                "open_positions": open_count,
                "breaker_state": verdict.state.value,
                "drawdown_pct": verdict.drawdown_pct,
                "daily_pnl_pct": verdict.daily_pnl_pct,
                "strategy": strategy,
                "strategy_kelly_multiplier": strat.kelly_multiplier,
                "strategy_consecutive_losses": strat.consecutive_losses,
                "strategy_open_exposure": strat.open_exposure_usd,
                "market_open_exposure": (
                    market_snap.open_exposure_usd if market_snap else 0.0
                ),
                "quality_score": quality_score,
            },
            kelly_multiplier=strat.kelly_multiplier,
            strategy_snapshot=strat,
            market_snapshot=market_snap,
        )

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
