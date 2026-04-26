/**
 * API service layer.
 *
 * Drop-in replacement for the previous mock layer. Every function returns a
 * typed promise; periods are passed straight through to the backend so the
 * server is the single source of truth for what "24h" / "7d" / "30d" means.
 */

export type Period = "24h" | "7d" | "30d" | "all";

export interface StrategyBreakdown {
  strategy: string;
  trades: number;
  win_rate: number;
  expectancy_usd: number;
  total_pnl_usd: number;
  profit_factor: number;
  avg_hold_minutes: number;
  state: string;
  reason: string;
}

export interface MetricsResponse {
  period: Period;
  total_pnl_usd: number;
  realized_today_usd: number;
  win_rate: number;
  total_trades: number;
  avg_ev_usd: number;
  expectancy_usd: number;
  profit_factor: number;
  sharpe: number;
  sortino: number;
  max_drawdown_pct: number;
  open_positions: number;
  equity_usd: number;
  cash_usd: number;
  by_strategy: StrategyBreakdown[];
}

export interface EquityPoint {
  time: string;
  equity: number;
  cash: number;
  unrealized: number;
}

export interface EquityResponse {
  period: Period;
  points: EquityPoint[];
}

export interface PositionRow {
  id: number;
  market_question: string;
  market_slug: string;
  strategy: string;
  side: string;
  status: string;
  entry_price: number;
  entry_size_usd: number;
  shares: number;
  take_profit: number | null;
  stop_loss: number | null;
  opened_at: string;
  closed_at: string | null;
  exit_price: number | null;
  realized_pnl_usd: number | null;
}

export interface TradeRow {
  id: number;
  client_order_id: string;
  market_question: string;
  strategy: string;
  market_side: string;
  order_side: string;
  status: string;
  price: number;
  size_usd: number;
  shares: number;
  filled_shares: number;
  created_at: string;
  filled_at: string | null;
}

export interface BotStatus {
  running: boolean;
  started_at: string | null;
  last_loop_at: string | null;
  last_error: string | null;
  open_positions: number;
  equity_usd: number;
  dry_run: boolean;
  live_trading_enabled: boolean;
}

export interface BotControlResponse {
  running: boolean;
  message: string;
}

const _env =
  typeof import.meta !== "undefined" ? (import.meta as any).env ?? {} : {};

const API_URL: string = _env.VITE_API_URL ?? "http://localhost:8000";
const API_KEY: string = _env.VITE_API_KEY ?? "";

async function request<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(init.headers as Record<string, string> | undefined),
  };
  if (API_KEY) headers["X-API-Key"] = API_KEY;

  const response = await fetch(`${API_URL}${path}`, { ...init, headers });
  if (!response.ok) {
    const text = await response.text().catch(() => "");
    throw new Error(`${response.status} ${response.statusText}: ${text}`);
  }
  return (await response.json()) as T;
}

export const api = {
  baseUrl: API_URL,

  getMetrics(period: Period = "24h") {
    return request<MetricsResponse>(`/metrics?period=${period}`);
  },

  getEquity(period: Period = "24h") {
    return request<EquityResponse>(`/equity?period=${period}`);
  },

  getPositions(status: "all" | "open" | "closed" = "all", limit = 100) {
    return request<PositionRow[]>(
      `/positions?status=${status}&limit=${limit}`,
    );
  },

  getTrades(limit = 100, status: string = "all") {
    return request<TradeRow[]>(`/trades?limit=${limit}&status=${status}`);
  },

  getBotStatus() {
    return request<BotStatus>(`/bot/status`);
  },

  startBot() {
    return request<BotControlResponse>(`/bot/start`, { method: "POST" });
  },

  stopBot() {
    return request<BotControlResponse>(`/bot/stop`, { method: "POST" });
  },
};

/** Polling helper. Returns a cleanup function. */
export function pollEvery<T>(
  fn: () => Promise<T>,
  intervalMs: number,
  onUpdate: (data: T) => void,
  onError?: (err: unknown) => void,
): () => void {
  let cancelled = false;
  let timer: ReturnType<typeof setTimeout> | null = null;

  const tick = async () => {
    try {
      const data = await fn();
      if (!cancelled) onUpdate(data);
    } catch (err) {
      if (!cancelled && onError) onError(err);
    } finally {
      if (!cancelled) timer = setTimeout(tick, intervalMs);
    }
  };
  tick();

  return () => {
    cancelled = true;
    if (timer) clearTimeout(timer);
  };
}
