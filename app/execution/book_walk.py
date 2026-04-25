"""Book-walk execution cost simulator.

The naive "best ask × shares" pricing assumed by the original arbitrage
detector ignores depth. A 100-share order against a book that has 20 shares at
the best ask and 80 at a worse level pays the *VWAP*, not the top.

This module gives every layer above (signals, risk, executor) the same
realistic view of fill cost.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.data.schemas import OrderBook


@dataclass(frozen=True)
class FillEstimate:
    avg_price: float        # VWAP across the consumed levels (0 if nothing fills)
    filled_shares: float
    filled_notional: float
    exhausted: bool         # True if we couldn't fully fill the request
    levels_consumed: int


def walk_book_for_notional(book: OrderBook, side: str, notional_usd: float) -> FillEstimate:
    """Walk a book consuming `notional_usd`. `side` is 'BUY' (uses asks) or 'SELL'."""
    if notional_usd <= 0:
        return FillEstimate(0.0, 0.0, 0.0, exhausted=False, levels_consumed=0)
    levels = book.asks if side.upper() == "BUY" else book.bids
    return _walk(levels, notional_usd, mode="notional")


def walk_book_for_shares(book: OrderBook, side: str, shares: float) -> FillEstimate:
    """Walk a book consuming `shares`. `side` is 'BUY' (uses asks) or 'SELL'."""
    if shares <= 0:
        return FillEstimate(0.0, 0.0, 0.0, exhausted=False, levels_consumed=0)
    levels = book.asks if side.upper() == "BUY" else book.bids
    return _walk(levels, shares, mode="shares")


def _walk(levels, target: float, *, mode: str) -> FillEstimate:
    if not levels:
        return FillEstimate(0.0, 0.0, 0.0, exhausted=True, levels_consumed=0)
    remaining = target
    total_shares = 0.0
    total_notional = 0.0
    consumed = 0
    for lvl in levels:
        if mode == "notional":
            available_notional = lvl.price * lvl.size
            take_notional = min(remaining, available_notional)
            if take_notional <= 0:
                break
            shares = take_notional / lvl.price if lvl.price > 0 else 0.0
            remaining -= take_notional
        else:  # shares
            shares = min(remaining, lvl.size)
            if shares <= 0:
                break
            take_notional = shares * lvl.price
            remaining -= shares

        total_shares += shares
        total_notional += take_notional
        consumed += 1
        if remaining <= 1e-9:
            break

    avg = (total_notional / total_shares) if total_shares > 0 else 0.0
    return FillEstimate(
        avg_price=avg,
        filled_shares=total_shares,
        filled_notional=total_notional,
        exhausted=remaining > 1e-6,
        levels_consumed=consumed,
    )


@dataclass(frozen=True)
class ArbitrageExecutionPlan:
    bonds: float
    yes_avg_price: float
    no_avg_price: float
    yes_filled_shares: float
    no_filled_shares: float
    profit_per_bond: float        # 1.0 - (yes_avg + no_avg)
    total_profit_usd: float
    confidence: float             # 0..1, 1.0 means ample headroom
    exhausted: bool               # one of the legs couldn't fill
    notes: str = ""


def plan_arbitrage_execution(
    yes_book: OrderBook,
    no_book: OrderBook,
    target_bonds: float,
    safety_multiplier: float,
    min_profit_per_bond: float,
) -> ArbitrageExecutionPlan:
    """Simulate buying `target_bonds` of (YES + NO) using book depth.

    `safety_multiplier` requests a slightly larger pool of shares than we'll
    actually take, so we have headroom against latency-induced book movement.
    `min_profit_per_bond` is the floor we expect after slippage.
    """
    if target_bonds <= 0:
        return ArbitrageExecutionPlan(0, 0, 0, 0, 0, 0, 0, 0.0, exhausted=True,
                                      notes="zero bonds")

    request_shares = target_bonds * safety_multiplier
    yes_fill = walk_book_for_shares(yes_book, "BUY", request_shares)
    no_fill = walk_book_for_shares(no_book, "BUY", request_shares)

    if yes_fill.exhausted or no_fill.exhausted:
        return ArbitrageExecutionPlan(
            bonds=0,
            yes_avg_price=yes_fill.avg_price,
            no_avg_price=no_fill.avg_price,
            yes_filled_shares=yes_fill.filled_shares,
            no_filled_shares=no_fill.filled_shares,
            profit_per_bond=0.0,
            total_profit_usd=0.0,
            confidence=0.0,
            exhausted=True,
            notes=(
                f"insufficient depth — yes:{yes_fill.filled_shares:.1f}, "
                f"no:{no_fill.filled_shares:.1f}, requested:{request_shares:.1f}"
            ),
        )

    # Cap actual bonds at the smaller of the two legs (after stripping the safety
    # buffer back out so callers see the realistic maximum).
    max_yes_bonds = yes_fill.filled_shares / safety_multiplier
    max_no_bonds = no_fill.filled_shares / safety_multiplier
    bonds = min(target_bonds, max_yes_bonds, max_no_bonds)
    bonds = max(0.0, float(int(bonds)))   # 1-share increments

    profit_per_bond = 1.0 - (yes_fill.avg_price + no_fill.avg_price)
    confidence = 0.0
    if profit_per_bond > 0 and min_profit_per_bond > 0:
        # Confidence saturates at 3× the min: we want comfortable headroom.
        confidence = min(1.0, profit_per_bond / (min_profit_per_bond * 3))

    return ArbitrageExecutionPlan(
        bonds=bonds,
        yes_avg_price=yes_fill.avg_price,
        no_avg_price=no_fill.avg_price,
        yes_filled_shares=yes_fill.filled_shares,
        no_filled_shares=no_fill.filled_shares,
        profit_per_bond=profit_per_bond,
        total_profit_usd=profit_per_bond * bonds,
        confidence=confidence,
        exhausted=False,
    )
