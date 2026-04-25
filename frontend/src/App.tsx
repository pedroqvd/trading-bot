import { useEffect, useState } from "react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import {
  api,
  BotStatus,
  EquityResponse,
  MetricsResponse,
  Period,
  pollEvery,
  PositionRow,
  TradeRow,
} from "./services/api";

const PERIODS: Period[] = ["24h", "7d", "30d", "all"];
const REFRESH_MS = 5_000;

function fmtUsd(value: number): string {
  return value.toLocaleString("en-US", { style: "currency", currency: "USD" });
}

function fmtPct(value: number): string {
  return `${(value * 100).toFixed(2)}%`;
}

function fmtTime(value: string | null): string {
  if (!value) return "—";
  return new Date(value).toLocaleTimeString();
}

function MetricCard({
  label,
  value,
  className,
}: {
  label: string;
  value: string;
  className?: string;
}) {
  return (
    <div className="card">
      <div className="label">{label}</div>
      <div className={`value ${className ?? ""}`}>{value}</div>
    </div>
  );
}

export default function App() {
  const [period, setPeriod] = useState<Period>("24h");
  const [metrics, setMetrics] = useState<MetricsResponse | null>(null);
  const [equity, setEquity] = useState<EquityResponse | null>(null);
  const [positions, setPositions] = useState<PositionRow[]>([]);
  const [trades, setTrades] = useState<TradeRow[]>([]);
  const [bot, setBot] = useState<BotStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    setError(null);
    const stops = [
      pollEvery(() => api.getMetrics(period), REFRESH_MS, setMetrics, (e) =>
        setError(String(e)),
      ),
      pollEvery(() => api.getEquity(period), REFRESH_MS, setEquity, (e) =>
        setError(String(e)),
      ),
      pollEvery(
        () => api.getPositions("all", 50),
        REFRESH_MS,
        setPositions,
        (e) => setError(String(e)),
      ),
      pollEvery(
        () => api.getTrades(50),
        REFRESH_MS,
        setTrades,
        (e) => setError(String(e)),
      ),
      pollEvery(() => api.getBotStatus(), REFRESH_MS, setBot, (e) =>
        setError(String(e)),
      ),
    ];
    setLoading(false);
    return () => stops.forEach((stop) => stop());
  }, [period]);

  const equityPoints = (equity?.points ?? []).map((p) => ({
    time: new Date(p.time).toLocaleTimeString(),
    equity: p.equity,
  }));

  return (
    <div className="app">
      <header className="header">
        <div className="brand">⚡ Trading Bot Dashboard</div>
        <div className="controls">
          <div className="tabs">
            {PERIODS.map((p) => (
              <button
                key={p}
                className={`tab ${p === period ? "active" : ""}`}
                onClick={() => setPeriod(p)}
              >
                {p}
              </button>
            ))}
          </div>
          {bot?.running ? (
            <button
              className="btn danger"
              onClick={async () => {
                await api.stopBot();
                setBot(await api.getBotStatus());
              }}
            >
              Stop
            </button>
          ) : (
            <button
              className="btn primary"
              onClick={async () => {
                await api.startBot();
                setBot(await api.getBotStatus());
              }}
            >
              Start
            </button>
          )}
        </div>
      </header>

      {error && <div className="error">⚠ {error}</div>}

      {loading && !metrics ? (
        <div className="cards">
          {Array.from({ length: 5 }).map((_, i) => (
            <div className="skeleton" key={i} />
          ))}
        </div>
      ) : metrics ? (
        <div className="cards">
          <MetricCard label="Equity" value={fmtUsd(metrics.equity_usd)} />
          <MetricCard
            label="Total PnL"
            value={fmtUsd(metrics.total_pnl_usd)}
            className={metrics.total_pnl_usd >= 0 ? "ok" : "bad"}
          />
          <MetricCard label="Win Rate" value={fmtPct(metrics.win_rate)} />
          <MetricCard
            label="Trades"
            value={String(metrics.total_trades)}
          />
          <MetricCard
            label="Expectancy"
            value={fmtUsd(metrics.expectancy_usd)}
          />
          <MetricCard
            label="Sharpe"
            value={metrics.sharpe.toFixed(2)}
          />
          <MetricCard
            label="Sortino"
            value={metrics.sortino.toFixed(2)}
          />
          <MetricCard
            label="Open"
            value={String(metrics.open_positions)}
          />
        </div>
      ) : null}

      <section className="section">
        <h3>Equity curve</h3>
        {equityPoints.length === 0 ? (
          <div className="skeleton" />
        ) : (
          <ResponsiveContainer width="100%" height={260}>
            <LineChart data={equityPoints}>
              <CartesianGrid strokeDasharray="3 3" stroke="#243154" />
              <XAxis dataKey="time" stroke="#8090b0" fontSize={11} />
              <YAxis stroke="#8090b0" fontSize={11} />
              <Tooltip
                contentStyle={{
                  background: "#1b253b",
                  border: "1px solid #243154",
                }}
              />
              <Line
                type="monotone"
                dataKey="equity"
                stroke="#5cf2c7"
                strokeWidth={2}
                dot={false}
              />
            </LineChart>
          </ResponsiveContainer>
        )}
      </section>

      <section className="section">
        <h3>Strategies</h3>
        {(metrics?.by_strategy ?? []).length === 0 ? (
          <div className="row">
            <span className="meta">No strategy activity yet.</span>
          </div>
        ) : (
          (metrics?.by_strategy ?? []).map((s) => (
            <div className="row" key={s.strategy}>
              <div className="meta">
                <strong>{s.strategy}</strong>
                <small>
                  {s.trades} trades · win {fmtPct(s.win_rate)} · pf{" "}
                  {s.profit_factor.toFixed(2)} · hold{" "}
                  {s.avg_hold_minutes.toFixed(0)}m
                </small>
              </div>
              <span className={`pill ${s.state.toLowerCase()}`}>{s.state}</span>
            </div>
          ))
        )}
      </section>

      <section className="section">
        <h3>Open positions</h3>
        {positions.filter((p) => p.status === "OPEN").length === 0 ? (
          <div className="row">
            <span className="meta">No open positions.</span>
          </div>
        ) : (
          positions
            .filter((p) => p.status === "OPEN")
            .map((p) => (
              <div className="row" key={p.id}>
                <div className="meta">
                  <strong>{p.market_question || p.market_slug}</strong>
                  <small>
                    {p.strategy} · {p.side} · entry {p.entry_price.toFixed(3)} ·{" "}
                    size {fmtUsd(p.entry_size_usd)}
                  </small>
                </div>
                <span className="pill">{p.shares.toFixed(0)} shares</span>
              </div>
            ))
        )}
      </section>

      <section className="section">
        <h3>Recent trades</h3>
        {trades.length === 0 ? (
          <div className="row">
            <span className="meta">No trades yet.</span>
          </div>
        ) : (
          trades.slice(0, 25).map((t) => (
            <div className="row" key={t.id}>
              <div className="meta">
                <strong>{t.market_question || t.client_order_id}</strong>
                <small>
                  {t.strategy} · {t.order_side} {t.market_side} · price{" "}
                  {t.price.toFixed(3)} · size {fmtUsd(t.size_usd)} ·{" "}
                  {fmtTime(t.created_at)}
                </small>
              </div>
              <span className={`pill ${t.status.toLowerCase()}`}>
                {t.status}
              </span>
            </div>
          ))
        )}
      </section>
    </div>
  );
}
