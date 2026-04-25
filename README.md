# Polymarket Prediction-Market Trading Bot

Production-grade multi-edge automated trading system for binary prediction
markets (Polymarket). The bot does **not** try to forecast the future — it
detects when the market is *wrong*, sizes adaptively against an edge-health
signal, and ships a portfolio-aware risk filter on top.

> **Phase 2 — multi-edge, execution-aware, portfolio-driven, observable.**
> Adds a third edge (momentum), a portfolio optimiser, vol-adaptive sizing,
> auto-shutdown on broken edges, realistic execution simulation, an HTTP
> API, and a reference React dashboard.

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

## Edge quality (post-audit upgrades)

The bot has explicit **quality scoring** before any risk check fires.

### Overreaction — composite score
Five sub-scores combine into `overreaction_score ∈ [0, 1]`. Hard filters reject
the candidate before scoring; the score then must clear `overreaction_min_score`.

| Sub-score | Drives the hypothesis |
| --------- | --------------------- |
| Magnitude | Bigger moves carry more reversion potential (saturates at 25%) |
| Velocity | Fast (`%/min`) implies panic / order-flow, not fundamentals |
| Volume z-score | Move on strong participation > move on dead book |
| Spike ratio | Concentration in one tick distinguishes spike from trend |
| Persistence penalty | Monotonic drifts get dampened (they're trends) |
| Realised-vol penalty | Markets that already swing wildly are not surprises |

### Bayesian prob_real
`prob_real` is a posterior, not a static reversion target:
```
prob_real = w_anchor * anchor + w_current * current + w_mean * 0.5
```
Weights derive from the overreaction score and realised volatility: high-score
fades pull toward anchor; high vol pulls toward 0.5 (prior ignorance).

### Arbitrage — book-walk + execution confidence
The detector simulates walking both YES and NO books with a safety multiplier
on requested depth. It emits the candidate **only** when:
- both books fill the safety-buffered notional without exhaustion;
- VWAP profit per bond after the walk still clears `arbitrage_min_edge`;
- the `confidence` (headroom above the floor) clears `arbitrage_min_exec_confidence`.

The strategy then **rebuilds the plan with the live book** at order-construction
time so legs are sized to what's actually fillable. `sell_both` was removed —
the bot is long-only and emitting it just polluted metrics.

## Risk management

| Control | Default | Knob |
| ------- | ------- | ---- |
| Fractional Kelly | 25% | `KELLY_FRACTION` |
| Max trade % of equity | 5% | `MAX_POSITION_PCT` |
| Max portfolio exposure | 60% | `MAX_PORTFOLIO_EXPOSURE` |
| **Max strategy exposure** | **35%** | **`MAX_STRATEGY_EXPOSURE_PCT`** |
| **Max market exposure** | **8%** | **`MAX_MARKET_EXPOSURE_PCT`** |
| **Market cooldown after close** | **30 min** | **`MARKET_COOLDOWN_MINUTES`** |
| Daily loss circuit breaker | 5% | `MAX_DAILY_LOSS_PCT` |
| **Per-strategy daily loss cap** | **3%** | **`DAILY_STRATEGY_LOSS_CAP_PCT`** |
| **Loss-streak Kelly cut (soft)** | **3 losses → ×0.5** | **`LOSS_STREAK_SOFT_THRESHOLD`** |
| **Loss-streak Kelly cut (hard)** | **5 losses → ×0.25** | **`LOSS_STREAK_HARD_THRESHOLD`** |
| Drawdown kill-switch | 15% | `MAX_DRAWDOWN_PCT` |
| Max open positions | 20 | `MAX_OPEN_POSITIONS` |

Per-strategy and per-market state is **derived from the persistent Position
table** so it survives restarts. Loss-streak Kelly scaling shrinks size after
consecutive losses and resets only after `LOSS_STREAK_RECOVERY_TRADES` wins.

Every breaker trip is persisted to `risk_events` and alerted via `ALERT_WEBHOOK_URL`.

## Smart execution

`SmartOrderPlacer` keeps the spread when possible:
1. Place a passive limit one tick inside the spread (`SMART_ORDER_PASSIVE_OFFSET`).
2. Wait up to `SMART_ORDER_WAIT_SECONDS` watching the book.
3. Abort if price drifts > `SMART_ORDER_MAX_PRICE_DRIFT` against us.
4. On timeout, cancel and fall back to an IOC taker with a fresh
   `client_order_id`.

Arbitrage legs **always go taker** — they cannot risk a leg sitting passive while the other one fills.

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

## Phase 2 — Multi-edge & full-stack

### Third edge: momentum (continuation)
`app/signals/momentum.py` and `app/strategies/momentum_strategy.py` add a
trend-following edge that is *mutually exclusive* with overreaction:

- `momentum_score` rewards velocity, volume z-score, persistence, low
  immediate mean-reversion, and stable spreads — penalised by realised vol.
- A high overreaction score blocks momentum (and vice-versa) so the same
  market never produces both signals.
- A separate Bayesian estimator (`bayesian_prob_real_momentum`) projects
  continuation rather than reversion.

### Portfolio optimizer
`app/portfolio/portfolio_optimizer.py` consults the open book before final
approval:

- **Categoriser** auto-tags markets (politics / crypto / macro / sports / …).
- **Category exposure cap** (`PORTFOLIO_MAX_CATEGORY_EXPOSURE_PCT`).
- **Correlation throttle**: same category + same direction halves the size.
- **Capital allocation** per strategy
  (`PORTFOLIO_CAPITAL_ALLOC_*` knobs).
- **Position throttling** as you approach the category / strategy caps.

### Risk 2.0
`app/risk/adaptive_risk.py`:
- **Volatility-adaptive sizing** — linear floor when realised vol is high.
- **Recovery mode** — global Kelly multiplier when ANY strategy has K losses
  in a row.
- **Per-strategy auto-shutdown** via `app/monitoring/edge_health.py`:
  *HEALTHY → WATCH → IMPAIRED → DISABLED* states. Disabled strategies are
  rejected at the risk gate AND the transition is alerted via the webhook.

### Realistic execution
`app/execution/realistic_execution.py`:
- Latency budget sampler (`EXEC_LATENCY_MIN_MS` / `MAX_MS`).
- **Dynamic slippage** = base + size factor × consumed-depth% + vol factor × realised vol.
- Configurable execution-failure rate for backtest realism.

### Real-time data layer
`app/data/ingestion.py` runs an `IngestionLoop` thread that decouples market
data refresh from the trading loop and feeds an in-memory `SnapshotCache` the
API can read without touching Polymarket.

### Advanced metrics
`app/portfolio/advanced_metrics.py` adds **Sharpe, Sortino, MAE, MFE** on top
of the existing expectancy / profit-factor / drawdown breakdown.

### HTTP API (FastAPI)
`app/api/` exposes:

| Endpoint | What it returns |
| -------- | --------------- |
| `GET /metrics?period=24h\|7d\|30d\|all` | aggregate + per-strategy stats |
| `GET /equity?period=…` | equity-curve series |
| `GET /positions?status=…&limit=…` | open + closed positions |
| `GET /trades?limit=…&status=…` | recent trades |
| `GET /bot/status` | runner state |
| `POST /bot/start` / `POST /bot/stop` | thread-safe runner control |
| `GET /health` | liveness probe |

CORS is enabled (`API_CORS_ORIGINS`, defaults to `*` in dev).

Run: `python -m app.api_main` or `docker compose up api`.

### Frontend dashboard
`frontend/` is a self-contained Vite + React + TypeScript reference UI:

- `frontend/src/services/api.ts` — typed API client (drop into Lovable).
- `frontend/src/App.tsx` — equity chart, metric cards, strategy table,
  open positions, recent trades, start/stop control, period switcher.
- Polling at 5s with skeleton loaders + error banner.

Configure with `VITE_API_URL` (defaults to `http://localhost:8000`).

### Full-stack docker compose

```bash
docker compose up -d --build
# bot       → http://localhost:9108/metrics  (Prometheus)
# api       → http://localhost:8000          (FastAPI)
# frontend  → http://localhost:5173          (nginx + built React)
```

## Tests

```bash
pytest tests/
```

**78 tests** covering math primitives, signal quality, Bayesian prob_real,
book-walk, risk-state, momentum, portfolio optimiser, edge health, adaptive
risk, realistic execution, backtest engine, and the FastAPI layer.
