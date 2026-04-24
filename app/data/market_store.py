"""Persist markets and quotes to the database."""
from __future__ import annotations

from datetime import timedelta
from typing import Iterable

from sqlalchemy import select

from app.data.polymarket_client import PolymarketClient
from app.data.schemas import MarketQuote
from app.database import session_scope
from app.database.models import Market, Quote
from app.monitoring.logger import get_logger
from app.utils.time_utils import utcnow

log = get_logger(__name__)


class MarketStore:
    def __init__(self, client: PolymarketClient) -> None:
        self.client = client

    def refresh_universe(self, max_markets: int = 500) -> list[MarketQuote]:
        """Pull active markets + books and persist a lightweight snapshot.

        Returns the in-memory quotes for the signal layer — the DB copy is only
        used for auditing, backtests, and restart resilience.
        """
        markets = list(self.client.iter_active_markets(batch_size=100, max_total=max_markets))
        if not markets:
            log.warning("market_store.no_markets_returned")
            return []

        quotes: list[MarketQuote] = []
        token_ids: list[str] = []
        for m in markets:
            tokens = PolymarketClient._token_ids(m)
            token_ids.extend(tokens)

        books = self._batched_books(token_ids)

        for m in markets:
            quote = self.client.build_quote(m, books)
            if quote is None:
                continue
            if quote.yes_mid is None or quote.no_mid is None:
                continue
            quotes.append(quote)

        self._persist(quotes)
        log.info("market_store.refreshed", count=len(quotes), total_markets=len(markets))
        return quotes

    def _batched_books(self, token_ids: list[str], batch: int = 50) -> dict:
        out: dict = {}
        for i in range(0, len(token_ids), batch):
            chunk = token_ids[i:i + batch]
            out.update(self.client.get_orderbooks(chunk))
        return out

    def _persist(self, quotes: Iterable[MarketQuote]) -> None:
        with session_scope() as session:
            for q in quotes:
                market = session.execute(
                    select(Market).where(Market.condition_id == q.condition_id)
                ).scalar_one_or_none()
                if market is None:
                    market = Market(
                        condition_id=q.condition_id,
                        slug=q.slug,
                        question=q.question,
                        yes_token_id=q.yes_token_id,
                        no_token_id=q.no_token_id,
                        end_date=q.end_date,
                        active=q.active,
                        closed=q.closed,
                        meta={},
                    )
                    session.add(market)
                    session.flush()
                else:
                    market.slug = q.slug or market.slug
                    market.question = q.question or market.question
                    market.yes_token_id = q.yes_token_id or market.yes_token_id
                    market.no_token_id = q.no_token_id or market.no_token_id
                    market.end_date = q.end_date or market.end_date
                    market.active = q.active
                    market.closed = q.closed
                    market.last_seen_at = utcnow()

                session.add(Quote(
                    market_id=market.id,
                    ts=utcnow(),
                    yes_bid=q.yes_bid,
                    yes_ask=q.yes_ask,
                    no_bid=q.no_bid,
                    no_ask=q.no_ask,
                    yes_mid=q.yes_mid,
                    no_mid=q.no_mid,
                    yes_liquidity=q.yes_liquidity_usd,
                    no_liquidity=q.no_liquidity_usd,
                    volume_24h=q.volume_24h,
                ))

    # -----------------------------------------------------------------------
    # History lookups used by overreaction detector
    # -----------------------------------------------------------------------
    def recent_quotes(self, market_id: int, minutes: int) -> list[Quote]:
        cutoff = utcnow() - timedelta(minutes=minutes)
        with session_scope() as session:
            rows = session.execute(
                select(Quote)
                .where(Quote.market_id == market_id, Quote.ts >= cutoff)
                .order_by(Quote.ts.asc())
            ).scalars().all()
            # detach
            session.expunge_all()
            return list(rows)

    def get_market_id(self, condition_id: str) -> int | None:
        with session_scope() as session:
            market = session.execute(
                select(Market).where(Market.condition_id == condition_id)
            ).scalar_one_or_none()
            return market.id if market else None
