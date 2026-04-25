"""Realistic execution model — latency, dynamic slippage, fill failures.

Used by both the live executor (to refresh stale book snapshots) and the
backtest engine (to simulate the friction the live path actually experiences).
"""
from __future__ import annotations

import random
import time
from dataclasses import dataclass

from app.config import settings
from app.data.schemas import OrderBook
from app.execution.book_walk import walk_book_for_shares


@dataclass
class LatencyBudget:
    sleep_ms: int
    failed: bool


def sample_latency() -> LatencyBudget:
    """Draw a random latency between configured bounds."""
    lo = max(0, settings.exec_latency_min_ms)
    hi = max(lo, settings.exec_latency_max_ms)
    if hi == 0:
        return LatencyBudget(0, False)
    sleep_ms = random.randint(lo, hi)
    failed = random.random() < settings.exec_failure_rate
    return LatencyBudget(sleep_ms=sleep_ms, failed=failed)


def apply_latency(budget: LatencyBudget) -> None:
    if budget.sleep_ms > 0:
        time.sleep(budget.sleep_ms / 1000.0)


def dynamic_slippage_bps(
    *,
    book: OrderBook,
    side: str,
    shares: float,
    realized_vol: float = 0.0,
    base_bps: float | None = None,
) -> float:
    """Compute total slippage budget for an order in basis points.

    Components:
      base_bps                       — fixed venue friction (config default)
      size factor × consumed-depth%  — penalty for chewing through the book
      vol factor × realised vol       — wider book in volatile regimes

    The size factor uses the *fraction of the visible book* the order eats.
    """
    if not settings.exec_dynamic_slippage_enabled:
        return base_bps if base_bps is not None else settings.slippage_bps

    base = base_bps if base_bps is not None else settings.slippage_bps

    fill = walk_book_for_shares(book, side, shares)
    visible = max(1e-9, fill.filled_shares + (book.asks[0].size if side.upper() == "BUY" and book.asks else 0.0))
    consumed_pct = min(1.0, fill.filled_shares / visible) if visible > 0 else 0.0

    size_extra = consumed_pct * 100.0 * settings.exec_dynamic_slippage_size_factor  # bps
    vol_extra = realized_vol * settings.exec_dynamic_slippage_vol_factor             # bps
    return base + size_extra + vol_extra


def stale_book_snapshot(book: OrderBook, latency_ms: int) -> OrderBook:
    """Return a *plausible* stale view of `book` proportional to `latency_ms`.

    For now we leave the book identical but tag the staleness on the result via
    the caller so the executor / backtester knows to widen its slippage budget.
    A full implementation would walk top-level cancels — out of scope for this
    pass.
    """
    return book
