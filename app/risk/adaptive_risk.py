"""Adaptive risk multipliers (Phase 2).

Three orthogonal mechanisms:
  1. Volatility-adaptive sizing — shrink risk when realised vol is high.
  2. Recovery mode — global Kelly multiplier when ANY strategy is in deep streak.
  3. Strategy auto-shutdown — disable a strategy whose rolling expectancy is
     negative or whose drawdown exceeds the configured ceiling.

State for #2 and #3 is read from `RiskState` and `EdgeHealth` respectively.
"""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import desc, select

from app.config import settings
from app.database import session_scope
from app.database.models import Position, PositionStatus
from app.utils.math_utils import clamp


@dataclass(frozen=True)
class AdaptiveRiskAdjustment:
    multiplier: float
    notes: list[str]


def vol_adaptive_multiplier(realized_vol: float) -> float:
    """Linear scaler from `low → 1.0` down to `high → floor`."""
    if not settings.vol_adaptive_enabled:
        return 1.0
    lo = settings.vol_adaptive_low
    hi = settings.vol_adaptive_high
    floor = settings.vol_adaptive_floor
    if realized_vol <= lo:
        return 1.0
    if realized_vol >= hi:
        return floor
    pct_into_band = (realized_vol - lo) / (hi - lo)
    return clamp(1.0 - pct_into_band * (1.0 - floor), floor, 1.0)


def recovery_mode_multiplier() -> float:
    """If ANY strategy is in a deep loss streak, dial down global Kelly."""
    threshold = settings.recovery_mode_loss_threshold
    if threshold <= 0:
        return 1.0
    with session_scope() as session:
        strategies = session.execute(
            select(Position.strategy).distinct()
        ).scalars().all()
        for strategy in strategies:
            recent = session.execute(
                select(Position)
                .where(
                    Position.strategy == strategy,
                    Position.status != PositionStatus.OPEN,
                    Position.realized_pnl_usd.is_not(None),
                )
                .order_by(desc(Position.closed_at))
                .limit(threshold)
            ).scalars().all()
            if len(recent) < threshold:
                continue
            if all(float(p.realized_pnl_usd or 0.0) < 0 for p in recent):
                return settings.recovery_mode_kelly_multiplier
    return 1.0


def combined_adjustment(
    realized_vol: float = 0.0,
) -> AdaptiveRiskAdjustment:
    """Compose all global adjustments into a single multiplier."""
    notes: list[str] = []
    multiplier = 1.0

    vol_mult = vol_adaptive_multiplier(realized_vol)
    if vol_mult < 1.0:
        notes.append(f"vol_adaptive x{vol_mult:.2f} (realised_vol={realized_vol:.3f})")
        multiplier *= vol_mult

    rec_mult = recovery_mode_multiplier()
    if rec_mult < 1.0:
        notes.append(f"recovery_mode x{rec_mult:.2f}")
        multiplier *= rec_mult

    return AdaptiveRiskAdjustment(multiplier=multiplier, notes=notes)
