"""YES/NO arbitrage strategy — always emits two legs to avoid half-executed arbs."""
from __future__ import annotations

from app.config import settings
from app.database.models import OrderSide, Side
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
        edge = signal.edge
        kind = signal.context.get("kind")
        if kind not in ("buy_both", "sell_both"):
            return StrategyResult(False, [], reason="unknown arbitrage kind")

        # Position the arb at min(per-trade cap, visible liquidity on each leg).
        per_trade_cap = current_equity_usd * settings.max_position_pct
        leg_liquidity = signal.liquidity_usd
        notional_cap = min(per_trade_cap, leg_liquidity * 0.25)
        if notional_cap < settings.min_liquidity_usd / 10:
            return StrategyResult(False, [], reason="Arb notional below minimum")

        decision = self.risk.check(
            strategy=self.name,
            suggested_size_usd=notional_cap,
            edge_mispricing=edge.mispricing,
            edge_ev=edge.ev,
            liquidity_usd=leg_liquidity,
            spread=None,
            current_equity_usd=current_equity_usd,
        )
        if not decision.approved:
            return StrategyResult(False, [], reason=decision.reason, risk=decision)

        notional = decision.size_usd
        yes_price = float(signal.context["yes_price"])
        no_price = float(signal.context["no_price"])

        if yes_price <= 0 or no_price <= 0 or yes_price >= 1 or no_price >= 1:
            return StrategyResult(False, [], reason="invalid leg prices")

        # For buy_both: 1$ bond = 1 yes share + 1 no share.
        # Notional spent per bond = yes_price + no_price. Shares per bond = 1.
        # For sell_both: we need 1 yes + 1 no in inventory before selling; we skip
        # that path unless we already hold matching shares. The current bot is
        # long-only so we only emit buy_both.

        if kind != "buy_both":
            return StrategyResult(False, [], reason="Only buy_both arbitrage supported (inventory-free)")

        price_sum = yes_price + no_price
        bonds = notional / price_sum
        bonds = max(1.0, round(bonds))  # 1-share increments
        if bonds < 1:
            return StrategyResult(False, [], reason="Arb below 1 bond")

        base = new_client_order_id(prefix="arb")
        orders = [
            OrderRequest(
                market_condition_id=signal.market.condition_id,
                market_id=0,
                token_id=signal.market.yes_token_id,
                market_side=Side.YES,
                order_side=OrderSide.BUY,
                price=yes_price,
                size_usd=bonds * yes_price,
                shares=bonds,
                strategy=self.name,
                client_order_id=f"{base}-yes",
                time_in_force="FOK",
                metadata={"leg": "yes", "pair_id": base, "rationale": signal.rationale},
            ),
            OrderRequest(
                market_condition_id=signal.market.condition_id,
                market_id=0,
                token_id=signal.market.no_token_id,
                market_side=Side.NO,
                order_side=OrderSide.BUY,
                price=no_price,
                size_usd=bonds * no_price,
                shares=bonds,
                strategy=self.name,
                client_order_id=f"{base}-no",
                time_in_force="FOK",
                metadata={"leg": "no", "pair_id": base, "rationale": signal.rationale},
            ),
        ]
        SIGNALS_ACCEPTED.labels(signal_type=signal.signal_type.value).inc()
        return StrategyResult(True, orders, risk=decision)
