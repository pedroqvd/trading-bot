// ==========================================================
// Formatters + small primitives (animated number, pills, etc)
// Babel JSX, runs after React is loaded.
// ==========================================================

// ---------- format helpers ----------
const Fmt = {
  usd(v, opts = {}) {
    if (v == null || isNaN(v)) return "—";
    const abs = Math.abs(v);
    const sign = v < 0 ? "-" : (opts.signed ? "+" : "");
    if (abs >= 1_000_000) return `${sign}$${(abs / 1_000_000).toFixed(2)}M`;
    if (abs >= 10_000) return `${sign}$${(abs / 1000).toFixed(1)}k`;
    return `${sign}$${abs.toLocaleString("en-US", { minimumFractionDigits: opts.cents ? 2 : 0, maximumFractionDigits: opts.cents ? 2 : 0 })}`;
  },
  usdPrecise(v) {
    if (v == null || isNaN(v)) return "—";
    return v.toLocaleString("en-US", { style: "currency", currency: "USD" });
  },
  pct(v, dec = 2) {
    if (v == null || isNaN(v)) return "—";
    return `${(v * 100).toFixed(dec)}%`;
  },
  pctRaw(v, dec = 2) {
    if (v == null || isNaN(v)) return "—";
    return `${v.toFixed(dec)}%`;
  },
  num(v, dec = 2) {
    if (v == null || isNaN(v)) return "—";
    if (!isFinite(v)) return "∞";
    return v.toLocaleString("en-US", { minimumFractionDigits: dec, maximumFractionDigits: dec });
  },
  int(v) {
    if (v == null || isNaN(v)) return "—";
    return v.toLocaleString("en-US");
  },
  price(v) {
    if (v == null || isNaN(v)) return "—";
    return v.toFixed(3);
  },
  timeAgo(iso) {
    if (!iso) return "—";
    const ms = Date.now() - new Date(iso).getTime();
    if (ms < 0) return "agora";
    const s = Math.floor(ms / 1000);
    if (s < 60) return `há ${s}s`;
    const m = Math.floor(s / 60);
    if (m < 60) return `há ${m}m`;
    const h = Math.floor(m / 60);
    const rem = m - h * 60;
    if (h < 24) return rem ? `há ${h}h ${rem}m` : `há ${h}h`;
    const d = Math.floor(h / 24);
    if (d < 7) return `há ${d}d`;
    return new Date(iso).toLocaleDateString("pt-BR");
  },
  timeOfDay(iso) {
    if (!iso) return "—";
    return new Date(iso).toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit", hour12: false });
  },
  durationSince(iso) {
    if (!iso) return "—";
    const ms = Date.now() - new Date(iso).getTime();
    const m = Math.floor(ms / 60000);
    const h = Math.floor(m / 60);
    const rem = m - h * 60;
    if (h > 0) return `${h}h ${rem}m`;
    return `${m}m`;
  },
};

// ---------- AnimatedNumber: tween + flash on change ----------
function AnimatedNumber({ value, format, className = "", duration = 400 }) {
  const [display, setDisplay] = React.useState(value);
  const [flash, setFlash] = React.useState("");
  const fromRef = React.useRef(value);
  const rafRef = React.useRef(0);
  const lastRef = React.useRef(value);

  React.useEffect(() => {
    if (value === lastRef.current) return;
    const delta = value - lastRef.current;
    setFlash(delta > 0 ? "flash-pos" : "flash-neg");
    fromRef.current = display;
    const start = performance.now();
    const from = display;
    const to = value;
    cancelAnimationFrame(rafRef.current);
    const step = (now) => {
      const t = Math.min(1, (now - start) / duration);
      const eased = 1 - Math.pow(1 - t, 3);
      setDisplay(from + (to - from) * eased);
      if (t < 1) rafRef.current = requestAnimationFrame(step);
      else setDisplay(to);
    };
    rafRef.current = requestAnimationFrame(step);
    lastRef.current = value;
    const ft = setTimeout(() => setFlash(""), duration + 220);
    return () => { cancelAnimationFrame(rafRef.current); clearTimeout(ft); };
  }, [value]);

  return <span className={`mono ${className} ${flash}`} aria-live="polite">{format(display)}</span>;
}

// ---------- StatePill ----------
function StatePill({ kind, children, title }) {
  return (
    <span className={`pill ${kind}`} title={title || undefined}>
      {children}
    </span>
  );
}

// ---------- SidePill ----------
function SidePill({ side }) {
  return <span className={`pill ${side === "YES" ? "yes" : "no"}`}>{side}</span>;
}

// ---------- StatusPill (top-bar bot status) ----------
function BotStatusPill({ status, error }) {
  if (error) return <span className="status-pill"><span className="dot-error" /> Erro</span>;
  if (status === "running") return <span className="status-pill"><span className="dot-pulse" /> Em execução</span>;
  return <span className="status-pill"><span className="dot-stopped" /> Parado</span>;
}

// ---------- Skeleton ----------
function Skel({ w = "100%", h = 14, className = "", style = {} }) {
  return <div className={`skeleton ${className}`} style={{ width: w, height: h, ...style }} />;
}

// ---------- Tooltip wrapper ----------
function Tip({ label, children }) {
  return <span className="tip-wrap">{children}<span className="tip">{label}</span></span>;
}

// expose
Object.assign(window, { Fmt, AnimatedNumber, StatePill, SidePill, BotStatusPill, Skel, Tip });
