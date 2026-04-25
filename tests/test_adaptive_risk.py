"""Tests for vol-adaptive sizing and recovery mode."""
from datetime import timedelta

from app.config import settings
from app.database import session_scope
from app.database.models import Market, Position, PositionStatus, Side
from app.risk.adaptive_risk import (
    combined_adjustment,
    recovery_mode_multiplier,
    vol_adaptive_multiplier,
)
from app.utils.time_utils import utcnow


def test_vol_multiplier_full_at_low_vol():
    assert vol_adaptive_multiplier(0.0) == 1.0
    assert vol_adaptive_multiplier(settings.vol_adaptive_low / 2) == 1.0


def test_vol_multiplier_floor_at_high_vol():
    assert vol_adaptive_multiplier(settings.vol_adaptive_high * 2) == settings.vol_adaptive_floor


def test_vol_multiplier_monotonic_in_band():
    lo = vol_adaptive_multiplier(settings.vol_adaptive_low + 0.001)
    mid = vol_adaptive_multiplier(
        (settings.vol_adaptive_low + settings.vol_adaptive_high) / 2,
    )
    hi = vol_adaptive_multiplier(settings.vol_adaptive_high - 0.001)
    assert lo > mid > hi


def _seed_consecutive_losses(strategy: str, n: int) -> None:
    with session_scope() as session:
        m = Market(condition_id="0xm", slug="s", question="q",
                   yes_token_id="1", no_token_id="2")
        session.add(m)
        session.flush()
        for i in range(n):
            session.add(Position(
                market_id=m.id, strategy=strategy, side=Side.YES,
                status=PositionStatus.CLOSED,
                entry_price=0.5, entry_size_usd=10, shares=20,
                exit_price=0.4, realized_pnl_usd=-2.0,
                opened_at=utcnow() - timedelta(minutes=20 + i),
                closed_at=utcnow() - timedelta(minutes=10 + i),
            ))


def test_recovery_mode_triggers_on_deep_streak():
    _seed_consecutive_losses("overreaction", settings.recovery_mode_loss_threshold)
    assert recovery_mode_multiplier() == settings.recovery_mode_kelly_multiplier


def test_recovery_mode_does_not_trigger_below_threshold():
    _seed_consecutive_losses("overreaction", settings.recovery_mode_loss_threshold - 1)
    assert recovery_mode_multiplier() == 1.0


def test_combined_adjustment_aggregates_multipliers():
    _seed_consecutive_losses("overreaction", settings.recovery_mode_loss_threshold)
    adj = combined_adjustment(realized_vol=settings.vol_adaptive_high)
    # Both vol-adaptive AND recovery should fire
    assert adj.multiplier <= settings.vol_adaptive_floor * settings.recovery_mode_kelly_multiplier + 1e-6
    assert any("vol_adaptive" in n for n in adj.notes)
    assert any("recovery_mode" in n for n in adj.notes)
