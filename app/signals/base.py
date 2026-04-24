"""Signal detector contract."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Iterable

from app.data.schemas import MarketQuote
from app.database.models import Side, SignalType
from app.utils.math_utils import EdgeSnapshot


@dataclass
class SignalCandidate:
    """A trading opportunity surfaced by a detector.

    The detector's sole responsibility is identifying *where* the market is
    wrong. Sizing, risk, and execution are downstream.
    """
    signal_type: SignalType
    strategy: str
    market: MarketQuote
    side: Side
    edge: EdgeSnapshot
    liquidity_usd: float
    spread: float | None
    rationale: str
    context: dict = field(default_factory=dict)


class SignalDetector(ABC):
    name: str

    @abstractmethod
    def scan(self, markets: Iterable[MarketQuote]) -> list[SignalCandidate]:
        ...
