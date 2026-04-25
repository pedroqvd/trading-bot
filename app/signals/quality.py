"""Composite quality scores used to gate signal emission.

Both scores return a number in `[0, 1]`. The detector layer *never* emits a
candidate with score below the configured floor, which is how we eliminate the
long tail of borderline trades.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from app.config import settings
from app.data.market_analytics import MarketFeatures


def _logistic(x: float, midpoint: float = 0.0, slope: float = 1.0) -> float:
    return 1.0 / (1.0 + math.exp(-slope * (x - midpoint)))


def _saturate(x: float, cap: float) -> float:
    return max(0.0, min(1.0, x / cap)) if cap > 0 else 0.0


@dataclass(frozen=True)
class OverreactionScore:
    score: float
    magnitude: float
    velocity: float
    volume: float
    spike: float
    persistence_penalty: float
    vol_penalty: float

    @property
    def passes_filter(self) -> bool:
        return self.score >= settings.overreaction_min_score


def overreaction_score(f: MarketFeatures) -> OverreactionScore:
    """Compose sub-scores into an aggregate overreaction confidence.

    Design intent:
    - We want to *fade* sharp, fast, high-volume moves (spikes).
    - We want to avoid fading trends: smooth monotonic climbs / declines.
    - We want to avoid noise: movements well within realised volatility.
    """
    mag = _saturate(abs(f.rel_move), 0.25)                 # saturates at a 25% move
    vel = _saturate(abs(f.velocity), 0.01)                 # saturates at 1%/min
    # Volume z: logistic centred at 0.5 so z≈2 ≈ 0.82 and z≈0 ≈ 0.38.
    vol = _logistic(f.volume_z, midpoint=0.5, slope=1.5)
    spike = min(1.0, max(0.0, f.spike_ratio))

    # Trend penalty: monotonic moves (persistence close to 1) *aren't* overreactions.
    # We tolerate persistence up to 0.6; beyond that we dampen aggressively.
    persistence_penalty = _saturate(max(0.0, f.persistence - 0.6), 0.4)

    # Vol penalty: if realised vol is already high, a big move isn't statistically
    # surprising — fading it has no edge. Penalty saturates near max_realized_vol.
    vol_penalty = _saturate(f.realized_vol, settings.overreaction_max_realized_vol)

    weights = (0.30, 0.20, 0.25, 0.25)  # (mag, vel, vol, spike)
    raw = weights[0] * mag + weights[1] * vel + weights[2] * vol + weights[3] * spike
    penalised = raw * (1.0 - 0.4 * persistence_penalty) * (1.0 - 0.35 * vol_penalty)
    return OverreactionScore(
        score=max(0.0, min(1.0, penalised)),
        magnitude=mag,
        velocity=vel,
        volume=vol,
        spike=spike,
        persistence_penalty=persistence_penalty,
        vol_penalty=vol_penalty,
    )


def overreaction_hard_filters_pass(f: MarketFeatures) -> tuple[bool, str]:
    """Non-negotiable thresholds. Returns (ok, reason_if_not_ok)."""
    if f.ticks < settings.overreaction_min_ticks:
        return False, f"need >={settings.overreaction_min_ticks} ticks, have {f.ticks}"
    if abs(f.rel_move) < settings.overreaction_move_pct:
        return False, f"move {f.rel_move:.2%} below threshold"
    if abs(f.velocity) < settings.overreaction_min_velocity_pct_per_min:
        return False, f"velocity {f.velocity:.3%}/min below threshold"
    if f.volume_z < settings.overreaction_min_volume_z:
        return False, f"volume z {f.volume_z:.2f} below threshold"
    if f.spike_ratio < settings.overreaction_min_spike_ratio:
        return False, f"spike ratio {f.spike_ratio:.2f} below threshold (likely trend)"
    if f.realized_vol > settings.overreaction_max_realized_vol:
        return False, f"realised vol {f.realized_vol:.2%} too high"
    return True, ""
