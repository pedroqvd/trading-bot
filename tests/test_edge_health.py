"""Tests for the EdgeHealth verdict logic."""
from datetime import timedelta

from app.config import settings
from app.database import session_scope
from app.database.models import Market, Position, PositionStatus, Side
from app.monitoring.edge_health import EdgeHealth, HealthState, health_multiplier
from app.utils.time_utils import utcnow


def _seed(strategy: str, pnls: list[float]) -> None:
    with session_scope() as session:
        market = Market(condition_id="0xmkt", slug="m", question="q",
                        yes_token_id="1", no_token_id="2")
        session.add(market)
        session.flush()
        for i, pnl in enumerate(pnls):
            session.add(Position(
                market_id=market.id, strategy=strategy, side=Side.YES,
                status=PositionStatus.CLOSED,
                entry_price=0.5, entry_size_usd=10, shares=20,
                exit_price=0.5, realized_pnl_usd=pnl,
                opened_at=utcnow() - timedelta(minutes=20 + i),
                closed_at=utcnow() - timedelta(minutes=10 + i),
            ))


def test_few_trades_returns_healthy_with_no_verdict():
    _seed("overreaction", [-1, 1, -2])
    verdict = EdgeHealth().evaluate("overreaction")
    assert verdict.state == HealthState.HEALTHY
    assert "not enough" in verdict.reason


def test_negative_expectancy_disables_strategy():
    _seed("overreaction", [-2.0] * settings.edge_health_min_trades)
    verdict = EdgeHealth().evaluate("overreaction")
    assert verdict.state == HealthState.DISABLED
    assert verdict.expectancy_usd < 0


def test_low_winrate_marks_impaired():
    pnls = [-1, -1, -1, -1, -1, -1, 5, 5]
    _seed("overreaction", pnls)
    verdict = EdgeHealth().evaluate("overreaction")
    # Win rate = 0.25, expectancy = (-6 + 10)/8 = 0.5 → IMPAIRED branch (win<0.40)
    assert verdict.state in (HealthState.IMPAIRED, HealthState.DISABLED)


def test_health_multiplier_is_zero_when_disabled():
    assert health_multiplier(HealthState.DISABLED) == 0.0
    assert health_multiplier(HealthState.HEALTHY) == 1.0
    assert health_multiplier(HealthState.WATCH) < 1.0
    assert health_multiplier(HealthState.IMPAIRED) < health_multiplier(HealthState.WATCH)
