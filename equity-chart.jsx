// =====================================================================
// EquityChart with event markers, scrubber/replay, ghost empty state.
// =====================================================================

const { LineChart, Line, AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, ComposedChart, ReferenceDot } = window.Recharts;

function fmtAxisUSD(v) {
  if (Math.abs(v) >= 1_000_000) return `$${(v / 1_000_000).toFixed(1)}M`;
  if (Math.abs(v) >= 1000) return `$${(v / 1000).toFixed(1)}k`;
  return `$${v.toFixed(0)}`;
}

function fmtAxisTime(iso, period) {
  const d = new Date(iso);
  if (period === "24h") return d.toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit", hour12: false });
  if (period === "7d" || period === "30d") return d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

const KIND_COLOR = {
  position_open: "#5cf2c7",
  position_close: "#6aa9ff",
  risk: "#ffb84a",
  drawdown_kill: "#ff5c7a",
  edge_disabled: "#ff5c7a",
};
const KIND_LABEL = {
  position_open: "Posição aberta",
  position_close: "Posição fechada",
  risk: "Evento de risco",
  drawdown_kill: "Kill switch",
  edge_disabled: "Edge desabilitado",
};

function EquityTooltip({ active, payload, events }) {
  if (!active || !payload || !payload.length) return null;
  const p = payload[0].payload;
  // any event near this timestamp?
  const ts = +new Date(p.time);
  const nearby = (events || []).filter(e => Math.abs(+new Date(e.ts) - ts) < 90_000);
  return (
    <div className="equity-tooltip">
      <div className="ttl">{new Date(p.time).toLocaleString("pt-BR", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit", hour12: false })}</div>
      <div className="ttrow"><span className="k">Patrimônio</span><span className="mono">{Fmt.usdPrecise(p.equity)}</span></div>
      <div className="ttrow"><span className="k">Caixa</span><span className="mono txt-muted">{Fmt.usdPrecise(p.cash)}</span></div>
      <div className="ttrow"><span className="k">Não realizado</span><span className={`mono ${p.unrealized >= 0 ? "txt-pos" : "txt-neg"}`}>{Fmt.usdPrecise(p.unrealized)}</span></div>
      {nearby.length > 0 && (
        <>
          <div style={{ height: 1, background: "var(--border)", margin: "6px 0" }} />
          {nearby.map((ev, i) => (
            <div className="ttrow" key={i}>
              <span style={{ display: "inline-flex", alignItems: "center", gap: 5 }}>
                <span style={{ width: 6, height: 6, borderRadius: "50%", background: KIND_COLOR[ev.kind] || "#7c8aa8" }} />
                <span className="k">{KIND_LABEL[ev.kind] || ev.kind}</span>
              </span>
              <span className="mono txt-muted" style={{ fontSize: 10 }}>{ev.label}</span>
            </div>
          ))}
        </>
      )}
    </div>
  );
}

function EquityChart({ points, events, period, onStart, running }) {
  const [scrubFrac, setScrubFrac] = React.useState(1.0);
  const [scrubbing, setScrubbing] = React.useState(false);

  if (!points || !points.length) {
    return <GhostChart />;
  }

  const sliced = scrubbing
    ? points.slice(0, Math.max(2, Math.round(points.length * scrubFrac)))
    : points;

  // Compute Y domain padded — based on the FULL series so the axis is stable while scrubbing.
  const eqs = points.map(p => p.equity);
  const min = Math.min(...eqs), max = Math.max(...eqs);
  const pad = (max - min) * 0.12 || max * 0.02;
  const dom = [Math.floor(min - pad), Math.ceil(max + pad)];

  // Map events → reference dots that match a sliced point
  const sliceTimes = sliced.map(p => +new Date(p.time));
  const dots = (events || []).map(ev => {
    const evT = +new Date(ev.ts);
    // find closest slice point within 5 minutes
    let bestIdx = -1, bestDelta = Infinity;
    sliceTimes.forEach((t, i) => {
      const d = Math.abs(t - evT);
      if (d < bestDelta) { bestDelta = d; bestIdx = i; }
    });
    if (bestIdx === -1 || bestDelta > 5 * 60_000) return null;
    return { ...ev, time: sliced[bestIdx].time, equity: sliced[bestIdx].equity };
  }).filter(Boolean);

  return (
    <div style={{ height: "100%", display: "flex", flexDirection: "column" }}>
      <div style={{ flex: 1, minHeight: 0 }}>
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={sliced} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
            <defs>
              <linearGradient id="eqArea" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#5cf2c7" stopOpacity={0.18} />
                <stop offset="100%" stopColor="#5cf2c7" stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 4" stroke="#1e2740" vertical={false} />
            <XAxis
              dataKey="time"
              tickFormatter={(t) => fmtAxisTime(t, period)}
              tick={{ fill: "#7c8aa8", fontSize: 10.5, fontFamily: "JetBrains Mono, monospace" }}
              axisLine={{ stroke: "#1e2740" }}
              tickLine={false}
              minTickGap={50}
            />
            <YAxis
              orientation="right"
              domain={dom}
              tickFormatter={fmtAxisUSD}
              tick={{ fill: "#7c8aa8", fontSize: 10.5, fontFamily: "JetBrains Mono, monospace" }}
              axisLine={false}
              tickLine={false}
              width={56}
            />
            <Tooltip content={<EquityTooltip events={events} />} cursor={{ stroke: "#2a3554", strokeDasharray: "3 3" }} />
            <Area type="monotone" dataKey="equity" stroke="none" fill="url(#eqArea)" isAnimationActive={false} />
            <Line type="monotone" dataKey="equity" stroke="#5cf2c7" strokeWidth={2} dot={false} activeDot={{ r: 4, fill: "#5cf2c7", stroke: "#0a0e17", strokeWidth: 2 }} isAnimationActive={false} />
            {dots.map((d, i) => (
              <ReferenceDot
                key={i}
                x={d.time}
                y={d.equity}
                r={4.5}
                fill={KIND_COLOR[d.kind] || "#ffb84a"}
                stroke="#0a0e17"
                strokeWidth={1.5}
                isFront
              />
            ))}
          </ComposedChart>
        </ResponsiveContainer>
      </div>

      {/* Replay scrubber */}
      <div className="scrubber-wrap">
        <button
          className="scrubber-btn"
          onClick={() => setScrubbing(s => !s)}
          title={scrubbing ? "Voltar para tempo real" : "Reproduzir (replay)"}
        >
          {scrubbing ? "⏵ ao vivo" : "↺ replay"}
        </button>
        <input
          type="range"
          min="0.05"
          max="1"
          step="0.005"
          value={scrubFrac}
          disabled={!scrubbing}
          onChange={e => setScrubFrac(parseFloat(e.target.value))}
        />
        <span className="mono" style={{ minWidth: 60, textAlign: "right", color: scrubbing ? "var(--text)" : "var(--text-dim)" }}>
          {scrubbing
            ? `${Math.round(scrubFrac * 100)}%`
            : `${points.length} pts`}
        </span>
      </div>
    </div>
  );
}

// Tiny sparkline for KPI card (Recharts-based, takes equity points)
function KpiSparkline({ points }) {
  if (!points || points.length < 2) return null;
  const data = points.slice(-30);
  return (
    <ResponsiveContainer width="100%" height={28}>
      <LineChart data={data} margin={{ top: 2, right: 0, left: 0, bottom: 2 }}>
        <Line type="monotone" dataKey="equity" stroke="#5cf2c7" strokeWidth={1.4} dot={false} isAnimationActive={false} />
      </LineChart>
    </ResponsiveContainer>
  );
}

Object.assign(window, { EquityChart, KpiSparkline });
