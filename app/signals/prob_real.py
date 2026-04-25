"""Bayesian prob_real estimator.

The previous version computed a static `yes_mid - 0.5 * move` reversion target.
That's a hard-coded prior without any notion of confidence.

Here we build the estimate as a weighted combination:

    prob_real = w_anchor * anchor + w_current * current + w_mean * 0.5

- `w_anchor` dominates when the overreaction score is high (we trust reversion).
- `w_current` dominates when the score is low (no edge → no trade).
- `w_mean`   pulls toward 0.5 proportional to realised volatility
             (high-vol markets mean-revert toward the prior of the prior).

The output is converted to the *side we are buying* by the caller.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.data.market_analytics import MarketFeatures
from app.signals.quality import OverreactionScore
from app.utils.math_utils import clamp


@dataclass(frozen=True)
class ProbRealEstimate:
    prob_real_yes_mid: float   # posterior estimate of the fair YES price
    weight_anchor: float
    weight_current: float
    weight_mean: float


def bayesian_prob_real(
    features: MarketFeatures,
    score: OverreactionScore,
    base_reversion: float,
) -> ProbRealEstimate:
    """Posterior fair-value estimate of YES mid.

    * `base_reversion` is the configured *maximum* reversion fraction (e.g. 0.5
      means even a perfect-score overreaction only reverts halfway by our prior).
    * `score` shrinks the reversion weight when confidence is low.
    * High realised vol adds a pull toward 0.5, our prior on "we have no idea".
    """
    anchor = clamp(features.anchor_mid, 0.01, 0.99)
    current = clamp(features.current_mid, 0.01, 0.99)

    # Reversion weight scales with score: at score=1.0 we take `base_reversion` of
    # the way back to anchor; at score=0 we stay at current.
    reversion_weight = clamp(score.score * base_reversion, 0.0, 1.0)

    # Vol-driven pull toward 0.5 (prior ignorance). Cap at 0.15 so it never drowns
    # out the anchor signal.
    vol_pull = min(0.15, features.realized_vol)  # realized_vol already in (0, 1)

    w_anchor = reversion_weight * (1 - vol_pull)
    w_mean = vol_pull
    w_current = max(0.0, 1 - w_anchor - w_mean)

    posterior_yes = w_anchor * anchor + w_current * current + w_mean * 0.5
    return ProbRealEstimate(
        prob_real_yes_mid=clamp(posterior_yes, 0.01, 0.99),
        weight_anchor=w_anchor,
        weight_current=w_current,
        weight_mean=w_mean,
    )
