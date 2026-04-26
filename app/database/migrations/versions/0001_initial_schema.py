"""Initial schema — markets, quotes, signals, positions, trades, equity_snapshots, risk_events.

Revision ID: 0001
Revises:
Create Date: 2025-01-01 00:00:00.000000
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "markets",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("condition_id", sa.String(length=128), nullable=False),
        sa.Column("slug", sa.String(length=256), nullable=False),
        sa.Column("question", sa.String(length=1024), nullable=False),
        sa.Column("yes_token_id", sa.String(length=128), nullable=True),
        sa.Column("no_token_id", sa.String(length=128), nullable=True),
        sa.Column("end_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("closed", sa.Boolean(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("meta", sa.JSON(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_markets_condition_id", "markets", ["condition_id"], unique=True)
    op.create_index("ix_markets_slug", "markets", ["slug"])

    op.create_table(
        "quotes",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("market_id", sa.Integer(), nullable=False),
        sa.Column("ts", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("yes_bid", sa.Float(), nullable=True),
        sa.Column("yes_ask", sa.Float(), nullable=True),
        sa.Column("no_bid", sa.Float(), nullable=True),
        sa.Column("no_ask", sa.Float(), nullable=True),
        sa.Column("yes_mid", sa.Float(), nullable=True),
        sa.Column("no_mid", sa.Float(), nullable=True),
        sa.Column("yes_liquidity", sa.Float(), nullable=True),
        sa.Column("no_liquidity", sa.Float(), nullable=True),
        sa.Column("volume_24h", sa.Float(), nullable=True),
        sa.ForeignKeyConstraint(["market_id"], ["markets.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_quotes_ts", "quotes", ["ts"])
    op.create_index("ix_quotes_market_time", "quotes", ["market_id", "ts"])

    op.create_table(
        "signals",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("market_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("signal_type", sa.Enum("OVERREACTION", "ARBITRAGE", "MOMENTUM", name="signaltype"), nullable=False),
        sa.Column("side", sa.Enum("YES", "NO", name="side"), nullable=False),
        sa.Column("prob_market", sa.Float(), nullable=False),
        sa.Column("prob_real", sa.Float(), nullable=False),
        sa.Column("mispricing", sa.Float(), nullable=False),
        sa.Column("expected_value", sa.Float(), nullable=False),
        sa.Column("kelly_fraction", sa.Float(), nullable=False),
        sa.Column("suggested_size_usd", sa.Float(), nullable=False),
        sa.Column("consumed", sa.Boolean(), nullable=False),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["market_id"], ["markets.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_signals_market_created", "signals", ["market_id", "created_at"])

    op.create_table(
        "positions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("market_id", sa.Integer(), nullable=False),
        sa.Column("strategy", sa.String(length=64), nullable=False),
        sa.Column("side", sa.Enum("YES", "NO", name="side"), nullable=False),
        sa.Column("status", sa.Enum("OPEN", "CLOSED", "LIQUIDATED", name="positionstatus"), nullable=False),
        sa.Column("entry_price", sa.Float(), nullable=False),
        sa.Column("entry_size_usd", sa.Float(), nullable=False),
        sa.Column("shares", sa.Float(), nullable=False),
        sa.Column("take_profit", sa.Float(), nullable=True),
        sa.Column("stop_loss", sa.Float(), nullable=True),
        sa.Column("max_hold_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("exit_price", sa.Float(), nullable=True),
        sa.Column("realized_pnl_usd", sa.Float(), nullable=True),
        sa.Column("opened_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("signal_id", sa.Integer(), nullable=True),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["market_id"], ["markets.id"]),
        sa.ForeignKeyConstraint(["signal_id"], ["signals.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_positions_market_id", "positions", ["market_id"])
    op.create_index("ix_positions_status", "positions", ["status"])
    op.create_index("ix_positions_strategy", "positions", ["strategy"])

    op.create_table(
        "trades",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("position_id", sa.Integer(), nullable=True),
        sa.Column("market_id", sa.Integer(), nullable=False),
        sa.Column("order_side", sa.Enum("BUY", "SELL", name="orderside"), nullable=False),
        sa.Column("market_side", sa.Enum("YES", "NO", name="side"), nullable=False),
        sa.Column("status", sa.Enum("PENDING", "FILLED", "PARTIAL", "CANCELED", "FAILED", name="tradestatus"), nullable=False),
        sa.Column("price", sa.Float(), nullable=False),
        sa.Column("size_usd", sa.Float(), nullable=False),
        sa.Column("shares", sa.Float(), nullable=False),
        sa.Column("filled_shares", sa.Float(), nullable=False),
        sa.Column("fees_usd", sa.Float(), nullable=False),
        sa.Column("client_order_id", sa.String(length=96), nullable=False),
        sa.Column("exchange_order_id", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("filled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", sa.String(length=512), nullable=True),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["market_id"], ["markets.id"]),
        sa.ForeignKeyConstraint(["position_id"], ["positions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("client_order_id", name="uq_trades_client_order_id"),
    )
    op.create_index("ix_trades_client_order_id", "trades", ["client_order_id"])
    op.create_index("ix_trades_position", "trades", ["position_id"])
    op.create_index("ix_trades_status", "trades", ["status"])

    op.create_table(
        "equity_snapshots",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("ts", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("cash_usd", sa.Float(), nullable=False),
        sa.Column("unrealized_usd", sa.Float(), nullable=False),
        sa.Column("equity_usd", sa.Float(), nullable=False),
        sa.Column("realized_today_usd", sa.Float(), nullable=False),
        sa.Column("open_positions", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_equity_snapshots_ts", "equity_snapshots", ["ts"])

    op.create_table(
        "risk_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("ts", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("kind", sa.String(length=64), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False),
        sa.Column("message", sa.String(length=1024), nullable=False),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_risk_events_ts", "risk_events", ["ts"])
    op.create_index("ix_risk_events_kind", "risk_events", ["kind"])


def downgrade() -> None:
    op.drop_table("risk_events")
    op.drop_table("equity_snapshots")
    op.drop_table("trades")
    op.drop_table("positions")
    op.drop_table("signals")
    op.drop_table("quotes")
    op.drop_table("markets")
    op.execute("DROP TYPE IF EXISTS tradestatus")
    op.execute("DROP TYPE IF EXISTS positionstatus")
    op.execute("DROP TYPE IF EXISTS orderside")
    op.execute("DROP TYPE IF EXISTS signaltype")
    op.execute("DROP TYPE IF EXISTS side")
