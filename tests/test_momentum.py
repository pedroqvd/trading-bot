"""Tests for the momentum scoring + mutual exclusion."""
from app.config import settings
from app.data.market_analytics import MarketFeatures
from app.signals.prob_real import bayesian_prob_real_momentum
from app.signals.quality import (
    momentum_hard_filters_pass,
    momentum_score,
    overreaction_score,
)


def _features(**kw) -> MarketFeatures:
    base = dict(
        window_minutes=30,
        ticks=12,
        anchor_mid=0.30,
        current_mid=0.45,
        abs_move=0.15,
        rel_move=0.50,
        velocity=0.008,        # 0.8 %/min
        spike_ratio=0.20,      # not a spike — distributed move
        persistence=0.85,      # strongly directional
        realized_vol=0.02,
        volume_z=2.0,
        avg_spread=0.005,
        spread_volatility=0.002,
        trend_strength=0.42,
        mean_reversion_signal=0.05,
    )
    base.update(kw)
    return MarketFeatures(**base)


def test_momentum_score_high_for_clean_trend():
    f = _features()
    s = momentum_score(f)
    assert s.score >= settings.momentum_min_score
    assert s.passes_filter


def test_momentum_score_low_when_persistence_low():
    f = _features(persistence=0.3, mean_reversion_signal=0.4)
    s = momentum_score(f)
    assert not s.passes_filter


def test_momentum_score_low_when_volatile():
    f = _features(realized_vol=0.20)
    s = momentum_score(f)
    assert not s.passes_filter


def test_momentum_score_low_when_spread_unstable():
    f = _features(spread_volatility=0.05)
    s = momentum_score(f)
    # spread_stability collapses; vol_penalty kicks in via low_reversion etc.
    assert s.score < settings.momentum_min_score


def test_momentum_hard_filters_reject_low_persistence():
    f = _features(persistence=0.4)
    ok, reason = momentum_hard_filters_pass(f)
    assert not ok
    assert "persistence" in reason


def test_momentum_hard_filters_reject_unstable_spread():
    f = _features(spread_volatility=0.05)
    ok, reason = momentum_hard_filters_pass(f)
    assert not ok
    assert "spread" in reason


def test_overreaction_and_momentum_are_mutually_exclusive_in_practice():
    """A textbook overreaction (sharp spike) must NOT pass momentum filters."""
    spike_features = MarketFeatures(
        window_minutes=15, ticks=12, anchor_mid=0.50, current_mid=0.40,
        abs_move=-0.10, rel_move=-0.20, velocity=-0.012,
        spike_ratio=0.85, persistence=0.30, realized_vol=0.02,
        volume_z=2.0, avg_spread=0.01,
        spread_volatility=0.002, trend_strength=0.20,
        mean_reversion_signal=0.40,
    )
    o = overreaction_score(spike_features)
    m = momentum_score(spike_features)
    assert o.score > m.score
    assert not m.passes_filter


def test_momentum_prob_real_extrapolates_in_trend_direction():
    f = _features()  # +50% rel_move, current 0.45
    s = momentum_score(f)
    est = bayesian_prob_real_momentum(f, s)
    # Continuation projects upward from 0.45 toward 0.45 + 0.5*move (0.075)
    assert est.prob_real_yes_mid > f.current_mid
    assert est.confidence > 0
