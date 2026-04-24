"""Pure math primitives used across the trading engine.

All functions are deterministic and side-effect free so they can be unit tested
and reused from the live engine, backtester, and risk module.
"""
from __future__ import annotations

from dataclasses import dataclass


def clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def mispricing(prob_real: float, prob_market: float) -> float:
    """Edge in probability space: positive means buying the side is cheap."""
    return prob_real - prob_market


def expected_value(prob_real: float, price: float) -> float:
    """Per-$1 expected value of buying a YES/NO share at `price`.

    Payoff is $1 on win, $0 on loss.
    EV = prob_real * (1 - price) - (1 - prob_real) * price
       = prob_real - price
    (Algebraically identical but we keep the verbose form for clarity / audit.)
    """
    if not 0 < price < 1:
        return 0.0
    return prob_real * (1.0 - price) - (1.0 - prob_real) * price


def kelly_fraction(prob_real: float, price: float) -> float:
    """Optimal Kelly fraction for a binary bet at `price`.

    Decimal odds b = (1 - price) / price.
    f* = (b*p - q) / b = (p - price) / (1 - price).
    Negative values mean no edge → do not bet.
    """
    if price <= 0 or price >= 1:
        return 0.0
    edge = prob_real - price
    if edge <= 0:
        return 0.0
    return edge / (1.0 - price)


def fractional_kelly(prob_real: float, price: float, fraction: float) -> float:
    return max(0.0, kelly_fraction(prob_real, price) * fraction)


def slippage_adjust(price: float, side: str, bps: float) -> float:
    """Adjust `price` by `bps` slippage for the given `side` ('BUY' worsens up)."""
    delta = price * (bps / 10_000.0)
    if side.upper() == "BUY":
        return clamp(price + delta, 0.0, 1.0)
    return clamp(price - delta, 0.0, 1.0)


@dataclass(frozen=True)
class EdgeSnapshot:
    prob_market: float
    prob_real: float
    price: float
    mispricing: float
    ev: float
    kelly: float

    @classmethod
    def build(cls, prob_real: float, price: float, kelly_mult: float = 1.0) -> "EdgeSnapshot":
        prob_market = price  # on Polymarket, the price *is* the market-implied probability
        return cls(
            prob_market=prob_market,
            prob_real=prob_real,
            price=price,
            mispricing=mispricing(prob_real, prob_market),
            ev=expected_value(prob_real, price),
            kelly=fractional_kelly(prob_real, price, kelly_mult),
        )
