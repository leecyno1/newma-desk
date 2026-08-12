import { GitCompareArrows, RefreshCw } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import {
  RelativeStrengthChart,
  normalizedStrengthSeries,
  type RelativeStrengthSeries,
} from "@newma-desk/chart-kit";

import { securityKey } from "../data";
import type { Bar, MarketDataSource, SecurityRef } from "../types";
import { WORKSPACE_SECURITIES, movement, signed } from "./shared";

const COLORS = [
  "var(--vibe-accent)",
  "var(--workspace-verdigris)",
  "var(--workspace-olive)",
  "var(--workspace-copper)",
  "var(--vibe-text-soft)",
  "var(--vibe-border-strong)",
];
const DEFAULT_COMPARE = WORKSPACE_SECURITIES.slice(0, 5);

function finalReturn(series: RelativeStrengthSeries) {
  return series.points.at(-1)?.value ?? 0;
}

export function RelativeStrengthWorkspace({
  dataSource,
  security,
  onSelectSecurity,
  refreshNonce,
  onContextChange,
}: {
  dataSource: MarketDataSource;
  security: SecurityRef;
  onSelectSecurity: (security: SecurityRef) => void;
  refreshNonce: number;
  onContextChange: (value: Record<string, unknown>) => void;
}) {
  const initial = useMemo(() => {
    const byKey = new Map(DEFAULT_COMPARE.map((item) => [securityKey(item), item]));
    byKey.set(securityKey(security), security);
    return [...byKey.values()].slice(0, 6);
  }, []);
  const [securities, setSecurities] = useState(initial);
  const [barsBySecurity, setBarsBySecurity] = useState<Record<string, Bar[]>>({});
  const [loading, setLoading] = useState(true);
  const [period, setPeriod] = useState<"1d" | "1w">("1d");

  useEffect(() => {
    if (securities.some((item) => securityKey(item) === securityKey(security))) return;
    setSecurities((current) => [...current.slice(0, 5), security]);
  }, [security, securities]);

  useEffect(() => {
    let active = true;
    setLoading(true);
    void Promise.all(securities.map(async (item) => {
      const result = await dataSource.ohlcv(item, period, item.market === "CN" ? "qfq" : "none");
      return [securityKey(item), result.items] as const;
    })).then((entries) => {
      if (active) setBarsBySecurity(Object.fromEntries(entries));
    }).catch(() => {
      if (active) setBarsBySecurity({});
    }).finally(() => active && setLoading(false));
    return () => {
      active = false;
    };
  }, [dataSource, period, refreshNonce, securities]);

  const series = useMemo(() => securities.map((item, index) =>
    normalizedStrengthSeries(
      securityKey(item),
      item.name,
      COLORS[index % COLORS.length] ?? "var(--vibe-accent)",
      barsBySecurity[securityKey(item)] ?? [],
    )), [barsBySecurity, securities]);
  const ranking = useMemo(() => [...series].sort((left, right) => finalReturn(right) - finalReturn(left)), [series]);

  useEffect(() => {
    onContextChange({
      timeframe: period,
      comparedSecurities: securities.map((item) => ({ symbol: item.symbol, name: item.name, market: item.market })),
      ranking: ranking.map((item) => ({ id: item.id, label: item.label, returnPct: Number(finalReturn(item).toFixed(2)) })),
    });
  }, [onContextChange, period, ranking, securities]);

  return (
    <div className="relative-workspace">
      <section className="relative-chart-panel">
        <div className="workspace-section-title">
          <span><GitCompareArrows size={14} />归一化相对强弱</span>
          <div className="workspace-segment" role="group" aria-label="对比周期">
            <button type="button" aria-pressed={period === "1d"} onClick={() => setPeriod("1d")}>日线</button>
            <button type="button" aria-pressed={period === "1w"} onClick={() => setPeriod("1w")}>周线</button>
          </div>
        </div>
        {loading ? <div className="workspace-chart-loading"><RefreshCw className="spin" size={16} />正在计算归一化走势…</div> : null}
        {!loading && series.some((item) => item.points.length) ? <RelativeStrengthChart series={series} /> : null}
        {!loading && series.every((item) => item.points.length === 0) ? <div className="workspace-empty">相对强弱数据暂不可用</div> : null}
      </section>
      <aside className="relative-ranking-panel">
        <div className="workspace-section-title"><span>阶段排名</span><small>基准日 = 0%</small></div>
        <div className="relative-ranking-list">
          {ranking.map((item, index) => {
            const ref = securities.find((securityItem) => securityKey(securityItem) === item.id);
            const value = finalReturn(item);
            return (
              <button
                type="button"
                key={item.id}
                data-selected={item.id === securityKey(security)}
                onClick={() => ref && onSelectSecurity(ref)}
              >
                <span className="relative-rank">{index + 1}</span>
                <i style={{ background: item.color }} />
                <span><strong>{item.label}</strong><small>{item.id}</small></span>
                <em className={movement(value)}>{signed(value)}</em>
              </button>
            );
          })}
        </div>
        <p className="workspace-help">归一化曲线比较阶段收益，不代表风险调整后的完整表现。</p>
      </aside>
    </div>
  );
}
