"""Portfolio-level decisions.

The risk manager already enforces *per-trade* and *per-strategy* limits. The
optimiser sits one level above and considers the *whole open book*:

  • aggregate exposure by category (politics, crypto, macro, …)
  • naive correlation buckets — same category and same direction overlap risk
  • capital allocation budgets per strategy (so a runaway strategy can't eat the book)
  • position throttling — shrink a candidate when correlated exposure is already heavy

The optimiser is consulted by `RiskManager` after the per-strategy / per-market
gates have passed but before final approval.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from sqlalchemy import select

from app.config import settings
from app.database import session_scope
from app.database.models import Market, Position, PositionStatus, Side
from app.monitoring.logger import get_logger
from app.portfolio.categorizer import categorise

log = get_logger(__name__)


@dataclass
class PortfolioThrottle:
    multiplier: float = 1.0           # 0..1 size multiplier; <1 shrinks the trade
    blocked: bool = False
    reason: str = ""
    category: str = "other"
    category_exposure_usd: float = 0.0
    correlated_exposure_usd: float = 0.0
    strategy_alloc_usd: float = 0.0
    strategy_alloc_used_usd: float = 0.0
    notes: list[str] = field(default_factory=list)


# Strategy → fraction of equity reserved
def _strategy_alloc_fraction(strategy: str) -> float:
    return {
        "overreaction": settings.portfolio_capital_alloc_overreaction,
        "arbitrage": settings.portfolio_capital_alloc_arbitrage,
        "momentum": settings.portfolio_capital_alloc_momentum,
    }.get(strategy, 0.0)


class PortfolioOptimizer:
    """Reads open positions and current market to compute throttles."""

    def evaluate(
        self,
        *,
        strategy: str,
        condition_id: str,
        side: Side,
        question: str,
        slug: str,
        equity_usd: float,
    ) -> PortfolioThrottle:
        category = categorise(question, slug)
        throttle = PortfolioThrottle(category=category)

        with session_scope() as session:
            open_positions = session.execute(
                select(Position, Market)
                .join(Market, Market.id == Position.market_id)
                .where(Position.status == PositionStatus.OPEN)
            ).all()
            session.expunge_all()

        cat_exposure = 0.0
        correlated_exposure = 0.0
        strategy_used = 0.0

        for pos, mkt in open_positions:
            cat = categorise(mkt.question, mkt.slug)
            if cat == category:
                cat_exposure += float(pos.entry_size_usd or 0.0)
                # Same category AND same direction = correlated bucket
                if pos.side == side:
                    correlated_exposure += float(pos.entry_size_usd or 0.0)
            if pos.strategy.split(":", 1)[0] == strategy:
                strategy_used += float(pos.entry_size_usd or 0.0)

        throttle.category_exposure_usd = cat_exposure
        throttle.correlated_exposure_usd = correlated_exposure
        throttle.strategy_alloc_used_usd = strategy_used

        if equity_usd <= 0:
            return throttle

        # --- Strategy capital allocation ---
        alloc_fraction = _strategy_alloc_fraction(strategy)
        if alloc_fraction > 0:
            alloc_usd = equity_usd * alloc_fraction
            throttle.strategy_alloc_usd = alloc_usd
            if strategy_used >= alloc_usd:
                throttle.blocked = True
                throttle.reason = (
                    f"strategy '{strategy}' allocation exhausted: "
                    f"used ${strategy_used:,.0f} / ${alloc_usd:,.0f}"
                )
                return throttle

        # --- Category exposure cap ---
        cat_cap = equity_usd * settings.portfolio_max_category_exposure_pct
        if cat_exposure >= cat_cap:
            throttle.blocked = True
            throttle.reason = (
                f"category '{category}' exposure ${cat_exposure:,.0f} >= cap ${cat_cap:,.0f}"
            )
            return throttle

        # --- Correlation throttle ---
        # If we already have correlated exposure greater than half the category cap,
        # halve the candidate's size (configurable).
        if correlated_exposure > cat_cap * 0.5:
            throttle.multiplier *= settings.portfolio_correlated_throttle_pct
            throttle.notes.append(
                f"correlated bucket loaded (${correlated_exposure:,.0f}) → "
                f"throttle ×{settings.portfolio_correlated_throttle_pct:.2f}"
            )

        # --- Approaching category cap → shrink ---
        room = cat_cap - cat_exposure
        if room < cat_cap * 0.25:
            throttle.multiplier *= 0.5
            throttle.notes.append("approaching category cap — halving size")

        # --- Strategy alloc nearly used → shrink ---
        if alloc_fraction > 0:
            alloc_usd = throttle.strategy_alloc_usd
            if alloc_usd > 0 and (alloc_usd - strategy_used) < alloc_usd * 0.25:
                throttle.multiplier *= 0.5
                throttle.notes.append("approaching strategy allocation cap — halving size")

        # Clamp the multiplier
        throttle.multiplier = max(0.0, min(1.0, throttle.multiplier))
        return throttle
