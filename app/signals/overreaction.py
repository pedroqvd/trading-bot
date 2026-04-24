"""Overreaction edge: fade rapid moves with high volume.

Core hypothesis (per playbook):
  When the market moves more than N% in a short window on elevated volume,
  participants are typically overreacting to news/order-flow. Mean reversion
  toward the pre-move anchor has statistically significant expected value on
  binary prediction markets, especially for YES priced in (0.1, 0.9).
"""
from __future__ import annotations

from typing import Iterable

from app.config import settings
from app.data.market_store import MarketStore
from app.data.schemas import MarketQuote
from app.database.models import Side, SignalType
from app.monitoring.logger import get_logger
from app.monitoring.metrics import SIGNALS_DETECTED
from app.signals.base import SignalCandidate, SignalDetector
from app.utils.math_utils import EdgeSnapshot

log = get_logger(__name__)


class OverreactionDetector(SignalDetector):
    name = "overreaction"

    def __init__(self, store: MarketStore) -> None:
        self.store = store

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
        # Avoid degenerate books (prices at extremes are expensive to fade)
        if not (0.05 <= m.yes_mid <= 0.95):
            return None

        market_id = self.store.get_market_id(m.condition_id)
        if market_id is None:
            return None

        recent = self.store.recent_quotes(market_id, minutes=settings.overreaction_window_minutes)
        if len(recent) < 3:
            return None

        anchor = recent[0].yes_mid
        if anchor is None or anchor <= 0 or anchor >= 1:
            return None

        move = m.yes_mid - anchor
        rel_move = move / anchor
        if abs(rel_move) < settings.overreaction_move_pct:
            return None

        # Fade the move — target is a partial reversion toward anchor.
        reversion = settings.overreaction_reversion_target
        target = m.yes_mid - reversion * move  # pulls halfway back toward anchor by default

        if move > 0:
            # YES rallied too hard → fade by buying NO (equivalent to selling YES).
            side = Side.NO
            price = m.no_ask
            prob_real = 1.0 - target
            liquidity = m.no_liquidity_usd
            spread = m.no_spread
        else:
            # YES crashed too hard → buy YES.
            side = Side.YES
            price = m.yes_ask
            prob_real = target
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
                f"{side.value} fade: YES moved {rel_move:+.2%} in "
                f"{settings.overreaction_window_minutes}m (anchor {anchor:.3f} → {m.yes_mid:.3f}); "
                f"target reversion to {target:.3f}"
            ),
            context={
                "anchor_price": anchor,
                "current_yes_mid": m.yes_mid,
                "rel_move": rel_move,
                "reversion_target": target,
                "volume_24h": m.volume_24h,
            },
        )
