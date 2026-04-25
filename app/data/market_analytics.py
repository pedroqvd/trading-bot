"""Rolling market statistics derived from the persisted quote history.

These features feed the quality scoring layer so detectors can distinguish
overreactions (fadeable) from genuine trends (do-not-touch).
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import timedelta
from typing import Sequence

from sqlalchemy import select

from app.database import session_scope
from app.database.models import Quote
from app.utils.time_utils import utcnow


@dataclass(frozen=True)
class MarketFeatures:
    """Snapshot of recent market behaviour for a single market."""
    window_minutes: int
    ticks: int

    anchor_mid: float            # robust anchor (median of the first third of the window)
    current_mid: float

    abs_move: float              # current - anchor
    rel_move: float              # abs_move / anchor (signed)
    velocity: float              # rel_move per minute across last few ticks
    spike_ratio: float           # |biggest single-tick move| / |total move|
    persistence: float           # fraction of tick-to-tick returns with the sign of total move
    realized_vol: float          # stdev of tick-to-tick returns
    volume_z: float              # current 24h volume z-score vs rolling baseline
    avg_spread: float            # mean (yes_ask - yes_bid)

    @property
    def is_valid(self) -> bool:
        return self.ticks >= 3 and self.anchor_mid > 0


class MarketAnalytics:
    """Compute `MarketFeatures` from persisted quotes."""

    def compute(self, market_id: int, window_minutes: int) -> MarketFeatures | None:
        quotes = self._load_quotes(market_id, window_minutes)
        if len(quotes) < 3:
            return None

        mids = [q.yes_mid for q in quotes if q.yes_mid is not None]
        if len(mids) < 3:
            return None

        # Robust anchor: median of the first third of observations inside the window.
        first_third = max(1, len(mids) // 3)
        anchor_candidates = sorted(mids[:first_third])
        anchor = anchor_candidates[len(anchor_candidates) // 2]
        current = mids[-1]
        if anchor <= 0 or anchor >= 1:
            return None

        abs_move = current - anchor
        rel_move = abs_move / anchor

        returns = [(b - a) / a for a, b in zip(mids[:-1], mids[1:]) if a > 0]
        realized_vol = _stdev(returns)

        # Velocity: measured over the last ~25% of the window so sudden late-window
        # spikes dominate, not an even-paced drift.
        tail = mids[-max(2, len(mids) // 4):]
        tail_minutes = self._duration_minutes(quotes[-len(tail):])
        tail_move = (tail[-1] - tail[0]) / tail[0] if tail[0] > 0 else 0.0
        velocity = tail_move / max(tail_minutes, 1.0)

        # Spike ratio: how concentrated the move is.
        if abs(abs_move) > 1e-9 and returns:
            biggest_tick_move = max(abs(r) for r in returns)
            spike_ratio = min(1.0, biggest_tick_move / (abs(rel_move) + 1e-9))
        else:
            spike_ratio = 0.0

        # Persistence: fraction of tick returns moving in the same direction as the total move.
        if returns and abs(rel_move) > 1e-9:
            total_sign = 1.0 if rel_move > 0 else -1.0
            same = sum(1 for r in returns if (r > 0) == (total_sign > 0))
            persistence = same / len(returns)
        else:
            persistence = 0.0

        # Volume z-score: compare the latest 24h volume snapshot to the rolling mean.
        volumes = [q.volume_24h for q in quotes if q.volume_24h is not None]
        volume_z = _zscore(volumes)

        spreads = [
            (q.yes_ask - q.yes_bid)
            for q in quotes
            if q.yes_ask is not None and q.yes_bid is not None
        ]
        avg_spread = sum(spreads) / len(spreads) if spreads else 0.0

        return MarketFeatures(
            window_minutes=window_minutes,
            ticks=len(mids),
            anchor_mid=anchor,
            current_mid=current,
            abs_move=abs_move,
            rel_move=rel_move,
            velocity=velocity,
            spike_ratio=spike_ratio,
            persistence=persistence,
            realized_vol=realized_vol,
            volume_z=volume_z,
            avg_spread=avg_spread,
        )

    # -----------------------------------------------------------------------
    @staticmethod
    def _load_quotes(market_id: int, window_minutes: int) -> list[Quote]:
        # Pull a slightly larger window so baseline stats have enough context.
        lookback = max(window_minutes * 4, 60)
        cutoff = utcnow() - timedelta(minutes=lookback)
        with session_scope() as session:
            rows = session.execute(
                select(Quote)
                .where(Quote.market_id == market_id, Quote.ts >= cutoff)
                .order_by(Quote.ts.asc())
            ).scalars().all()
            session.expunge_all()
            return list(rows)

    @staticmethod
    def _duration_minutes(quotes: Sequence[Quote]) -> float:
        if len(quotes) < 2:
            return 0.0
        delta = quotes[-1].ts - quotes[0].ts
        return max(delta.total_seconds() / 60.0, 0.0)


def _stdev(values: Sequence[float]) -> float:
    if len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    var = sum((v - mean) ** 2 for v in values) / (len(values) - 1)
    return math.sqrt(var)


def _zscore(values: Sequence[float]) -> float:
    if len(values) < 3:
        return 0.0
    mean = sum(values[:-1]) / max(1, len(values) - 1)
    std = _stdev(values[:-1])
    if std <= 0:
        return 0.0
    return (values[-1] - mean) / std
