from app.utils.math_utils import (
    EdgeSnapshot,
    expected_value,
    fractional_kelly,
    kelly_fraction,
    mispricing,
    slippage_adjust,
)


def test_mispricing_signs():
    assert abs(mispricing(0.6, 0.5) - 0.1) < 1e-9
    assert abs(mispricing(0.4, 0.5) - (-0.1)) < 1e-9


def test_expected_value_matches_closed_form():
    ev = expected_value(0.7, 0.5)
    # p*(1-price) - (1-p)*price = 0.7*0.5 - 0.3*0.5 = 0.2 = p - price
    assert abs(ev - 0.2) < 1e-9


def test_expected_value_zero_at_fair_price():
    assert abs(expected_value(0.5, 0.5)) < 1e-12


def test_kelly_no_edge_is_zero():
    assert kelly_fraction(0.5, 0.5) == 0.0
    assert kelly_fraction(0.4, 0.5) == 0.0


def test_kelly_with_edge():
    # f* = (p - price) / (1 - price) = 0.1 / 0.5 = 0.2
    assert abs(kelly_fraction(0.6, 0.5) - 0.2) < 1e-9


def test_fractional_kelly_scaled():
    assert abs(fractional_kelly(0.6, 0.5, 0.25) - 0.05) < 1e-9


def test_slippage_adjust_bounds():
    assert slippage_adjust(0.50, "BUY", 100) > 0.50
    assert slippage_adjust(0.50, "SELL", 100) < 0.50
    # slippage cannot push price above 1
    assert slippage_adjust(0.999, "BUY", 100000) <= 1.0


def test_edge_snapshot_builds_consistent():
    snap = EdgeSnapshot.build(prob_real=0.65, price=0.5, kelly_mult=0.25)
    assert snap.prob_market == 0.5
    assert abs(snap.mispricing - 0.15) < 1e-9
    assert snap.ev > 0
    assert snap.kelly > 0
