"""End-to-end tests for the FastAPI surface."""
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from app.api.app import create_app
from app.database import session_scope
from app.database.models import EquitySnapshot, Market, Position, PositionStatus, Side
from app.utils.time_utils import utcnow


@pytest.fixture
def client():
    return TestClient(create_app())


def _seed_basic_state():
    with session_scope() as session:
        market = Market(condition_id="0xapi", slug="api-test",
                        question="API test market",
                        yes_token_id="1", no_token_id="2")
        session.add(market)
        session.flush()
        # Closed winning trade
        session.add(Position(
            market_id=market.id, strategy="overreaction", side=Side.YES,
            status=PositionStatus.CLOSED,
            entry_price=0.4, entry_size_usd=40, shares=100,
            exit_price=0.5, realized_pnl_usd=10.0,
            opened_at=utcnow() - timedelta(minutes=30),
            closed_at=utcnow() - timedelta(minutes=10),
        ))
        # Open trade
        session.add(Position(
            market_id=market.id, strategy="momentum", side=Side.NO,
            status=PositionStatus.OPEN,
            entry_price=0.6, entry_size_usd=30, shares=50,
            opened_at=utcnow() - timedelta(minutes=5),
        ))
        # Equity snapshot
        session.add(EquitySnapshot(
            cash_usd=970.0, unrealized_usd=0.0, equity_usd=1010.0,
            realized_today_usd=10.0, open_positions=1,
        ))


def test_health_endpoint(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_metrics_endpoint_with_seed(client):
    _seed_basic_state()
    r = client.get("/metrics?period=24h")
    assert r.status_code == 200
    body = r.json()
    assert body["period"] == "24h"
    assert body["equity_usd"] == 1010.0
    assert body["open_positions"] == 1
    assert isinstance(body["by_strategy"], list)


def test_metrics_endpoint_period_validation(client):
    r = client.get("/metrics?period=42x")
    assert r.status_code == 422  # FastAPI rejects values outside the Literal


def test_equity_endpoint(client):
    _seed_basic_state()
    r = client.get("/equity?period=24h")
    assert r.status_code == 200
    body = r.json()
    assert body["period"] == "24h"
    assert len(body["points"]) >= 1
    assert body["points"][0]["equity"] == 1010.0


def test_positions_endpoint_filter(client):
    _seed_basic_state()
    r = client.get("/positions?status=open")
    assert r.status_code == 200
    rows = r.json()
    assert len(rows) == 1
    assert rows[0]["status"] == "OPEN"


def test_bot_status_endpoint(client):
    _seed_basic_state()
    r = client.get("/bot/status")
    assert r.status_code == 200
    body = r.json()
    # No runner started in tests → not running, but reads the latest snapshot
    assert body["running"] is False
    assert body["equity_usd"] == 1010.0
    assert body["dry_run"] is True


def test_bot_start_stop_cycle_safely(client, monkeypatch):
    """Verify start/stop don't actually launch the runner during tests."""
    from app.api.runner_proxy import get_runner_proxy
    proxy = get_runner_proxy()
    monkeypatch.setattr(proxy, "start", lambda: True)
    monkeypatch.setattr(proxy, "stop", lambda timeout=10.0: True)
    # Not actually starting the trading runner — just verifying the route shape.
    r = client.post("/bot/start")
    assert r.status_code == 200
    assert r.json()["running"] is True
