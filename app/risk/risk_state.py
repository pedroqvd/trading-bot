"""Adaptive risk state: per-strategy and per-market.

The original `RiskManager` only enforced *static* limits. After repeated losses
on a strategy, a quant operation would shrink position sizes; after a stop on
a market, it would block re-entry to avoid getting whipsawed at the same
level. Both behaviours are captured here.

State is *derived* from the persistent `Position` table — the bot is crash
safe (a restart re-derives the same state).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional, Sequence

from sqlalchemy import desc, func, select

from app.config import settings
from app.database import session_scope
from app.database.models import Market, Position, PositionStatus
from app.utils.time_utils import utcnow


def _aware(dt: Optional[datetime]) -> Optional[datetime]:
    """Return `dt` with UTC tz attached if it was naive (e.g. coming from SQLite)."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        from datetime import timezone
        return dt.replace(tzinfo=timezone.utc)
    return dt


@dataclass(frozen=True)
class StrategyRiskSnapshot:
    strategy: str
    open_exposure_usd: float
    open_positions: int
    daily_pnl_usd: float
    consecutive_losses: int
    consecutive_wins: int
    paused: bool
    pause_reason: str
    kelly_multiplier: float


@dataclass(frozen=True)
class MarketRiskSnapshot:
    condition_id: str
    open_exposure_usd: float
    last_close_at: Optional[datetime]
    minutes_since_close: Optional[float]
    cooldown_active: bool


class RiskState:
    """Read-only views over the database used by `RiskManager`."""

    # -----------------------------------------------------------------------
    # Strategy-level
    # -----------------------------------------------------------------------
    def strategy_snapshot(self, strategy: str, equity_usd: float) -> StrategyRiskSnapshot:
        with session_scope() as session:
            open_exposure = session.execute(
                select(func.coalesce(func.sum(Position.entry_size_usd), 0.0))
                .where(Position.status == PositionStatus.OPEN, Position.strategy == strategy)
            ).scalar_one() or 0.0

            open_positions = session.execute(
                select(func.count(Position.id))
                .where(Position.status == PositionStatus.OPEN, Position.strategy == strategy)
            ).scalar_one() or 0

            recent = session.execute(
                select(Position)
                .where(
                    Position.strategy == strategy,
                    Position.status != PositionStatus.OPEN,
                    Position.realized_pnl_usd.is_not(None),
                )
                .order_by(desc(Position.closed_at))
                .limit(50)
            ).scalars().all()
            session.expunge_all()

        # Compute daily PnL in Python so the filter is tz-aware regardless of backend.
        today_start = utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        daily_pnl = sum(
            float(p.realized_pnl_usd or 0.0)
            for p in recent
            if _aware(p.closed_at) is not None and _aware(p.closed_at) >= today_start
        )

        consecutive_losses = self._count_streak(recent, kind="loss")
        consecutive_wins = self._count_streak(recent, kind="win")
        kelly_multiplier = self._kelly_multiplier(consecutive_losses, consecutive_wins)
        paused, reason = self._strategy_paused(daily_pnl, equity_usd, consecutive_losses)

        return StrategyRiskSnapshot(
            strategy=strategy,
            open_exposure_usd=float(open_exposure),
            open_positions=int(open_positions),
            daily_pnl_usd=float(daily_pnl),
            consecutive_losses=consecutive_losses,
            consecutive_wins=consecutive_wins,
            paused=paused,
            pause_reason=reason,
            kelly_multiplier=kelly_multiplier,
        )

    @staticmethod
    def _count_streak(positions: Sequence[Position], *, kind: str) -> int:
        streak = 0
        for p in positions:
            pnl = float(p.realized_pnl_usd or 0.0)
            if kind == "loss":
                if pnl < 0:
                    streak += 1
                else:
                    break
            else:
                if pnl > 0:
                    streak += 1
                else:
                    break
        return streak

    @staticmethod
    def _kelly_multiplier(consecutive_losses: int, consecutive_wins: int) -> float:
        # If we've had a fresh win after the recovery threshold, restore full size.
        if consecutive_wins >= settings.loss_streak_recovery_trades:
            return 1.0
        if consecutive_losses >= settings.loss_streak_hard_threshold:
            return 0.25
        if consecutive_losses >= settings.loss_streak_soft_threshold:
            return 0.5
        return 1.0

    @staticmethod
    def _strategy_paused(daily_pnl: float, equity_usd: float, losses: int) -> tuple[bool, str]:
        if equity_usd <= 0:
            return False, ""
        cap = -abs(equity_usd * settings.daily_strategy_loss_cap_pct)
        if daily_pnl <= cap:
            return True, (
                f"daily PnL ${daily_pnl:,.2f} ≤ cap ${cap:,.2f}; strategy paused for the day"
            )
        return False, ""

    # -----------------------------------------------------------------------
    # Market-level
    # -----------------------------------------------------------------------
    def market_snapshot(self, condition_id: str) -> MarketRiskSnapshot:
        with session_scope() as session:
            market = session.execute(
                select(Market).where(Market.condition_id == condition_id)
            ).scalar_one_or_none()
            if market is None:
                return MarketRiskSnapshot(condition_id, 0.0, None, None, False)

            open_exposure = session.execute(
                select(func.coalesce(func.sum(Position.entry_size_usd), 0.0))
                .where(Position.status == PositionStatus.OPEN, Position.market_id == market.id)
            ).scalar_one() or 0.0

            last_close = session.execute(
                select(func.max(Position.closed_at))
                .where(Position.market_id == market.id, Position.status != PositionStatus.OPEN)
            ).scalar_one()

        minutes_since = None
        cooldown_active = False
        last_close_aware = _aware(last_close)
        if last_close_aware is not None:
            minutes_since = (utcnow() - last_close_aware).total_seconds() / 60.0
            cooldown_active = minutes_since < settings.market_cooldown_minutes

        return MarketRiskSnapshot(
            condition_id=condition_id,
            open_exposure_usd=float(open_exposure),
            last_close_at=last_close_aware,
            minutes_since_close=minutes_since,
            cooldown_active=cooldown_active,
        )
