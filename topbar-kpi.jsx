// =====================================================================
// Top bar, KPI strip, Bot panel
// =====================================================================

function TopBar({ period, setPeriod, status, onStart, onStop, mockMode, onCmd }) {
  const env = "produção";
  return (
    <div className="topbar">
      <div className="brand">
        <span className="brand-bolt">⚡</span>
        <span>Bot de Trading</span>
        <span className="env-tag">{env}</span>
        {mockMode && <span className="env-tag mock">Dados simulados</span>}
      </div>
      <div className="segmented" role="tablist" aria-label="Seletor de período">
        {["24h", "7d", "30d", "all"].map(p => (
          <button key={p} role="tab" aria-selected={p === period} className={p === period ? "active" : ""} onClick={() => setPeriod(p)}>
            {p}
          </button>
        ))}
      </div>
      <div className="topbar-right">
        <button className="btn btn-ghost" onClick={onCmd} title="Paleta de comandos (⌘K)">
          <span style={{ fontSize: 13 }}>⌘</span>K
        </button>
        <BotStatusPill status={status?.running ? "running" : "stopped"} error={status?.last_error} />
        {status?.dry_run && <span className="pill dry-run">Simulação</span>}
        {status?.running ? (
          <button className="btn btn-danger" onClick={onStop}>■ Parar</button>
        ) : (
          <button className="btn btn-primary" onClick={onStart}>▶ Iniciar</button>
        )}
      </div>
    </div>
  );
}

// ---------------- KPI strip ----------------
function KpiCard({ label, value, format, delta, deltaClass, valueClass = "", sparkline, refetching }) {
  return (
    <div className="kpi">
      {refetching && <div className="refetch-dot on" />}
      <div className="kpi-label">{label}</div>
      <div className={`kpi-value mono ${valueClass}`}>
        {typeof value === "number" ? <AnimatedNumber value={value} format={format} /> : value}
      </div>
      {delta !== undefined && <div className={`kpi-delta ${deltaClass || ""}`}>{delta}</div>}
      {sparkline && <div className="sparkline-wrap"><Sparkline points={sparkline} /></div>}
    </div>
  );
}

function KpiStrip({ metrics, equityPoints, refetching }) {
  if (!metrics) {
    return (
      <div className="kpi-grid">
        {Array.from({ length: 8 }).map((_, i) => (
          <div className="kpi" key={i}>
            <Skel w={70} h={9} />
            <Skel w={"75%"} h={26} style={{ marginTop: 6 }} />
            <Skel w={50} h={10} style={{ marginTop: 8 }} />
          </div>
        ))}
      </div>
    );
  }

  const m = metrics;
  return (
    <div className="kpi-grid">
      <KpiCard
        label="Patrimônio"
        value={m.equity_usd}
        format={(v) => Fmt.usdPrecise(v)}
        delta={`Caixa ${Fmt.usd(m.cash_usd)}`}
        sparkline={equityPoints}
        refetching={refetching}
      />
      <KpiCard
        label={`Resultado (${m.period})`}
        value={m.total_pnl_usd}
        format={(v) => `${v >= 0 ? "+" : ""}${Fmt.usd(v, { cents: true })}`}
        valueClass={m.total_pnl_usd >= 0 ? "pos" : "neg"}
        delta={`${m.total_pnl_usd >= 0 ? "+" : ""}${((m.total_pnl_usd / Math.max(1, m.equity_usd - m.total_pnl_usd)) * 100).toFixed(2)}%`}
        deltaClass={m.total_pnl_usd >= 0 ? "pos" : "neg"}
      />
      <KpiCard
        label="Realizado hoje"
        value={m.realized_today_usd}
        format={(v) => `${v >= 0 ? "+" : ""}${Fmt.usd(v, { cents: true })}`}
        valueClass={m.realized_today_usd >= 0 ? "pos" : ""}
        delta={`${m.total_trades > 0 ? Math.round(m.total_trades / 4) : 0} execuções`}
      />
      <KpiCard
        label="Taxa de acerto"
        value={m.win_rate * 100}
        format={(v) => `${v.toFixed(1)}%`}
        delta={`${m.total_trades} operações`}
      />
      <KpiCard
        label="Operações"
        value={m.total_trades}
        format={(v) => Fmt.int(Math.round(v))}
        delta={`VE médio ${Fmt.usd(m.avg_ev_usd, { cents: true })}`}
      />
      <KpiCard
        label="Expectativa"
        value={m.expectancy_usd}
        format={(v) => `${v >= 0 ? "+" : ""}${Fmt.usd(v, { cents: true })}`}
        valueClass={m.expectancy_usd >= 0 ? "pos" : "neg"}
        delta={`FL ${m.profit_factor.toFixed(2)}x`}
      />
      <KpiCard
        label="Sharpe"
        value={m.sharpe}
        format={(v) => v.toFixed(2)}
        delta={`Drawdown ${m.max_drawdown_pct.toFixed(2)}%`}
        deltaClass="neg"
      />
      <KpiCard
        label="Sortino"
        value={m.sortino}
        format={(v) => v.toFixed(2)}
        delta={`${m.open_positions} abertas`}
      />
    </div>
  );
}

// ---------------- Bot panel ----------------
function BotPanel({ status, onStart, onStopRequest, onShowError }) {
  if (!status) {
    return (
      <div className="card" style={{ height: 320 }}>
        <div className="card-header"><div className="card-title">Bot</div></div>

        {Array.from({ length: 6 }).map((_, i) => (
          <div className="status-row" key={i}><Skel w={70} h={10} /><Skel w={120} h={12} /></div>
        ))}
      </div>
    );
  }
  const lastLoopMs = status.last_loop_at ? Date.now() - new Date(status.last_loop_at).getTime() : null;
  const stale = lastLoopMs != null && lastLoopMs > 60_000;

  return (
    <div className="card" style={{ height: 320, display: "flex", flexDirection: "column" }}>
      <div className="card-header">
        <div className="card-title">Executor</div>
        <span className="card-sub">ao vivo</span>
      </div>
      <div className="status-panel" style={{ flex: 1 }}>
        <div className="status-row">
          <span className="lbl">Status</span>
          <span className="val">
            {status.running ? <><span className="dot-pulse" /> <span className="txt-pos">Em execução</span></> : <><span className="dot-stopped" /> <span className="txt-muted">Parado</span></>}
          </span>
        </div>
        <div className="status-row">
          <span className="lbl">Modo</span>
          <span className="val">
            {status.dry_run ? <span className="pill dry-run">Simulação</span> : <span className="pill live">Real</span>}
          </span>
        </div>
        <div className="status-row">
          <span className="lbl">Iniciado</span>
          <span className="val mono">{status.started_at ? "há " + Fmt.durationSince(status.started_at) : "—"}</span>
        </div>
        <div className="status-row">
          <span className="lbl">Último ciclo</span>
          <span className="val mono">
            {stale && <span className="dot-error" style={{ marginRight: 4 }} />}
            <span className={stale ? "txt-neg" : ""}>{Fmt.timeAgo(status.last_loop_at)}</span>
          </span>
        </div>
        <div className="status-row">
          <span className="lbl">Último erro</span>
          <span className="val mono" style={{ maxWidth: 180, overflow: "hidden", textOverflow: "ellipsis" }}>
            {status.last_error ? (
              <a onClick={onShowError} style={{ color: "var(--danger)", cursor: "pointer", textDecoration: "underline dotted" }}>
                {status.last_error.slice(0, 30)}…
              </a>
            ) : <span className="txt-dim">nenhum</span>}
          </span>
        </div>
        <div className="status-row">
          <span className="lbl">Pos. abertas</span>
          <span className="val mono">{status.open_positions}</span>
        </div>
        <div className="status-row">
          <span className="lbl">Patrimônio</span>
          <span className="val mono"><AnimatedNumber value={status.equity_usd} format={(v) => Fmt.usdPrecise(v)} /></span>
        </div>
      </div>
      <div style={{ marginTop: 12 }}>
        {status.running ? (
          <button className="btn btn-danger btn-full" onClick={onStopRequest}>■ Parar executor</button>
        ) : (
          <button className="btn btn-primary btn-full" onClick={onStart}>▶ Iniciar executor</button>
        )}
      </div>
    </div>
  );
}

Object.assign(window, { TopBar, KpiStrip, BotPanel });
