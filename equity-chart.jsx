// =====================================================================
// EquityChart: Recharts line + area, accent stroke, dark tooltip.
// =====================================================================

const { LineChart, Line, AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, ComposedChart } = window.Recharts;

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

function EquityTooltip({ active, payload, label }) {
  if (!active || !payload || !payload.length) return null;
  const p = payload[0].payload;
  return (
    <div className="equity-tooltip">
      <div className="ttl">{new Date(p.time).toLocaleString("pt-BR", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit", hour12: false })}</div>
      <div className="ttrow"><span className="k">Patrimônio</span><span className="mono">{Fmt.usdPrecise(p.equity)}</span></div>
      <div className="ttrow"><span className="k">Caixa</span><span className="mono txt-muted">{Fmt.usdPrecise(p.cash)}</span></div>
      <div className="ttrow"><span className="k">Não realizado</span><span className={`mono ${p.unrealized >= 0 ? "txt-pos" : "txt-neg"}`}>{Fmt.usdPrecise(p.unrealized)}</span></div>
    </div>
  );
}

function EquityChart({ points, period, onStart, running }) {
  if (!points || !points.length) {
    return (
      <div className="empty" style={{ padding: 60 }}>
        O bot ainda não registrou patrimônio — inicie-o para começar a rastrear.
        {!running && <div style={{ marginTop: 14 }}><button className="btn btn-primary" onClick={onStart}>Iniciar bot</button></div>}
      </div>
    );
  }

  // Compute Y domain padded
  const eqs = points.map(p => p.equity);
  const min = Math.min(...eqs), max = Math.max(...eqs);
  const pad = (max - min) * 0.12 || max * 0.02;
  const dom = [Math.floor(min - pad), Math.ceil(max + pad)];

  return (
    <ResponsiveContainer width="100%" height="100%">
      <ComposedChart data={points} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
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
        <Tooltip content={<EquityTooltip />} cursor={{ stroke: "#2a3554", strokeDasharray: "3 3" }} />
        <Area type="monotone" dataKey="equity" stroke="none" fill="url(#eqArea)" isAnimationActive={false} />
        <Line type="monotone" dataKey="equity" stroke="#5cf2c7" strokeWidth={2} dot={false} activeDot={{ r: 4, fill: "#5cf2c7", stroke: "#0a0e17", strokeWidth: 2 }} isAnimationActive={false} />
      </ComposedChart>
    </ResponsiveContainer>
  );
}

// Tiny sparkline for KPI card
function Sparkline({ points }) {
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

Object.assign(window, { EquityChart, Sparkline });
