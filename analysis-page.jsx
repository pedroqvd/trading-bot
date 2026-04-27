// =====================================================================
// Analysis page: heatmap (hour x weekday), distribution, decomposition,
// strategy cohorts.
// =====================================================================

function buildAnalysisData(seed = 42) {
  // PRNG (deterministic per seed)
  let s = seed; const rng = () => { s = (s * 1664525 + 1013904223) >>> 0; return (s & 0xffffffff) / 0xffffffff; };

  // 7x24 PnL grid (weekday x hour)
  const grid = Array.from({ length: 7 }, () =>
    Array.from({ length: 24 }, () => +((rng() - 0.42) * 180).toFixed(2))
  );
  // emphasize US trading hours weekdays
  for (let d = 1; d <= 5; d++) for (let h = 13; h <= 21; h++) grid[d][h] += rng() * 90;
  // weekend dip
  for (let h = 0; h < 24; h++) { grid[0][h] -= rng() * 30; grid[6][h] -= rng() * 25; }

  // PnL per trade distribution (300 trades)
  const dist = [];
  for (let i = 0; i < 300; i++) {
    const r = (rng() - 0.4);
    const v = Math.sign(r) * Math.pow(Math.abs(r) * 4, 1.6) * 35;
    dist.push(+v.toFixed(2));
  }

  // Decomposition (gross alpha → fees → slippage → net)
  const grossAlpha = 12_400;
  const fees = -480;
  const slippage = -1_120;
  const fundingFx = -90;
  const net = grossAlpha + fees + slippage + fundingFx;

  // Strategy cohort table
  const cohorts = [
    { strategy: "overreaction", trades: 188, win: 0.612, expectancy: 14.2, pnl: 2670, sharpe: 2.3, mdd: -3.4 },
    { strategy: "arbitrage", trades: 94, win: 0.79, expectancy: 9.6, pnl: 902, sharpe: 3.1, mdd: -1.2 },
    { strategy: "momentum", trades: 152, win: 0.49, expectancy: 1.8, pnl: 274, sharpe: 0.9, mdd: -7.1 },
  ];

  return { grid, dist, decomposition: { grossAlpha, fees, slippage, fundingFx, net }, cohorts };
}

function Heatmap({ grid }) {
  // grid: 7x24. Color by signed magnitude
  const flat = grid.flat();
  const maxAbs = Math.max(...flat.map(Math.abs)) || 1;
  const days = ["Dom", "Seg", "Ter", "Qua", "Qui", "Sex", "Sáb"];
  const cellFor = (v) => {
    const t = Math.min(1, Math.abs(v) / maxAbs);
    if (v >= 0) return `rgba(92, 242, 199, ${0.05 + t * 0.55})`;
    return `rgba(255, 92, 122, ${0.05 + t * 0.55})`;
  };
  return (
    <div className="heatmap-grid">
      <div className="hm-corner" />
      {Array.from({ length: 24 }, (_, h) => (
        <div key={h} className="hm-h-label mono">{h.toString().padStart(2, "0")}</div>
      ))}
      {grid.map((row, d) => (
        <React.Fragment key={d}>
          <div className="hm-d-label">{days[d]}</div>
          {row.map((v, h) => (
            <div
              key={h}
              className="hm-pnl-cell"
              style={{ background: cellFor(v) }}
              title={`${days[d]} ${h}:00 → ${v >= 0 ? "+" : ""}${v.toFixed(2)} USD`}
            />
          ))}
        </React.Fragment>
      ))}
    </div>
  );
}

function Histogram({ values }) {
  const bins = 24;
  const min = Math.min(...values), max = Math.max(...values);
  const range = max - min || 1;
  const counts = Array(bins).fill(0);
  values.forEach(v => {
    const idx = Math.min(bins - 1, Math.floor(((v - min) / range) * bins));
    counts[idx]++;
  });
  const maxC = Math.max(...counts);
  const zeroBin = Math.floor(((0 - min) / range) * bins);
  return (
    <div className="histogram">
      {counts.map((c, i) => (
        <div key={i} className="hist-col" title={`${(min + (i / bins) * range).toFixed(1)}…${(min + ((i + 1) / bins) * range).toFixed(1)}: ${c} trades`}>
          <div
            className="hist-bar"
            style={{
              height: `${(c / maxC) * 100}%`,
              background: i < zeroBin ? "var(--danger)" : "var(--accent)",
              opacity: i < zeroBin ? 0.5 + (c / maxC) * 0.5 : 0.4 + (c / maxC) * 0.6,
            }}
          />
        </div>
      ))}
      <div className="hist-axis mono">
        <span>{Fmt.usd(min, { signed: true })}</span>
        <span className="txt-dim">|</span>
        <span>{Fmt.usd(max, { signed: true })}</span>
      </div>
    </div>
  );
}

function Decomposition({ d }) {
  const items = [
    { label: "Alpha bruto", v: d.grossAlpha, pos: true },
    { label: "Taxas", v: d.fees },
    { label: "Slippage", v: d.slippage },
    { label: "Funding/FX", v: d.fundingFx },
  ];
  const max = Math.max(...items.map(x => Math.abs(x.v)));
  return (
    <div className="decomp">
      {items.map((it, i) => (
        <div className="decomp-row" key={i}>
          <div className="decomp-lbl">{it.label}</div>
          <div className="decomp-bar-wrap">
            <div
              className={`decomp-bar ${it.v >= 0 ? "pos" : "neg"}`}
              style={{ width: `${(Math.abs(it.v) / max) * 100}%` }}
            />
          </div>
          <div className={`decomp-val mono ${it.v >= 0 ? "txt-pos" : "txt-neg"}`}>
            {(it.v >= 0 ? "+" : "") + Fmt.usd(it.v, { cents: true })}
          </div>
        </div>
      ))}
      <div className="decomp-row decomp-net">
        <div className="decomp-lbl">PnL líquido</div>
        <div className="decomp-bar-wrap" />
        <div className={`decomp-val mono ${d.net >= 0 ? "txt-pos" : "txt-neg"}`}>
          {(d.net >= 0 ? "+" : "") + Fmt.usd(d.net, { cents: true })}
        </div>
      </div>
    </div>
  );
}

function CohortTable({ rows }) {
  return (
    <div className="tbl-wrap">
      <table className="tbl">
        <thead>
          <tr>
            <th>Estratégia</th>
            <th className="numeric">Trades</th>
            <th className="numeric">Acerto</th>
            <th className="numeric">Expectativa</th>
            <th className="numeric">PnL</th>
            <th className="numeric">Sharpe</th>
            <th className="numeric">Max DD</th>
          </tr>
        </thead>
        <tbody>
          {rows.map(r => (
            <tr key={r.strategy}>
              <td>{r.strategy}</td>
              <td className="numeric mono">{r.trades}</td>
              <td className="numeric mono">{(r.win * 100).toFixed(1)}%</td>
              <td className="numeric mono">{Fmt.usd(r.expectancy, { cents: true, signed: true })}</td>
              <td className={`numeric mono ${r.pnl >= 0 ? "txt-pos" : "txt-neg"}`}>{(r.pnl >= 0 ? "+" : "") + Fmt.usd(r.pnl)}</td>
              <td className="numeric mono">{r.sharpe.toFixed(2)}</td>
              <td className="numeric mono txt-neg">{r.mdd.toFixed(2)}%</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function AnalysisPage() {
  const data = React.useMemo(() => buildAnalysisData(), []);
  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h1>Análise &amp; Performance</h1>
          <div className="sub">Decomposição, distribuição e cohorts dos últimos 30 dias.</div>
        </div>
      </div>

      <div className="card" style={{ marginBottom: 12 }}>
        <div className="card-header">
          <div className="card-title">PnL por hora × dia da semana</div>
          <span className="card-sub">verde = lucro, rosa = perda</span>
        </div>
        <Heatmap grid={data.grid} />
      </div>

      <div className="row-2">
        <div className="card">
          <div className="card-header">
            <div className="card-title">Distribuição de PnL por trade</div>
            <span className="card-sub mono">{300} trades</span>
          </div>
          <Histogram values={data.dist} />
        </div>

        <div className="card">
          <div className="card-header">
            <div className="card-title">Decomposição de PnL</div>
            <span className="card-sub">do alpha bruto ao líquido</span>
          </div>
          <Decomposition d={data.decomposition} />
        </div>
      </div>

      <div className="card" style={{ marginTop: 12 }}>
        <div className="card-header">
          <div className="card-title">Cohorts por estratégia</div>
          <span className="card-sub">comparação entre edges no período</span>
        </div>
        <CohortTable rows={data.cohorts} />
      </div>
    </div>
  );
}

Object.assign(window, { AnalysisPage });
