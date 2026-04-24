"""Translate edge + Kelly fraction into a concrete USD allocation."""
from __future__ import annotations

from app.config import settings
from app.utils.math_utils import fractional_kelly


def suggested_size_usd(
    prob_real: float,
    price: float,
    capital_usd: float,
    liquidity_usd: float,
) -> float:
    """Fractional-Kelly dollar size clipped by per-trade and liquidity caps."""
    if capital_usd <= 0 or price <= 0 or price >= 1:
        return 0.0

    k = fractional_kelly(prob_real, price, settings.kelly_fraction)
    raw = capital_usd * k

    per_trade_cap = capital_usd * settings.max_position_pct
    liquidity_cap = max(0.0, liquidity_usd * 0.25)  # don't consume >25% of visible book

    return max(0.0, min(raw, per_trade_cap, liquidity_cap))
