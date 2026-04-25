"""Overreaction edge: fade rapid moves, but only when the *shape* of the move
matches the hypothesis.

Hypothesis (refined from the original playbook):
  Sharp, fast, high-volume, single-tick-spike moves on prices in (0.05, 0.95)
  on stable-volatility markets revert at least partway toward the pre-spike
  anchor. Continuous monotonic drifts and noise on already-volatile markets do
  *not* satisfy this hypothesis and are excluded by the quality scoring layer.

Pipeline per market:
  1. Compute `MarketFeatures` from the persisted quote history.
  2. Apply hard filters (move size, ticks, velocity, volume z, spike, vol).
  3. Compute the composite `OverreactionScore`.
  4. If score passes, derive `prob_real` via the Bayesian estimator.
  5. Validate EV / mispricing on the resulting edge before emitting.
"""
from __future__ import annotations

from typing import Iterable

from app.config import settings
from app.data.market_analytics import MarketAnalytics, MarketFeatures
from app.data.market_store import MarketStore
from app.data.schemas import MarketQuote
from app.database.models import Side, SignalType
from app.monitoring.logger import get_logger
from app.monitoring.metrics import SIGNALS_DETECTED
from app.signals.base import SignalCandidate, SignalDetector
from app.signals.prob_real import bayesian_prob_real
from app.signals.quality import (
    OverreactionScore,
    momentum_score,
    overreaction_hard_filters_pass,
    overreaction_score,
)
from app.utils.math_utils import EdgeSnapshot

log = get_logger(__name__)


class OverreactionDetector(SignalDetector):
    name = "overreaction"

    def __init__(self, store: MarketStore, analytics: MarketAnalytics | None = None) -> None:
        self.store = store
        self.analytics = analytics or MarketAnalytics()

    def scan(self, markets: Iterable[MarketQuote]) -> list[SignalCandidate]:
        out: list[SignalCandidate] = []
        for m in markets:
            candidate = self._evaluate(m)
            if candidate is not None:
                SIGNALS_DETECTED.labels(signal_type=SignalType.OVERREACTION.value).inc()
                out.append(candidate)
        return out

    # -----------------------------------------------------------------------
    def _evaluate(self, m: MarketQuote) -> SignalCandidate | None:
        if m.yes_mid is None or m.no_mid is None:
            return None
        if m.volume_24h < settings.overreaction_min_volume_usd:
            return None
        if not (0.05 <= m.yes_mid <= 0.95):
            return None

        market_id = self.store.get_market_id(m.condition_id)
        if market_id is None:
            return None

        features = self.analytics.compute(market_id, settings.overreaction_window_minutes)
        if features is None or not features.is_valid:
            return None

        ok, reason = overreaction_hard_filters_pass(features)
        if not ok:
            log.debug("overreaction.rejected_hard_filter",
                      market=m.slug, reason=reason)
            return None

        score = overreaction_score(features)
        if not score.passes_filter:
            log.debug("overreaction.rejected_low_score",
                      market=m.slug, score=score.score)
            return None

        # Mutual exclusion: skip overreaction when momentum is also strong.
        m_score = momentum_score(features)
        if m_score.score >= settings.overreaction_block_when_momentum_above:
            log.info("overreaction.blocked_by_momentum",
                     market=m.slug, overreaction=score.score, momentum=m_score.score)
            return None

        # Derive Bayesian fair value of YES, then translate to the leg we're buying.
        estimate = bayesian_prob_real(
            features=features,
            score=score,
            base_reversion=settings.overreaction_reversion_target,
        )
        return self._build_candidate(m, features, score, estimate.prob_real_yes_mid)

    # -----------------------------------------------------------------------
    def _build_candidate(
        self,
        m: MarketQuote,
        f: MarketFeatures,
        score: OverreactionScore,
        prob_real_yes_mid: float,
    ) -> SignalCandidate | None:
        if f.rel_move > 0:
            # YES rallied → fade by buying NO.
            side = Side.NO
            price = m.no_ask
            prob_real = 1.0 - prob_real_yes_mid
            liquidity = m.no_liquidity_usd
            spread = m.no_spread
        else:
            side = Side.YES
            price = m.yes_ask
            prob_real = prob_real_yes_mid
            liquidity = m.yes_liquidity_usd
            spread = m.yes_spread

        if price is None or not (0 < price < 1):
            return None
        if not (0 < prob_real < 1):
            return None

        edge = EdgeSnapshot.build(prob_real=prob_real, price=price, kelly_mult=1.0)
        if edge.mispricing <= 0 or edge.ev <= 0:
            return None

        return SignalCandidate(
            signal_type=SignalType.OVERREACTION,
            strategy=self.name,
            market=m,
            side=side,
            edge=edge,
            liquidity_usd=liquidity,
            spread=spread,
            rationale=(
                f"{side.value} fade · score={score.score:.2f} · "
                f"move={f.rel_move:+.2%} · vel={f.velocity:.3%}/min · "
                f"vol_z={f.volume_z:+.2f} · spike={f.spike_ratio:.2f}"
            ),
            context={
                "anchor_mid": f.anchor_mid,
                "current_mid": f.current_mid,
                "rel_move": f.rel_move,
                "velocity": f.velocity,
                "spike_ratio": f.spike_ratio,
                "persistence": f.persistence,
                "realized_vol": f.realized_vol,
                "volume_z": f.volume_z,
                "score": score.score,
                "score_breakdown": {
                    "magnitude": score.magnitude,
                    "velocity": score.velocity,
                    "volume": score.volume,
                    "spike": score.spike,
                    "persistence_penalty": score.persistence_penalty,
                    "vol_penalty": score.vol_penalty,
                },
                "prob_real_yes_mid": prob_real_yes_mid,
                "ticks": f.ticks,
            },
        )
