"""Smart order placement: try to capture spread before paying it.

Strategy:
  1. Place a *passive* limit at `best_bid + offset` (we sit one cent inside
     the spread, hoping a taker hits us).
  2. Poll the live order book for `wait_seconds` while the order rests.
  3. If filled while we wait → great, we kept the spread.
  4. If the price drifts > `max_drift` against us → cancel, abort.
  5. Otherwise after the timeout → cancel + fall back to taker (IOC).

In dry-run / simulated mode we don't actually rest on the book. We instead
*model* a partial probability of capturing the passive price as a function of
spread and queue dynamics. This stops the simulation from over-claiming
maker-fill PnL.
"""
from __future__ import annotations

import time
from dataclasses import replace
from typing import Optional

from app.config import settings
from app.data.polymarket_client import PolymarketAPIError, PolymarketClient
from app.data.schemas import OrderBook
from app.database.models import OrderSide, TradeStatus
from app.execution.executor import Executor
from app.execution.orders import ExecutionResult, OrderRequest, new_client_order_id
from app.monitoring.logger import get_logger
from app.utils.math_utils import clamp

log = get_logger(__name__)


def passive_buy_price(book: OrderBook, fallback_ask: float) -> float:
    """Choose a passive buy price one tick inside the spread."""
    if book.best_bid is None or book.best_ask is None:
        return fallback_ask
    spread = book.best_ask - book.best_bid
    if spread <= settings.smart_order_passive_offset * 2:
        return book.best_ask  # spread too tight to gain anything from waiting
    return clamp(book.best_bid + settings.smart_order_passive_offset, 0.01, 0.99)


def passive_sell_price(book: OrderBook, fallback_bid: float) -> float:
    if book.best_bid is None or book.best_ask is None:
        return fallback_bid
    spread = book.best_ask - book.best_bid
    if spread <= settings.smart_order_passive_offset * 2:
        return book.best_bid
    return clamp(book.best_ask - settings.smart_order_passive_offset, 0.01, 0.99)


class SmartOrderPlacer:
    """Wraps the underlying executor with patient passive placement."""

    def __init__(self, client: PolymarketClient, executor: Executor) -> None:
        self.client = client
        self.executor = executor

    # -----------------------------------------------------------------------
    def place(
        self,
        request: OrderRequest,
        book: OrderBook,
        *,
        passive: bool = True,
    ) -> ExecutionResult:
        """Submit `request` patiently when possible, falling back to taker.

        For arbitrage legs the caller passes `passive=False` to skip the wait —
        we must take liquidity right now to keep the legs in lockstep.
        """
        if not settings.smart_order_enabled or not passive:
            return self.executor.execute(request)

        passive_price = self._choose_passive_price(request, book)
        if passive_price is None:
            return self.executor.execute(request)

        passive_request = replace(
            request,
            price=passive_price,
            time_in_force="GTC",
            post_only=True,
        )
        # Re-deriving notional here keeps shares consistent with the new price.
        passive_request.size_usd = passive_request.shares * passive_price

        result = self.executor.execute(passive_request)
        if result.status in (TradeStatus.FILLED, TradeStatus.PARTIAL):
            log.info("smart_order.passive_filled_immediately",
                     client_order_id=passive_request.client_order_id,
                     price=result.filled_price)
            return result

        filled = self._wait_for_fill(passive_request, result, book)
        if filled is not None:
            self.executor.record_external_fill(filled)
            log.info("smart_order.passive_filled_after_wait",
                     client_order_id=passive_request.client_order_id,
                     price=filled.filled_price)
            return filled

        self._safe_cancel(result)
        self.executor.cancel_passive(passive_request)
        # Fresh client_order_id so the executor records the taker leg as a new trade row.
        taker_request = replace(
            request,
            time_in_force="IOC",
            post_only=False,
            client_order_id=new_client_order_id(prefix=f"{request.strategy[:6]}-tk"),
        )
        log.info("smart_order.fallback_to_taker",
                 original=passive_request.client_order_id,
                 taker=taker_request.client_order_id)
        return self.executor.execute(taker_request)

    # -----------------------------------------------------------------------
    def _choose_passive_price(
        self, request: OrderRequest, book: OrderBook
    ) -> Optional[float]:
        if request.order_side == OrderSide.BUY:
            price = passive_buy_price(book, fallback_ask=request.price)
            if price >= request.price:
                return None  # nothing to gain — go taker
            return price
        price = passive_sell_price(book, fallback_bid=request.price)
        if price <= request.price:
            return None
        return price

    def _wait_for_fill(
        self,
        request: OrderRequest,
        initial: ExecutionResult,
        book: OrderBook,
    ) -> Optional[ExecutionResult]:
        deadline = time.monotonic() + settings.smart_order_wait_seconds
        anchor_price = request.price
        poll = max(0.05, settings.smart_order_poll_ms / 1000.0)

        if not self.client.has_signed_client:
            # Simulated venue — model a probability of getting hit.
            return self._simulate_passive_fill(initial, book)

        while time.monotonic() < deadline:
            time.sleep(poll)
            current_book = self._refresh_book(request.token_id)
            if current_book is None:
                continue
            if self._price_drifted_against_us(request, anchor_price, current_book):
                log.info("smart_order.abort_drift",
                         client_order_id=request.client_order_id)
                return None
            status = self._check_live_order(request, initial.exchange_order_id)
            if status is not None and status.status in (TradeStatus.FILLED, TradeStatus.PARTIAL):
                return status
        return None

    @staticmethod
    def _price_drifted_against_us(
        request: OrderRequest, anchor: float, book: OrderBook
    ) -> bool:
        drift_limit = settings.smart_order_max_price_drift
        if request.order_side == OrderSide.BUY:
            ref = book.best_ask
            if ref is None:
                return False
            return ref - anchor > drift_limit
        ref = book.best_bid
        if ref is None:
            return False
        return anchor - ref > drift_limit

    def _refresh_book(self, token_id: str) -> Optional[OrderBook]:
        try:
            return self.client.get_orderbook(token_id)
        except PolymarketAPIError:
            return None

    def _check_live_order(
        self, request: OrderRequest, exchange_order_id: Optional[str]
    ) -> Optional[ExecutionResult]:
        if not exchange_order_id or not self.client.has_signed_client:
            return None
        try:
            order = self.client.signed.get_order(exchange_order_id)
        except Exception:  # noqa: BLE001
            return None
        status = (order or {}).get("status", "").lower()
        if status in ("matched", "filled"):
            return ExecutionResult(
                request=request,
                status=TradeStatus.FILLED,
                filled_shares=float(order.get("size", 0)),
                filled_price=float(order.get("price", 0)),
                exchange_order_id=exchange_order_id,
                details={"mode": "live", "passive": True},
            )
        return None

    def _safe_cancel(self, result: ExecutionResult) -> None:
        if not result.exchange_order_id or not self.client.has_signed_client:
            return
        try:
            self.client.signed.cancel(result.exchange_order_id)
        except Exception as exc:  # noqa: BLE001
            log.warning("smart_order.cancel_failed",
                        order_id=result.exchange_order_id, error=str(exc))

    # -----------------------------------------------------------------------
    def _simulate_passive_fill(
        self, initial: ExecutionResult, book: OrderBook
    ) -> Optional[ExecutionResult]:
        """In simulated mode, decide deterministically whether the passive order fills.

        Heuristic: the wider the spread, the higher the chance someone hits us at the
        passive price. We fill at most half the time and only when the spread is at
        least 2× the passive offset. This keeps backtests honest about maker fills.
        """
        if not initial or initial.request is None:
            return None
        if book.best_bid is None or book.best_ask is None:
            return None
        spread = book.best_ask - book.best_bid
        offset = settings.smart_order_passive_offset
        # Probability of fill scales with spread above threshold, capped at 0.5.
        if spread <= 2 * offset:
            return None
        # Deterministic surrogate: use the lower bits of the client_order_id for stability.
        coid = initial.request.client_order_id or ""
        digest = sum(ord(c) for c in coid) if coid else 0
        prob_seed = (digest % 100) / 100.0
        fill_prob = min(0.5, (spread - 2 * offset) * 5)
        if prob_seed > fill_prob:
            return None
        # Fill at the passive price we set — no slippage paid.
        return ExecutionResult(
            request=initial.request,
            status=TradeStatus.FILLED,
            filled_shares=initial.request.shares,
            filled_price=initial.request.price,
            fees_usd=0.0,
            exchange_order_id=None,
            details={"mode": "simulated_passive"},
        )
