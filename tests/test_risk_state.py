"""Tests for adaptive RiskState behaviour."""
from datetime import timedelta

from app.config import settings
from app.database import session_scope
from app.database.models import Market, Position, PositionStatus, Side
from app.risk.risk_state import RiskState
from app.utils.time_utils import utcnow


def _seed_market(condition_id: str = "0xabc") -> int:
    with session_scope() as session:
        m = Market(
            condition_id=condition_id, slug="seed", question="q",
            yes_token_id="1", no_token_id="2",
        )
        session.add(m)
        session.flush()
        return m.id


def _seed_closed_position(strategy: str, pnl: float, market_id: int, *, days_ago: float = 0.1):
    closed_at = utcnow() - timedelta(days=days_ago)
    with session_scope() as session:
        session.add(Position(
            market_id=market_id, strategy=strategy, side=Side.YES,
            status=PositionStatus.CLOSED,
            entry_price=0.5, entry_size_usd=10, shares=20,
            exit_price=0.5, realized_pnl_usd=pnl,
            opened_at=closed_at - timedelta(minutes=10),
            closed_at=closed_at,
        ))


def test_no_streak_returns_full_kelly_multiplier():
    market_id = _seed_market()
    _seed_closed_position("overreaction", pnl=5.0, market_id=market_id)
    snap = RiskState().strategy_snapshot("overreaction", equity_usd=1000)
    assert snap.kelly_multiplier == 1.0
    assert snap.consecutive_losses == 0


def test_loss_streak_halves_kelly_at_soft_threshold():
    market_id = _seed_market()
    for i in range(settings.loss_streak_soft_threshold):
        _seed_closed_position("overreaction", pnl=-2.0, market_id=market_id, days_ago=0.01 * (i + 1))
    snap = RiskState().strategy_snapshot("overreaction", equity_usd=1000)
    assert snap.consecutive_losses >= settings.loss_streak_soft_threshold
    assert snap.kelly_multiplier == 0.5


def test_loss_streak_quarters_kelly_at_hard_threshold():
    market_id = _seed_market()
    for i in range(settings.loss_streak_hard_threshold):
        _seed_closed_position("overreaction", pnl=-2.0, market_id=market_id, days_ago=0.01 * (i + 1))
    snap = RiskState().strategy_snapshot("overreaction", equity_usd=1000)
    assert snap.kelly_multiplier == 0.25


def test_recovery_after_consecutive_wins_resets_kelly():
    market_id = _seed_market()
    # Three losses
    for i in range(3):
        _seed_closed_position("overreaction", pnl=-2.0, market_id=market_id, days_ago=0.10 - 0.01 * i)
    # Then recovery wins
    for i in range(settings.loss_streak_recovery_trades):
        _seed_closed_position("overreaction", pnl=5.0, market_id=market_id, days_ago=0.05 - 0.01 * i)
    snap = RiskState().strategy_snapshot("overreaction", equity_usd=1000)
    assert snap.kelly_multiplier == 1.0


def test_daily_loss_cap_pauses_strategy():
    market_id = _seed_market()
    big_loss = -1000 * settings.daily_strategy_loss_cap_pct - 1.0
    # closed-at within seconds of now so it is definitely "today" regardless of UTC time
    _seed_closed_position("overreaction", pnl=big_loss, market_id=market_id, days_ago=0.0001)
    snap = RiskState().strategy_snapshot("overreaction", equity_usd=1000)
    assert snap.paused
    assert "paused" in snap.pause_reason.lower()


def test_market_cooldown_active_after_recent_close():
    market_id = _seed_market("0xrecent")
    _seed_closed_position("overreaction", pnl=-1.0, market_id=market_id, days_ago=0.001)
    snap = RiskState().market_snapshot("0xrecent")
    assert snap.cooldown_active


def test_market_cooldown_expires():
    market_id = _seed_market("0xold")
    # Closed long enough ago that cooldown is over
    long_ago = (settings.market_cooldown_minutes / (24 * 60)) + 0.1
    _seed_closed_position("overreaction", pnl=-1.0, market_id=market_id, days_ago=long_ago)
    snap = RiskState().market_snapshot("0xold")
    assert not snap.cooldown_active
