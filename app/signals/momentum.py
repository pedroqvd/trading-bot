"""Momentum / information-flow edge.

Hypothesis (continuation):
  Sustained moves with high velocity, high relative volume, strong persistence
  and low immediate mean-reversion tend to *continue* — at least for one more
  push. The bet is that the next N minutes carry the same direction.

Mutual exclusion:
  Overreaction and momentum cannot both fire on the same market in the same
  scan. A high overreaction score blocks momentum (we're fading), and a high
  momentum score blocks overreaction (we're trend-following). The shared
  feature pipeline (`MarketAnalytics`) makes this comparison cheap.
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
from app.signals.prob_real import bayesian_prob_real_momentum
from app.signals.quality import (
    MomentumScore,
    momentum_hard_filters_pass,
    momentum_score,
    overreaction_score,
)
from app.utils.math_utils import EdgeSnapshot

log = get_logger(__name__)


class MomentumDetector(SignalDetector):
    name = "momentum"

    def __init__(self, store: MarketStore, analytics: MarketAnalytics | None = None) -> None:
        self.store = store
        self.analytics = analytics or MarketAnalytics()

    def scan(self, markets: Iterable[MarketQuote]) -> list[SignalCandidate]:
        out: list[SignalCandidate] = []
        for m in markets:
            candidate = self._evaluate(m)
            if candidate is not None:
                SIGNALS_DETECTED.labels(signal_type=SignalType.MOMENTUM.value).inc()
                out.append(candidate)
        return out

    # -----------------------------------------------------------------------
    def _evaluate(self, m: MarketQuote) -> SignalCandidate | None:
        if m.yes_mid is None or m.no_mid is None:
            return None
        if not (settings.momentum_min_price <= m.yes_mid <= settings.momentum_max_price):
            return None

        market_id = self.store.get_market_id(m.condition_id)
        if market_id is None:
            return None

        features = self.analytics.compute(market_id, settings.momentum_window_minutes)
        if features is None or not features.is_valid:
            return None

        ok, reason = momentum_hard_filters_pass(features)
        if not ok:
            log.debug("momentum.rejected_hard_filter", market=m.slug, reason=reason)
            return None

        mscore = momentum_score(features)
        if not mscore.passes_filter:
            log.debug("momentum.rejected_low_score", market=m.slug, score=mscore.score)
            return None

        # Mutual exclusion with overreaction: if the same features score high as
        # an overreaction, we are *not* a clean continuation candidate.
        oscore = overreaction_score(features)
        if oscore.score >= settings.momentum_block_when_overreaction_above:
            log.info("momentum.blocked_by_overreaction",
                     market=m.slug, momentum=mscore.score, overreaction=oscore.score)
            return None

        return self._build_candidate(m, features, mscore, oscore)

    # -----------------------------------------------------------------------
    def _build_candidate(
        self,
        m: MarketQuote,
        f: MarketFeatures,
        mscore: MomentumScore,
        oscore,
    ) -> SignalCandidate | None:
        estimate = bayesian_prob_real_momentum(f, mscore)

        # Direction: trend up → buy YES, trend down → buy NO.
        if f.rel_move > 0:
            side = Side.YES
            price = m.yes_ask
            prob_real = estimate.prob_real_yes_mid
            liquidity = m.yes_liquidity_usd
            spread = m.yes_spread
        else:
            side = Side.NO
            price = m.no_ask
            prob_real = 1.0 - estimate.prob_real_yes_mid
            liquidity = m.no_liquidity_usd
            spread = m.no_spread

        if price is None or not (0 < price < 1):
            return None
        if not (0 < prob_real < 1):
            return None

        edge = EdgeSnapshot.build(prob_real=prob_real, price=price, kelly_mult=1.0)
        if edge.mispricing <= 0 or edge.ev <= 0:
            return None

        return SignalCandidate(
            signal_type=SignalType.MOMENTUM,
            strategy=self.name,
            market=m,
            side=side,
            edge=edge,
            liquidity_usd=liquidity,
            spread=spread,
            rationale=(
                f"{side.value} momentum · score={mscore.score:.2f} · "
                f"trend={f.trend_strength:.2f} · vel={f.velocity:.3%}/min · "
                f"persist={f.persistence:.2f} · rev_signal={f.mean_reversion_signal:.2f}"
            ),
            context={
                "momentum_score": mscore.score,
                "overreaction_score": oscore.score,
                "trend_strength": f.trend_strength,
                "persistence": f.persistence,
                "rel_move": f.rel_move,
                "velocity": f.velocity,
                "volume_z": f.volume_z,
                "spread_volatility": f.spread_volatility,
                "mean_reversion_signal": f.mean_reversion_signal,
                "extrapolation": estimate.extrapolation,
                "prob_real_yes_mid": estimate.prob_real_yes_mid,
                "ticks": f.ticks,
                "score_breakdown": {
                    "velocity": mscore.velocity,
                    "volume": mscore.volume,
                    "persistence": mscore.persistence,
                    "low_reversion": mscore.low_reversion,
                    "spread_stability": mscore.spread_stability,
                },
            },
        )
