"""In-memory dataclasses used by signal detectors and strategies."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class BookLevel:
    price: float
    size: float  # in shares


@dataclass
class OrderBook:
    bids: list[BookLevel] = field(default_factory=list)  # descending price
    asks: list[BookLevel] = field(default_factory=list)  # ascending price

    @property
    def best_bid(self) -> Optional[float]:
        return self.bids[0].price if self.bids else None

    @property
    def best_ask(self) -> Optional[float]:
        return self.asks[0].price if self.asks else None

    @property
    def mid(self) -> Optional[float]:
        if self.best_bid is None or self.best_ask is None:
            return None
        return (self.best_bid + self.best_ask) / 2.0

    @property
    def spread(self) -> Optional[float]:
        if self.best_bid is None or self.best_ask is None:
            return None
        return self.best_ask - self.best_bid

    def top_liquidity_usd(self, depth: int = 5) -> float:
        """Notional USD resting in the top `depth` levels of both sides."""
        def side_sum(levels: list[BookLevel]) -> float:
            return sum(lv.price * lv.size for lv in levels[:depth])
        return side_sum(self.bids) + side_sum(self.asks)


@dataclass
class MarketQuote:
    condition_id: str
    slug: str
    question: str
    yes_token_id: str
    no_token_id: str
    yes_book: OrderBook
    no_book: OrderBook
    volume_24h: float = 0.0
    end_date: Optional[datetime] = None
    active: bool = True
    closed: bool = False
    raw: dict = field(default_factory=dict)

    @property
    def yes_mid(self) -> Optional[float]:
        return self.yes_book.mid

    @property
    def no_mid(self) -> Optional[float]:
        return self.no_book.mid

    @property
    def yes_ask(self) -> Optional[float]:
        return self.yes_book.best_ask

    @property
    def no_ask(self) -> Optional[float]:
        return self.no_book.best_ask

    @property
    def yes_bid(self) -> Optional[float]:
        return self.yes_book.best_bid

    @property
    def no_bid(self) -> Optional[float]:
        return self.no_book.best_bid

    @property
    def yes_spread(self) -> Optional[float]:
        return self.yes_book.spread

    @property
    def no_spread(self) -> Optional[float]:
        return self.no_book.spread

    @property
    def yes_liquidity_usd(self) -> float:
        return self.yes_book.top_liquidity_usd()

    @property
    def no_liquidity_usd(self) -> float:
        return self.no_book.top_liquidity_usd()
