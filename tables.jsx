// =====================================================================
// Strategy table, Positions panel (tabs), Trades, Risk events, Markets
// =====================================================================

// ---------- generic sortable table hook ----------
function useSort(initialKey, initialDir = "desc") {
  const [primary, setPrimary] = React.useState({ key: initialKey, dir: initialDir });
  const [secondary, setSecondary] = React.useState(null);
  const onClick = (key, e) => {
    if (e.shiftKey) {
      if (secondary?.key === key) setSecondary({ key, dir: secondary.dir === "asc" ? "desc" : "asc" });
      else setSecondary({ key, dir: "desc" });
    } else {
      if (primary.key === key) setPrimary({ key, dir: primary.dir === "asc" ? "desc" : "asc" });
      else setPrimary({ key, dir: "desc" });
      setSecondary(null);
    }
  };
  const sort = (rows, accessors = {}) => {
    const get = (r, k) => (accessors[k] ? accessors[k](r) : r[k]);
    const cmp = (a, b, key, dir) => {
      const va = get(a, key), vb = get(b, key);
      if (va == null && vb == null) return 0;
      if (va == null) return 1;
      if (vb == null) return -1;
      const r = typeof va === "string" ? va.localeCompare(vb) : (va < vb ? -1 : va > vb ? 1 : 0);
      return dir === "asc" ? r : -r;
    };
    return [...rows].sort((a, b) => cmp(a, b, primary.key, primary.dir) || (secondary ? cmp(a, b, secondary.key, secondary.dir) : 0));
  };
  return { primary, secondary, onClick, sort };
}

function SortHeader({ label, sortKey, sort, numeric }) {
  const active = sort.primary.key === sortKey;
  const sec = sort.secondary?.key === sortKey;
  return (
    <th onClick={(e) => sort.onClick(sortKey, e)} className={`${active || sec ? "sorted" : ""} ${numeric ? "numeric" : ""}`}>
      {label}
      <span className="sort-ind">
        {active ? (sort.primary.dir === "asc" ? "▲" : "▼") : sec ? "·" : ""}
      </span>
    </th>
  );
}

// ---------------- Strategy table ----------------
function StrategyTable({ rows, sparklines, refetching }) {
  const sort = useSort("total_pnl_usd", "desc");
  if (!rows) return <div className="card"><div className="card-header"><div className="card-title">Saúde das estratégias</div></div><Skel w="100%" h={140} /></div>;

  const sorted = sort.sort(rows);
  return (
    <div className="card" style={{ padding: 0, overflow: "hidden" }}>
      {refetching && <div className="refetch-dot on" />}
      <div className="card-header" style={{ padding: "16px 16px 12px" }}>
        <div className="card-title">Saúde das estratégias</div>
        <span className="card-sub">{rows.length} estratégias · sparkline = PnL acumulado últimos 30 ciclos</span>
      </div>
      {rows.length === 0 ? (
        <div className="empty">Sem atividade de estratégia neste período.</div>
      ) : (
        <div className="tbl-wrap">
          <table className="tbl">
            <thead>
              <tr>
                <SortHeader label="Estratégia" sortKey="strategy" sort={sort} />
                <th className="sparkline-cell">PnL</th>
                <SortHeader label="Estado" sortKey="state" sort={sort} />
                <SortHeader label="Operações" sortKey="trades" sort={sort} numeric />
                <SortHeader label="Taxa de acerto" sortKey="win_rate" sort={sort} numeric />
                <SortHeader label="Expectativa" sortKey="expectancy_usd" sort={sort} numeric />
                <SortHeader label="Resultado" sortKey="total_pnl_usd" sort={sort} numeric />
                <SortHeader label="Fator de lucro" sortKey="profit_factor" sort={sort} numeric />
                <SortHeader label="Tempo médio" sortKey="avg_hold_minutes" sort={sort} numeric />
              </tr>
            </thead>
            <tbody>
              {sorted.map(r => (
                <tr key={r.strategy}>
                  <td style={{ fontWeight: 500 }}>{r.strategy}</td>
                  <td className="sparkline-cell">
                    <Sparkline values={sparklines?.[r.strategy]} width={80} height={22} />
                  </td>
                  <td><StatePill kind={r.state.toLowerCase()} title={r.reason}>{r.state}</StatePill></td>
                  <td className="numeric mono">{Fmt.int(r.trades)}</td>
                  <td className="numeric mono">{(r.win_rate * 100).toFixed(1)}%</td>
                  <td className="numeric mono">{Fmt.usd(r.expectancy_usd, { cents: true, signed: r.expectancy_usd > 0 })}</td>
                  <td className={`numeric mono ${r.total_pnl_usd >= 0 ? "txt-pos" : "txt-neg"}`}>
                    {(r.total_pnl_usd >= 0 ? "+" : "") + Fmt.usd(r.total_pnl_usd, { cents: true })}
                  </td>
                  <td className="numeric mono">{isFinite(r.profit_factor) ? r.profit_factor.toFixed(2) + "x" : "∞"}</td>
                  <td className="numeric mono txt-muted">{r.avg_hold_minutes}m</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

// ---------------- Positions / Risk events tabs ----------------
function PositionsRiskCard({ positions, riskEvents, onOpenPosition, refetching }) {
  const [tab, setTab] = React.useState("open");
  const open = positions ? positions.filter(p => p.status === "OPEN") : [];
  const closed = positions ? positions.filter(p => p.status !== "OPEN").slice(0, 50) : [];
  const criticalRecent = (riskEvents || []).some(r => r.severity === "critical" && (Date.now() - new Date(r.ts).getTime() < 3600_000));

  const sortOpen = useSort("opened_at", "desc");
  const sortClosed = useSort("closed_at", "desc");

  return (
    <div className="card" style={{ padding: 16 }}>
      {refetching && <div className="refetch-dot on" />}
      <div className="tabs-bar">
        <button className={`tab ${tab === "open" ? "active" : ""}`} onClick={() => setTab("open")}>
          Posições abertas <span className="count">{open.length}</span>
        </button>
        <button className={`tab ${tab === "closed" ? "active" : ""}`} onClick={() => setTab("closed")}>
          Encerradas <span className="count">{closed.length}</span>
        </button>
        <button className={`tab ${tab === "risk" ? "active" : ""}`} onClick={() => setTab("risk")}>
          {criticalRecent && <span className="tab-red-dot" />} Eventos de risco <span className="count">{(riskEvents || []).length}</span>
        </button>
      </div>

      {tab === "open" && (
        open.length === 0 ? (
          <div className="empty">Nenhuma posição aberta.</div>
        ) : (
          <div className="tbl-wrap" style={{ maxHeight: 380 }}>
            <table className="tbl">
              <thead>
                <tr>
                  <SortHeader label="Mercado" sortKey="market_question" sort={sortOpen} />
                  <SortHeader label="Estratégia" sortKey="strategy" sort={sortOpen} />
                  <SortHeader label="Lado" sortKey="side" sort={sortOpen} />
                  <SortHeader label="Entrada" sortKey="entry_price" sort={sortOpen} numeric />
                  <SortHeader label="Tamanho" sortKey="entry_size_usd" sort={sortOpen} numeric />
                  <SortHeader label="Cotas" sortKey="shares" sort={sortOpen} numeric />
                  <SortHeader label="TP / SL" sortKey="take_profit" sort={sortOpen} numeric />
                  <SortHeader label="Aberta" sortKey="opened_at" sort={sortOpen} />
                </tr>
              </thead>
              <tbody>
                {sortOpen.sort(open).map(p => (
                  <tr key={p.id} className="clickable" onClick={() => onOpenPosition(p)}>
                    <td className="market-q" title={p.market_question}>{p.market_question}</td>
                    <td className="txt-muted">{p.strategy}</td>
                    <td><SidePill side={p.side} /></td>
                    <td className="numeric mono">{p.entry_price.toFixed(3)}</td>
                    <td className="numeric mono">{Fmt.usd(p.entry_size_usd)}</td>
                    <td className="numeric mono">{Fmt.int(p.shares)}</td>
                    <td className="numeric mono txt-muted">
                      <span className="txt-pos">{p.take_profit?.toFixed(3)}</span>
                      <span style={{ color: "var(--text-dim)" }}> / </span>
                      <span className="txt-neg">{p.stop_loss?.toFixed(3)}</span>
                    </td>
                    <td className="mono txt-muted">{Fmt.timeAgo(p.opened_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )
      )}

      {tab === "closed" && (
        closed.length === 0 ? (
          <div className="empty">Nenhuma posição encerrada neste período.</div>
        ) : (
          <div className="tbl-wrap" style={{ maxHeight: 380 }}>
            <table className="tbl">
              <thead>
                <tr>
                  <SortHeader label="Mercado" sortKey="market_question" sort={sortClosed} />
                  <SortHeader label="Estratégia" sortKey="strategy" sort={sortClosed} />
                  <SortHeader label="Lado" sortKey="side" sort={sortClosed} />
                  <SortHeader label="Entrada" sortKey="entry_price" sort={sortClosed} numeric />
                  <SortHeader label="Saída" sortKey="exit_price" sort={sortClosed} numeric />
                  <SortHeader label="Tamanho" sortKey="entry_size_usd" sort={sortClosed} numeric />
                  <SortHeader label="Resultado" sortKey="realized_pnl_usd" sort={sortClosed} numeric />
                  <SortHeader label="Encerrada" sortKey="closed_at" sort={sortClosed} />
                </tr>
              </thead>
              <tbody>
                {sortClosed.sort(closed).map(p => (
                  <tr key={p.id} className="clickable" onClick={() => onOpenPosition(p)}>
                    <td className="market-q" title={p.market_question}>{p.market_question}</td>
                    <td className="txt-muted">{p.strategy}</td>
                    <td><SidePill side={p.side} /></td>
                    <td className="numeric mono">{p.entry_price.toFixed(3)}</td>
                    <td className="numeric mono">{p.exit_price?.toFixed(3)}</td>
                    <td className="numeric mono">{Fmt.usd(p.entry_size_usd)}</td>
                    <td className={`numeric mono ${p.realized_pnl_usd >= 0 ? "txt-pos" : "txt-neg"}`}>
                      {(p.realized_pnl_usd >= 0 ? "+" : "") + Fmt.usd(p.realized_pnl_usd, { cents: true })}
                    </td>
                    <td className="mono txt-muted">{Fmt.timeAgo(p.closed_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )
      )}

      {tab === "risk" && (
        (riskEvents || []).length === 0 ? (
          <div className="empty">Nenhum evento de risco. O bot está operando normalmente.</div>
        ) : (
          <div className="risk-list" style={{ maxHeight: 380, overflow: "auto" }}>
            {riskEvents.map(r => (
              <div className="risk-item" key={r.id}>
                <span className={`risk-icon ${r.severity}`} />
                <div className="risk-content">
                  <div className="risk-meta">
                    <span className={`pill ${r.severity}`}>{r.severity}</span>
                    <span className="mono txt-dim">{r.kind}</span>
                    <span className="mono txt-dim">·</span>
                    <span className="mono txt-muted">{Fmt.timeAgo(r.ts)}</span>
                  </div>
                  <div className="risk-msg">{r.message}</div>
                </div>
              </div>
            ))}
          </div>
        )
      )}
    </div>
  );
}

// ---------------- Recent trades ----------------
function TradesTable({ trades, refetching, onJumpToLogs }) {
  const sort = useSort("created_at", "desc");
  if (!trades) return <div className="card"><div className="card-title">Operações recentes</div><Skel w="100%" h={120} /></div>;
  const recent = trades.slice(0, 25);
  const sorted = sort.sort(recent);
  return (
    <div className="card" style={{ padding: 0, overflow: "hidden" }}>
      {refetching && <div className="refetch-dot on" />}
      <div className="card-header" style={{ padding: "16px 16px 12px" }}>
        <div className="card-title">Operações recentes</div>
        <span className="card-sub">últimas {recent.length}</span>
      </div>
      {recent.length === 0 ? (
        <div className="empty">Nenhuma operação ainda.</div>
      ) : (
        <div className="tbl-wrap" style={{ maxHeight: 360 }}>
          <table className="tbl">
            <thead>
              <tr>
                <SortHeader label="Hora" sortKey="created_at" sort={sort} />
                <SortHeader label="Mercado" sortKey="market_question" sort={sort} />
                <SortHeader label="Estratégia" sortKey="strategy" sort={sort} />
                <SortHeader label="Lado" sortKey="market_side" sort={sort} />
                <SortHeader label="Ordem" sortKey="order_side" sort={sort} />
                <SortHeader label="Status" sortKey="status" sort={sort} />
                <SortHeader label="Preço" sortKey="price" sort={sort} numeric />
                <SortHeader label="Tamanho" sortKey="size_usd" sort={sort} numeric />
                <SortHeader label="Executado" sortKey="filled_shares" sort={sort} numeric />
              </tr>
            </thead>
            <tbody>
              {sorted.map(t => (
                <tr key={t.id}>
                  <td className="mono txt-muted">{Fmt.timeAgo(t.created_at)}</td>
                  <td className="market-q" title={t.market_question}>
                    {t.market_question}
                    {onJumpToLogs && (
                      <a
                        className="lf-cid"
                        style={{ marginLeft: 8 }}
                        onClick={(e) => { e.stopPropagation(); onJumpToLogs(t.client_order_id); }}
                        title={`Ver logs de ${t.client_order_id}`}
                      >
                        ≡ logs
                      </a>
                    )}
                  </td>
                  <td className="txt-muted">{t.strategy}</td>
                  <td><SidePill side={t.market_side} /></td>
                  <td className="mono" style={{ color: t.order_side === "BUY" ? "var(--accent)" : "var(--no)" }}>{t.order_side}</td>
                  <td><StatePill kind={t.status.toLowerCase()}>{t.status}</StatePill></td>
                  <td className="numeric mono">{t.price.toFixed(3)}</td>
                  <td className="numeric mono">{Fmt.usd(t.size_usd)}</td>
                  <td className="numeric mono">
                    <span className={t.filled_shares === t.shares ? "" : "txt-muted"}>
                      {Fmt.int(t.filled_shares)}/{Fmt.int(t.shares)}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

// ---------------- Markets snapshot ----------------
function MarketsSnapshot({ data, refetching }) {
  const [open, setOpen] = React.useState(false);
  const [q, setQ] = React.useState("");
  const sort = useSort("volume_24h", "desc");
  if (!data) return <div className="card"><Skel w="100%" h={36} /></div>;

  const filtered = data.markets.filter(m => !q || m.question.toLowerCase().includes(q.toLowerCase()));
  const sorted = sort.sort(filtered);

  return (
    <div className="card">
      {refetching && <div className="refetch-dot on" />}
      <div className="card-header" style={{ marginBottom: open ? 12 : 0 }}>
        <div className="collapser" onClick={() => setOpen(o => !o)}>
          <span className={`chev ${open ? "open" : ""}`}>▶</span>
          <div className="card-title">Universo ({data.count} mercados)</div>
          <span className="card-sub" style={{ marginLeft: 8 }}>atualizado há {Fmt.timeAgo(data.refreshed_at).replace(" ago","")}</span>
          {data.is_stale && <span className="pill warning" style={{ marginLeft: 6 }}><span className="dot-stale" />Desatualizado</span>}
        </div>
        {open && <input className="search" placeholder="Buscar mercados…" value={q} onChange={e => setQ(e.target.value)} onClick={e => e.stopPropagation()} />}
      </div>
      {open && (
        <div className="tbl-wrap" style={{ maxHeight: 360 }}>
          <table className="tbl">
            <thead>
              <tr>
                <SortHeader label="Pergunta" sortKey="question" sort={sort} />
                <SortHeader label="SIM compra" sortKey="yes_bid" sort={sort} numeric />
                <SortHeader label="SIM venda" sortKey="yes_ask" sort={sort} numeric />
                <SortHeader label="NÃO compra" sortKey="no_bid" sort={sort} numeric />
                <SortHeader label="NÃO venda" sortKey="no_ask" sort={sort} numeric />
                <SortHeader label="Liquidez" sortKey="yes_liquidity" sort={sort} numeric />
                <SortHeader label="Volume 24h" sortKey="volume_24h" sort={sort} numeric />
              </tr>
            </thead>
            <tbody>
              {sorted.map(m => {
                const arb = (m.yes_ask + m.no_ask) < 1;
                return (
                  <tr key={m.condition_id} className={arb ? "row-arb clickable" : "clickable"}>
                    <td className="market-q" title={m.question}>
                      {arb && <span style={{ color: "var(--accent)", marginRight: 6 }} title="Candidato a arbitragem">◆</span>}
                      {m.question}
                    </td>
                    <td className="numeric mono">{m.yes_bid.toFixed(3)}</td>
                    <td className="numeric mono">{m.yes_ask.toFixed(3)}</td>
                    <td className="numeric mono">{m.no_bid.toFixed(3)}</td>
                    <td className="numeric mono">{m.no_ask.toFixed(3)}</td>
                    <td className="numeric mono txt-muted">{Fmt.usd(Math.min(m.yes_liquidity, m.no_liquidity))}</td>
                    <td className="numeric mono">{Fmt.usd(m.volume_24h)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

Object.assign(window, { StrategyTable, PositionsRiskCard, TradesTable, MarketsSnapshot });
