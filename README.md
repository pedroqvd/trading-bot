# Polymarket Prediction-Market Trading Bot

Production-grade automated trading system for binary prediction markets (Polymarket).
The bot does **not** try to forecast the future — it detects when the market is *wrong*
and exploits the statistical edge.

```
                  ┌───────────────────────────┐
                  │  Polymarket Gamma + CLOB  │
                  └────────────┬──────────────┘
                               │
                   ┌───────────▼──────────┐
                   │  PolymarketClient     │  (httpx + py-clob-client)
                   └─────┬─────────────┬──┘
                         │             │
              ┌──────────▼─┐      ┌────▼──────────┐
              │ MarketStore│      │ price history │
              └─────┬──────┘      └────────┬──────┘
                    │                      │
              ┌─────▼──────────────────────▼──────┐
              │   Signal Detectors                │
              │   • ArbitrageDetector             │
              │   • OverreactionDetector          │
              └─────────────┬─────────────────────┘
                            ▼
              ┌──────────────────────────────────┐
              │     Strategies (Kelly sizing)     │
              │   • ArbitrageStrategy             │
              │   • OverreactionStrategy          │
              └─────────────┬─────────────────────┘
                            ▼
              ┌──────────────────────────────────┐
              │     RiskManager                  │
              │   mispricing / EV / liquidity /  │
              │   portfolio exposure / breakers  │
              └─────────────┬────────────────────┘
                            ▼
              ┌──────────────────────────────────┐
              │     Executor (live | simulated)  │
              └─────────────┬────────────────────┘
                            ▼
              ┌──────────────────────────────────┐
              │ Portfolio · Position Manager ·   │
              │ Metrics · PostgreSQL · Prometheus│
              └──────────────────────────────────┘
```

## Core principle

> The system does **not** predict the future. It detects where the market is wrong.
>
> `mispricing = prob_real - prob_market`
>
> Only trade when: `mispricing > threshold`, `EV > 0`, liquidity is sufficient, risk is approved.

## Implemented edges

| Edge | Hypothesis | Entry | Exit |
| ---- | ---------- | ----- | ---- |
| **Overreaction** | Rapid (>10%) short-term moves on high volume mean-revert | Fade the move (buy opposite side) with Kelly-sized position | Take-profit, stop-loss, or time-stop |
| **YES/NO Arbitrage** | When best asks sum to <1 the composite is a risk-free bond | Buy both legs atomically (FOK) | Realised at settlement |

Math primitives live in `app/utils/math_utils.py` and are shared between live engine
and backtester, so behaviour is identical.

## Layout

```
trading-bot/
├── app/
│   ├── main.py                     # entry point
│   ├── runner.py                   # orchestrator loop
│   ├── config.py                   # pydantic settings
│   ├── data/                       # Polymarket client + persistence
│   ├── signals/                    # overreaction + arbitrage detectors
│   ├── strategies/                 # sizing & order-request construction
│   ├── execution/                  # order manager, executor, position manager
│   ├── risk/                       # Kelly, circuit breakers, limits
│   ├── portfolio/                  # equity tracking + metrics
│   ├── database/                   # SQLAlchemy models + session
│   ├── monitoring/                 # structlog, Prometheus, alerts
│   └── utils/                      # math + time + retry helpers
├── backtest/
│   ├── engine.py                   # deterministic replay
│   ├── walk_forward.py             # out-of-sample validation
│   └── run.py                      # CLI
├── tests/                          # pytest
├── scripts/
├── Dockerfile
├── docker-compose.yml
└── requirements.txt
```

## Running locally (dry-run)

```bash
cp .env.example .env          # then edit — DRY_RUN=true by default
docker compose up --build
```

The `bot` service boots, waits for Postgres, creates tables, exposes metrics on
`:9108`, and starts scanning Polymarket every `POLL_INTERVAL_SECONDS`.

## Running live

1. Create a dedicated Polygon wallet and fund it with USDC.
2. Generate CLOB API credentials (`py_clob_client` → `create_or_derive_api_creds`).
3. Populate `.env`:
   ```
   POLYMARKET_PRIVATE_KEY=0x...
   POLYMARKET_API_KEY=...
   POLYMARKET_API_SECRET=...
   POLYMARKET_API_PASSPHRASE=...
   POLYMARKET_FUNDER_ADDRESS=0x...      # only if using a proxy wallet
   DRY_RUN=false
   APP_ENV=production
   ```
4. `docker compose up -d --build` — orders flow through `py-clob-client`.

The executor refuses to place live orders unless **all** of: `dry_run=false`,
`app_env=production`, and the four credentials above are present.

## Backtesting

```bash
# From CSV (schema in backtest/run.py):
docker compose --profile backtest run --rm backtest \
  python -m backtest.run --ticks /srv/trading-bot/data/ticks.csv

# From the Postgres quote history accumulated by the bot:
docker compose --profile backtest run --rm backtest \
  python -m backtest.run --db --since 2025-01-01

# Walk-forward validation (guards against overfitting):
docker compose --profile backtest run --rm backtest \
  python -m backtest.run --ticks ticks.csv --walk-forward --folds 5
```

## Risk management

| Control | Default | Knob |
| ------- | ------- | ---- |
| Fractional Kelly | 25% | `KELLY_FRACTION` |
| Max trade % of equity | 5% | `MAX_POSITION_PCT` |
| Max portfolio exposure | 60% | `MAX_PORTFOLIO_EXPOSURE` |
| Daily loss circuit breaker | 5% | `MAX_DAILY_LOSS_PCT` |
| Drawdown kill-switch | 15% | `MAX_DRAWDOWN_PCT` |
| Max open positions | 20 | `MAX_OPEN_POSITIONS` |

Every breaker trip is persisted to `risk_events` and alerted via `ALERT_WEBHOOK_URL`.

## Resilience

* The runner installs SIGINT/SIGTERM handlers and completes the active scan
  before exiting — no orphaned orders.
* Pre-flight writes of `Trade(status=PENDING)` are idempotent on
  `client_order_id`; a crash mid-execute leaves an auditable trail.
* Open positions are loaded from Postgres on restart; take-profit / stop-loss
  / time-stop evaluation is stateless.
* API calls use tenacity-style exponential backoff (2→4→8→16 s, 4 attempts).
* All monetary state is derived from persistent trade rows, not in-memory
  counters — safe across crashes.

## Observability

* **Logs**: structured JSON (`structlog`) — every detector, risk decision, and
  trade is traceable by `client_order_id` / `condition_id`.
* **Metrics**: Prometheus on `:9108` — signals, fills, equity, drawdown,
  circuit-breaker trips, API latency.
* **Alerts**: webhook (Slack/Discord compatible) on circuit-breaker trips and
  partial-arb fills.

## Deploying on DigitalOcean

1. Spin up a Droplet with Docker + Compose (`do-docker-20.04` image works).
2. `git clone` this repo, `cp .env.example .env`, fill credentials.
3. `docker compose up -d --build`.
4. Open `:9108/metrics` through the firewall for Grafana / Datadog.
5. Set restart policy — compose already uses `restart: unless-stopped`.

## Proibições embutidas (hard rules)

* Zero trades without `mispricing > MIN_MISPRICING` **and** `EV > MIN_EXPECTED_VALUE`.
* Zero trades when circuit breaker is tripped or drawdown exceeds threshold.
* Zero live orders unless credentials **and** `DRY_RUN=false` **and** `APP_ENV=production`.
* No half-executed arbitrage: YES leg + NO leg are submitted atomically; if the
  second leg fails, an alert is raised and the open leg is handed to the
  position manager for exit.

## Tests

```bash
pytest tests/
```

16 tests covering math primitives, Kelly sizing bounds, arbitrage detector,
and the backtest engine.
