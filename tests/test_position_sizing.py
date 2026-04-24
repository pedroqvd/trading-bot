from app.config import settings
from app.risk.position_sizing import suggested_size_usd


def test_sizing_respects_max_position_cap():
    # High edge: prob_real=0.9, price=0.3 → huge Kelly fraction
    size = suggested_size_usd(prob_real=0.9, price=0.3, capital_usd=10_000, liquidity_usd=1_000_000)
    assert size <= 10_000 * settings.max_position_pct + 1e-6


def test_sizing_respects_liquidity_cap():
    size = suggested_size_usd(prob_real=0.9, price=0.3, capital_usd=10_000, liquidity_usd=100)
    # 25% of 100 = 25; should not exceed that
    assert size <= 25 + 1e-6


def test_sizing_zero_without_edge():
    assert suggested_size_usd(prob_real=0.3, price=0.5, capital_usd=10_000, liquidity_usd=1_000_000) == 0.0
