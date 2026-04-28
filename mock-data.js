// ============================================================
// Mock data + simulated API for Polymarket trading bot dashboard
// Mimics the spec'd FastAPI backend; polls update values live.
// ============================================================

(function () {
  const STRATS = ["overreaction", "arbitrage", "momentum"];

  function rand(min, max) { return Math.random() * (max - min) + min; }
  function ri(min, max) { return Math.floor(rand(min, max)); }
  function pick(arr) { return arr[ri(0, arr.length)]; }

  // --- Seed equity history (per period) ---
  const NOW = Date.now();
  function genEquityHistory(points, stepMs, startEquity, vol) {
    const out = [];
    let eq = startEquity;
    let cash = startEquity * 0.62;
    for (let i = points - 1; i >= 0; i--) {
      const t = NOW - i * stepMs;
      const drift = 0.00018 * stepMs / 60000; // small upward drift per minute
      const noise = (Math.random() - 0.48) * vol;
      eq = Math.max(eq * (1 + drift + noise), eq * 0.5);
      cash = eq * (0.55 + Math.sin(i / 18) * 0.08);
      const unrealized = eq - cash;
      out.push({
        time: new Date(t).toISOString(),
        equity: +eq.toFixed(2),
        cash: +cash.toFixed(2),
        unrealized: +unrealized.toFixed(2),
      });
    }
    return out;
  }

  const equityHistories = {
    "24h": genEquityHistory(96, 15 * 60_000, 38_500, 0.0024),
    "7d":  genEquityHistory(168, 60 * 60_000, 33_000, 0.0034),
    "30d": genEquityHistory(180, 4 * 60 * 60_000, 28_500, 0.0042),
    "all": genEquityHistory(220, 12 * 60 * 60_000, 20_000, 0.0058),
  };

  // ensure most recent equity is consistent across periods
  const LIVE_EQUITY = equityHistories["24h"][equityHistories["24h"].length - 1].equity;
  Object.keys(equityHistories).forEach(k => {
    const arr = equityHistories[k];
    arr[arr.length - 1] = { ...arr[arr.length - 1], equity: LIVE_EQUITY };
  });

  // --- Markets universe ---
  const MARKET_SEEDS = [
    "Will the Federal Reserve cut rates by 50bps before July 2026?",
    "Will Bitcoin close above $120,000 on May 1, 2026?",
    "Will OpenAI release GPT-6 in 2026?",
    "Will the U.S. enter a recession in Q3 2026?",
    "Will SpaceX complete a crewed Mars flyby by 2030?",
    "Will the S&P 500 close above 6,500 on June 30?",
    "Will Apple announce an AR/VR headset successor by August?",
    "Will Ethereum ETH/USD exceed $5,000 in May 2026?",
    "Will the Lakers make the 2026 NBA Finals?",
    "Will TSMC announce a new U.S. fab before September?",
    "Will Argentina win the 2026 World Cup?",
    "Will Tesla deliver more than 600k vehicles in Q2?",
    "Will Anthropic release a new model family before July 1?",
    "Will the EU pass the AI Liability Directive in 2026?",
    "Will UK CPI print above 3.0% for April?",
    "Will gold trade above $3,000/oz on June 1?",
    "Will Powell remain Fed Chair through year end?",
    "Will Solana reach $300 in 2026?",
    "Will Nvidia revenue exceed $50B for FY26 Q1?",
    "Will WTI crude oil close above $90 on May 15?",
  ];
  const markets = MARKET_SEEDS.map((q, i) => {
    const yes_mid = +rand(0.05, 0.95).toFixed(3);
    const spread = +rand(0.005, 0.04).toFixed(3);
    const yes_bid = Math.max(0.01, +(yes_mid - spread / 2).toFixed(3));
    const yes_ask = Math.min(0.99, +(yes_mid + spread / 2).toFixed(3));
    const no_mid = +(1 - yes_mid).toFixed(3);
    const no_bid = Math.max(0.01, +(no_mid - spread / 2).toFixed(3));
    const no_ask = Math.min(0.99, +(no_mid + spread / 2).toFixed(3));
    // 4 markets get arb opportunities (yes_ask + no_ask < 1)
    const arb = i % 5 === 0;
    return {
      condition_id: "0x" + Math.random().toString(16).slice(2, 14).padEnd(12, "0"),
      slug: q.toLowerCase().replace(/[^a-z0-9]+/g, "-").slice(0, 60),
      question: q,
      yes_bid, yes_ask: arb ? Math.max(0.01, yes_ask - 0.04) : yes_ask,
      no_bid, no_ask: arb ? Math.max(0.01, no_ask - 0.03) : no_ask,
      yes_mid, no_mid,
      yes_liquidity: +rand(2_000, 80_000).toFixed(0),
      no_liquidity: +rand(2_000, 80_000).toFixed(0),
      volume_24h: +rand(8_000, 420_000).toFixed(0),
    };
  });

  // --- Positions ---
  let positionId = 1000;
  function makePosition(open) {
    const m = pick(markets);
    const side = Math.random() > 0.5 ? "YES" : "NO";
    const entry_price = +rand(0.18, 0.78).toFixed(3);
    const entry_size_usd = +rand(120, 1400).toFixed(0);
    const shares = +(entry_size_usd / entry_price).toFixed(0);
    const tp = entry_price + rand(0.04, 0.18);
    const sl = entry_price - rand(0.04, 0.12);
    const ageMin = open ? ri(2, 720) : ri(60, 4000);
    const opened = new Date(NOW - ageMin * 60_000).toISOString();
    let exit_price = null, closed_at = null, realized = null, status = "OPEN";
    if (!open) {
      status = Math.random() > 0.93 ? "LIQUIDATED" : "CLOSED";
      exit_price = +Math.max(0.02, Math.min(0.98, entry_price + (Math.random() - 0.45) * 0.15)).toFixed(3);
      const sign = side === "YES" ? 1 : -1;
      realized = +((exit_price - entry_price) * sign * shares).toFixed(2);
      closed_at = new Date(NOW - Math.max(0, ageMin - ri(15, 200)) * 60_000).toISOString();
    }
    return {
      id: positionId++,
      market_question: m.question,
      market_slug: m.slug,
      strategy: pick(STRATS),
      side,
      status,
      entry_price,
      entry_size_usd,
      shares,
      take_profit: +tp.toFixed(3),
      stop_loss: +sl.toFixed(3),
      opened_at: opened,
      closed_at,
      exit_price,
      realized_pnl_usd: realized,
    };
  }

  const positions = [];
  for (let i = 0; i < 11; i++) positions.push(makePosition(true));
  for (let i = 0; i < 38; i++) positions.push(makePosition(false));

  // Per-position price history (for mini-chart in detail drawer)
  function genPriceHistory(entry, current, points = 48) {
    const out = [];
    let p = entry;
    for (let i = 0; i < points; i++) {
      const t = (i / (points - 1));
      const targetMix = entry + (current - entry) * t;
      p = targetMix + (Math.random() - 0.5) * 0.018;
      p = Math.max(0.02, Math.min(0.98, p));
      out.push({
        t: new Date(NOW - (points - i) * 5 * 60_000).toISOString(),
        p: +p.toFixed(3),
      });
    }
    out[out.length - 1].p = current;
    return out;
  }
  positions.forEach(pos => {
    const cur = pos.exit_price ?? +(pos.entry_price + (Math.random() - 0.4) * 0.12).toFixed(3);
    pos.current_price = Math.max(0.02, Math.min(0.98, cur));
    pos.price_history = genPriceHistory(pos.entry_price, pos.current_price);
    pos.correlation_id = "ord_" + Math.random().toString(36).slice(2, 10);
    // unrealized PnL for open
    if (pos.status === "OPEN") {
      const sign = pos.side === "YES" ? 1 : -1;
      pos.unrealized_pnl_usd = +((pos.current_price - pos.entry_price) * sign * pos.shares).toFixed(2);
      pos.ev_now = +(rand(-0.04, 0.08)).toFixed(3);
      pos.kelly_now = +(rand(0.02, 0.18)).toFixed(3);
    }
  });

  // Sparkline history per strategy (for inline mini-charts)
  const stratSparklines = {};
  STRATS.forEach(s => {
    const arr = []; let v = 0;
    for (let i = 0; i < 30; i++) {
      v += (Math.random() - (s === "momentum" ? 0.55 : 0.4)) * 100;
      arr.push(+v.toFixed(2));
    }
    stratSparklines[s] = arr;
  });

  // Logs (with correlation_ids matching trades + positions)
  const LOG_LEVELS = ["INFO", "INFO", "INFO", "INFO", "DEBUG", "DEBUG", "WARN", "WARN", "ERROR"];
  const LOG_TEMPLATES = [
    (cid) => ["INFO", `Loop varreu 18 mercados em ${ri(180,420)}ms`, cid],
    (cid) => ["INFO", `Edge candidato: 'overreaction' EV=${rand(0.01,0.05).toFixed(3)} Kelly=${rand(0.04,0.18).toFixed(3)}`, cid],
    (cid) => ["INFO", `Ordem ${cid} enviada: BUY YES @ ${rand(0.3,0.8).toFixed(3)}`, cid],
    (cid) => ["INFO", `Ordem ${cid} FILLED em ${ri(80,400)}ms`, cid],
    (cid) => ["WARN", `CLOB API 429 em ${cid} — backoff 30s`, cid],
    (cid) => ["INFO", `Posição atingiu TP — fechando ${cid}`, cid],
    (cid) => ["DEBUG", `Cache invalidado · ttl expirado`, cid],
    (cid) => ["WARN", `Slippage +${rand(1,3).toFixed(1)}% acima do esperado em ${cid}`, cid],
    (cid) => ["ERROR", `Falha ao reconciliar ${cid} — retry 1/3`, cid],
    (cid) => ["INFO", `Reconciliação OK em ${cid} após 2 tentativas`, cid],
    (cid) => ["INFO", `WS reconectado após ${rand(2,8).toFixed(1)}s`, cid],
    (cid) => ["DEBUG", `Edge 'momentum' score=${rand(0.4,0.9).toFixed(2)} z=${rand(-2,2.5).toFixed(2)}`, cid],
    (cid) => ["INFO", `Risk-mgr: drawdown ${(-rand(0.5,4)).toFixed(2)}% (limite -15%)`, cid],
  ];

  const logs = [];
  let logId = 1;
  // seed: 200 historical logs
  for (let i = 200; i > 0; i--) {
    const tpl = LOG_TEMPLATES[ri(0, LOG_TEMPLATES.length - 1)];
    const cid = Math.random() < 0.3 && positions.length ? positions[ri(0, positions.length)].correlation_id : "ord_" + Math.random().toString(36).slice(2, 10);
    const [lvl, msg] = tpl(cid);
    logs.push({ id: logId++, ts: new Date(NOW - i * 4500).toISOString(), level: lvl, msg, correlation_id: cid });
  }

  // Equity curve event markers
  const equityEvents = [];
  for (let i = 0; i < 8; i++) {
    const arr = equityHistories["24h"];
    const idx = ri(2, arr.length - 2);
    equityEvents.push({
      ts: arr[idx].time,
      kind: pick(["position_open", "position_close", "risk", "drawdown_kill", "edge_disabled"]),
      label: pick(["Posição aberta", "Posição fechada", "Slippage alto", "Kill-switch", "Edge desabilitado"]),
    });
  }

  // Config history (for diff/audit log)
  const configHistory = [
    { ts: new Date(NOW - 3 * 86400_000).toISOString(), user: "operator", changes: [{ key: "kelly_fraction", from: 0.20, to: 0.25 }] },
    { ts: new Date(NOW - 2 * 86400_000).toISOString(), user: "operator", changes: [{ key: "max_open_positions", from: 15, to: 20 }, { key: "min_ev", from: 0.020, to: 0.015 }] },
    { ts: new Date(NOW - 18 * 3600_000).toISOString(), user: "auto", changes: [{ key: "momentum_enabled", from: true, to: false }] },
    { ts: new Date(NOW - 4 * 3600_000).toISOString(), user: "operator", changes: [{ key: "max_daily_loss_pct", from: 0.03, to: 0.05 }] },
  ];

  // Alerts
  const alerts = [
    { id: 1, name: "Drawdown crítico", channel: "telegram", trigger: "drawdown < -10%", enabled: true, last_fired: new Date(NOW - 18*3600_000).toISOString() },
    { id: 2, name: "Edge desabilitado", channel: "email", trigger: "any strategy → DISABLED", enabled: true, last_fired: new Date(NOW - 4*3600_000).toISOString() },
    { id: 3, name: "Posição parada > 6h", channel: "telegram", trigger: "open position age > 6h", enabled: false, last_fired: null },
    { id: 4, name: "Kill switch acionado", channel: "telegram+email", trigger: "kill_switch fired", enabled: true, last_fired: null },
  ];
  let tradeId = 50000;
  function makeTrade(ageMin) {
    const m = pick(markets);
    const side = Math.random() > 0.5 ? "YES" : "NO";
    const order_side = Math.random() > 0.6 ? "BUY" : "SELL";
    const r = Math.random();
    const status = r > 0.92 ? "FAILED" : r > 0.84 ? "CANCELED" : r > 0.78 ? "PARTIAL" : r > 0.74 ? "PENDING" : "FILLED";
    const price = +rand(0.1, 0.9).toFixed(3);
    const size = +rand(80, 1500).toFixed(0);
    const shares = +(size / price).toFixed(0);
    const filled_shares = status === "FILLED" ? shares : status === "PARTIAL" ? Math.floor(shares * rand(0.2, 0.85)) : 0;
    const created = new Date(NOW - ageMin * 60_000).toISOString();
    const filled = (status === "FILLED" || status === "PARTIAL") ? new Date(NOW - (ageMin - rand(0.1, 1.2)) * 60_000).toISOString() : null;
    return {
      id: tradeId++,
      client_order_id: "ord_" + Math.random().toString(36).slice(2, 10),
      market_question: m.question,
      strategy: pick(STRATS),
      market_side: side,
      order_side,
      status,
      price,
      size_usd: size,
      shares,
      filled_shares,
      created_at: created,
      filled_at: filled,
    };
  }
  const trades = [];
  for (let i = 0; i < 60; i++) trades.push(makeTrade(i * 7 + rand(0, 6)));

  // --- Risk events ---
  const RISK_KINDS = [
    { kind: "edge_disabled", sev: "warning", msg: "Strategy 'momentum' auto-disabled — win rate < 45% over last 30 trades" },
    { kind: "daily_loss", sev: "warning", msg: "Daily realized loss exceeded -$400 threshold" },
    { kind: "stale_quote", sev: "info", msg: "Polymarket order book stale > 12s on 3 markets" },
    { kind: "drawdown_kill", sev: "critical", msg: "Drawdown -8.2% triggered global kill switch" },
    { kind: "rate_limit", sev: "warning", msg: "CLOB API returned 429 — backing off 30s" },
    { kind: "fill_quality", sev: "info", msg: "Slippage on order 50421 was +1.8% above expected" },
    { kind: "position_size_clip", sev: "info", msg: "Sizing clipped 'arbitrage' entry from $1,400 → $1,000 (per-market cap)" },
    { kind: "ws_reconnect", sev: "info", msg: "WebSocket reconnected after 4.2s outage" },
    { kind: "liquidity_thin", sev: "warning", msg: "Yes-side depth < $2k on 'Will Apple announce…'" },
  ];
  let riskId = 8000;
  const riskEvents = [];
  for (let i = 0; i < 14; i++) {
    const r = RISK_KINDS[ri(0, RISK_KINDS.length)];
    riskEvents.push({
      id: riskId++,
      ts: new Date(NOW - ri(2, 1400) * 60_000).toISOString(),
      kind: r.kind,
      severity: r.sev,
      message: r.msg,
      details: { trigger: "auto", source: "risk-mgr" },
    });
  }
  riskEvents.sort((a, b) => +new Date(b.ts) - +new Date(a.ts));

  // --- Strategy breakdowns per period ---
  function makeStrats(period) {
    const k = period === "24h" ? 1 : period === "7d" ? 4.5 : period === "30d" ? 19 : 88;
    const states = [["overreaction", "HEALTHY"], ["arbitrage", "HEALTHY"], ["momentum", "WATCH"]];
    return states.map(([s, st], i) => {
      const trades = Math.round(rand(8, 32) * k);
      const wins = Math.round(trades * rand(0.46, 0.66));
      const win_rate = wins / Math.max(1, trades);
      const expectancy = +rand(2.4, 18).toFixed(2);
      const total_pnl = +(expectancy * trades).toFixed(2);
      const profit_factor = i === 2 ? +rand(0.95, 1.18).toFixed(2) : +rand(1.4, 3.1).toFixed(2);
      return {
        strategy: s,
        trades,
        win_rate: +win_rate.toFixed(4),
        expectancy_usd: expectancy,
        total_pnl_usd: total_pnl,
        profit_factor,
        avg_hold_minutes: Math.round(rand(8, 240)),
        state: st,
        reason: st === "WATCH" ? "Profit factor below 1.2x last 50 trades" : "",
      };
    });
  }

  // --- Bot status ---
  const botState = {
    running: true,
    started_at: new Date(NOW - 3 * 3600_000 - 12 * 60_000).toISOString(),
    last_loop_at: new Date(NOW - 3_000).toISOString(),
    last_error: null,
    open_positions: 11,
    equity_usd: LIVE_EQUITY,
    dry_run: true,
    live_trading_enabled: false,
  };

  // --- Metrics aggregator per period ---
  function makeMetrics(period) {
    const eqArr = equityHistories[period];
    const first = eqArr[0].equity, last = eqArr[eqArr.length - 1].equity;
    const total_pnl = +(last - first).toFixed(2);
    const realized_today = +rand(180, 1280).toFixed(2);
    const strats = makeStrats(period);
    const total_trades = strats.reduce((s, x) => s + x.trades, 0);
    const wRates = strats.map(s => s.win_rate * s.trades);
    const win_rate = wRates.reduce((a, b) => a + b, 0) / Math.max(1, total_trades);
    const expectancy = +(strats.reduce((s, x) => s + x.expectancy_usd * x.trades, 0) / Math.max(1, total_trades)).toFixed(2);
    return {
      period,
      total_pnl_usd: total_pnl,
      realized_today_usd: realized_today,
      win_rate: +win_rate.toFixed(4),
      total_trades,
      avg_ev_usd: +rand(3.2, 7.8).toFixed(2),
      expectancy_usd: expectancy,
      profit_factor: +rand(1.4, 2.4).toFixed(2),
      sharpe: +rand(1.6, 3.1).toFixed(2),
      sortino: +rand(2.1, 4.4).toFixed(2),
      max_drawdown_pct: +(-rand(2.5, 9.4)).toFixed(2),
      open_positions: positions.filter(p => p.status === "OPEN").length,
      equity_usd: LIVE_EQUITY,
      cash_usd: +(LIVE_EQUITY * 0.58).toFixed(2),
      by_strategy: strats,
    };
  }

  // === LIVE TICK SIMULATION ===
  // Every 5s, drift the equity. Every ~12s, push a new trade. Every ~25s, sometimes a risk event.
  function tick() {
    if (!botState.running) {
      botState.last_loop_at = botState.last_loop_at; // freeze
      return;
    }
    botState.last_loop_at = new Date().toISOString();

    // drift equity
    const drift = (Math.random() - 0.45) * 80;
    const newEq = Math.max(5000, botState.equity_usd + drift);
    botState.equity_usd = +newEq.toFixed(2);

    // append a new equity point on the 24h history (rolling)
    Object.keys(equityHistories).forEach(k => {
      const arr = equityHistories[k];
      arr[arr.length - 1] = {
        ...arr[arr.length - 1],
        time: new Date().toISOString(),
        equity: botState.equity_usd,
      };
    });

    // every few ticks, push new trade
    if (Math.random() < 0.45) {
      trades.unshift(makeTrade(0.1));
      if (trades.length > 200) trades.pop();
    }

    // rare risk event
    if (Math.random() < 0.08) {
      const r = RISK_KINDS[ri(0, RISK_KINDS.length)];
      riskEvents.unshift({
        id: ++riskId,
        ts: new Date().toISOString(),
        kind: r.kind,
        severity: r.sev,
        message: r.msg,
        details: { trigger: "auto" },
      });
      if (riskEvents.length > 50) riskEvents.pop();
    }
    // append fresh log every tick
    {
      const tpl = LOG_TEMPLATES[ri(0, LOG_TEMPLATES.length - 1)];
      const cid = Math.random() < 0.3 && positions.length ? positions[ri(0, positions.length)].correlation_id : "ord_" + Math.random().toString(36).slice(2, 10);
      const [lvl, msg] = tpl(cid);
      logs.push({ id: ++logId, ts: new Date().toISOString(), level: lvl, msg, correlation_id: cid });
      if (logs.length > 800) logs.shift();
    }
  }
  setInterval(tick, 5_000);

  // === Public API surface (mimics fetch w/ React Query) ===
  window.MockAPI = {
    getMetrics: (period) => makeMetrics(period),
    getEquity: (period) => ({ period, points: equityHistories[period].slice() }),
    getEquityEvents: () => equityEvents.slice(),
    getStratSparklines: () => ({ ...stratSparklines }),
    getPositions: (status, limit = 100) => {
      let p = positions;
      if (status === "open") p = positions.filter(x => x.status === "OPEN");
      else if (status === "closed") p = positions.filter(x => x.status !== "OPEN");
      return p.slice(0, limit);
    },
    getTrades: (limit = 25) => trades.slice(0, limit),
    getRiskEvents: (limit = 50) => riskEvents.slice(0, limit),
    getMarkets: () => ({
      count: markets.length,
      refreshed_at: new Date(Date.now() - 8_000).toISOString(),
      is_stale: false,
      markets: markets.slice(),
    }),
    getLogs: (limit = 200, filter = {}) => {
      let L = logs.slice().reverse(); // newest first
      if (filter.level && filter.level !== "ALL") L = L.filter(x => x.level === filter.level);
      if (filter.q) L = L.filter(x => x.msg.toLowerCase().includes(filter.q.toLowerCase()) || x.correlation_id.includes(filter.q));
      if (filter.cid) L = L.filter(x => x.correlation_id === filter.cid);
      return L.slice(0, limit);
    },
    getConfigHistory: () => configHistory.slice().reverse(),
    getAlerts: () => alerts.slice(),
    toggleAlert: (id) => { const a = alerts.find(x => x.id === id); if (a) a.enabled = !a.enabled; return a; },
    closePosition: (id) => {
      const p = positions.find(x => x.id === id);
      if (!p || p.status !== "OPEN") return null;
      p.status = "CLOSED";
      p.exit_price = p.current_price;
      const sign = p.side === "YES" ? 1 : -1;
      p.realized_pnl_usd = +((p.exit_price - p.entry_price) * sign * p.shares).toFixed(2);
      p.closed_at = new Date().toISOString();
      botState.open_positions = positions.filter(x => x.status === "OPEN").length;
      return p;
    },
    killSwitch: () => {
      botState.running = false;
      botState.last_error = "KILL_SWITCH_FIRED";
      // cancel all pending
      trades.forEach(t => { if (t.status === "PENDING") t.status = "CANCELED"; });
      // emit risk event
      riskEvents.unshift({ id: ++riskId, ts: new Date().toISOString(), kind: "kill_switch", severity: "critical", message: "Kill switch global acionado pelo operador", details: { trigger: "manual" } });
      return { running: false };
    },
    setMode: (mode /* "paper" | "live" */) => {
      botState.dry_run = mode === "paper";
      botState.live_trading_enabled = mode === "live";
      return { dry_run: botState.dry_run };
    },
    getBotStatus: () => ({ ...botState }),
    startBot: () => {
      botState.running = true;
      botState.started_at = new Date().toISOString();
      botState.last_error = null;
      return { running: true, message: "Trading runner started." };
    },
    stopBot: () => {
      botState.running = false;
      return { running: false, message: "Trading runner stopped — open positions handed to position manager." };
    },
  };
})();
