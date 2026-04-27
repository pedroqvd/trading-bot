// =====================================================================
// Main App + sidebar nav + page routing
// =====================================================================

function usePoll(fn, interval, deps = []) {
  const [data, setData] = React.useState(null);
  const [error, setError] = React.useState(null);
  const [refetching, setRefetching] = React.useState(false);
  const tick = React.useCallback(() => {
    setRefetching(true);
    try {
      const v = fn();
      setData(v);
      setError(null);
    } catch (e) {
      setError(e);
    } finally {
      setTimeout(() => setRefetching(false), 700);
    }
  }, deps);
  React.useEffect(() => {
    tick();
    const id = setInterval(tick, interval);
    return () => clearInterval(id);
  }, [tick, interval]);
  return { data, error, refetching, refetch: tick };
}

function Sidebar({ page, setPage, status }) {
  const items = [
  { id: "dashboard", label: "Painel", ico: "▣" },
  { id: "settings", label: "Configurações", ico: "⚙" },
  { id: "backtest", label: "Backtest", ico: "▶" },
  { id: "logs", label: "Logs", ico: "≡" }];

  return (
    <aside className="sidebar">
      <div className="sidebar-brand">
        <span className="brand-bolt">⚡</span>
        <span>PedroBot
</span>
      </div>
      {items.map((it) => <button key={it.id} className={`nav-item ${page === it.id ? "active" : ""}`} onClick={() => setPage(it.id)}>
          <span className="ico">{it.ico}</span>{it.label}
        </button>
      )}
      <div className="sidebar-foot">
        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <span className={`status-dot ${status?.running ? "running" : "stopped"}`} />
          <span>{status?.running ? "EM EXECUÇÃO" : "PARADO"}</span>
        </div>
        <div style={{ marginTop: 6 }}>v1.4.2 · pt-BR</div>
      </div>
    </aside>);

}

function DashboardPage({ period, setPeriod, status, onStart, onStopRequest, onShowError, setOpenPos, onCmd, refetchAll }) {
  const metrics = usePoll(() => MockAPI.getMetrics(period), 5_000, [period]);
  const equity = usePoll(() => MockAPI.getEquity(period), 5_000, [period]);
  const positions = usePoll(() => MockAPI.getPositions("all", 200), 10_000, []);
  const trades = usePoll(() => MockAPI.getTrades(50), 10_000, []);
  const risk = usePoll(() => MockAPI.getRiskEvents(50), 30_000, []);
  const markets = usePoll(() => MockAPI.getMarkets(), 30_000, []);

  React.useEffect(() => {
    refetchAll.current = () => {
      metrics.refetch();equity.refetch();
      positions.refetch();trades.refetch();risk.refetch();markets.refetch();
    };
  });

  return (
    <div className="page">
      <TopBar
        period={period}
        setPeriod={setPeriod}
        status={status}
        onStart={onStart}
        onStop={onStopRequest}
        mockMode={true}
        onCmd={onCmd} />
      
      <KpiStrip metrics={metrics.data} equityPoints={equity.data?.points} refetching={metrics.refetching} />
      <div className="row-3">
        <div className="card equity-chart-card">
          {equity.refetching && <div className="refetch-dot on" />}
          <div className="card-header">
            <div className="card-title">Curva de patrimônio</div>
            <span className="card-sub mono">{period} · {equity.data?.points?.length ?? 0} pts</span>
          </div>
          <div className="chart-area">
            <EquityChart points={equity.data?.points} period={period} onStart={onStart} running={status?.running} />
          </div>
        </div>
        <BotPanel
          status={status}
          onStart={onStart}
          onStopRequest={onStopRequest}
          onShowError={onShowError} />
        
      </div>
      <div style={{ marginBottom: 12 }}>
        <StrategyTable rows={metrics.data?.by_strategy} refetching={metrics.refetching} />
      </div>
      <div data-anchor="positions" style={{ marginBottom: 12 }}>
        <PositionsRiskCard
          positions={positions.data}
          riskEvents={risk.data}
          onOpenPosition={setOpenPos}
          refetching={positions.refetching || risk.refetching} />
        
      </div>
      <div data-anchor="trades" style={{ marginBottom: 12 }}>
        <TradesTable trades={trades.data} refetching={trades.refetching} />
      </div>
      <div data-anchor="universe">
        <MarketsSnapshot data={markets.data} refetching={markets.refetching} />
      </div>
    </div>);

}

function App() {
  const [page, setPage] = React.useState("dashboard");
  const [period, setPeriod] = React.useState("24h");
  const [openPos, setOpenPos] = React.useState(null);
  const [stopOpen, setStopOpen] = React.useState(false);
  const [errOpen, setErrOpen] = React.useState(null);
  const [cmdOpen, setCmdOpen] = React.useState(false);
  const [toasts, setToasts] = React.useState([]);
  const [, force] = React.useReducer((x) => x + 1, 0);
  const refetchAll = React.useRef(() => {});

  const status = usePoll(() => MockAPI.getBotStatus(), 5_000, []);

  React.useEffect(() => {const id = setInterval(force, 15_000);return () => clearInterval(id);}, []);

  React.useEffect(() => {
    if (status.data) {
      document.title = `${Fmt.usdPrecise(status.data.equity_usd)} · Bot de Trading`;
      const c = status.data.last_error ? "#ff5c7a" : status.data.running ? "#5cf2c7" : "#7c8aa8";
      const link = document.querySelector("link[rel~='icon']") || document.createElement("link");
      link.rel = "icon";
      link.href = `data:image/svg+xml,${encodeURIComponent(`<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'><rect width='32' height='32' rx='6' fill='%230a0e17'/><path d='M18 4 L9 18 H15 L13 28 L23 13 H17 Z' fill='${c}'/></svg>`)}`;
      document.head.appendChild(link);
    }
  }, [status.data?.running, status.data?.last_error, status.data?.equity_usd]);

  React.useEffect(() => {
    const onKey = (e) => {
      const meta = e.metaKey || e.ctrlKey;
      if (meta && e.key.toLowerCase() === "k") {e.preventDefault();setCmdOpen(true);}
      if (meta && e.key.toLowerCase() === "r") {
        e.preventDefault();
        status.refetch();
        refetchAll.current();
        pushToast("Todos os dados atualizados", "warn");
      }
      if (e.key === "Escape") {
        setCmdOpen(false);setStopOpen(false);setErrOpen(null);
        if (!cmdOpen && !stopOpen && !errOpen) setOpenPos(null);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [cmdOpen, stopOpen, errOpen]);

  function pushToast(message, kind = "warn") {
    const id = Math.random();
    setToasts((t) => [...t, { id, message, kind }]);
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 3500);
  }

  const onStart = () => {MockAPI.startBot();status.refetch();pushToast("Executor de trading iniciado.", "warn");};
  const onStopRequest = () => setStopOpen(true);
  const onStopConfirm = () => {MockAPI.stopBot();setStopOpen(false);status.refetch();pushToast("Executor de trading parado.", "warn");};
  const onShowError = () => setErrOpen(status.data?.last_error || "Connection refused: clob.polymarket.com:443");

  const commands = [
  { label: status.data?.running ? "Parar executor de trading" : "Iniciar executor de trading", run: () => status.data?.running ? setStopOpen(true) : onStart(), kbd: "S" },
  { label: "Ir para o painel", run: () => setPage("dashboard") },
  { label: "Ir para configurações", run: () => setPage("settings") },
  { label: "Ir para backtest", run: () => setPage("backtest") },
  { label: "Ir para logs", run: () => setPage("logs") },
  { label: "Mudar período: 24h", run: () => setPeriod("24h") },
  { label: "Mudar período: 7d", run: () => setPeriod("7d") },
  { label: "Mudar período: 30d", run: () => setPeriod("30d") },
  { label: "Mudar período: tudo", run: () => setPeriod("all") },
  { label: "Atualizar todos os dados", run: () => {status.refetch();refetchAll.current();}, kbd: "⌘R" }];


  return (
    <div className="app-shell">
      <Sidebar page={page} setPage={setPage} status={status.data} />
      <main>
        {page === "dashboard" &&
        <DashboardPage
          period={period} setPeriod={setPeriod}
          status={status.data}
          onStart={onStart}
          onStopRequest={onStopRequest}
          onShowError={onShowError}
          setOpenPos={setOpenPos}
          onCmd={() => setCmdOpen(true)}
          refetchAll={refetchAll} />

        }
        {page === "settings" && <SettingsPage />}
        {page === "backtest" && <BacktestPage />}
        {page === "logs" && <LogsPage />}
      </main>

      {openPos && <PositionDetailSheet pos={openPos} onClose={() => setOpenPos(null)} />}
      <StopDialog open={stopOpen} onConfirm={onStopConfirm} onCancel={() => setStopOpen(false)} />
      <ErrorDialog error={errOpen} onClose={() => setErrOpen(null)} />
      <CommandPalette open={cmdOpen} onClose={() => setCmdOpen(false)} commands={commands} />
      <ToastStack toasts={toasts} />
    </div>);

}

ReactDOM.createRoot(document.getElementById("root")).render(<App />);