import { useEffect, useState } from "react";
import type { TurnoverHistoryData } from "./types";

export interface TurnoverHistoryState {
  enabled: boolean; days: 20 | 60; data: TurnoverHistoryData | null; loading: boolean; error: string;
}

export function useTurnoverHistory(active: boolean, refreshKey: number) {
  const [enabled, setEnabled] = useState(false);
  const [days, setDays] = useState<20 | 60>(20);
  const [data, setData] = useState<TurnoverHistoryData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [retryKey, setRetryKey] = useState(0);
  useEffect(() => {
    if (!enabled || !active) { setLoading(false); return; }
    const controller = new AbortController();
    setLoading(true); setError("");
    void (async () => {
      try {
        // At most 61 sessions, eight sessions per bounded server request.
        for (let batch = 0; batch < 8; batch++) {
          const refresh = batch === 0 && (retryKey > 0 || refreshKey > 0);
          const response = await fetch(`/api/capital-flow/turnover-history?days=${days}&refresh=${refresh}`, { signal: controller.signal });
          if (!response.ok) throw new Error(`成交历史读取失败（${response.status}）`);
          const next: TurnoverHistoryData = await response.json();
          if (controller.signal.aborted) return;
          setData(next);
          if (!next.canContinue) break;
        }
      } catch (reason) {
        if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : "成交历史读取失败");
      } finally { if (!controller.signal.aborted) setLoading(false); }
    })();
    return () => controller.abort();
  }, [active, enabled, days, refreshKey, retryKey]);
  const state: TurnoverHistoryState = { enabled, days, data: data?.days === days ? data : null, loading, error };
  return { state, toggle: () => setEnabled(value => !value), setDays, retry: () => setRetryKey(value => value + 1) };
}

export function turnoverHistoryContext(state?: TurnoverHistoryState) {
  if (!state?.enabled) return null;
  return { ...state, data: state.data ? { ...state.data, current: state.data.current && !state.loading && !state.error,
    snapshotOnly: state.loading || !!state.error || !state.data.current } : null };
}

const fmt = (value: number | null | undefined) => value == null ? "--" : value.toLocaleString("zh-CN", { maximumFractionDigits: 2 });

export function TurnoverHistory({ state, toggle, setDays, retry }: ReturnType<typeof useTurnoverHistory>) {
  const { data, days, loading, error, enabled } = state;
  const summary = data?.summary;
  const confirmed = data?.current && !loading && !error;
  const max = Math.max(1, ...(data?.points.map(row => row.turnoverYi ?? 0) ?? []));
  return <div className="turnover-baseline">
    <button type="button" className="turnover-history-toggle" aria-expanded={enabled} onClick={toggle}>{enabled ? "收起成交历史" : "研究20/60日成交基线"}</button>
    {enabled && <section aria-label="成交历史基线">
      <div className="liquidity-toolbar"><span>基线不含最新日</span><div className="research-period">{([20, 60] as const).map(n => <button key={n} aria-pressed={days === n} onClick={() => setDays(n)}>{n}日基线</button>)}</div></div>
      <p>{data?.start ?? "--"} → {data?.asOf ?? "--"} · {data?.completed ?? 0}/{days + 1}日{loading ? " · 正在分批补齐" : ""}</p>
      {error && <p className="turnover-warning">{error}；保留快照不代表更新成功。</p>}
      {data?.reason && <p className="turnover-warning">{data.reason}</p>}
      {!!data?.failedDates.length && <p className="turnover-warning">未取得：{data.failedDates.join("、")}</p>}
      <p className="turnover-readout">{confirmed && summary?.relativeVolume != null ? `共同样本成交为前${days}日均值的 ${fmt(summary.relativeVolume)} 倍` : "窗口未确认，不判断放量或集中度变化"}</p>
      <p>共同样本最新成交 {fmt(summary?.latestTurnoverYi)} 亿元 · 前20占比 {fmt(summary?.top20SharePct)}%。与上方单日全样本的范围不同。</p>
      <div className="turnover-summary"><div><small>历史均值 · 亿元</small><strong>{fmt(summary?.meanTurnoverYi)}</strong></div><div><small>成交历史分位</small><strong>{fmt(summary?.percentilePct)}{summary?.percentilePct != null ? "%" : ""}</strong></div><div><small>集中度较均值 · pp</small><strong>{fmt(summary?.concentrationChangePp)}</strong></div></div>
      <div className="turnover-baseline-chart" role="img" aria-label="固定共同样本成交额历史">{data?.points.map(row => <div key={row.date} title={`${row.date} · ${fmt(row.turnoverYi)}亿元 · 前20占比${fmt(row.top20SharePct)}%`}>
        {row.turnoverYi == null ? <span>·</span> : <i style={{ height: `${row.turnoverYi / max * 100}%` }} />}
      </div>)}</div>
      <p>固定共同样本 {data?.commonCount ?? "--"} 只；最新日样本 {data?.latestSampleCount ?? "--"} 只，排除 {data?.excludedLatest ?? "--"} 只。切换窗口会重选比较池，两个窗口数值不能直接相减。</p>
      <p>{data?.note ?? "缺失日期不补零；新股、停牌和缺数标的会影响共同样本覆盖。"}</p>
      <details><summary>逐日成交与集中度</summary><div className="turnover-history-table"><table><thead><tr><th>日期</th><th>当日样本</th><th>共同样本成交/亿</th><th>前20占比</th></tr></thead><tbody>{data?.points.map(row => <tr key={row.date}><td>{row.date}</td><td>{row.sampleCount || "--"}</td><td>{fmt(row.turnoverYi)}</td><td>{fmt(row.top20SharePct)}{row.top20SharePct != null ? "%" : ""}</td></tr>)}</tbody></table></div></details>
      <button type="button" onClick={retry} disabled={loading}>{data?.current ? "刷新最新日" : "重试 / 补齐缺口"}</button>
    </section>}
  </div>;
}
