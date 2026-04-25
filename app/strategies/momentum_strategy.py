"""Momentum strategy — Kelly-sized continuation entry."""
from __future__ import annotations

from datetime import timedelta

from app.config import settings
from app.database.models import OrderSide, Side
from app.execution.orders import OrderRequest, new_client_order_id
from app.monitoring.logger import get_logger
from app.monitoring.metrics import SIGNALS_ACCEPTED
from app.risk.position_sizing import suggested_size_usd
from app.risk.risk_manager import RiskManager
from app.signals.base import SignalCandidate
from app.strategies.base import Strategy, StrategyResult
from app.utils.math_utils import clamp
from app.utils.time_utils import utcnow

log = get_logger(__name__)


class MomentumStrategy(Strategy):
    name = "momentum"

    def __init__(self, risk: RiskManager) -> None:
        self.risk = risk

    def plan(self, signal: SignalCandidate, current_equity_usd: float) -> StrategyResult:
        edge = signal.edge
        price = edge.price
        if not (0 < price < 1):
            return StrategyResult(False, [], reason="invalid price")

        raw_size = suggested_size_usd(
            prob_real=edge.prob_real,
            price=price,
            capital_usd=current_equity_usd,
            liquidity_usd=signal.liquidity_usd,
        )

        decision = self.risk.check(
            strategy=self.name,
            condition_id=signal.market.condition_id,
            suggested_size_usd=raw_size,
            edge_mispricing=edge.mispricing,
            edge_ev=edge.ev,
            liquidity_usd=signal.liquidity_usd,
            spread=signal.spread,
            current_equity_usd=current_equity_usd,
            quality_score=signal.context.get("momentum_score"),
            side=signal.side,
            question=signal.market.question,
            slug=signal.market.slug,
            realized_vol=float(signal.context.get("realized_vol", 0.0) or 0.0),
        )
        if not decision.approved:
            log.info("strategy.momentum.rejected",
                     market=signal.market.slug, reason=decision.reason)
            return StrategyResult(False, [], reason=decision.reason, risk=decision)

        shares = decision.size_usd / price
        if shares < 1:
            return StrategyResult(False, [], reason="size < 1 share", risk=decision)

        entry_price = clamp(price, 0.0001, 0.9999)
        # Tighter take/stop than overreaction — momentum is shorter-lived.
        take_profit = clamp(entry_price + settings.momentum_take_profit, 0.0001, 0.9999)
        stop_loss = clamp(entry_price - settings.momentum_stop_loss, 0.0001, 0.9999)
        max_hold_until = utcnow() + timedelta(minutes=settings.momentum_max_hold_minutes)

        token_id = (signal.market.yes_token_id
                    if signal.side == Side.YES else signal.market.no_token_id)

        request = OrderRequest(
            market_condition_id=signal.market.condition_id,
            market_id=0,
            token_id=token_id,
            market_side=signal.side,
            order_side=OrderSide.BUY,
            price=entry_price,
            size_usd=shares * entry_price,
            shares=shares,
            strategy=self.name,
            client_order_id=new_client_order_id(prefix="mom"),
            metadata={
                "rationale": signal.rationale,
                "edge": {
                    "prob_real": edge.prob_real,
                    "prob_market": edge.prob_market,
                    "mispricing": edge.mispricing,
                    "ev": edge.ev,
                    "kelly": edge.kelly,
                },
                "context": signal.context,
            },
            take_profit=take_profit,
            stop_loss=stop_loss,
            max_hold_until=max_hold_until,
        )
        SIGNALS_ACCEPTED.labels(signal_type=signal.signal_type.value).inc()
        return StrategyResult(True, [request], risk=decision)
