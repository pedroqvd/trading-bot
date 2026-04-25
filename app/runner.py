"""Trading orchestrator: scan → signal → strategy → risk → execute → reconcile."""
from __future__ import annotations

import signal as signal_lib
import time
from typing import Iterable

from sqlalchemy import select

from app.config import settings
from app.data.market_store import MarketStore
from app.data.polymarket_client import PolymarketClient
from app.data.schemas import MarketQuote
from app.database import init_db, session_scope
from app.database.models import (
    Market,
    Signal as SignalRow,
    SignalType,
    TradeStatus,
)
from app.execution.executor import Executor
from app.execution.orders import ExecutionResult, OrderRequest
from app.execution.position_manager import PositionManager
from app.execution.smart_order import SmartOrderPlacer
from app.monitoring.alerts import send_alert
from app.monitoring.logger import get_logger
from app.monitoring.metrics import LOOP_LATENCY, start_metrics_server
from app.portfolio.portfolio import Portfolio
from app.portfolio.strategy_metrics import per_strategy_report
from app.risk.risk_manager import RiskManager
from app.signals.arbitrage import ArbitrageDetector
from app.signals.base import SignalCandidate, SignalDetector
from app.signals.overreaction import OverreactionDetector
from app.strategies.arbitrage_strategy import ArbitrageStrategy
from app.strategies.base import Strategy
from app.strategies.overreaction_strategy import OverreactionStrategy

log = get_logger(__name__)


class TradingRunner:
    def __init__(self) -> None:
        self.client = PolymarketClient()
        self.store = MarketStore(self.client)
        self.executor = Executor(self.client)
        self.smart_orders = SmartOrderPlacer(self.client, self.executor)
        self.portfolio = Portfolio()
        self.risk = RiskManager()
        self.position_manager = PositionManager(self.client, self.executor)

        self.detectors: list[SignalDetector] = [
            ArbitrageDetector(),
            OverreactionDetector(self.store),
        ]
        self.strategies: dict[str, Strategy] = {
            "arbitrage": ArbitrageStrategy(self.risk),
            "overreaction": OverreactionStrategy(self.risk),
        }

        self._shutdown = False

    # -----------------------------------------------------------------------
    # Lifecycle
    # -----------------------------------------------------------------------
    def install_signal_handlers(self) -> None:
        signal_lib.signal(signal_lib.SIGINT, self._handle_shutdown)
        signal_lib.signal(signal_lib.SIGTERM, self._handle_shutdown)

    def _handle_shutdown(self, *_) -> None:
        log.info("runner.shutdown_requested")
        self._shutdown = True

    def close(self) -> None:
        self.client.close()

    # -----------------------------------------------------------------------
    # Main loop
    # -----------------------------------------------------------------------
    def run_forever(self) -> None:
        log.info(
            "runner.start",
            env=settings.app_env,
            dry_run=settings.dry_run,
            live=settings.live_trading_enabled,
            capital=settings.capital_usd,
        )
        while not self._shutdown:
            loop_started = time.monotonic()
            try:
                self.run_once()
            except Exception as exc:  # noqa: BLE001
                log.exception("runner.loop_failed")
                send_alert("Trading loop failed", str(exc), severity="warning")
            finally:
                elapsed = time.monotonic() - loop_started
                LOOP_LATENCY.observe(elapsed)
            # Sleep until next scan; bail out immediately on shutdown
            for _ in range(settings.poll_interval_seconds):
                if self._shutdown:
                    break
                time.sleep(1)
        log.info("runner.stopped")

    def run_once(self) -> None:
        quotes = self.store.refresh_universe()

        # Mark-to-market + snapshot BEFORE generating new orders
        summary = self.portfolio.snapshot(quotes)
        log.info(
            "portfolio.snapshot",
            equity=summary.equity_usd,
            cash=summary.cash_usd,
            unrealized=summary.unrealized_usd,
            open_positions=summary.open_positions,
            daily_pnl=summary.realized_today_usd,
            drawdown=summary.drawdown_pct,
        )
        for sr in per_strategy_report(lookback_days=7):
            log.info(
                "portfolio.strategy_report",
                strategy=sr.strategy,
                trades=sr.trades,
                win_rate=sr.win_rate,
                expectancy_usd=sr.expectancy_usd,
                profit_factor=sr.profit_factor,
                avg_hold_min=sr.avg_hold_minutes,
                max_drawdown_usd=sr.max_drawdown_usd,
            )

        # Reconcile exits first (take-profit / stop-loss / time stop)
        exit_results = self.position_manager.reconcile(quotes)
        if exit_results:
            log.info("runner.exits_processed", count=len(exit_results))

        # Detect new signals
        signals = self._detect_all(quotes)
        if not signals:
            return
        log.info("runner.signals_detected", total=len(signals))

        # Plan + execute
        self._handle_signals(signals, summary.equity_usd)

    # -----------------------------------------------------------------------
    def _detect_all(self, quotes: Iterable[MarketQuote]) -> list[SignalCandidate]:
        materialised = list(quotes)
        signals: list[SignalCandidate] = []
        for detector in self.detectors:
            try:
                found = detector.scan(materialised)
                signals.extend(found)
            except Exception:  # noqa: BLE001
                log.exception("detector.failed", detector=detector.name)
        # Persist for audit
        self._persist_signals(signals)
        return signals

    def _persist_signals(self, signals: Iterable[SignalCandidate]) -> None:
        with session_scope() as session:
            for s in signals:
                market = session.execute(
                    select(Market).where(Market.condition_id == s.market.condition_id)
                ).scalar_one_or_none()
                if market is None:
                    continue
                session.add(SignalRow(
                    market_id=market.id,
                    signal_type=s.signal_type,
                    side=s.side,
                    prob_market=s.edge.prob_market,
                    prob_real=s.edge.prob_real,
                    mispricing=s.edge.mispricing,
                    expected_value=s.edge.ev,
                    kelly_fraction=s.edge.kelly,
                    suggested_size_usd=0.0,
                    details={"rationale": s.rationale, "context": s.context},
                ))

    # -----------------------------------------------------------------------
    def _handle_signals(self, signals: list[SignalCandidate], equity_usd: float) -> None:
        # Rank signals by EV desc to consume the best opportunities first.
        signals.sort(key=lambda s: s.edge.ev, reverse=True)
        for s in signals:
            strategy = self.strategies.get(s.strategy)
            if strategy is None:
                continue

            plan = strategy.plan(s, equity_usd)
            if not plan.approved:
                log.info("strategy.rejected", strategy=s.strategy,
                         reason=plan.reason, market=s.market.slug)
                continue

            market_id = self.store.get_market_id(s.market.condition_id)
            if market_id is None:
                log.warning("strategy.skipped_missing_market_id", market=s.market.slug)
                continue
            for req in plan.orders:
                req.market_id = market_id

            # Arbitrage: execute atomically — cancel the second leg if first fails.
            if s.signal_type == SignalType.ARBITRAGE:
                self._execute_arb_atomic(plan.orders, s.market)
            else:
                self._execute_and_record(plan.orders, s.market)

            # Refresh equity between consecutive entries so exposure stays bounded.
            equity_usd = self.portfolio.summary([]).equity_usd

    def _execute_and_record(self, orders: list[OrderRequest], market: MarketQuote) -> None:
        for req in orders:
            book = market.yes_book if req.market_side.value == "YES" else market.no_book
            result = self.smart_orders.place(req, book, passive=True)
            if result.status in (TradeStatus.FILLED, TradeStatus.PARTIAL):
                # The smart placer may have used a fallback request with a
                # different client_order_id; use whatever request is in the
                # result so portfolio accounting matches the persisted row.
                effective_req = result.request or req
                self.portfolio.record_entry(effective_req, result)

    def _execute_arb_atomic(self, orders: list[OrderRequest], market: MarketQuote) -> None:
        if len(orders) != 2:
            self._execute_and_record(orders, market)
            return
        yes_leg, no_leg = orders
        # Arbitrage legs MUST be takers; we cannot afford a passive wait that
        # would leave us with one leg open and the other resting.
        yes_result = self.smart_orders.place(yes_leg, market.yes_book, passive=False)
        if yes_result.status not in (TradeStatus.FILLED, TradeStatus.PARTIAL):
            log.warning("arbitrage.leg_failed", leg="yes", status=yes_result.status.value)
            return
        no_result = self.smart_orders.place(no_leg, market.no_book, passive=False)
        if no_result.status not in (TradeStatus.FILLED, TradeStatus.PARTIAL):
            log.error("arbitrage.leg_failed_after_fill", leg="no",
                      status=no_result.status.value)
            # Record the YES leg anyway so the existing position can be managed.
            self.portfolio.record_entry(yes_leg, yes_result)
            send_alert(
                "Arbitrage only partially executed",
                f"YES filled but NO leg {no_result.status.value}. Review position {yes_leg.client_order_id}.",
                severity="warning",
            )
            return
        self.portfolio.record_entry(yes_leg, yes_result)
        self.portfolio.record_entry(no_leg, no_result)


def main() -> None:
    from app.monitoring.logger import configure_logging

    configure_logging()
    init_db()
    start_metrics_server()

    runner = TradingRunner()
    runner.install_signal_handlers()
    try:
        runner.run_forever()
    finally:
        runner.close()
