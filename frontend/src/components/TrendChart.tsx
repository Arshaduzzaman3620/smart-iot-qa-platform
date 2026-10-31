import type { Telemetry } from "../types";

const W = 600;
const H = 150;
const PAD = 8;

interface Series {
  key: "temperature" | "humidity";
  label: string;
  unit: string;
  className: string;
}

const SERIES: Series[] = [
  { key: "temperature", label: "Temperature", unit: "°C", className: "trend-temp" },
  { key: "humidity", label: "Humidity", unit: "%", className: "trend-hum" },
];

/** Temperature and humidity over the recent readings, each on its own scale. Plain SVG, no chart library. */
export function TrendChart({ history }: { history: Telemetry[] }) {
  const points = [...history].reverse(); // the API returns newest first
  const x = (i: number) => PAD + (i / (points.length - 1)) * (W - 2 * PAD);

  return (
    <figure className="trend" aria-label="Temperature and humidity trend">
      <div className="trend-legend">
        {SERIES.map((s) => {
          const values = points.map((p) => p[s.key]);
          return (
            <span key={s.key} className={`trend-key ${s.className}`}>
              <span className="trend-swatch" aria-hidden="true" />
              {s.label}
              <span className="meta">
                {Math.min(...values).toFixed(1)}–{Math.max(...values).toFixed(1)} {s.unit}
              </span>
            </span>
          );
        })}
        <span className="meta trend-span">last {points.length} readings</span>
      </div>
      <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" className="trend-svg" aria-hidden="true">
        {[0.25, 0.5, 0.75].map((f) => (
          <line key={f} x1={0} x2={W} y1={H * f} y2={H * f} className="trend-grid" />
        ))}
        {SERIES.map((s) => {
          const values = points.map((p) => p[s.key]);
          const min = Math.min(...values);
          const span = Math.max(...values) - min || 1;
          const y = (v: number) => H - PAD - ((v - min) / span) * (H - 2 * PAD);
          const line = points.map((p, i) => `${x(i).toFixed(1)},${y(p[s.key]).toFixed(1)}`).join(" ");
          return (
            <g key={s.key} className={s.className}>
              <polygon points={`${x(0)},${H} ${line} ${x(points.length - 1)},${H}`} className="trend-area" />
              <polyline points={line} className="trend-line" vectorEffect="non-scaling-stroke" />
            </g>
          );
        })}
      </svg>
    </figure>
  );
}
