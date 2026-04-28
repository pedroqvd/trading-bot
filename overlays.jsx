// =====================================================================
// Position detail Sheet, Stop confirmation Dialog, Command palette, Toasts
// =====================================================================

function PositionMiniChart({ history, entry, tp, sl }) {
  if (!history || history.length < 2) return null;
  const W = 280, H = 84, pad = 6;
  const prices = history.map(p => p.p);
  const min = Math.min(...prices, sl ?? Infinity, entry ?? Infinity);
  const max = Math.max(...prices, tp ?? -Infinity, entry ?? -Infinity);
  const span = max - min || 1;
  const stepX = (W - pad * 2) / (history.length - 1);
  const yFor = v => pad + (1 - (v - min) / span) * (H - pad * 2);
  const pts = history.map((p, i) => `${pad + i * stepX},${yFor(p.p).toFixed(1)}`);
  const last = prices[prices.length - 1];
  const stroke = last >= (entry ?? last) ? "var(--accent)" : "var(--danger)";
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="pos-mini-chart" preserveAspectRatio="none" width="100%">
      {/* TP/SL guides */}
      {tp != null && tp >= min && tp <= max && (
        <line x1={pad} x2={W - pad} y1={yFor(tp)} y2={yFor(tp)}
              stroke="var(--accent)" strokeDasharray="4 4" strokeWidth="0.7" opacity="0.55" />
      )}
      {sl != null && sl >= min && sl <= max && (
        <line x1={pad} x2={W - pad} y1={yFor(sl)} y2={yFor(sl)}
              stroke="var(--danger)" strokeDasharray="4 4" strokeWidth="0.7" opacity="0.55" />
      )}
      {entry != null && (
        <line x1={pad} x2={W - pad} y1={yFor(entry)} y2={yFor(entry)}
              stroke="var(--text-dim)" strokeDasharray="2 4" strokeWidth="0.6" opacity="0.65" />
      )}
      <polyline points={pts.join(" ")} fill="none" stroke={stroke} strokeWidth="1.5" strokeLinejoin="round" />
      <circle cx={pad + (history.length - 1) * stepX} cy={yFor(last)} r="2.2" fill={stroke} />
    </svg>
  );
}

function RelatedLogs({ correlation_id }) {
  const [logs, setLogs] = React.useState([]);
  React.useEffect(() => {
    if (!correlation_id) return;
    const refresh = () => setLogs(MockAPI.getLogs(40, { cid: correlation_id }));
    refresh();
    const id = setInterval(refresh, 4000);
    return () => clearInterval(id);
  }, [correlation_id]);
  if (!logs || logs.length === 0) {
    return <div className="empty" style={{ padding: 14, fontSize: 11 }}>Nenhum log relacionado encontrado.</div>;
  }
  return (
    <div className="pos-related-logs">
      {logs.map(l => (
        <div className="rl-line" key={l.id}>
          <span className="rl-time">{Fmt.timeOfDay(l.ts)}</span>
          <span className={`log-level ${l.level}`} style={{ marginRight: 6 }}>{l.level}</span>
          <span className="rl-msg">{l.msg}</span>
        </div>
      ))}
    </div>
  );
}

function PositionDetailSheet({ pos, onClose, onCloseNow, onJumpToLogs }) {
  if (!pos) return null;
  const isOpen = pos.status === "OPEN";
  const statusLabels = { OPEN: "ABERTA", CLOSED: "ENCERRADA", LIQUIDATED: "LIQUIDADA" };
  const unrealized = pos.unrealized_pnl_usd;
  const sign = pos.side === "YES" ? 1 : -1;
  const livePrice = pos.current_price ?? pos.exit_price ?? pos.entry_price;
  return (
    <>
      <div className="sheet-overlay" onClick={onClose} />
      <aside className="sheet" role="dialog" aria-label="Detalhe da posição">
        <div className="sheet-head">
          <div style={{ flex: 1, minWidth: 0 }}>
            <div className="card-sub">Posição #{pos.id} · {pos.correlation_id}</div>
            <div style={{ fontSize: 14, fontWeight: 500, marginTop: 4, lineHeight: 1.4 }} title={pos.market_question}>
              {pos.market_question}
            </div>
            <div style={{ marginTop: 8, display: "flex", gap: 6, flexWrap: "wrap" }}>
              <SidePill side={pos.side} />
              <StatePill kind={pos.status === "OPEN" ? "filled" : pos.status === "LIQUIDATED" ? "failed" : "pending"}>{statusLabels[pos.status]}</StatePill>
              <span className="pill" style={{ color: "var(--text-muted)", borderColor: "var(--border-hi)" }}>{pos.strategy}</span>
            </div>
          </div>
          <button className="btn btn-ghost" onClick={onClose} aria-label="Fechar">✕</button>
        </div>
        <div className="sheet-body">
          {/* mini chart of price history */}
          <div className="card-sub" style={{ marginBottom: 4 }}>Trajetória de preço</div>
          <PositionMiniChart
            history={pos.price_history}
            entry={pos.entry_price}
            tp={pos.take_profit}
            sl={pos.stop_loss}
          />
          <div style={{ display: "flex", justifyContent: "space-between", fontSize: 10.5, color: "var(--text-dim)", padding: "0 4px" }}>
            <span>entrada {pos.entry_price?.toFixed(3)}</span>
            <span>atual <strong style={{ color: "var(--text)" }}>{livePrice?.toFixed(3)}</strong></span>
            <span>SL {pos.stop_loss?.toFixed(3)} · TP {pos.take_profit?.toFixed(3)}</span>
          </div>

          {/* EV / Kelly cards (open positions only) */}
          {isOpen && pos.ev_now != null && (
            <div className="pos-evkelly">
              <div className="pe-card">
                <div className="pe-lbl">EV agora</div>
                <div className={`pe-val ${pos.ev_now >= 0 ? "txt-pos" : "txt-neg"}`}>
                  {(pos.ev_now >= 0 ? "+" : "") + (pos.ev_now * 100).toFixed(2) + "%"}
                </div>
              </div>
              <div className="pe-card">
                <div className="pe-lbl">Kelly atual</div>
                <div className="pe-val">
                  {(pos.kelly_now * 100).toFixed(2) + "%"}
                </div>
              </div>
            </div>
          )}

          <div className="kv">
            <span className="k">Slug</span><span className="v mono txt-muted">{pos.market_slug}</span>
            <span className="k">Preço de entrada</span><span className="v mono">{pos.entry_price.toFixed(3)}</span>
            <span className="k">Tamanho da entrada</span><span className="v mono">{Fmt.usdPrecise(pos.entry_size_usd)}</span>
            <span className="k">Cotas</span><span className="v mono">{Fmt.int(pos.shares)}</span>
            {isOpen && unrealized != null && (
              <>
                <span className="k">PnL não realizado</span>
                <span className={`v mono ${unrealized >= 0 ? "txt-pos" : "txt-neg"}`}>
                  {(unrealized >= 0 ? "+" : "") + Fmt.usdPrecise(unrealized)}
                </span>
              </>
            )}
            <span className="k">Realização de lucro</span><span className="v mono txt-pos">{pos.take_profit?.toFixed(3) ?? "—"}</span>
            <span className="k">Stop loss</span><span className="v mono txt-neg">{pos.stop_loss?.toFixed(3) ?? "—"}</span>
            <span className="k">Aberta em</span><span className="v mono">{new Date(pos.opened_at).toLocaleString("pt-BR")}</span>
            {pos.closed_at && <><span className="k">Encerrada em</span><span className="v mono">{new Date(pos.closed_at).toLocaleString("pt-BR")}</span></>}
            {pos.exit_price != null && <><span className="k">Preço de saída</span><span className="v mono">{pos.exit_price.toFixed(3)}</span></>}
            {pos.realized_pnl_usd != null && (
              <>
                <span className="k">Resultado realizado</span>
                <span className={`v mono ${pos.realized_pnl_usd >= 0 ? "txt-pos" : "txt-neg"}`}>
                  {(pos.realized_pnl_usd >= 0 ? "+" : "") + Fmt.usdPrecise(pos.realized_pnl_usd)}
                </span>
              </>
            )}
          </div>

          <hr />
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
            <span className="card-sub">Logs relacionados</span>
            {onJumpToLogs && (
              <a className="lf-cid" onClick={() => onJumpToLogs(pos.correlation_id)}>
                ver tudo →
              </a>
            )}
          </div>
          <RelatedLogs correlation_id={pos.correlation_id} />

          {isOpen && (
            <>
              <hr />
              <div style={{ display: "flex", gap: 8 }}>
                <button className="btn btn-full" onClick={onClose}>Fechar painel</button>
                <button
                  className="btn btn-danger btn-full"
                  onClick={() => onCloseNow?.(pos.id)}
                >
                  ■ Encerrar posição agora
                </button>
              </div>
            </>
          )}
        </div>
      </aside>
    </>
  );
}

function StopDialog({ open, onConfirm, onCancel }) {
  if (!open) return null;
  return (
    <div className="dialog-overlay" onClick={onCancel}>
      <div className="dialog" onClick={e => e.stopPropagation()} role="alertdialog" aria-labelledby="stop-title">
        <h3 id="stop-title">Parar o executor de trading?</h3>
        <p>As posições abertas serão entregues ao gerenciador de posições — elas continuam sendo monitoradas para saídas em TP/SL, mas nenhuma nova entrada será aberta.</p>
        <div className="dialog-actions">
          <button className="btn" onClick={onCancel} autoFocus>Cancelar</button>
          <button className="btn btn-danger" onClick={onConfirm}>Parar executor</button>
        </div>
      </div>
    </div>
  );
}

function ErrorDialog({ error, onClose }) {
  if (!error) return null;
  return (
    <div className="dialog-overlay" onClick={onClose}>
      <div className="dialog" onClick={e => e.stopPropagation()}>
        <h3>Último erro</h3>
        <pre style={{ background: "var(--bg)", border: "1px solid var(--border)", padding: 12, borderRadius: 6, overflow: "auto", fontSize: 11.5, color: "var(--danger)", whiteSpace: "pre-wrap", margin: 0 }}>
          {error}
        </pre>
        <div className="dialog-actions" style={{ marginTop: 18 }}>
          <button className="btn" onClick={onClose}>Fechar</button>
        </div>
      </div>
    </div>
  );
}

function CommandPalette({ open, onClose, commands }) {
  const [q, setQ] = React.useState("");
  const [idx, setIdx] = React.useState(0);
  const inputRef = React.useRef(null);

  React.useEffect(() => {
    if (open) {
      setQ(""); setIdx(0);
      setTimeout(() => inputRef.current?.focus(), 30);
    }
  }, [open]);

  const filtered = commands.filter(c => c.label.toLowerCase().includes(q.toLowerCase()));

  const onKey = (e) => {
    if (e.key === "ArrowDown") { e.preventDefault(); setIdx(i => Math.min(filtered.length - 1, i + 1)); }
    if (e.key === "ArrowUp") { e.preventDefault(); setIdx(i => Math.max(0, i - 1)); }
    if (e.key === "Enter") { e.preventDefault(); filtered[idx]?.run(); onClose(); }
    if (e.key === "Escape") onClose();
  };

  if (!open) return null;
  return (
    <div className="cmd-overlay" onClick={onClose}>
      <div className="cmd" onClick={e => e.stopPropagation()}>
        <input ref={inputRef} value={q} onChange={e => { setQ(e.target.value); setIdx(0); }} onKeyDown={onKey} placeholder="Digite um comando…" />
        <div className="cmd-list">
          {filtered.length === 0 && <div className="cmd-item txt-muted">Nenhum resultado</div>}
          {filtered.map((c, i) => (
            <div key={c.label} className={`cmd-item ${i === idx ? "active" : ""}`} onMouseEnter={() => setIdx(i)} onClick={() => { c.run(); onClose(); }}>
              <span>{c.label}</span>
              {c.kbd && <span className="kbd">{c.kbd}</span>}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function ToastStack({ toasts }) {
  if (!toasts.length) return null;
  return (
    <div className="toast-wrap">
      {toasts.map(t => (
        <div key={t.id} className={`toast ${t.kind || ""}`}>
          <span className={t.kind === "warn" ? "dot-stale" : "dot-error"} />
          <span>{t.message}</span>
        </div>
      ))}
    </div>
  );
}

Object.assign(window, { PositionDetailSheet, StopDialog, ErrorDialog, CommandPalette, ToastStack });
