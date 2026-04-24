"""Persistent domain models."""
from __future__ import annotations

import enum
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.session import Base


class Side(str, enum.Enum):
    YES = "YES"
    NO = "NO"


class OrderSide(str, enum.Enum):
    BUY = "BUY"
    SELL = "SELL"


class PositionStatus(str, enum.Enum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"
    LIQUIDATED = "LIQUIDATED"


class TradeStatus(str, enum.Enum):
    PENDING = "PENDING"
    FILLED = "FILLED"
    PARTIAL = "PARTIAL"
    CANCELED = "CANCELED"
    FAILED = "FAILED"


class SignalType(str, enum.Enum):
    OVERREACTION = "OVERREACTION"
    ARBITRAGE = "ARBITRAGE"


class Market(Base):
    __tablename__ = "markets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    condition_id: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    slug: Mapped[str] = mapped_column(String(256), index=True)
    question: Mapped[str] = mapped_column(String(1024))
    yes_token_id: Mapped[Optional[str]] = mapped_column(String(128))
    no_token_id: Mapped[Optional[str]] = mapped_column(String(128))
    end_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    closed: Mapped[bool] = mapped_column(Boolean, default=False)
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    meta: Mapped[dict] = mapped_column(JSON, default=dict)

    quotes: Mapped[list["Quote"]] = relationship(back_populates="market", cascade="all, delete-orphan")
    signals: Mapped[list["Signal"]] = relationship(back_populates="market", cascade="all, delete-orphan")
    positions: Mapped[list["Position"]] = relationship(back_populates="market")


class Quote(Base):
    """Snapshot of best bid/ask and mid prices for a market at a point in time."""
    __tablename__ = "quotes"
    __table_args__ = (Index("ix_quotes_market_time", "market_id", "ts"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    market_id: Mapped[int] = mapped_column(ForeignKey("markets.id", ondelete="CASCADE"), index=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)

    yes_bid: Mapped[Optional[float]] = mapped_column(Float)
    yes_ask: Mapped[Optional[float]] = mapped_column(Float)
    no_bid: Mapped[Optional[float]] = mapped_column(Float)
    no_ask: Mapped[Optional[float]] = mapped_column(Float)
    yes_mid: Mapped[Optional[float]] = mapped_column(Float)
    no_mid: Mapped[Optional[float]] = mapped_column(Float)
    yes_liquidity: Mapped[Optional[float]] = mapped_column(Float)
    no_liquidity: Mapped[Optional[float]] = mapped_column(Float)
    volume_24h: Mapped[Optional[float]] = mapped_column(Float)

    market: Mapped[Market] = relationship(back_populates="quotes")


class Signal(Base):
    __tablename__ = "signals"
    __table_args__ = (Index("ix_signals_market_created", "market_id", "created_at"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    market_id: Mapped[int] = mapped_column(ForeignKey("markets.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    signal_type: Mapped[SignalType] = mapped_column(Enum(SignalType))
    side: Mapped[Side] = mapped_column(Enum(Side))

    prob_market: Mapped[float] = mapped_column(Float)
    prob_real: Mapped[float] = mapped_column(Float)
    mispricing: Mapped[float] = mapped_column(Float)
    expected_value: Mapped[float] = mapped_column(Float)
    kelly_fraction: Mapped[float] = mapped_column(Float)
    suggested_size_usd: Mapped[float] = mapped_column(Float)

    consumed: Mapped[bool] = mapped_column(Boolean, default=False)
    details: Mapped[dict] = mapped_column(JSON, default=dict)

    market: Mapped[Market] = relationship(back_populates="signals")


class Position(Base):
    __tablename__ = "positions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    market_id: Mapped[int] = mapped_column(ForeignKey("markets.id"), index=True)
    strategy: Mapped[str] = mapped_column(String(64), index=True)
    side: Mapped[Side] = mapped_column(Enum(Side))
    status: Mapped[PositionStatus] = mapped_column(Enum(PositionStatus), default=PositionStatus.OPEN, index=True)

    entry_price: Mapped[float] = mapped_column(Float)
    entry_size_usd: Mapped[float] = mapped_column(Float)
    shares: Mapped[float] = mapped_column(Float)
    take_profit: Mapped[Optional[float]] = mapped_column(Float)
    stop_loss: Mapped[Optional[float]] = mapped_column(Float)
    max_hold_until: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    exit_price: Mapped[Optional[float]] = mapped_column(Float)
    realized_pnl_usd: Mapped[Optional[float]] = mapped_column(Float)

    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    closed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    signal_id: Mapped[Optional[int]] = mapped_column(ForeignKey("signals.id"))
    details: Mapped[dict] = mapped_column(JSON, default=dict)

    market: Mapped[Market] = relationship(back_populates="positions")
    trades: Mapped[list["Trade"]] = relationship(back_populates="position", cascade="all, delete-orphan")


class Trade(Base):
    """Concrete order fill associated with opening/closing a position."""
    __tablename__ = "trades"
    __table_args__ = (
        UniqueConstraint("client_order_id", name="uq_trades_client_order_id"),
        Index("ix_trades_position", "position_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    position_id: Mapped[Optional[int]] = mapped_column(ForeignKey("positions.id", ondelete="CASCADE"), index=True)
    market_id: Mapped[int] = mapped_column(ForeignKey("markets.id"), index=True)

    order_side: Mapped[OrderSide] = mapped_column(Enum(OrderSide))
    market_side: Mapped[Side] = mapped_column(Enum(Side))
    status: Mapped[TradeStatus] = mapped_column(Enum(TradeStatus), default=TradeStatus.PENDING, index=True)

    price: Mapped[float] = mapped_column(Float)
    size_usd: Mapped[float] = mapped_column(Float)
    shares: Mapped[float] = mapped_column(Float)
    filled_shares: Mapped[float] = mapped_column(Float, default=0.0)
    fees_usd: Mapped[float] = mapped_column(Float, default=0.0)

    client_order_id: Mapped[str] = mapped_column(String(96), index=True)
    exchange_order_id: Mapped[Optional[str]] = mapped_column(String(128))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    filled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    error: Mapped[Optional[str]] = mapped_column(String(512))
    details: Mapped[dict] = mapped_column(JSON, default=dict)

    position: Mapped[Optional[Position]] = relationship(back_populates="trades")


class EquitySnapshot(Base):
    """Per-interval equity curve snapshot for drawdown and Sharpe computation."""
    __tablename__ = "equity_snapshots"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    cash_usd: Mapped[float] = mapped_column(Float)
    unrealized_usd: Mapped[float] = mapped_column(Float)
    equity_usd: Mapped[float] = mapped_column(Float)
    realized_today_usd: Mapped[float] = mapped_column(Float, default=0.0)
    open_positions: Mapped[int] = mapped_column(Integer, default=0)


class RiskEvent(Base):
    """Circuit-breaker and kill-switch events."""
    __tablename__ = "risk_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    kind: Mapped[str] = mapped_column(String(64), index=True)
    severity: Mapped[str] = mapped_column(String(16))
    message: Mapped[str] = mapped_column(String(1024))
    details: Mapped[dict] = mapped_column(JSON, default=dict)
