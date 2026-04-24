"""Prometheus metrics exported by the trading bot."""
from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram, start_http_server

from app.config import settings

# --- Core trading counters ----------------------------------------------------
SIGNALS_DETECTED = Counter(
    "bot_signals_detected_total", "Signals produced by each detector", ["signal_type"]
)
SIGNALS_ACCEPTED = Counter(
    "bot_signals_accepted_total", "Signals that passed the risk filter", ["signal_type"]
)
TRADES_SUBMITTED = Counter(
    "bot_trades_submitted_total", "Trades submitted to the exchange", ["strategy", "side"]
)
TRADES_FILLED = Counter(
    "bot_trades_filled_total", "Trades filled fully or partially", ["strategy", "side"]
)
TRADES_FAILED = Counter(
    "bot_trades_failed_total", "Trades that failed to submit or fill", ["strategy", "reason"]
)

# --- State gauges -------------------------------------------------------------
EQUITY_USD = Gauge("bot_equity_usd", "Current equity in USD")
CASH_USD = Gauge("bot_cash_usd", "Cash available in USD")
OPEN_POSITIONS = Gauge("bot_open_positions", "Number of open positions")
DAILY_PNL_USD = Gauge("bot_daily_pnl_usd", "Realized PnL today in USD")
DRAWDOWN_PCT = Gauge("bot_drawdown_pct", "Current drawdown from peak equity")

# --- Latency ------------------------------------------------------------------
LOOP_LATENCY = Histogram(
    "bot_loop_latency_seconds",
    "End-to-end latency of the scan/execute loop",
    buckets=(0.1, 0.25, 0.5, 1, 2, 5, 10, 30, 60, 120),
)
API_LATENCY = Histogram(
    "bot_api_latency_seconds",
    "Latency of outbound API calls",
    ["endpoint"],
    buckets=(0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10),
)

# --- Risk ---------------------------------------------------------------------
CIRCUIT_BREAKER_TRIPS = Counter(
    "bot_circuit_breaker_trips_total", "Circuit breaker activations", ["kind"]
)


def start_metrics_server() -> None:
    start_http_server(settings.prometheus_port)
