// =====================================================================
// Position detail Sheet, Stop confirmation Dialog, Command palette, Toasts
// =====================================================================

function PositionDetailSheet({ pos, onClose }) {
  if (!pos) return null;
  const isOpen = pos.status === "OPEN";
  const statusLabels = { OPEN: "ABERTA", CLOSED: "ENCERRADA", LIQUIDATED: "LIQUIDADA" };
  return (
    <>
      <div className="sheet-overlay" onClick={onClose} />
      <aside className="sheet" role="dialog" aria-label="Detalhe da posição">
        <div className="sheet-head">
          <div style={{ flex: 1, minWidth: 0 }}>
            <div className="card-sub">Posição #{pos.id}</div>
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
          <div className="kv">
            <span className="k">Slug</span><span className="v mono txt-muted">{pos.market_slug}</span>
            <span className="k">Preço de entrada</span><span className="v mono">{pos.entry_price.toFixed(3)}</span>
            <span className="k">Tamanho da entrada</span><span className="v mono">{Fmt.usdPrecise(pos.entry_size_usd)}</span>
            <span className="k">Cotas</span><span className="v mono">{Fmt.int(pos.shares)}</span>
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
          <div className="card-sub" style={{ marginBottom: 8 }}>Ciclo de vida</div>
          <div style={{ fontSize: 12, color: "var(--text-muted)", lineHeight: 1.6 }}>
            {isOpen ? (
              <>A posição está atualmente <span className="txt-pos">aberta</span>. O gerenciador monitora o preço a cada ciclo e sai por TP, SL ou sinal da estratégia.</>
            ) : (
              <>Posição encerrada via {pos.status === "LIQUIDATED" ? <span className="txt-neg">liquidação</span> : "saída do gerenciador"}.</>
            )}
          </div>
          {isOpen && (
            <>
              <hr />
              <div style={{ display: "flex", gap: 8 }}>
                <button className="btn btn-full" onClick={onClose}>Fechar painel</button>
                <button className="btn btn-danger btn-full">Encerrar posição</button>
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
