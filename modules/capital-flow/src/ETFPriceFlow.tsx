import { useEffect, useState } from "react";
import type { ETFResearch } from "./types";
import type { ETFStrengthDays } from "./etfStrength";

export interface ETFPriceWindow {
  days: number; baseDate: string | null; start: string | null; end: string | null;
  baseClose: number | null; endClose: number | null; baseFactor: number | null; endFactor: number | null;
  rawReturnPct: number | null; adjustedReturnPct: number | null; missingDates: string[]; factorChangeDates: string[];
  current: boolean; reason: string;
  points: Array<{ date: string; close: number | null; factor: number | null; volume: number | null }>;
}
export interface ETFPriceData {
  code: string; source: string; currency: string; generatedAt: string; method: string;
  windows: Record<string, ETFPriceWindow>;
  feeds: Record<string, { status: string; reason: string; usingSaved: boolean; receivedAt: string }>;
}
export interface ETFPriceState { data: ETFPriceData | null; loading: boolean; error: string }

export function useETFPrice(code: string, active: boolean, refresh: number): ETFPriceState {
  const [data, setData] = useState<ETFPriceData | null>(null);
  const [settledKey, setSettledKey] = useState("");
  const [loading, setLoading] = useState(false), [error, setError] = useState("");
  const key = `${code}:${refresh}`;
  useEffect(() => {
    if (!active) { setLoading(false); return; }
    const controller = new AbortController(); setLoading(true); setError("");
    void fetch(`/api/capital-flow/etf-price?code=${encodeURIComponent(code)}&refresh=${refresh > 0}`, { signal: controller.signal })
      .then(async response => { if (!response.ok) throw new Error(`ETF价格读取失败（${response.status}）`); return response.json() as Promise<ETFPriceData>; })
      .then(result => { if (!controller.signal.aborted) setData(result); })
      .catch(reason => { if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : "ETF价格读取失败"); })
      .finally(() => { if (!controller.signal.aborted) { setLoading(false); setSettledKey(key); } });
    return () => controller.abort();
  }, [active, code, refresh]);
  return { data: active && data?.code === code ? data : null, loading: active && (loading || settledKey !== key), error: settledKey === key ? error : "" };
}

export function priceFlowContext(etf: ETFResearch | undefined, state: ETFPriceState | undefined, days: ETFStrengthDays) {
  if (!etf) return null;
  const data = state?.data?.code === etf.code ? state.data : null;
  const windows = ([1, 5, 20] as const).map(period => {
    const price = data?.windows[period], flow = etf.summary.strength?.[period];
    const aligned = !!price && !!flow && price.baseDate === flow.baseDate && price.start === flow.start && price.end === flow.end;
    const current = !!price?.current && !!flow?.current && aligned && !state?.loading && !state?.error;
    const p = price?.adjustedReturnPct, f = flow?.strengthPct;
    let phase = "未确认", divergence = false;
    if (current && p != null && f != null) {
      if (Math.abs(p) <= .05 || Math.abs(f) <= .05) phase = "幅度不足，不判方向";
      else if (p > 0 && f > 0) phase = "上涨伴随净申购";
      else if (p < 0 && f < 0) phase = "下跌伴随净赎回";
      else { divergence = true; phase = p > 0 ? "上涨伴随净赎回 · 背离" : "下跌伴随净申购 · 背离"; }
    }
    return { days: period, baseDate: flow?.baseDate ?? price?.baseDate, start: flow?.start ?? price?.start, end: flow?.end ?? price?.end,
      current, phase, divergence, rawReturnPct: price?.rawReturnPct ?? null, adjustedReturnPct: p ?? null, strengthPct: f ?? null,
      baseClose: price?.baseClose, endClose: price?.endClose, baseFactor: price?.baseFactor, endFactor: price?.endFactor,
      missingDates: price?.missingDates ?? [], factorChangeDates: price?.factorChangeDates ?? [],
      reason: [state?.loading ? "正在更新价格，暂不判定" : state?.error, !price ? "尚未取得价格与复权因子" : price.reason,
        !flow ? "尚未取得申赎强度" : flow.reason, price && flow && !aligned ? "价格与申赎窗口日期不一致" : ""].filter(Boolean).join("；"),
      points: price?.points ?? [] };
  });
  return { code: etf.code, name: etf.name, days, windows, selected: windows.find(row => row.days === days)!,
    loading: !!state?.loading, error: state?.error || "", source: data?.source, feeds: data?.feeds,
    method: "市场收盘价×复权因子的区间涨跌，与同窗口申赎强度比较；任一绝对值≤0.05%不判方向。非成交量价指标、不是净值回报或买卖指令。" };
}

const percent = (value: number | null | undefined) => value == null ? "--" : `${value > 0 ? "+" : ""}${value.toLocaleString("zh-CN", { maximumFractionDigits: 2 })}%`;
export function ETFPriceFlow({ context }: { context: ReturnType<typeof priceFlowContext> }) {
  if (!context) return null;
  const selected = context.selected;
  return <section className="etf-price-flow" aria-label="ETF价格与申赎背离">
    <div className="research-subhead"><h3>{context.name} · 价格与申赎</h3><strong>{selected.phase}</strong></div>
    <div className="research-table-scroll"><table className="etf-price-flow-table"><thead><tr><th>交易日窗口</th><th>原始价格涨跌</th><th>复权参考涨跌</th><th>申赎强度</th><th>关系判断</th></tr></thead>
      <tbody>{context.windows.map(row => <tr key={row.days} className={row.days === context.days ? "selected" : ""} data-price-flow-days={row.days}>
        <td>{row.days}日<small>{row.start ?? "--"} → {row.end ?? "--"}</small></td><td>{percent(row.rawReturnPct)}</td><td>{percent(row.adjustedReturnPct)}</td><td>{percent(row.strengthPct)}</td><td>{row.phase}<small>{row.reason}</small></td>
      </tr>)}</tbody></table></div>
    <div className="research-readout"><span>所选{context.days}日：{selected.baseDate ?? "--"} → {selected.end ?? "--"}</span><span>收盘价 {selected.baseClose ?? "--"} → {selected.endClose ?? "--"} 元</span><span>复权因子 {selected.baseFactor ?? "--"} → {selected.endFactor ?? "--"}</span></div>
    {!!selected.factorChangeDates.length && <p className="research-warning">复权因子变化日：{selected.factorChangeDates.join("、")}；先核验分红／折算，不输出背离信号。</p>}
    {!!selected.missingDates.length && <p className="research-warning">价格／因子／有效成交缺口：{selected.missingDates.join("、")}</p>}
    <p className="research-source">{context.source || "Tushare fund_daily + fund_adj"} · {context.method} 背离仅为复核线索：可能涉及套利、做市及份额时点差，不能直接解释为抄底或出货。</p>
    <div className="source-links"><a href="https://tushare.pro/document/2?doc_id=127" target="_blank" rel="noreferrer">ETF市场日线</a><a href="https://tushare.pro/document/2?doc_id=199" target="_blank" rel="noreferrer">复权因子口径</a></div>
  </section>;
}
