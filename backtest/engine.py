"""Deterministic backtesting engine.

Loads historical quotes from the DB (or a user-provided DataFrame), replays
them through the same signal detectors, strategies, and risk manager that
production uses, and simulates executions with the configured slippage/fees.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Iterable, Optional

from app.config import settings
from app.data.schemas import BookLevel, MarketQuote, OrderBook
from app.database.models import Side
from app.signals.arbitrage import ArbitrageDetector
from app.signals.base import SignalCandidate
from app.utils.math_utils import EdgeSnapshot, fractional_kelly, slippage_adjust


@dataclass
class HistoricalTick:
    ts: datetime
    condition_id: str
    slug: str
    question: str
    yes_token_id: str
    no_token_id: str
    yes_bid: float
    yes_ask: float
    no_bid: float
    no_ask: float
    volume_24h: float = 0.0
    depth_usd: float = 1000.0

    def as_quote(self) -> MarketQuote:
        return MarketQuote(
            condition_id=self.condition_id,
            slug=self.slug,
            question=self.question,
            yes_token_id=self.yes_token_id,
            no_token_id=self.no_token_id,
            yes_book=OrderBook(
                bids=[BookLevel(self.yes_bid, self.depth_usd / max(self.yes_bid, 0.01))],
                asks=[BookLevel(self.yes_ask, self.depth_usd / max(self.yes_ask, 0.01))],
            ),
            no_book=OrderBook(
                bids=[BookLevel(self.no_bid, self.depth_usd / max(self.no_bid, 0.01))],
                asks=[BookLevel(self.no_ask, self.depth_usd / max(self.no_ask, 0.01))],
            ),
            volume_24h=self.volume_24h,
        )


@dataclass
class BacktestPosition:
    strategy: str
    condition_id: str
    side: Side
    entry_ts: datetime
    entry_price: float
    shares: float
    take_profit: Optional[float]
    stop_loss: Optional[float]
    max_hold_until: Optional[datetime]


@dataclass
class BacktestReport:
    trades: int = 0
    wins: int = 0
    losses: int = 0
    gross_win_usd: float = 0.0
    gross_loss_usd: float = 0.0
    total_pnl_usd: float = 0.0
    equity_curve: list[tuple[datetime, float]] = field(default_factory=list)
    trade_log: list[dict] = field(default_factory=list)

    @property
    def win_rate(self) -> float:
        return (self.wins / self.trades) if self.trades else 0.0

    @property
    def expectancy_usd(self) -> float:
        return (self.total_pnl_usd / self.trades) if self.trades else 0.0

    @property
    def profit_factor(self) -> float:
        return (self.gross_win_usd / self.gross_loss_usd) if self.gross_loss_usd else float("inf")


class BacktestEngine:
    """Replays historical ticks through the overreaction + arbitrage playbook.

    Uses simplified in-memory detectors (does not write to the DB). The core
    math (EV, Kelly, sizing, slippage) is shared with production.
    """

    def __init__(self, ticks: Iterable[HistoricalTick], initial_capital: float | None = None) -> None:
        self.ticks = list(ticks)
        self.capital = initial_capital or settings.capital_usd
        self.cash = self.capital
        self.positions: list[BacktestPosition] = []
        self.report = BacktestReport()

        self._price_history: dict[str, list[tuple[datetime, float]]] = {}
        self._arb = ArbitrageDetector()

    # -----------------------------------------------------------------------
    def run(self) -> BacktestReport:
        for tick in sorted(self.ticks, key=lambda t: t.ts):
            self._on_tick(tick)
        # Force-close any remaining positions at last observed mid
        for pos in list(self.positions):
            last = self._last_mid(pos.condition_id, pos.side)
            if last is not None:
                self._close_position(pos, last, self.ticks[-1].ts, "final_close")
        return self.report

    # -----------------------------------------------------------------------
    def _on_tick(self, tick: HistoricalTick) -> None:
        q = tick.as_quote()
        self._push_history(tick)
        self._check_exits(tick, q)

        # Arbitrage
        for s in self._arb.scan([q]):
            self._enter_arb(s, tick)

        # Overreaction — lightweight inline version that uses the in-memory history
        self._maybe_enter_overreaction(tick, q)

        # Mark equity
        equity = self._mark_equity(tick)
        self.report.equity_curve.append((tick.ts, equity))

    def _push_history(self, tick: HistoricalTick) -> None:
        lst = self._price_history.setdefault(tick.condition_id, [])
        lst.append((tick.ts, (tick.yes_bid + tick.yes_ask) / 2))
        cutoff = tick.ts - timedelta(minutes=settings.overreaction_window_minutes * 3)
        while lst and lst[0][0] < cutoff:
            lst.pop(0)

    def _last_mid(self, condition_id: str, side: Side) -> float | None:
        hist = self._price_history.get(condition_id) or []
        if not hist:
            return None
        last = hist[-1][1]
        return last if side == Side.YES else (1.0 - last)

    # -----------------------------------------------------------------------
    def _maybe_enter_overreaction(self, tick: HistoricalTick, q: MarketQuote) -> None:
        hist = self._price_history.get(tick.condition_id) or []
        if len(hist) < 3:
            return
        window_start = tick.ts - timedelta(minutes=settings.overreaction_window_minutes)
        anchor = next((price for ts, price in hist if ts >= window_start), None)
        if anchor is None or anchor <= 0 or anchor >= 1:
            return
        yes_mid = (tick.yes_bid + tick.yes_ask) / 2
        if not (0.05 <= yes_mid <= 0.95):
            return
        move = yes_mid - anchor
        rel_move = move / anchor
        if abs(rel_move) < settings.overreaction_move_pct:
            return

        reversion = settings.overreaction_reversion_target
        target = yes_mid - reversion * move
        if move > 0:
            side = Side.NO
            price = tick.no_ask
            prob_real = 1.0 - target
        else:
            side = Side.YES
            price = tick.yes_ask
            prob_real = target

        if not (0 < price < 1 and 0 < prob_real < 1):
            return

        edge = EdgeSnapshot.build(prob_real=prob_real, price=price, kelly_mult=1.0)
        if edge.mispricing < settings.min_mispricing or edge.ev < settings.min_expected_value:
            return

        raw_size = self.cash * fractional_kelly(prob_real, price, settings.kelly_fraction)
        size = min(raw_size, self.capital * settings.max_position_pct, tick.depth_usd * 0.25)
        if size < 1:
            return
        fill_price = slippage_adjust(price, "BUY", settings.slippage_bps)
        shares = size / fill_price
        if shares < 1:
            return
        self.cash -= shares * fill_price

        take_profit = min(0.99, fill_price + settings.overreaction_take_profit)
        stop_loss = max(0.01, fill_price - settings.overreaction_stop_loss)

        self.positions.append(BacktestPosition(
            strategy="overreaction",
            condition_id=tick.condition_id,
            side=side,
            entry_ts=tick.ts,
            entry_price=fill_price,
            shares=shares,
            take_profit=take_profit,
            stop_loss=stop_loss,
            max_hold_until=tick.ts + timedelta(minutes=settings.overreaction_max_hold_minutes),
        ))

    def _enter_arb(self, s: SignalCandidate, tick: HistoricalTick) -> None:
        if s.context.get("kind") != "buy_both":
            return
        # New detector exposes book-walk avg prices; older runs may still emit
        # the legacy `yes_price`/`no_price` keys.
        yes_price = float(s.context.get("yes_avg_price", s.context.get("yes_price", 0)))
        no_price = float(s.context.get("no_avg_price", s.context.get("no_price", 0)))
        if yes_price <= 0 or no_price <= 0:
            return
        per_trade_cap = self.capital * settings.max_position_pct
        bonds = min(per_trade_cap / (yes_price + no_price), tick.depth_usd / (yes_price + no_price))
        bonds = max(1.0, round(bonds))
        if bonds < 1:
            return
        yes_fill = slippage_adjust(yes_price, "BUY", settings.slippage_bps)
        no_fill = slippage_adjust(no_price, "BUY", settings.slippage_bps)
        cost = bonds * (yes_fill + no_fill)
        if cost > self.cash:
            return
        self.cash -= cost
        # Instant mark — arb profit realised immediately, payoff at expiry is 1.0 per bond
        pnl = bonds * (1.0 - (yes_fill + no_fill))
        self._record_trade("arbitrage", tick.ts, tick.ts, yes_fill + no_fill, 1.0, bonds, pnl)
        self.cash += bonds * 1.0

    # -----------------------------------------------------------------------
    def _check_exits(self, tick: HistoricalTick, q: MarketQuote) -> None:
        for pos in list(self.positions):
            if pos.condition_id != tick.condition_id:
                continue
            mark = q.yes_bid if pos.side == Side.YES else q.no_bid
            if mark is None:
                continue
            reason: str | None = None
            if pos.take_profit is not None and mark >= pos.take_profit:
                reason = "take_profit"
            elif pos.stop_loss is not None and mark <= pos.stop_loss:
                reason = "stop_loss"
            elif pos.max_hold_until is not None and tick.ts >= pos.max_hold_until:
                reason = "time_stop"
            if reason is not None:
                self._close_position(pos, mark, tick.ts, reason)

    def _close_position(self, pos: BacktestPosition, mark: float, ts: datetime, reason: str) -> None:
        fill_price = slippage_adjust(mark, "SELL", settings.slippage_bps)
        proceeds = pos.shares * fill_price
        self.cash += proceeds
        pnl = (fill_price - pos.entry_price) * pos.shares
        self._record_trade(pos.strategy, pos.entry_ts, ts, pos.entry_price, fill_price, pos.shares, pnl, reason)
        self.positions.remove(pos)

    def _record_trade(self, strategy: str, entry_ts: datetime, exit_ts: datetime,
                      entry_px: float, exit_px: float, shares: float, pnl: float,
                      reason: str = "") -> None:
        self.report.trades += 1
        self.report.total_pnl_usd += pnl
        if pnl > 0:
            self.report.wins += 1
            self.report.gross_win_usd += pnl
        elif pnl < 0:
            self.report.losses += 1
            self.report.gross_loss_usd += abs(pnl)
        self.report.trade_log.append({
            "strategy": strategy, "entry_ts": entry_ts.isoformat(),
            "exit_ts": exit_ts.isoformat(), "entry": entry_px, "exit": exit_px,
            "shares": shares, "pnl": pnl, "reason": reason,
        })

    def _mark_equity(self, tick: HistoricalTick) -> float:
        equity = self.cash
        for pos in self.positions:
            mark = tick.yes_bid if pos.side == Side.YES else tick.no_bid
            equity += pos.shares * mark
        return equity
