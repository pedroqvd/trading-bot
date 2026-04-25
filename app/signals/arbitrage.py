"""YES/NO arbitrage detector with realistic book-walk costing.

Old behaviour: looked at top-of-book ask sums only and assumed unlimited depth
at that price. Real Polymarket books are stacked — putting in $500 against a
$50 top level pays the level-2/3 prices, eliminating the apparent edge.

New behaviour:
  1. Quick pre-filter on top-of-book to short-circuit obvious non-arbs.
  2. Build an `ArbitrageExecutionPlan` that walks both books.
  3. Emit a signal only when the plan still profits *after* slippage and the
     `execution_confidence` clears the configured floor.

Sell-both is intentionally *not* emitted: it requires pre-existing inventory
on both sides, which the bot is structurally long-only. Falsely emitting it
would just generate rejected signals and pollute the metrics.
"""
from __future__ import annotations

from typing import Iterable

from app.config import settings
from app.data.schemas import MarketQuote
from app.database.models import Side, SignalType
from app.execution.book_walk import (
    ArbitrageExecutionPlan,
    plan_arbitrage_execution,
)
from app.monitoring.logger import get_logger
from app.monitoring.metrics import SIGNALS_DETECTED
from app.signals.base import SignalCandidate, SignalDetector
from app.utils.math_utils import EdgeSnapshot

log = get_logger(__name__)


class ArbitrageDetector(SignalDetector):
    name = "arbitrage"

    def scan(self, markets: Iterable[MarketQuote]) -> list[SignalCandidate]:
        out: list[SignalCandidate] = []
        for m in markets:
            candidate = self._evaluate(m)
            if candidate is not None:
                SIGNALS_DETECTED.labels(signal_type=SignalType.ARBITRAGE.value).inc()
                out.append(candidate)
        return out

    # -----------------------------------------------------------------------
    def _evaluate(self, m: MarketQuote) -> SignalCandidate | None:
        yes_ask, no_ask = m.yes_ask, m.no_ask
        if yes_ask is None or no_ask is None:
            return None

        # Pre-filter: top-of-book sum must already imply at least the minimum edge.
        top_sum = yes_ask + no_ask
        if top_sum >= 1 - settings.arbitrage_min_edge:
            return None

        # We *probe* with a notional sized to the per-trade cap so the detector
        # discards arbs that are too thin. Actual execution uses the same plan,
        # so what we measure here is what we'd actually take.
        equity_proxy = settings.capital_usd  # sizing finalised by RiskManager
        per_trade_cap = equity_proxy * settings.max_position_pct
        target_bonds = per_trade_cap / max(top_sum, 1e-3)
        target_bonds = max(1.0, float(int(target_bonds)))

        plan = plan_arbitrage_execution(
            yes_book=m.yes_book,
            no_book=m.no_book,
            target_bonds=target_bonds,
            safety_multiplier=settings.arbitrage_size_safety_multiplier,
            min_profit_per_bond=settings.arbitrage_min_edge,
        )
        if plan.exhausted or plan.bonds < 1:
            log.debug("arbitrage.insufficient_depth",
                      market=m.slug, notes=plan.notes,
                      target_bonds=target_bonds)
            return None
        if plan.profit_per_bond < settings.arbitrage_min_edge:
            log.debug("arbitrage.below_min_edge",
                      market=m.slug,
                      profit_per_bond=plan.profit_per_bond)
            return None
        if plan.confidence < settings.arbitrage_min_exec_confidence:
            log.debug("arbitrage.low_confidence",
                      market=m.slug, confidence=plan.confidence)
            return None

        edge = EdgeSnapshot(
            prob_market=plan.yes_avg_price + plan.no_avg_price,
            prob_real=1.0,
            price=plan.yes_avg_price + plan.no_avg_price,
            mispricing=plan.profit_per_bond,
            ev=plan.profit_per_bond,
            kelly=plan.profit_per_bond,
        )
        return SignalCandidate(
            signal_type=SignalType.ARBITRAGE,
            strategy=self.name,
            market=m,
            side=Side.YES,  # canonical; both legs carried in context
            edge=edge,
            liquidity_usd=min(m.yes_liquidity_usd, m.no_liquidity_usd),
            spread=None,
            rationale=(
                f"buy_both arb · bonds={plan.bonds:.0f} · "
                f"yes_avg={plan.yes_avg_price:.4f} no_avg={plan.no_avg_price:.4f} · "
                f"profit/bond={plan.profit_per_bond:.4f} · "
                f"conf={plan.confidence:.2f}"
            ),
            context={
                "kind": "buy_both",
                "yes_avg_price": plan.yes_avg_price,
                "no_avg_price": plan.no_avg_price,
                "yes_top_ask": yes_ask,
                "no_top_ask": no_ask,
                "bonds": plan.bonds,
                "profit_per_bond": plan.profit_per_bond,
                "confidence": plan.confidence,
                "yes_filled_shares": plan.yes_filled_shares,
                "no_filled_shares": plan.no_filled_shares,
            },
        )

    @staticmethod
    def build_execution_plan_for_arb(
        market: MarketQuote, target_bonds: float
    ) -> ArbitrageExecutionPlan:
        """Helper used by the strategy at order-construction time."""
        return plan_arbitrage_execution(
            yes_book=market.yes_book,
            no_book=market.no_book,
            target_bonds=target_bonds,
            safety_multiplier=settings.arbitrage_size_safety_multiplier,
            min_profit_per_bond=settings.arbitrage_min_edge,
        )
