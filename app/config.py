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

    arbitrage_min_edge: float = 0.02
    arbitrage_max_leg_slippage: float = 0.005

    # --- Risk ----------------------------------------------------------------
    kelly_fraction: float = 0.25
    max_position_pct: float = 0.05
    max_portfolio_exposure: float = 0.6
    max_daily_loss_pct: float = 0.05
    max_drawdown_pct: float = 0.15

    # --- Execution -----------------------------------------------------------
    slippage_bps: float = 20.0
    taker_fee_bps: float = 0.0

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
