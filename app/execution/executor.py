"""Order executor. Routes to live CLOB or the simulated venue based on config."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable

from sqlalchemy import select

from app.config import settings
from app.data.polymarket_client import PolymarketAPIError, PolymarketClient
from app.database import session_scope
from app.database.models import OrderSide, Trade, TradeStatus
from app.execution.orders import ExecutionResult, OrderRequest
from app.monitoring.logger import get_logger
from app.monitoring.metrics import TRADES_FAILED, TRADES_FILLED, TRADES_SUBMITTED
from app.utils.math_utils import slippage_adjust

log = get_logger(__name__)


class Executor:
    """Facade over the two execution modes.

    - **dry_run / backtest**: deterministic fill model that applies configured
      slippage and fees.
    - **live**: signs orders via py-clob-client when credentials are available.
    """

    def __init__(self, client: PolymarketClient) -> None:
        self.client = client
        self._use_live = settings.live_trading_enabled and client.has_signed_client
        if settings.dry_run and self._use_live:
            log.warning("executor.dry_run_overrides_live_credentials")
            self._use_live = False
        log.info("executor.mode", live=self._use_live, dry_run=settings.dry_run)

    def execute_all(self, requests: Iterable[OrderRequest]) -> list[ExecutionResult]:
        return [self.execute(req) for req in requests]

    def execute(self, request: OrderRequest) -> ExecutionResult:
        TRADES_SUBMITTED.labels(strategy=request.strategy,
                                side=f"{request.order_side.value}-{request.market_side.value}").inc()
        self._record_pending(request)
        try:
            if self._use_live:
                result = self._execute_live(request)
            else:
                result = self._execute_simulated(request)
        except Exception as exc:  # noqa: BLE001
            log.exception("executor.failed", client_order_id=request.client_order_id)
            TRADES_FAILED.labels(strategy=request.strategy, reason="exception").inc()
            result = ExecutionResult(request=request, status=TradeStatus.FAILED, error=str(exc))

        self.record_result(result)
        if result.status in (TradeStatus.FILLED, TradeStatus.PARTIAL):
            TRADES_FILLED.labels(strategy=request.strategy,
                                 side=f"{request.order_side.value}-{request.market_side.value}").inc()
        elif result.status != TradeStatus.PENDING:
            TRADES_FAILED.labels(strategy=request.strategy, reason=result.status.value).inc()
        return result

    def record_external_fill(self, result: ExecutionResult) -> None:
        """Public hook used by the smart placer for passive-fill outcomes.

        The original PENDING row already exists (created by `execute`); this
        updates it to FILLED with the realised price/shares/fees.
        """
        self.record_result(result)
        TRADES_FILLED.labels(
            strategy=result.request.strategy,
            side=f"{result.request.order_side.value}-{result.request.market_side.value}",
        ).inc()

    def cancel_passive(self, request: OrderRequest) -> None:
        """Mark a resting passive order as CANCELED in our books."""
        with session_scope() as session:
            trade = session.execute(
                select(Trade).where(Trade.client_order_id == request.client_order_id)
            ).scalar_one_or_none()
            if trade is None:
                return
            if trade.status == TradeStatus.PENDING:
                trade.status = TradeStatus.CANCELED

    # -----------------------------------------------------------------------
    # Simulated venue
    # -----------------------------------------------------------------------
    def _execute_simulated(self, request: OrderRequest) -> ExecutionResult:
        # Post-only / GTC orders rest on the book in production. The
        # SmartOrderPlacer is responsible for deciding whether a passive order
        # gets hit. Returning PENDING here forces honest accounting in backtests.
        if request.post_only:
            return ExecutionResult(
                request=request,
                status=TradeStatus.PENDING,
                filled_shares=0.0,
                filled_price=0.0,
                fees_usd=0.0,
                exchange_order_id=None,
                details={"mode": "simulated_passive_pending"},
            )
        fill_price = slippage_adjust(request.price, request.order_side.value, settings.slippage_bps)
        fill_price = max(0.0001, min(0.9999, fill_price))
        fees = request.shares * fill_price * (settings.taker_fee_bps / 10_000.0)
        return ExecutionResult(
            request=request,
            status=TradeStatus.FILLED,
            filled_shares=request.shares,
            filled_price=fill_price,
            fees_usd=fees,
            exchange_order_id=None,
            filled_at=datetime.now(timezone.utc),
            details={"mode": "simulated"},
        )

    # -----------------------------------------------------------------------
    # Live venue (py-clob-client)
    # -----------------------------------------------------------------------
    def _execute_live(self, request: OrderRequest) -> ExecutionResult:
        try:
            from py_clob_client.clob_types import OrderArgs, OrderType
        except ImportError as exc:  # pragma: no cover
            raise PolymarketAPIError("py_clob_client not available for live trading") from exc

        args = OrderArgs(
            price=request.price,
            size=request.shares,
            side=request.order_side.value,
            token_id=request.token_id,
        )
        signed = self.client.signed.create_and_post_order(
            args,
            order_type=OrderType.GTC if request.time_in_force == "GTC" else OrderType.FOK,
        )
        order_id = (signed or {}).get("orderID") or (signed or {}).get("order_id")
        status = (signed or {}).get("status", "").lower()
        filled_shares = float((signed or {}).get("makingAmount", 0)) or request.shares
        filled_price = float((signed or {}).get("price", request.price))
        trade_status = TradeStatus.FILLED if status in ("matched", "filled") \
            else TradeStatus.PARTIAL if status in ("partially_matched", "partial") \
            else TradeStatus.PENDING
        return ExecutionResult(
            request=request,
            status=trade_status,
            filled_shares=filled_shares,
            filled_price=filled_price,
            fees_usd=0.0,
            exchange_order_id=order_id,
            filled_at=datetime.now(timezone.utc) if trade_status != TradeStatus.PENDING else None,
            details={"mode": "live", "response": signed or {}},
        )

    # -----------------------------------------------------------------------
    # Persistence
    # -----------------------------------------------------------------------
    @staticmethod
    def _record_pending(request: OrderRequest) -> None:
        with session_scope() as session:
            existing = session.execute(
                select(Trade).where(Trade.client_order_id == request.client_order_id)
            ).scalar_one_or_none()
            if existing is not None:
                return  # idempotent
            session.add(Trade(
                position_id=request.position_id,
                market_id=request.market_id,
                order_side=request.order_side,
                market_side=request.market_side,
                status=TradeStatus.PENDING,
                price=request.price,
                size_usd=request.size_usd,
                shares=request.shares,
                client_order_id=request.client_order_id,
                details={
                    "strategy": request.strategy,
                    "metadata": request.metadata,
                },
            ))

    @staticmethod
    def record_result(result: ExecutionResult) -> None:
        with session_scope() as session:
            trade = session.execute(
                select(Trade).where(Trade.client_order_id == result.request.client_order_id)
            ).scalar_one_or_none()
            if trade is None:
                return
            trade.status = result.status
            trade.filled_shares = result.filled_shares
            trade.fees_usd = result.fees_usd
            trade.exchange_order_id = result.exchange_order_id
            trade.filled_at = result.filled_at
            trade.error = result.error
            # Update price to realised price when we actually got a fill
            if result.filled_price and result.status in (TradeStatus.FILLED, TradeStatus.PARTIAL):
                trade.price = result.filled_price
            existing_details = trade.details or {}
            existing_details.update({"result": result.details})
            trade.details = existing_details
