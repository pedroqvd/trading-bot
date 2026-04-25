"""Tests for the overreaction quality score and hard filters."""
from app.config import settings
from app.data.market_analytics import MarketFeatures
from app.signals.quality import overreaction_hard_filters_pass, overreaction_score


def _features(**kw) -> MarketFeatures:
    base = dict(
        window_minutes=15,
        ticks=10,
        anchor_mid=0.50,
        current_mid=0.40,
        abs_move=-0.10,
        rel_move=-0.20,
        velocity=-0.012,
        spike_ratio=0.80,
        persistence=0.4,
        realized_vol=0.02,
        volume_z=2.0,
        avg_spread=0.01,
    )
    base.update(kw)
    return MarketFeatures(**base)


def test_score_high_for_textbook_overreaction():
    f = _features()
    score = overreaction_score(f)
    assert score.score >= settings.overreaction_min_score
    assert score.passes_filter


def test_score_dampened_by_high_persistence():
    """A monotonic trend (persistence ≈ 1) should not trigger even with the same magnitude."""
    f = _features(persistence=1.0, spike_ratio=0.2)
    score = overreaction_score(f)
    assert not score.passes_filter


def test_score_dampened_by_high_realized_vol():
    f = _features(realized_vol=0.20)
    score = overreaction_score(f)
    # vol penalty saturates above the configured ceiling, so the score collapses
    assert score.score < settings.overreaction_min_score


def test_score_low_when_volume_is_normal():
    f = _features(volume_z=-0.5)
    score = overreaction_score(f)
    assert score.score < settings.overreaction_min_score


def test_hard_filters_reject_small_moves():
    f = _features(rel_move=0.02)
    ok, reason = overreaction_hard_filters_pass(f)
    assert not ok
    assert "below threshold" in reason


def test_hard_filters_reject_low_volume_z():
    f = _features(volume_z=0.2)
    ok, reason = overreaction_hard_filters_pass(f)
    assert not ok
    assert "volume z" in reason


def test_hard_filters_reject_trends():
    f = _features(spike_ratio=0.20)
    ok, reason = overreaction_hard_filters_pass(f)
    assert not ok
    assert "spike ratio" in reason
