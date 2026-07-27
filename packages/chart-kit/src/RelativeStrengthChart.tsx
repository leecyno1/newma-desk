import { useMemo } from "react";

import type { Bar, RelativeStrengthSeries } from "./types";

const WIDTH = 1000;
const HEIGHT = 360;
const PADDING = { top: 34, right: 42, bottom: 34, left: 48 };

export function normalizedStrengthSeries(
  id: string,
  label: string,
  color: string,
  bars: Bar[],
): RelativeStrengthSeries {
  const first = bars.find((bar) => Number.isFinite(bar.close) && bar.close !== 0)?.close;
  if (!first) return { id, label, color, points: [] };
  return {
    id,
    label,
    color,
    points: bars.map((bar) => ({
      timestamp: bar.timestamp,
      value: ((bar.close / first) - 1) * 100,
    })),
  };
}

function pathFor(series: RelativeStrengthSeries, min: number, max: number) {
  if (series.points.length < 2) return "";
  const plotWidth = WIDTH - PADDING.left - PADDING.right;
  const plotHeight = HEIGHT - PADDING.top - PADDING.bottom;
  const denominator = Math.max(max - min, 1);
  return series.points.map((point, index) => {
    const x = PADDING.left + (index / Math.max(series.points.length - 1, 1)) * plotWidth;
    const y = PADDING.top + ((max - point.value) / denominator) * plotHeight;
    return `${index === 0 ? "M" : "L"}${x.toFixed(2)},${y.toFixed(2)}`;
  }).join(" ");
}

export function RelativeStrengthChart({
  series,
  ariaLabel = "相对强弱走势",
}: {
  series: RelativeStrengthSeries[];
  ariaLabel?: string;
}) {
  const bounds = useMemo(() => {
    const values = series.flatMap((item) => item.points.map((point) => point.value));
    if (!values.length) return { min: -5, max: 5 };
    const min = Math.min(...values, 0);
    const max = Math.max(...values, 0);
    const space = Math.max((max - min) * 0.12, 1);
    return { min: min - space, max: max + space };
  }, [series]);
  const ticks = Array.from({ length: 5 }, (_, index) =>
    bounds.max - ((bounds.max - bounds.min) * index) / 4,
  );
  const zeroY = PADDING.top + ((bounds.max - 0) / Math.max(bounds.max - bounds.min, 1)) * (HEIGHT - PADDING.top - PADDING.bottom);

  return (
    <div className="relative-chart-shell">
      <div className="relative-chart-legend" aria-label="对比标的图例">
        {series.map((item) => (
          <span key={item.id}><i style={{ background: item.color }} />{item.label}</span>
        ))}
      </div>
      <svg
        className="relative-chart-svg"
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        role="img"
        aria-label={ariaLabel}
        preserveAspectRatio="none"
      >
        {ticks.map((tick) => {
          const y = PADDING.top + ((bounds.max - tick) / Math.max(bounds.max - bounds.min, 1)) * (HEIGHT - PADDING.top - PADDING.bottom);
          return (
            <g key={tick}>
              <line x1={PADDING.left} y1={y} x2={WIDTH - PADDING.right} y2={y} className="relative-grid-line" />
              <text x={PADDING.left - 8} y={y + 4} textAnchor="end" className="relative-axis-label">{tick.toFixed(1)}%</text>
            </g>
          );
        })}
        <line x1={PADDING.left} y1={zeroY} x2={WIDTH - PADDING.right} y2={zeroY} className="relative-zero-line" />
        {series.map((item) => (
          <path key={item.id} d={pathFor(item, bounds.min, bounds.max)} fill="none" stroke={item.color} strokeWidth="2.4" vectorEffect="non-scaling-stroke" />
        ))}
      </svg>
    </div>
  );
}
