"""Typed configuration loaded from environment variables."""
from __future__ import annotations

from functools import lru_cache
from typing import Literal, Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Environment ---------------------------------------------------------
    app_env: Literal["production", "staging", "backtest"] = "production"
    log_level: str = "INFO"
    timezone: str = "UTC"

    # --- Database ------------------------------------------------------------
    database_url: str = "postgresql+psycopg2://trader:trader@db:5432/trading"

    # --- Polymarket ----------------------------------------------------------
    polymarket_gamma_url: str = "https://gamma-api.polymarket.com"
    polymarket_clob_url: str = "https://clob.polymarket.com"
    polymarket_chain_id: int = 137

    polymarket_private_key: Optional[str] = None
    polymarket_funder_address: Optional[str] = None
    polymarket_api_key: Optional[str] = None
    polymarket_api_secret: Optional[str] = None
    polymarket_api_passphrase: Optional[str] = None

    # --- Trading -------------------------------------------------------------
    capital_usd: float = 1000.0
    dry_run: bool = True
    poll_interval_seconds: int = 30
    max_open_positions: int = 20

    # --- Edge thresholds -----------------------------------------------------
    min_mispricing: float = 0.03
    min_expected_value: float = 0.015
    min_liquidity_usd: float = 500.0
    max_spread: float = 0.04

    overreaction_move_pct: float = 0.10
    overreaction_window_minutes: int = 15
    overreaction_min_volume_usd: float = 5000.0
    overreaction_reversion_target: float = 0.5
    overreaction_take_profit: float = 0.07
    overreaction_stop_loss: float = 0.05
    overreaction_max_hold_minutes: int = 240

    # Overreaction quality scoring — only trade when composite score exceeds this
    overreaction_min_score: float = 0.65
    overreaction_min_velocity_pct_per_min: float = 0.004  # 0.4 %/min
    overreaction_min_volume_z: float = 1.0                # volume must exceed 1σ of rolling baseline
    overreaction_min_spike_ratio: float = 0.55            # >55% of move must concentrate in one tick
    overreaction_max_realized_vol: float = 0.10           # skip ultra-volatile markets
    overreaction_min_ticks: int = 6                       # need at least N observations

    arbitrage_min_edge: float = 0.02
    arbitrage_max_leg_slippage: float = 0.005
    arbitrage_min_exec_confidence: float = 0.60           # 0..1 book-walk confidence floor
    arbitrage_size_safety_multiplier: float = 1.10        # ask 10% more depth than we use

    # --- Risk ----------------------------------------------------------------
    kelly_fraction: float = 0.25
    max_position_pct: float = 0.05
    max_portfolio_exposure: float = 0.6
    max_daily_loss_pct: float = 0.05
    max_drawdown_pct: float = 0.15

    # Per-strategy exposure cap (fraction of equity) — prevents one strategy sinking the book
    max_strategy_exposure_pct: float = 0.35
    # Per-market exposure cap (fraction of equity) — prevents concentration in one event
    max_market_exposure_pct: float = 0.08
    # Cooldown after closing a position on a market (prevents immediate re-entry at the same level)
    market_cooldown_minutes: int = 30
    # Post-loss Kelly scaling — after N consecutive losses on a strategy, cut Kelly by X
    loss_streak_soft_threshold: int = 3     # after 3 in a row, halve Kelly
    loss_streak_hard_threshold: int = 5     # after 5 in a row, quarter Kelly
    loss_streak_recovery_trades: int = 2    # N wins to reset the penalty
    daily_strategy_loss_cap_pct: float = 0.03   # 3% of equity lost by a single strategy pauses it

    # --- Execution -----------------------------------------------------------
    slippage_bps: float = 20.0
    taker_fee_bps: float = 0.0

    # Smart execution — wait for micro-retracement before paying the spread
    smart_order_enabled: bool = True
    smart_order_wait_seconds: int = 20
    smart_order_passive_offset: float = 0.01   # 1 cent inside the spread
    smart_order_max_price_drift: float = 0.02  # abort if price moves 2¢ against us while waiting
    smart_order_poll_ms: int = 500

    # --- Monitoring ----------------------------------------------------------
    prometheus_port: int = 9108
    alert_webhook_url: Optional[str] = None

    @field_validator("kelly_fraction", "max_position_pct", "max_portfolio_exposure",
                     "max_daily_loss_pct", "max_drawdown_pct")
    @classmethod
    def _pct_bounds(cls, v: float) -> float:
        if not 0 < v <= 1:
            raise ValueError("percentage parameters must be in (0, 1]")
        return v

    @field_validator("capital_usd")
    @classmethod
    def _capital_positive(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("capital_usd must be positive")
        return v

    @property
    def has_live_credentials(self) -> bool:
        return bool(
            self.polymarket_private_key
            and self.polymarket_api_key
            and self.polymarket_api_secret
            and self.polymarket_api_passphrase
        )

    @property
    def live_trading_enabled(self) -> bool:
        return (not self.dry_run) and self.has_live_credentials and self.app_env == "production"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
