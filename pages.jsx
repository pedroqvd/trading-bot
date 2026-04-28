// =====================================================================
// Settings (sliders + hot-reload preview + alerts + config history),
// Backtest (comparator: up to 3 runs overlaid),
// Logs (search + correlation_id filter, level chips, pause/clear).
// =====================================================================

const { LineChart: RcLineChart, Line: RcLine, XAxis: RcXAxis, YAxis: RcYAxis,
  CartesianGrid: RcGrid, Tooltip: RcTooltip, ResponsiveContainer: RcContainer,
  Legend: RcLegend } = window.Recharts;

// ----------------------------------------------------------------------
// Settings
// ----------------------------------------------------------------------

function Slider({ label, hint, value, min, max, step, fmt, onChange, dirty }) {
  return (
    <div className="slider-row">
      <div className="lbl">{label}<small>{hint}</small></div>
      <input
        type="range"
        min={min} max={max} step={step}
        value={value}
        onChange={e => onChange(parseFloat(e.target.value))}
      />
      <div className={`slider-val ${dirty ? "dirty" : ""}`}>{fmt(value)}</div>
    </div>
  );
}

function PreviewPanel({ initial, current }) {
  // preview: estimated change in expected daily PnL given knob deltas vs initial
  const dKelly = current.kelly_fraction - initial.kelly_fraction;
  const dEV = current.min_ev - initial.min_ev;
  const dDD = current.max_drawdown_pct - initial.max_drawdown_pct;

  // crude impact estimate (deterministic, illustrative only)
  const baselineDailyEV = 28.4;
  const dailyEV = baselineDailyEV
    * (1 + dKelly * 1.6)
    * (1 - dEV * 4)
    * (1 + dDD * 0.4);
  const winChance = 0.58 + dKelly * 0.05 - dEV * 0.6;
  const expDD = -3.2 + dKelly * -8 + dDD * 14;

  const dirty = dKelly || dEV || dDD;
  return (
    <div className="card" style={{ padding: 16 }}>
      <div className="card-header">
        <div className="card-title">Preview de impacto (estimativa)</div>
        <span className="card-sub">recalcula em tempo real conforme você ajusta</span>
      </div>
      <div className="kpi-grid" style={{ gridTemplateColumns: "repeat(3, 1fr)", marginTop: 4 }}>
        <div className="kpi">
          <div className="kpi-label">EV diário esperado</div>
          <div className={`kpi-value mono ${dailyEV >= 0 ? "pos" : "neg"}`}>
            {(dailyEV >= 0 ? "+" : "") + Fmt.usd(dailyEV, { cents: true })}
          </div>
          {dirty != 0 && <div className="kpi-delta">vs base {Fmt.usd(baselineDailyEV, { cents: true })}</div>}
        </div>
        <div className="kpi">
          <div className="kpi-label">Probabilidade dia &gt; 0</div>
          <div className="kpi-value mono">{(Math.min(0.95, Math.max(0.30, winChance)) * 100).toFixed(1)}%</div>
        </div>
        <div className="kpi">
          <div className="kpi-label">Drawdown projetado</div>
          <div className="kpi-value mono neg">{expDD.toFixed(2)}%</div>
        </div>
      </div>
      {dirty && (
        <div className="dialog-warn" style={{ marginTop: 12 }}>
          Alterações pendentes — clique em "Salvar alterações" para aplicar ao runner em tempo real.
        </div>
      )}
    </div>
  );
}

function AlertsPanel() {
  const [alerts, setAlerts] = React.useState(() => MockAPI.getAlerts());
  const toggle = (id) => {
    MockAPI.toggleAlert(id);
    setAlerts(MockAPI.getAlerts());
  };
  return (
    <div className="card" style={{ padding: 0, overflow: "hidden" }}>
      <div className="card-header" style={{ padding: "16px 16px 4px" }}>
        <div className="card-title">Alertas configuráveis</div>
        <span className="card-sub">Telegram, e-mail · disparo automático no servidor</span>
      </div>
      {alerts.map(a => (
        <div className="alert-row" key={a.id}>
          <div className="alert-name">
            {a.name}
            <small>quando: {a.trigger}</small>
          </div>
          <div className="alert-channel">{a.channel}</div>
          <div className="alert-fired">{a.last_fired ? `disparado ${Fmt.timeAgo(a.last_fired)}` : "nunca disparou"}</div>
          <span className={`toggle ${a.enabled ? "on" : ""}`} onClick={() => toggle(a.id)}>
            <span className="toggle-track" />
            <span style={{ color: a.enabled ? "var(--accent)" : "var(--text-muted)" }}>
              {a.enabled ? "Ativo" : "Inativo"}
            </span>
          </span>
        </div>
      ))}
    </div>
  );
}

function ConfigHistory() {
  const history = MockAPI.getConfigHistory();
  return (
    <div className="card" style={{ padding: 0, overflow: "hidden" }}>
      <div className="card-header" style={{ padding: "16px 16px 8px" }}>
        <div className="card-title">Histórico de mudanças</div>
        <span className="card-sub">auditoria · diff entre versões</span>
      </div>
      {history.length === 0 ? (
        <div className="empty">Sem alterações registradas.</div>
      ) : history.map((h, i) => (
        <div className="cfg-history-row" key={i}>
          <div className="cfg-history-meta">
            <span>
              <span className="pill" style={{ marginRight: 6 }}>{h.user}</span>
              {new Date(h.ts).toLocaleString("pt-BR")}
            </span>
            <span className="mono">{h.changes.length} mudança{h.changes.length > 1 ? "s" : ""}</span>
          </div>
          <div className="cfg-diff">
            {h.changes.map((c, j) => (
              <React.Fragment key={j}>
                <div className="cfg-diff-line from">- {c.key}: {JSON.stringify(c.from)}</div>
                <div className="cfg-diff-line to">+ {c.key}: {JSON.stringify(c.to)}</div>
              </React.Fragment>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

function SettingsPage({ pushToast }) {
  const initial = React.useMemo(() => ({
    capital_usd: 1000,
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
  }), []);
  const [cfg, setCfg] = React.useState(initial);
  const [saved, setSaved] = React.useState(false);
  const set = (k, v) => setCfg(c => ({ ...c, [k]: v }));
  const tog = (k) => (
    <span className={`toggle ${cfg[k] ? "on" : ""}`} onClick={() => set(k, !cfg[k])}>
      <span className="toggle-track" />
      <span style={{ color: cfg[k] ? "var(--accent)" : "var(--text-muted)" }}>{cfg[k] ? "Ativado" : "Desativado"}</span>
    </span>
  );
  const dirty = (k) => cfg[k] !== initial[k];
  const onSave = () => {
    setSaved(true);
    pushToast?.("Configurações aplicadas ao runner em tempo real.", "warn");
    setTimeout(() => setSaved(false), 2200);
  };
  const onReset = () => setCfg(initial);

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h1>Configurações</h1>
          <div className="sub">Sliders com hot-reload — preview de impacto recalcula instantaneamente.</div>
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          {saved && <span className="pill healthy">Salvo</span>}
          <button className="btn" onClick={onReset}>Restaurar</button>
          <button className="btn btn-primary" onClick={onSave}>Salvar alterações</button>
        </div>
      </div>

      <div style={{ marginBottom: 12 }}>
        <PreviewPanel initial={initial} current={cfg} />
      </div>

      <div className="row-2">
        <div>
          <div className="card" style={{ marginBottom: 12, padding: 0, overflow: "hidden" }}>
            <div className="card-header" style={{ padding: "16px 16px 4px" }}><div className="card-title">Risco</div></div>
            <Slider
              label="Fração de Kelly" hint="multiplicador da aposta"
              value={cfg.kelly_fraction} min={0.05} max={0.50} step={0.01}
              fmt={v => v.toFixed(2)}
              dirty={dirty("kelly_fraction")}
              onChange={v => set("kelly_fraction", v)}
            />
            <Slider
              label="Tamanho máx. por trade" hint="% do patrimônio"
              value={cfg.max_position_pct} min={0.01} max={0.20} step={0.005}
              fmt={v => (v * 100).toFixed(1) + "%"}
              dirty={dirty("max_position_pct")}
              onChange={v => set("max_position_pct", v)}
            />
            <Slider
              label="Perda diária máxima" hint="circuit breaker diário"
              value={cfg.max_daily_loss_pct} min={0.01} max={0.10} step={0.005}
              fmt={v => (v * 100).toFixed(1) + "%"}
              dirty={dirty("max_daily_loss_pct")}
              onChange={v => set("max_daily_loss_pct", v)}
            />
            <Slider
              label="Drawdown máximo" hint="kill switch geral"
              value={cfg.max_drawdown_pct} min={0.05} max={0.30} step={0.01}
              fmt={v => (v * 100).toFixed(1) + "%"}
              dirty={dirty("max_drawdown_pct")}
              onChange={v => set("max_drawdown_pct", v)}
            />
          </div>

          <div className="card" style={{ marginBottom: 12, padding: 0, overflow: "hidden" }}>
            <div className="card-header" style={{ padding: "16px 16px 4px" }}><div className="card-title">Edge</div></div>
            <Slider
              label="Mispricing mínimo" hint="diferença mínima de preço"
              value={cfg.min_mispricing} min={0.005} max={0.10} step={0.005}
              fmt={v => v.toFixed(3)}
              dirty={dirty("min_mispricing")}
              onChange={v => set("min_mispricing", v)}
            />
            <Slider
              label="EV mínimo" hint="valor esperado por trade"
              value={cfg.min_ev} min={0.005} max={0.05} step={0.0025}
              fmt={v => v.toFixed(4)}
              dirty={dirty("min_ev")}
              onChange={v => set("min_ev", v)}
            />
            <Slider
              label="Liquidez mínima" hint="profundidade do book (USD)"
              value={cfg.min_liquidity} min={100} max={5000} step={100}
              fmt={v => Fmt.usd(v)}
              dirty={dirty("min_liquidity")}
              onChange={v => set("min_liquidity", v)}
            />
            <Slider
              label="Spread máximo" hint="bid/ask aceitável"
              value={cfg.max_spread} min={0.005} max={0.10} step={0.005}
              fmt={v => v.toFixed(3)}
              dirty={dirty("max_spread")}
              onChange={v => set("max_spread", v)}
            />
          </div>

          <div className="card">
            <div className="card-header"><div className="card-title">Estratégias ativas</div></div>
            <div className="form-row"><div className="lbl">Sobrerreação<small>Reversão após movimentos &gt; 10%</small></div>{tog("overreaction_enabled")}</div>
            <div className="form-row"><div className="lbl">Arbitragem<small>Quando yes_ask + no_ask &lt; 1</small></div>{tog("arbitrage_enabled")}</div>
            <div className="form-row"><div className="lbl">Momentum<small>Continuação de tendência (Fase 2)</small></div>{tog("momentum_enabled")}</div>
          </div>
        </div>

        <div>
          <div style={{ marginBottom: 12 }}>
            <AlertsPanel />
          </div>
          <ConfigHistory />
        </div>
      </div>
    </div>
  );
}

// ----------------------------------------------------------------------
// Backtest (comparator)
// ----------------------------------------------------------------------

const BT_COLORS = ["#5cf2c7", "#6aa9ff", "#ffb84a"];

function BacktestPage() {
  const [running, setRunning] = React.useState(false);
  const [progress, setProgress] = React.useState(0);
  const [strategy, setStrategy] = React.useState("overreaction");
  const [from, setFrom] = React.useState("2026-01-01");
  const [to, setTo] = React.useState("2026-04-26");
  const [capital, setCapital] = React.useState(1000);
  const [runs, setRuns] = React.useState([]);  // up to 3 saved runs

  const run = () => {
    if (runs.length >= 3) return;
    setRunning(true); setProgress(0);
    let p = 0;
    const id = setInterval(() => {
      p += 4 + Math.random() * 6;
      if (p >= 100) {
        p = 100;
        clearInterval(id);
        setRunning(false);
        const points = [];
        let eq = capital;
        for (let i = 0; i < 120; i++) {
          eq *= 1 + (Math.random() - 0.46) * 0.012;
          points.push({
            time: new Date(Date.now() - (120 - i) * 86400000 / 4).toISOString(),
            equity: +eq.toFixed(2),
          });
        }
        const r = {
          id: Date.now(),
          label: `${strategy} · ${from} → ${to} · ${Fmt.usd(capital)}`,
          color: BT_COLORS[runs.length],
          strategy, from, to, capital,
          final_equity: +eq.toFixed(2),
          total_return: +((eq / capital - 1) * 100).toFixed(2),
          sharpe: +(1.4 + Math.random() * 1.6).toFixed(2),
          max_dd: +(-(2 + Math.random() * 8)).toFixed(2),
          trades: 80 + Math.floor(Math.random() * 200),
          win_rate: +(0.48 + Math.random() * 0.18).toFixed(3),
          points,
        };
        setRuns(rs => [...rs, r]);
      }
      setProgress(Math.min(100, p));
    }, 120);
  };

  const removeRun = (id) => setRuns(rs => rs.filter(r => r.id !== id));
  const clearAll = () => setRuns([]);

  // Build merged data series for overlay
  const merged = React.useMemo(() => {
    if (runs.length === 0) return [];
    const len = Math.max(...runs.map(r => r.points.length));
    const out = [];
    for (let i = 0; i < len; i++) {
      const row = { idx: i };
      runs.forEach(r => {
        row[`r${r.id}`] = r.points[i]?.equity ?? null;
      });
      out.push(row);
    }
    return out;
  }, [runs]);

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h1>Backtest</h1>
          <div className="sub">Compare até 3 execuções sobrepostas — ajuste edges, períodos e capital.</div>
        </div>
        {runs.length > 0 && <button className="btn" onClick={clearAll}>Limpar todas ({runs.length})</button>}
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
          <button className="btn btn-primary" onClick={run} disabled={running || runs.length >= 3}>
            {running ? "Executando…" : runs.length >= 3 ? "Máx. 3 execuções" : runs.length > 0 ? "▶ Rodar e adicionar" : "▶ Executar backtest"}
          </button>
          {running && (
            <div style={{ flex: 1, height: 6, background: "var(--surface-hi)", borderRadius: 3, overflow: "hidden" }}>
              <div style={{ width: `${progress}%`, height: "100%", background: "var(--accent)", transition: "width 100ms linear" }} />
            </div>
          )}
          {running && <span className="mono txt-muted" style={{ fontSize: 11 }}>{progress.toFixed(0)}%</span>}
        </div>
      </div>

      {runs.length > 0 && (
        <>
          <div className="card" style={{ marginBottom: 12 }}>
            <div className="card-header">
              <div className="card-title">Comparador</div>
              <span className="card-sub">{runs.length} de 3 execuções sobrepostas</span>
            </div>
            <div style={{ padding: "0 16px 8px" }}>
              {runs.map(r => (
                <div key={r.id} className="bt-overlay-row">
                  <span className="bt-color" style={{ background: r.color }} />
                  <span title={r.label} style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{r.label}</span>
                  <span className={`mono ${r.total_return >= 0 ? "txt-pos" : "txt-neg"}`} style={{ textAlign: "right" }}>
                    {(r.total_return >= 0 ? "+" : "") + r.total_return.toFixed(2) + "%"}
                  </span>
                  <span className="mono" style={{ textAlign: "right", color: "var(--text-muted)" }}>SR {r.sharpe.toFixed(2)}</span>
                  <span className="mono txt-neg" style={{ textAlign: "right" }}>DD {r.max_dd.toFixed(2)}%</span>
                  <button className="bt-rm" onClick={() => removeRun(r.id)} title="Remover">✕</button>
                </div>
              ))}
            </div>
          </div>

          <div className="card" style={{ height: 360, display: "flex", flexDirection: "column" }}>
            <div className="card-header"><div className="card-title">Curvas sobrepostas</div></div>
            <div style={{ flex: 1, minHeight: 0 }}>
              <RcContainer width="100%" height="100%">
                <RcLineChart data={merged} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
                  <RcGrid strokeDasharray="3 4" stroke="#1e2740" vertical={false} />
                  <RcXAxis dataKey="idx" tick={{ fill: "#7c8aa8", fontSize: 10.5 }} axisLine={{ stroke: "#1e2740" }} tickLine={false} />
                  <RcYAxis orientation="right" tick={{ fill: "#7c8aa8", fontSize: 10.5 }} axisLine={false} tickLine={false} width={56} tickFormatter={v => `$${(v/1000).toFixed(1)}k`} />
                  <RcTooltip
                    contentStyle={{ background: "#161d31", border: "1px solid #2a3554", fontSize: 11, fontFamily: "JetBrains Mono, monospace" }}
                    formatter={(v) => Fmt.usdPrecise(v)}
                  />
                  <RcLegend wrapperStyle={{ fontSize: 11 }} />
                  {runs.map(r => (
                    <RcLine
                      key={r.id}
                      type="monotone"
                      dataKey={`r${r.id}`}
                      name={r.strategy}
                      stroke={r.color}
                      strokeWidth={1.8}
                      dot={false}
                      isAnimationActive={false}
                    />
                  ))}
                </RcLineChart>
              </RcContainer>
            </div>
          </div>
        </>
      )}

      {runs.length === 0 && !running && (
        <div className="card empty">Configure os parâmetros acima e execute para começar a comparar.</div>
      )}
    </div>
  );
}

// ----------------------------------------------------------------------
// Logs page (search + correlation_id deep-link)
// ----------------------------------------------------------------------

function LogsPage({ cidFilter, onClearCid }) {
  const [logs, setLogs] = React.useState([]);
  const [filter, setFilter] = React.useState("ALL");
  const [paused, setPaused] = React.useState(false);
  const [q, setQ] = React.useState("");

  const fetchLogs = React.useCallback(() => {
    setLogs(MockAPI.getLogs(300, {
      level: filter,
      q: q || undefined,
      cid: cidFilter || undefined,
    }));
  }, [filter, q, cidFilter]);

  React.useEffect(() => {
    fetchLogs();
    if (paused) return;
    const id = setInterval(fetchLogs, 1500);
    return () => clearInterval(id);
  }, [fetchLogs, paused]);

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h1>Logs e observabilidade</h1>
          <div className="sub">Stream em tempo real do executor · busca por mensagem ou correlation_id.</div>
        </div>
        <div className="logs-toolbar">
          <input
            className="logs-search"
            placeholder="Buscar mensagem ou ord_xxxxxx…"
            value={q}
            onChange={e => setQ(e.target.value)}
          />
          <div className="segmented">
            {["ALL", "INFO", "WARN", "ERROR", "DEBUG"].map(l => (
              <button key={l} className={l === filter ? "active" : ""} onClick={() => setFilter(l)}>{l}</button>
            ))}
          </div>
          <button className="btn" onClick={() => setPaused(p => !p)}>{paused ? "▶ Retomar" : "⏸ Pausar"}</button>
          <button className="btn" onClick={() => setLogs([])}>Limpar</button>
        </div>
      </div>

      {cidFilter && (
        <div style={{ marginBottom: 8 }}>
          <span className="cid-filter-banner">
            Filtrando por correlation_id: <strong>{cidFilter}</strong>
            <button className="clear" onClick={onClearCid} title="Remover filtro">✕</button>
          </span>
        </div>
      )}

      <div className="card" style={{ padding: 0, overflow: "hidden", maxHeight: 640 }}>
        <div style={{ maxHeight: 640, overflow: "auto" }}>
          {logs.length === 0 ? (
            <div className="empty">Nenhum log para o filtro atual.</div>
          ) : (
            logs.map(l => (
              <div className={`log-line ${cidFilter && l.correlation_id === cidFilter ? "highlighted" : ""}`} key={l.id}>
                <span className="log-time">{Fmt.timeOfDay(l.ts)}</span>
                <span className={`log-level ${l.level}`}>{l.level}</span>
                <span className="log-msg" title={l.msg}>{l.msg}</span>
                {l.correlation_id && (
                  <span className="log-cid" title="Filtrar por este correlation_id">
                    {l.correlation_id}
                  </span>
                )}
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}

Object.assign(window, { SettingsPage, BacktestPage, LogsPage });
