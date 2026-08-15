import { GitCompareArrows, RefreshCw } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

import {
  RelativeStrengthChart,
  normalizedStrengthSeries,
  type RelativeStrengthSeries,
} from "@newma-desk/chart-kit";
import { createModSnapshotCache } from "@newma-desk/mod-sdk";

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
  cacheIdentity,
  security,
  onSelectSecurity,
  refreshNonce,
  onContextChange,
}: {
  dataSource: MarketDataSource;
  cacheIdentity?: { userId: string; workspaceId: string };
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
  const [error, setError] = useState("");
  const [period, setPeriod] = useState<"1d" | "1w">("1d");
  const resourceKey = useMemo(() => `period:${period}:securities:${securities
    .map(securityKey)
    .sort()
    .join(",")}`, [period, securities]);
  const cache = useMemo(() => cacheIdentity ? createModSnapshotCache<Record<string, Bar[]>>({
    modId: "relative-strength",
    ...cacheIdentity,
    resourceKey,
    maxBytes: 2 * 1024 * 1024,
  }) : undefined, [cacheIdentity?.userId, cacheIdentity?.workspaceId, resourceKey]);
  const cacheKey = cache?.key;
  const resourceKeyRef = useRef<string | undefined>(undefined);
  const cacheKeyRef = useRef<string | undefined>(undefined);
  const barsBySecurityRef = useRef(barsBySecurity);
  barsBySecurityRef.current = barsBySecurity;

  useEffect(() => {
    if (securities.some((item) => securityKey(item) === securityKey(security))) return;
    setSecurities((current) => [...current.slice(0, 5), security]);
  }, [security, securities]);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError("");
    const cached = cache?.read()?.value;
    const resourceChanged = resourceKeyRef.current !== resourceKey;
    const cacheChanged = cacheKeyRef.current !== cacheKey;
    resourceKeyRef.current = resourceKey;
    cacheKeyRef.current = cacheKey;
    if (resourceChanged) setBarsBySecurity(cached ?? {});
    else if (cacheChanged && cached && Object.keys(barsBySecurityRef.current).length === 0) {
      setBarsBySecurity(cached);
    }
    void Promise.all(securities.map(async (item) => {
      const result = await dataSource.ohlcv(item, period, item.market === "CN" ? "qfq" : "none");
      return [securityKey(item), result.items] as const;
    })).then((entries) => {
      if (!active) return;
      const next = Object.fromEntries(entries);
      setBarsBySecurity(next);
      cache?.write(next);
    }).catch(() => {
      if (active) setError(Object.keys(cached ?? barsBySecurityRef.current).length
        ? "更新失败，当前为上次数据"
        : "相对强弱数据暂不可用");
    }).finally(() => active && setLoading(false));
    return () => {
      active = false;
    };
  }, [cacheKey, dataSource, period, refreshNonce, resourceKey]);

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
        {loading && series.every((item) => item.points.length === 0) ? <div className="workspace-chart-loading"><RefreshCw className="spin" size={16} />正在计算归一化走势…</div> : null}
        {series.some((item) => item.points.length) ? <RelativeStrengthChart series={series} /> : null}
        {loading && series.some((item) => item.points.length) ? <div className="workspace-update-note"><RefreshCw className="spin" size={13} />更新中，当前展示上次数据</div> : null}
        {!loading && error ? <div className="workspace-update-note workspace-error">{error}</div> : null}
        {!loading && !error && series.every((item) => item.points.length === 0) ? <div className="workspace-empty">相对强弱数据暂不可用</div> : null}
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
