// =====================================================================
// Sparkline, MiniBar, Heatmap, LiveFeed, ShortcutsStrip,
// Density context, KillSwitch, ModeToggle, etc.
// =====================================================================

// ---- Density context (shared) ----
const DensityCtx = React.createContext({ dense: false, setDense: () => {} });

function DensityProvider({ children }) {
  const [dense, setDense] = React.useState(() => localStorage.getItem("dense") === "1");
  React.useEffect(() => {
    document.documentElement.classList.toggle("dense", dense);
    localStorage.setItem("dense", dense ? "1" : "0");
  }, [dense]);
  return <DensityCtx.Provider value={{ dense, setDense }}>{children}</DensityCtx.Provider>;
}

// ---- Pure SVG sparkline ----
function Sparkline({ values, width = 80, height = 22, strokeWidth = 1.4, color }) {
  if (!values || values.length < 2) return <svg width={width} height={height} />;
  const min = Math.min(...values), max = Math.max(...values);
  const span = max - min || 1;
  const stepX = width / (values.length - 1);
  const pts = values.map((v, i) => `${(i * stepX).toFixed(1)},${(height - ((v - min) / span) * height).toFixed(1)}`);
  const last = values[values.length - 1], first = values[0];
  const auto = last >= first ? "var(--accent)" : "var(--danger)";
  const stroke = color || auto;
  // baseline area
  const area = `M0,${height} L${pts.join(" L")} L${width},${height} Z`;
  return (
    <svg width={width} height={height} className="sparkline" style={{ display: "block" }}>
      <path d={area} fill={stroke} opacity="0.10" />
      <polyline points={pts.join(" ")} fill="none" stroke={stroke} strokeWidth={strokeWidth} strokeLinejoin="round" strokeLinecap="round" />
      <circle cx={width} cy={height - ((last - min) / span) * height} r="1.6" fill={stroke} />
    </svg>
  );
}

// ---- Live Feed (right column) ----
function LiveFeed({ trades, riskEvents, onJumpToLogs }) {
  const [tab, setTab] = React.useState("all");

  // merge + sort
  const items = React.useMemo(() => {
    const t = (trades || []).slice(0, 20).map(x => ({
      kind: "trade", ts: x.created_at, data: x, key: "t-" + x.id,
    }));
    const r = (riskEvents || []).slice(0, 15).map(x => ({
      kind: "risk", ts: x.ts, data: x, key: "r-" + x.id,
    }));
    return [...t, ...r].sort((a, b) => +new Date(b.ts) - +new Date(a.ts));
  }, [trades, riskEvents]);

  const filtered = items.filter(x => tab === "all" || x.kind === tab);

  return (
    <aside className="live-feed">
      <div className="lf-head">
        <span className="lf-pulse" />
        <span className="lf-title">AO VIVO</span>
        <div className="lf-tabs">
          <button className={tab === "all" ? "active" : ""} onClick={() => setTab("all")}>Tudo</button>
          <button className={tab === "trade" ? "active" : ""} onClick={() => setTab("trade")}>Ordens</button>
          <button className={tab === "risk" ? "active" : ""} onClick={() => setTab("risk")}>Risco</button>
        </div>
      </div>
      <div className="lf-body">
        {filtered.length === 0 && <div className="empty" style={{ padding: 24, fontSize: 11 }}>—</div>}
        {filtered.map((it, i) => (
          <div key={it.key} className={`lf-item ${i === 0 ? "fresh" : ""}`}>
            {it.kind === "trade" ? (
              <>
                <div className="lf-row1">
                  <span className={`lf-dot ${it.data.status === "FILLED" ? "ok" : it.data.status === "FAILED" ? "err" : it.data.status === "CANCELED" ? "muted" : "warn"}`} />
                  <span className="mono lf-cid" onClick={() => onJumpToLogs(it.data.client_order_id)} title="Ver logs relacionados">{it.data.client_order_id}</span>
                  <span className="lf-time mono">{Fmt.timeOfDay(it.ts)}</span>
                </div>
                <div className="lf-row2">
                  <span className="mono" style={{ color: it.data.order_side === "BUY" ? "var(--accent)" : "var(--no)" }}>{it.data.order_side}</span>
                  <span className={`pill mini ${it.data.market_side === "YES" ? "yes" : "no"}`}>{it.data.market_side}</span>
                  <span className="mono">@{it.data.price.toFixed(3)}</span>
                  <span className="mono txt-muted">{Fmt.usd(it.data.size_usd)}</span>
                </div>
                <div className="lf-mkt" title={it.data.market_question}>{it.data.market_question}</div>
              </>
            ) : (
              <>
                <div className="lf-row1">
                  <span className={`lf-dot risk-${it.data.severity}`} />
                  <span className="mono lf-kind">{it.data.kind}</span>
                  <span className="lf-time mono">{Fmt.timeOfDay(it.ts)}</span>
                </div>
                <div className="lf-mkt risk-msg">{it.data.message}</div>
              </>
            )}
          </div>
        ))}
      </div>
    </aside>
  );
}

// ---- Mode (Paper / Live) toggle ----
function ModeToggle({ status, onChange, refetch }) {
  const [confirming, setConfirming] = React.useState(false);
  const isLive = status?.live_trading_enabled === true;
  const requestSwitch = () => {
    if (isLive) {
      MockAPI.setMode("paper");
      refetch();
    } else {
      setConfirming(true);
    }
  };
  const confirmLive = () => {
    MockAPI.setMode("live");
    setConfirming(false);
    refetch();
    onChange?.("live");
  };
  return (
    <>
      <button className={`mode-toggle ${isLive ? "live" : "paper"}`} onClick={requestSwitch} title="Alterna entre Simulação e Real">
        <span className="mt-pill">{isLive ? "REAL" : "SIMULAÇÃO"}</span>
        <span className="mt-arrow">⇄</span>
        <span className="mt-pill ghost">{isLive ? "Simulação" : "Real"}</span>
      </button>
      {confirming && (
        <div className="dialog-backdrop" onClick={() => setConfirming(false)}>
          <div className="dialog danger-dialog" onClick={e => e.stopPropagation()}>
            <h3>Mudar para modo REAL?</h3>
            <p>Ordens reais passarão a ser enviadas para o Polymarket CLOB. Capital real será movido. Esta ação requer confirmação dupla.</p>
            <div className="dialog-warn">
              ⚠ Verifique limites de risco antes de prosseguir. Drawdown máximo: 15%. Fração de Kelly: 0.25.
            </div>
            <div className="dialog-actions">
              <button className="btn" onClick={() => setConfirming(false)}>Cancelar</button>
              <button className="btn btn-danger" onClick={confirmLive}>Sim, ativar modo REAL</button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}

// ---- Kill switch button + dialog ----
function KillSwitch({ status, refetch, pushToast }) {
  const [open, setOpen] = React.useState(false);
  const [stage, setStage] = React.useState(0); // 0=idle, 1=confirm, 2=typed
  const [typed, setTyped] = React.useState("");
  const fire = () => {
    MockAPI.killSwitch();
    setOpen(false); setStage(0); setTyped("");
    refetch();
    pushToast?.("KILL SWITCH acionado · todas as ordens canceladas.", "danger");
  };
  return (
    <>
      <button className="killswitch" onClick={() => { setOpen(true); setStage(1); }} title="Kill switch global — para o bot e cancela todas as ordens">
        <span className="ks-dot" /> KILL
      </button>
      {open && (
        <div className="dialog-backdrop" onClick={() => { setOpen(false); setStage(0); setTyped(""); }}>
          <div className="dialog danger-dialog" onClick={e => e.stopPropagation()}>
            <h3>⚠ Kill switch global</h3>
            <p>Esta ação:</p>
            <ul className="ks-list">
              <li>Para o executor de trading imediatamente</li>
              <li>Cancela <strong>todas</strong> as ordens pendentes</li>
              <li>Mantém posições abertas (gerenciadas manualmente depois)</li>
              <li>Emite evento de risco crítico</li>
            </ul>
            {stage === 1 && (
              <div className="dialog-actions">
                <button className="btn" onClick={() => { setOpen(false); setStage(0); }}>Cancelar</button>
                <button className="btn btn-danger" onClick={() => setStage(2)}>Confirmar</button>
              </div>
            )}
            {stage === 2 && (
              <>
                <div className="dialog-warn">Digite <strong>KILL</strong> para confirmar:</div>
                <input className="input" autoFocus value={typed} onChange={e => setTyped(e.target.value.toUpperCase())} />
                <div className="dialog-actions">
                  <button className="btn" onClick={() => { setOpen(false); setStage(0); setTyped(""); }}>Cancelar</button>
                  <button className="btn btn-danger" disabled={typed !== "KILL"} onClick={fire}>Acionar kill switch</button>
                </div>
              </>
            )}
          </div>
        </div>
      )}
    </>
  );
}

// ---- Markets heatmap (treemap) ----
function MarketsHeatmap({ markets, onPickMarket }) {
  if (!markets || markets.length === 0) return <div className="empty">Sem mercados.</div>;
  // size = sqrt(volume) for visual stability; arrange in flex with aspect-ratio
  const total = markets.reduce((s, m) => s + Math.sqrt(m.volume_24h || 1), 0);
  return (
    <div className="heatmap">
      {markets.map(m => {
        const w = (Math.sqrt(m.volume_24h || 1) / total) * 100;
        const arb = (m.yes_ask + m.no_ask) < 1;
        const arbDelta = 1 - (m.yes_ask + m.no_ask);
        const intensity = arb ? Math.min(1, arbDelta * 25) : 0;
        const liquidityScore = Math.min(1, (m.yes_liquidity + m.no_liquidity) / 100_000);
        const bg = arb
          ? `rgba(92, 242, 199, ${0.15 + intensity * 0.55})`
          : `rgba(125, 138, 168, ${0.05 + liquidityScore * 0.10})`;
        const border = arb ? "rgba(92, 242, 199, 0.65)" : "var(--border)";
        return (
          <div
            key={m.condition_id}
            className="hm-cell"
            style={{ flexBasis: `${Math.max(8, w * 4)}%`, background: bg, borderColor: border }}
            title={m.question}
            onClick={() => onPickMarket?.(m)}
          >
            <div className="hm-q">{m.question}</div>
            <div className="hm-meta mono">
              {arb && <span style={{ color: "var(--accent)" }}>◆ +{(arbDelta * 100).toFixed(1)}%</span>}
              <span className="txt-dim">{Fmt.usd(m.volume_24h)} 24h</span>
            </div>
          </div>
        );
      })}
    </div>
  );
}

// ---- Shortcuts strip footer ----
function ShortcutsStrip() {
  const items = [
    ["⌘K", "Buscar"],
    ["⌘R", "Atualizar"],
    ["⌘1-5", "Navegar"],
    ["S", "Iniciar/Parar"],
    ["D", "Densidade"],
    ["Esc", "Fechar"],
  ];
  return (
    <div className="shortcuts-strip">
      {items.map(([k, l]) => (
        <span key={k} className="sh-item"><kbd className="kbd">{k}</kbd>{l}</span>
      ))}
    </div>
  );
}

// ---- Density toggle button ----
function DensityToggle() {
  const { dense, setDense } = React.useContext(DensityCtx);
  return (
    <button className="btn btn-ghost density-tog" onClick={() => setDense(!dense)} title="Alternar densidade (D)">
      <span style={{ fontFamily: "monospace", fontSize: 11 }}>{dense ? "▤▤" : "▤"}</span>
      {dense ? "Denso" : "Confortável"}
    </button>
  );
}

// ---- Ghost chart (empty state) ----
function GhostChart() {
  // SVG with a faint dashed line + dots to suggest a future curve
  const W = 600, H = 220;
  const pts = [];
  for (let i = 0; i < 24; i++) {
    const x = (i / 23) * W;
    const y = H - 40 - Math.sin(i * 0.4) * 25 - i * 4;
    pts.push([x, y]);
  }
  const d = pts.map(([x, y], i) => `${i ? "L" : "M"}${x.toFixed(1)},${y.toFixed(1)}`).join(" ");
  return (
    <div className="ghost-chart">
      <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" width="100%" height="100%">
        <defs>
          <linearGradient id="ghostg" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="var(--accent)" stopOpacity="0.15" />
            <stop offset="100%" stopColor="var(--accent)" stopOpacity="0" />
          </linearGradient>
        </defs>
        <path d={`${d} L${W},${H} L0,${H} Z`} fill="url(#ghostg)" />
        <path d={d} fill="none" stroke="var(--text-dim)" strokeWidth="1.2" strokeDasharray="4 6" opacity="0.6" />
        {pts.filter((_, i) => i % 4 === 0).map(([x, y], i) => (
          <circle key={i} cx={x} cy={y} r="2" fill="var(--text-dim)" opacity="0.5" />
        ))}
      </svg>
      <div className="ghost-overlay">
        <div className="ghost-title">Aguardando dados de patrimônio</div>
        <div className="ghost-sub">O bot ainda não registrou pontos. Inicie o executor para começar a rastrear.</div>
      </div>
    </div>
  );
}

Object.assign(window, {
  DensityCtx, DensityProvider, Sparkline, LiveFeed, ModeToggle, KillSwitch,
  MarketsHeatmap, ShortcutsStrip, DensityToggle, GhostChart,
});
