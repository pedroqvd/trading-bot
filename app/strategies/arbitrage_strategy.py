"""YES/NO arbitrage strategy — book-walk-aware leg construction.

The detector already validated that the depth supports an execution plan with
acceptable confidence. We rebuild the plan here so the orders we send carry
the *averaged* leg prices (not the optimistic top-of-book numbers). The
runner enforces atomic execution with FOK; if either leg fails, the partial
position is handed to the position manager.
"""
from __future__ import annotations

from app.config import settings
from app.database.models import OrderSide, Side
from app.execution.book_walk import plan_arbitrage_execution
from app.execution.orders import OrderRequest, new_client_order_id
from app.monitoring.logger import get_logger
from app.monitoring.metrics import SIGNALS_ACCEPTED
from app.risk.risk_manager import RiskManager
from app.signals.base import SignalCandidate
from app.strategies.base import Strategy, StrategyResult

log = get_logger(__name__)


class ArbitrageStrategy(Strategy):
    name = "arbitrage"

    def __init__(self, risk: RiskManager) -> None:
        self.risk = risk

    def plan(self, signal: SignalCandidate, current_equity_usd: float) -> StrategyResult:
        if signal.context.get("kind") != "buy_both":
            return StrategyResult(False, [], reason="non-buy_both arbitrage not supported")

        # Re-derive notional cap with the current equity (the detector used the
        # configured capital_usd as a proxy at probe time).
        per_trade_cap = current_equity_usd * settings.max_position_pct
        if per_trade_cap < settings.min_liquidity_usd / 10:
            return StrategyResult(False, [], reason="per-trade cap below practical floor")

        target_bonds_from_capital = per_trade_cap / max(
            signal.context["yes_avg_price"] + signal.context["no_avg_price"],
            1e-3,
        )
        target_bonds = min(
            float(int(target_bonds_from_capital)),
            float(signal.context["bonds"]),
        )
        if target_bonds < 1:
            return StrategyResult(False, [], reason="target bonds < 1 after sizing")

        plan = plan_arbitrage_execution(
            yes_book=signal.market.yes_book,
            no_book=signal.market.no_book,
            target_bonds=target_bonds,
            safety_multiplier=settings.arbitrage_size_safety_multiplier,
            min_profit_per_bond=settings.arbitrage_min_edge,
        )
        if plan.exhausted or plan.bonds < 1:
            return StrategyResult(False, [], reason=f"book moved: {plan.notes}")
        if plan.confidence < settings.arbitrage_min_exec_confidence:
            return StrategyResult(False, [], reason=f"confidence {plan.confidence:.2f} too low")
        if plan.profit_per_bond < settings.arbitrage_min_edge:
            return StrategyResult(False, [], reason=f"edge collapsed to {plan.profit_per_bond:.4f}")

        decision = self.risk.check(
            strategy=self.name,
            condition_id=signal.market.condition_id,
            suggested_size_usd=plan.bonds * (plan.yes_avg_price + plan.no_avg_price),
            edge_mispricing=plan.profit_per_bond,
            edge_ev=plan.profit_per_bond,
            liquidity_usd=signal.liquidity_usd,
            spread=None,
            current_equity_usd=current_equity_usd,
            quality_score=plan.confidence,
            side=signal.side,
            question=signal.market.question,
            slug=signal.market.slug,
        )
        if not decision.approved:
            return StrategyResult(False, [], reason=decision.reason, risk=decision)

        # Re-size bonds to the risk-approved notional. Both legs use the same
        # bond count so they remain market-neutral.
        approved_notional = decision.size_usd
        bonds_after_risk = approved_notional / max(plan.yes_avg_price + plan.no_avg_price, 1e-3)
        bonds = max(1.0, float(int(bonds_after_risk)))
        if bonds < 1:
            return StrategyResult(False, [], reason="risk-sized bonds < 1")

        base = new_client_order_id(prefix="arb")
        orders = [
            OrderRequest(
                market_condition_id=signal.market.condition_id,
                market_id=0,
                token_id=signal.market.yes_token_id,
                market_side=Side.YES,
                order_side=OrderSide.BUY,
                price=plan.yes_avg_price,
                size_usd=bonds * plan.yes_avg_price,
                shares=bonds,
                strategy=self.name,
                client_order_id=f"{base}-yes",
                time_in_force="FOK",
                metadata={
                    "leg": "yes",
                    "pair_id": base,
                    "rationale": signal.rationale,
                    "plan": {
                        "yes_avg_price": plan.yes_avg_price,
                        "no_avg_price": plan.no_avg_price,
                        "profit_per_bond": plan.profit_per_bond,
                        "confidence": plan.confidence,
                    },
                },
            ),
            OrderRequest(
                market_condition_id=signal.market.condition_id,
                market_id=0,
                token_id=signal.market.no_token_id,
                market_side=Side.NO,
                order_side=OrderSide.BUY,
                price=plan.no_avg_price,
                size_usd=bonds * plan.no_avg_price,
                shares=bonds,
                strategy=self.name,
                client_order_id=f"{base}-no",
                time_in_force="FOK",
                metadata={"leg": "no", "pair_id": base, "rationale": signal.rationale},
            ),
        ]
        SIGNALS_ACCEPTED.labels(signal_type=signal.signal_type.value).inc()
        return StrategyResult(True, orders, risk=decision)
