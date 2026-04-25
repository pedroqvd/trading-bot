"""Pydantic v2 response schemas for the public API."""
from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field


Period = Literal["24h", "7d", "30d", "all"]


class MetricsResponse(BaseModel):
    period: Period
    total_pnl_usd: float
    realized_today_usd: float
    win_rate: float
    total_trades: int
    avg_ev_usd: float
    expectancy_usd: float
    profit_factor: float
    sharpe: float
    sortino: float
    max_drawdown_pct: float
    open_positions: int
    equity_usd: float
    cash_usd: float
    by_strategy: list["StrategyBreakdown"]


class StrategyBreakdown(BaseModel):
    strategy: str
    trades: int
    win_rate: float
    expectancy_usd: float
    total_pnl_usd: float
    profit_factor: float
    avg_hold_minutes: float
    state: str = "HEALTHY"     # edge_health verdict
    reason: str = ""


class EquityPoint(BaseModel):
    time: datetime
    equity: float
    cash: float
    unrealized: float


class EquityResponse(BaseModel):
    period: Period
    points: list[EquityPoint]


class PositionResponse(BaseModel):
    id: int
    market_question: str
    market_slug: str
    strategy: str
    side: str
    status: str
    entry_price: float
    entry_size_usd: float
    shares: float
    take_profit: Optional[float]
    stop_loss: Optional[float]
    opened_at: datetime
    closed_at: Optional[datetime]
    exit_price: Optional[float]
    realized_pnl_usd: Optional[float]


class TradeResponse(BaseModel):
    id: int
    client_order_id: str
    market_question: str
    strategy: str
    market_side: str
    order_side: str
    status: str
    price: float
    size_usd: float
    shares: float
    filled_shares: float
    created_at: datetime
    filled_at: Optional[datetime]


class BotStatus(BaseModel):
    running: bool
    started_at: Optional[datetime]
    last_loop_at: Optional[datetime]
    last_error: Optional[str] = None
    open_positions: int
    equity_usd: float
    dry_run: bool
    live_trading_enabled: bool


class BotControlResponse(BaseModel):
    running: bool
    message: str


# Allow forward refs
MetricsResponse.model_rebuild()
