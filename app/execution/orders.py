"""Order request/result value objects."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from app.database.models import OrderSide, Side, TradeStatus


def new_client_order_id(prefix: str = "bot") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:18]}"


@dataclass
class OrderRequest:
    market_condition_id: str
    market_id: int
    token_id: str
    market_side: Side
    order_side: OrderSide
    price: float
    size_usd: float
    shares: float
    strategy: str
    client_order_id: str = field(default_factory=new_client_order_id)
    post_only: bool = False
    time_in_force: str = "GTC"
    metadata: dict = field(default_factory=dict)

    # Derived fields populated after pairing legs
    position_id: Optional[int] = None
    take_profit: Optional[float] = None
    stop_loss: Optional[float] = None
    max_hold_until: Optional[datetime] = None


@dataclass
class ExecutionResult:
    request: OrderRequest
    status: TradeStatus
    filled_shares: float = 0.0
    filled_price: float = 0.0
    fees_usd: float = 0.0
    exchange_order_id: Optional[str] = None
    error: Optional[str] = None
    filled_at: Optional[datetime] = None
    details: dict = field(default_factory=dict)

    @property
    def filled_notional_usd(self) -> float:
        return self.filled_shares * self.filled_price
