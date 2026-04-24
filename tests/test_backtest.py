from datetime import datetime, timedelta, timezone

from backtest.engine import BacktestEngine, HistoricalTick


def _tick(ts, ya, nb, na, yb=None):
    yb = yb if yb is not None else ya - 0.01
    return HistoricalTick(
        ts=ts,
        condition_id="c1",
        slug="s",
        question="q",
        yes_token_id="1",
        no_token_id="2",
        yes_bid=yb,
        yes_ask=ya,
        no_bid=nb,
        no_ask=na,
        volume_24h=100000,
        depth_usd=5000,
    )


def test_arbitrage_path_produces_profit():
    t0 = datetime(2025, 1, 1, tzinfo=timezone.utc)
    # yes+no asks = 0.44+0.45 = 0.89 → riskless arb worth 0.11 per bond
    ticks = [_tick(t0 + timedelta(minutes=i), ya=0.45, nb=0.44, na=0.45, yb=0.44)
             for i in range(5)]
    engine = BacktestEngine(ticks, initial_capital=1_000)
    rep = engine.run()
    assert rep.trades >= 1
    assert rep.total_pnl_usd > 0


def test_no_trades_when_no_edge():
    t0 = datetime(2025, 1, 1, tzinfo=timezone.utc)
    ticks = [_tick(t0 + timedelta(minutes=i), ya=0.51, nb=0.49, na=0.50, yb=0.50)
             for i in range(20)]
    engine = BacktestEngine(ticks, initial_capital=1_000)
    rep = engine.run()
    assert rep.trades == 0
