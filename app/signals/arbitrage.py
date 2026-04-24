"""YES/NO arbitrage detector.

Binary prediction markets satisfy p(YES) + p(NO) = 1 at expiration. While open,
the best *ask* prices sometimes sum to less than 1 (mis-pricing against you on
both sides taken together as a synthetic bond) or the best *bid* prices sum to
more than 1 (synthetic short exceeds notional). Either creates a near-riskless
arb after paying the spread.
"""
from __future__ import annotations

from typing import Iterable

from app.config import settings
from app.data.schemas import MarketQuote
from app.database.models import Side, SignalType
from app.monitoring.metrics import SIGNALS_DETECTED
from app.signals.base import SignalCandidate, SignalDetector
from app.utils.math_utils import EdgeSnapshot


class ArbitrageDetector(SignalDetector):
    name = "arbitrage"

    def scan(self, markets: Iterable[MarketQuote]) -> list[SignalCandidate]:
        out: list[SignalCandidate] = []
        for m in markets:
            out.extend(self._evaluate(m))
        return out

    # -----------------------------------------------------------------------
    def _evaluate(self, m: MarketQuote) -> list[SignalCandidate]:
        yes_ask, no_ask = m.yes_ask, m.no_ask
        yes_bid, no_bid = m.yes_bid, m.no_bid
        if None in (yes_ask, no_ask, yes_bid, no_bid):
            return []

        results: list[SignalCandidate] = []

        # --- Underpriced composite: YES + NO asks < 1 → buy both, earn (1 - sum)
        ask_sum = yes_ask + no_ask
        if ask_sum < 1 - settings.arbitrage_min_edge:
            profit_per_dollar = 1.0 - ask_sum
            # We represent this as two YES+NO buy legs. The "signal" here is a
            # symmetric pair — we emit one candidate tagged with both legs and
            # let the strategy handle dual execution.
            edge_yes = EdgeSnapshot.build(prob_real=1.0, price=yes_ask, kelly_mult=1.0)
            edge_no = EdgeSnapshot.build(prob_real=1.0, price=no_ask, kelly_mult=1.0)
            # Use YES side as the canonical edge carrier; arbitrage strategy
            # reads context for both legs.
            SIGNALS_DETECTED.labels(signal_type=SignalType.ARBITRAGE.value).inc()
            results.append(SignalCandidate(
                signal_type=SignalType.ARBITRAGE,
                strategy=self.name,
                market=m,
                side=Side.YES,
                edge=EdgeSnapshot(
                    prob_market=ask_sum,
                    prob_real=1.0,
                    price=ask_sum,
                    mispricing=profit_per_dollar,
                    ev=profit_per_dollar,
                    kelly=profit_per_dollar,  # riskless => full Kelly is capped later
                ),
                liquidity_usd=min(m.yes_liquidity_usd, m.no_liquidity_usd),
                spread=None,
                rationale=(
                    f"YES+NO asks = {ask_sum:.4f}; composite underpriced by "
                    f"{profit_per_dollar:.4f} per $1 synthetic bond"
                ),
                context={
                    "kind": "buy_both",
                    "yes_price": yes_ask,
                    "no_price": no_ask,
                    "ask_sum": ask_sum,
                    "profit_per_dollar": profit_per_dollar,
                    "leg_edges": {"yes": edge_yes.__dict__, "no": edge_no.__dict__},
                },
            ))

        # --- Overpriced composite: YES bid + NO bid > 1 → sell both (requires holding shares)
        bid_sum = yes_bid + no_bid
        if bid_sum > 1 + settings.arbitrage_min_edge:
            profit_per_dollar = bid_sum - 1.0
            SIGNALS_DETECTED.labels(signal_type=SignalType.ARBITRAGE.value).inc()
            results.append(SignalCandidate(
                signal_type=SignalType.ARBITRAGE,
                strategy=self.name,
                market=m,
                side=Side.YES,  # canonical; strategy reads context
                edge=EdgeSnapshot(
                    prob_market=bid_sum,
                    prob_real=1.0,
                    price=bid_sum,
                    mispricing=profit_per_dollar,
                    ev=profit_per_dollar,
                    kelly=profit_per_dollar,
                ),
                liquidity_usd=min(m.yes_liquidity_usd, m.no_liquidity_usd),
                spread=None,
                rationale=(
                    f"YES+NO bids = {bid_sum:.4f}; composite overpriced by "
                    f"{profit_per_dollar:.4f} per $1 synthetic short"
                ),
                context={
                    "kind": "sell_both",
                    "yes_price": yes_bid,
                    "no_price": no_bid,
                    "bid_sum": bid_sum,
                    "profit_per_dollar": profit_per_dollar,
                },
            ))

        return results
