"""Strategy contract — converts an approved signal into concrete orders."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

from app.execution.orders import OrderRequest
from app.risk.risk_manager import RiskDecision
from app.signals.base import SignalCandidate


@dataclass
class StrategyResult:
    approved: bool
    orders: list[OrderRequest]
    reason: str = ""
    risk: Optional[RiskDecision] = None


class Strategy(ABC):
    name: str

    @abstractmethod
    def plan(self, signal: SignalCandidate, current_equity_usd: float) -> StrategyResult:
        ...
