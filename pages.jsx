// =====================================================================
// Settings, Backtest, Logs pages
// =====================================================================

function SettingsPage() {
  const [cfg, setCfg] = React.useState({
    capital_usd: 1000,
    dry_run: true,
    poll_interval: 30,
    max_open_positions: 20,
    min_mispricing: 0.03,
    min_ev: 0.015,
    min_liquidity: 500,
    max_spread: 0.04,
    kelly_fraction: 0.25,
    max_position_pct: 0.05,
    max_daily_loss_pct: 0.05,
    max_drawdown_pct: 0.15,
    overreaction_enabled: true,
    arbitrage_enabled: true,
    momentum_enabled: false,
  });
  const [saved, setSaved] = React.useState(false);

  const set = (k, v) => setCfg(c => ({ ...c, [k]: v }));
  const num = (k) => (
    <input className="input" type="number" value={cfg[k]} step="0.001" onChange={e => set(k, parseFloat(e.target.value))} />
  );
  const tog = (k) => (
    <span className={`toggle ${cfg[k] ? "on" : ""}`} onClick={() => set(k, !cfg[k])}>
      <span className="toggle-track" />
      <span style={{ color: cfg[k] ? "var(--accent)" : "var(--text-muted)" }}>{cfg[k] ? "Ativado" : "Desativado"}</span>
    </span>
  );

  const onSave = () => { setSaved(true); setTimeout(() => setSaved(false), 2200); };

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h1>Configurações</h1>
          <div className="sub">Parâmetros do bot, edges e gestão de risco.</div>
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          {saved && <span className="pill healthy">Salvo</span>}
          <button className="btn btn-primary" onClick={onSave}>Salvar alterações</button>
        </div>
      </div>

      <div className="card" style={{ marginBottom: 12 }}>
        <div className="card-header"><div className="card-title">Trading</div></div>
        <div className="form-row"><div className="lbl">Capital (USD)<small>Capital total disponível</small></div>{num("capital_usd")}</div>
        <div className="form-row"><div className="lbl">Modo simulação<small>true = nenhuma ordem real é enviada</small></div>{tog("dry_run")}</div>
        <div className="form-row"><div className="lbl">Intervalo de scan (s)<small>Cadência de varredura de mercado</small></div>{num("poll_interval")}</div>
        <div className="form-row"><div className="lbl">Máx. posições abertas<small>Limite simultâneo</small></div>{num("max_open_positions")}</div>
      </div>

      <div className="card" style={{ marginBottom: 12 }}>
        <div className="card-header"><div className="card-title">Limiares de edge</div></div>
        <div className="form-row"><div className="lbl">Mispricing mínimo<small>Diferença mínima de preço (centavos)</small></div>{num("min_mispricing")}</div>
        <div className="form-row"><div className="lbl">EV mínimo<small>Valor esperado mínimo</small></div>{num("min_ev")}</div>
        <div className="form-row"><div className="lbl">Liquidez mínima (USD)<small>Profundidade mínima de book</small></div>{num("min_liquidity")}</div>
        <div className="form-row"><div className="lbl">Spread máximo<small>Spread bid/ask aceitável</small></div>{num("max_spread")}</div>
      </div>

      <div className="card" style={{ marginBottom: 12 }}>
        <div className="card-header"><div className="card-title">Gestão de risco</div></div>
        <div className="form-row"><div className="lbl">Fração de Kelly<small>Multiplicador da aposta de Kelly</small></div>{num("kelly_fraction")}</div>
        <div className="form-row"><div className="lbl">Máx. posição (%)<small>Tamanho máximo por trade</small></div>{num("max_position_pct")}</div>
        <div className="form-row"><div className="lbl">Perda diária máxima<small>Disjuntor de drawdown diário</small></div>{num("max_daily_loss_pct")}</div>
        <div className="form-row"><div className="lbl">Drawdown máximo<small>Kill-switch geral</small></div>{num("max_drawdown_pct")}</div>
      </div>

      <div className="card">
        <div className="card-header"><div className="card-title">Estratégias ativas</div></div>
        <div className="form-row"><div className="lbl">Sobrerreação<small>Reversão após movimentos &gt; 10%</small></div>{tog("overreaction_enabled")}</div>
        <div className="form-row"><div className="lbl">Arbitragem<small>Quando yes_ask + no_ask &lt; 1</small></div>{tog("arbitrage_enabled")}</div>
        <div className="form-row"><div className="lbl">Momentum<small>Continuação de tendência (Fase 2)</small></div>{tog("momentum_enabled")}</div>
      </div>
    </div>
  );
}

function BacktestPage() {
  const [running, setRunning] = React.useState(false);
  const [progress, setProgress] = React.useState(0);
  const [result, setResult] = React.useState(null);
  const [strategy, setStrategy] = React.useState("overreaction");
  const [from, setFrom] = React.useState("2026-01-01");
  const [to, setTo] = React.useState("2026-04-26");
  const [capital, setCapital] = React.useState(1000);

  const run = () => {
    setRunning(true); setProgress(0); setResult(null);
    let p = 0;
    const id = setInterval(() => {
      p += 4 + Math.random() * 6;
      if (p >= 100) {
        p = 100;
        clearInterval(id);
        setRunning(false);
        // build a fake equity curve
        const points = [];
        let eq = capital;
        for (let i = 0; i < 120; i++) {
          eq *= 1 + (Math.random() - 0.46) * 0.012;
          points.push({ time: new Date(Date.now() - (120 - i) * 86400000 / 4).toISOString(), equity: +eq.toFixed(2), cash: eq * 0.6, unrealized: eq * 0.4 });
        }
        setResult({
          strategy, from, to, capital,
          final_equity: +eq.toFixed(2),
          total_return: +((eq / capital - 1) * 100).toFixed(2),
          sharpe: +(1.4 + Math.random() * 1.6).toFixed(2),
          max_dd: +(-(2 + Math.random() * 8)).toFixed(2),
          trades: 80 + Math.floor(Math.random() * 200),
          win_rate: +(0.48 + Math.random() * 0.18).toFixed(3),
          points,
        });
      }
      setProgress(Math.min(100, p));
    }, 120);
  };

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h1>Backtest</h1>
          <div className="sub">Reproduza estratégias contra dados históricos.</div>
        </div>
      </div>

      <div className="card" style={{ marginBottom: 12 }}>
        <div className="card-header"><div className="card-title">Configuração da execução</div></div>
        <div className="form-row">
          <div className="lbl">Estratégia<small>Edge a testar</small></div>
          <select className="input" value={strategy} onChange={e => setStrategy(e.target.value)}>
            <option value="overreaction">Sobrerreação</option>
            <option value="arbitrage">Arbitragem</option>
            <option value="momentum">Momentum</option>
            <option value="all">Todas combinadas</option>
          </select>
        </div>
        <div className="form-row"><div className="lbl">Início</div><input className="input" type="date" value={from} onChange={e => setFrom(e.target.value)} /></div>
        <div className="form-row"><div className="lbl">Fim</div><input className="input" type="date" value={to} onChange={e => setTo(e.target.value)} /></div>
        <div className="form-row"><div className="lbl">Capital inicial (USD)</div><input className="input" type="number" value={capital} onChange={e => setCapital(parseFloat(e.target.value))} /></div>
        <div style={{ marginTop: 14, display: "flex", gap: 8, alignItems: "center" }}>
          <button className="btn btn-primary" onClick={run} disabled={running}>{running ? "Executando…" : "▶ Executar backtest"}</button>
          {running && (
            <div style={{ flex: 1, height: 6, background: "var(--surface-hi)", borderRadius: 3, overflow: "hidden" }}>
              <div style={{ width: `${progress}%`, height: "100%", background: "var(--accent)", transition: "width 100ms linear" }} />
            </div>
          )}
          {running && <span className="mono txt-muted" style={{ fontSize: 11 }}>{progress.toFixed(0)}%</span>}
        </div>
      </div>

      {result && (
        <>
          <div className="kpi-grid" style={{ gridTemplateColumns: "repeat(4, 1fr)" }}>
            <div className="kpi"><div className="kpi-label">Patrimônio final</div><div className="kpi-value mono">{Fmt.usdPrecise(result.final_equity)}</div><div className="kpi-delta">de {Fmt.usdPrecise(result.capital)}</div></div>
            <div className="kpi"><div className="kpi-label">Retorno total</div><div className={`kpi-value mono ${result.total_return >= 0 ? "pos" : "neg"}`}>{(result.total_return >= 0 ? "+" : "") + result.total_return.toFixed(2) + "%"}</div></div>
            <div className="kpi"><div className="kpi-label">Sharpe</div><div className="kpi-value mono">{result.sharpe.toFixed(2)}</div><div className="kpi-delta neg">DD {result.max_dd.toFixed(2)}%</div></div>
            <div className="kpi"><div className="kpi-label">Operações</div><div className="kpi-value mono">{result.trades}</div><div className="kpi-delta">acerto {(result.win_rate * 100).toFixed(1)}%</div></div>
          </div>
          <div className="card" style={{ marginTop: 12, height: 320, display: "flex", flexDirection: "column" }}>
            <div className="card-header"><div className="card-title">Curva de patrimônio simulada</div><span className="card-sub">{result.from} → {result.to}</span></div>
            <div style={{ flex: 1, minHeight: 0 }}>
              <EquityChart points={result.points} period="all" running={true} onStart={() => {}} />
            </div>
          </div>
        </>
      )}

      {!result && !running && (
        <div className="card empty">Configure os parâmetros acima e execute para ver os resultados.</div>
      )}
    </div>
  );
}

const LOG_SAMPLES = [
  ["INFO", "Loop completo em 312ms — 18 mercados varridos"],
  ["INFO", "Candidato: 'Will Bitcoin close above…' edge=0.042 EV=0.018"],
  ["INFO", "Ordem ord_a8f3b2 enviada: BUY YES @ 0.612 size=$420"],
  ["INFO", "Ordem ord_a8f3b2 FILLED em 142ms"],
  ["WARN", "CLOB API 429 — backoff 30s"],
  ["INFO", "Posição 1042 atingiu TP @ 0.682 (+11.4%)"],
  ["DEBUG", "Cache de mercados invalidado (ttl)"],
  ["WARN", "Slippage observado +1.8% acima do esperado em ord_91ee4c"],
  ["ERROR", "Falha ao reconciliar posição 1018 — retry 1/3"],
  ["INFO", "Reconciliação OK após 2 tentativas"],
  ["INFO", "WS reconectado após 4.2s"],
  ["DEBUG", "Edge 'momentum' score=0.72 velocity=0.0041 z=1.6"],
  ["INFO", "Posição 1051 fechada — sinal de estratégia"],
  ["WARN", "Liquidez < $2k em 'Will Apple announce…' — pulando"],
  ["INFO", "Risk-mgr: drawdown atual -2.1% (limite -15%)"],
];

function LogsPage() {
  const [logs, setLogs] = React.useState(() => {
    const out = [];
    for (let i = 0; i < 60; i++) {
      const [lvl, msg] = LOG_SAMPLES[i % LOG_SAMPLES.length];
      out.push({ id: i, ts: new Date(Date.now() - i * 4200).toISOString(), level: lvl, msg });
    }
    return out;
  });
  const [filter, setFilter] = React.useState("ALL");
  const [paused, setPaused] = React.useState(false);

  React.useEffect(() => {
    if (paused) return;
    const id = setInterval(() => {
      const [lvl, msg] = LOG_SAMPLES[Math.floor(Math.random() * LOG_SAMPLES.length)];
      setLogs(L => [{ id: Date.now() + Math.random(), ts: new Date().toISOString(), level: lvl, msg }, ...L].slice(0, 200));
    }, 1800);
    return () => clearInterval(id);
  }, [paused]);

  const filtered = logs.filter(l => filter === "ALL" || l.level === filter);

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h1>Logs e observabilidade</h1>
          <div className="sub">Stream em tempo real do executor.</div>
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <div className="segmented">
            {["ALL", "INFO", "WARN", "ERROR", "DEBUG"].map(l => (
              <button key={l} className={l === filter ? "active" : ""} onClick={() => setFilter(l)}>{l}</button>
            ))}
          </div>
          <button className="btn" onClick={() => setPaused(p => !p)}>{paused ? "▶ Retomar" : "⏸ Pausar"}</button>
          <button className="btn" onClick={() => setLogs([])}>Limpar</button>
        </div>
      </div>

      <div className="card" style={{ padding: 0, overflow: "hidden", maxHeight: 640 }}>
        <div style={{ maxHeight: 640, overflow: "auto" }}>
          {filtered.length === 0 ? (
            <div className="empty">Nenhum log para o filtro atual.</div>
          ) : (
            filtered.map(l => (
              <div className="log-line" key={l.id}>
                <span className="log-time">{Fmt.timeOfDay(l.ts)}</span>
                <span className={`log-level ${l.level}`}>{l.level}</span>
                <span className="log-msg" title={l.msg}>{l.msg}</span>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}

Object.assign(window, { SettingsPage, BacktestPage, LogsPage });
