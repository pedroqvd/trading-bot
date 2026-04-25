from app.data.market_analytics import MarketFeatures
from app.signals.prob_real import bayesian_prob_real
from app.signals.quality import OverreactionScore


def _features(anchor=0.50, current=0.40, vol=0.02) -> MarketFeatures:
    return MarketFeatures(
        window_minutes=15, ticks=10,
        anchor_mid=anchor, current_mid=current,
        abs_move=current - anchor, rel_move=(current - anchor) / anchor,
        velocity=-0.012, spike_ratio=0.8, persistence=0.4,
        realized_vol=vol, volume_z=2.0, avg_spread=0.01,
    )


def _score(s: float) -> OverreactionScore:
    return OverreactionScore(score=s, magnitude=0, velocity=0, volume=0, spike=0,
                             persistence_penalty=0, vol_penalty=0)


def test_high_score_pulls_estimate_toward_anchor():
    f = _features(anchor=0.60, current=0.40)
    estimate = bayesian_prob_real(f, _score(1.0), base_reversion=0.5)
    # 1.0 score × 0.5 reversion → halfway between anchor (0.60) and current (0.40)
    assert estimate.prob_real_yes_mid > 0.46
    assert estimate.prob_real_yes_mid < 0.55


def test_zero_score_keeps_estimate_at_current():
    f = _features(anchor=0.60, current=0.40)
    estimate = bayesian_prob_real(f, _score(0.0), base_reversion=0.5)
    # No score → no reversion → posterior near current.
    assert abs(estimate.prob_real_yes_mid - 0.40) < 0.05


def test_high_vol_pulls_toward_one_half():
    f = _features(anchor=0.95, current=0.85, vol=0.30)
    estimate = bayesian_prob_real(f, _score(0.8), base_reversion=0.5)
    # The vol-driven mean pull should drag the estimate down toward 0.5,
    # well below the naive 0.5×anchor + 0.5×current = 0.90.
    assert estimate.prob_real_yes_mid < 0.90
    assert estimate.weight_mean > 0.0


def test_estimate_bounded_in_unit_interval():
    f = _features(anchor=0.999, current=0.001)
    estimate = bayesian_prob_real(f, _score(1.0), base_reversion=1.0)
    assert 0.01 <= estimate.prob_real_yes_mid <= 0.99
