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

    # --- Momentum edge (Phase 2) ---------------------------------------------
    momentum_window_minutes: int = 30
    momentum_min_score: float = 0.65
    momentum_min_velocity_pct_per_min: float = 0.003     # 0.3 %/min sustained
    momentum_min_volume_z: float = 1.0
    momentum_min_persistence: float = 0.70               # >70% of ticks in same direction
    momentum_max_realized_vol: float = 0.08
    momentum_max_spread_volatility: float = 0.012        # spread must be stable
    momentum_take_profit: float = 0.05
    momentum_stop_loss: float = 0.04
    momentum_max_hold_minutes: int = 180
    momentum_min_price: float = 0.10                     # avoid degenerate extremes
    momentum_max_price: float = 0.90
    overreaction_block_when_momentum_above: float = 0.55  # mutual exclusion threshold
    momentum_block_when_overreaction_above: float = 0.55

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

    # --- Risk 2.0 (Phase 2) --------------------------------------------------
    # Volatility-adaptive sizing: shrink risk when realised vol is high.
    vol_adaptive_enabled: bool = True
    vol_adaptive_low: float = 0.01      # below this realised vol, full size
    vol_adaptive_high: float = 0.10     # above this, multiplier hits the floor
    vol_adaptive_floor: float = 0.30    # minimum size multiplier in high-vol regime

    # Strategy auto-shutdown thresholds (consult edge_health rolling window)
    edge_health_min_trades: int = 8
    edge_health_min_expectancy_usd: float = 0.0
    edge_health_max_drawdown_pct: float = 0.20      # 20% strategy DD → disable

    # Recovery mode: when *any* strategy is in a deep streak, reduce global Kelly.
    recovery_mode_loss_threshold: int = 6
    recovery_mode_kelly_multiplier: float = 0.5

    # --- Portfolio optimizer (Phase 2) ---------------------------------------
    portfolio_max_category_exposure_pct: float = 0.25
    portfolio_correlated_throttle_pct: float = 0.5  # halve size when correlated bucket already loaded
    portfolio_capital_alloc_overreaction: float = 0.40
    portfolio_capital_alloc_arbitrage: float = 0.40
    portfolio_capital_alloc_momentum: float = 0.20

    # --- Execution -----------------------------------------------------------
    slippage_bps: float = 20.0
    taker_fee_bps: float = 0.0

    # Realistic execution (Phase 2)
    exec_latency_min_ms: int = 50
    exec_latency_max_ms: int = 250
    exec_dynamic_slippage_enabled: bool = True
    exec_dynamic_slippage_size_factor: float = 0.5   # bps per % of consumed depth
    exec_dynamic_slippage_vol_factor: float = 100.0  # bps per unit realised vol
    exec_failure_rate: float = 0.0                   # 0..1, used in backtest to drop fills

    # Smart execution — wait for micro-retracement before paying the spread
    smart_order_enabled: bool = True
    smart_order_wait_seconds: int = 20
    smart_order_passive_offset: float = 0.01   # 1 cent inside the spread
    smart_order_max_price_drift: float = 0.02  # abort if price moves 2¢ against us while waiting
    smart_order_poll_ms: int = 500

    # --- API + Frontend (Phase 2) --------------------------------------------
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    api_cors_origins: str = "*"   # comma-separated; "*" allows all in dev

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
