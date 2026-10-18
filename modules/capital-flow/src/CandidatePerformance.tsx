import { useEffect, useMemo, useRef, useState } from "react";

export interface PerformanceSelection { code: string; name?: string | null; signalDate: string }
interface Window {
  days: number; end: string | null; status: string; rawReturnPct: number | null; adjustedReturnPct: number | null;
  benchmarkReturnPct: number | null; excessPp: number | null; nextOpenReturnPct: number | null;
  execution: string; executionNote: string; reason: string;
}
interface PerformanceData {
  code: string; signalDate: string; asOf: string; windows: Window[]; source: string; method: string; reason: string;
  benchmark: { code: string; name: string; note: string };
  benchmarkOptions: Array<{ code: string; name: string }>;
  feeds: Record<string, { status: string; reason: string; usingSaved: boolean; receivedAt: string }>;
}
export interface PerformanceState { selection: PerformanceSelection; benchmarkCode: string; benchmarkOptions: Array<{ code: string; name: string }>; loading: boolean; error: string; data: PerformanceData | null }

export function useCandidatePerformance(selection: PerformanceSelection | null) {
  const [attempt, setAttempt] = useState({ nonce: 0, refresh: false });
  const [benchmarkCode, setBenchmarkCode] = useState("000300.SH");
  const [benchmarkOptions, setBenchmarkOptions] = useState<PerformanceData["benchmarkOptions"]>([]);
  const key = selection ? `${selection.code}:${selection.signalDate}:${benchmarkCode}:${attempt.nonce}` : "";
  const [result, setResult] = useState<{ key: string; loading: boolean; error: string; data: PerformanceData | null }>({ key: "", loading: false, error: "", data: null });
  useEffect(() => {
    if (!selection) return;
    const abort = new AbortController();
    setResult({ key, loading: true, error: "", data: null });
    const params = new URLSearchParams({ code: selection.code, signal_date: selection.signalDate, benchmark_code: benchmarkCode, refresh: String(attempt.refresh) });
    void fetch(`/api/capital-flow/candidate-performance?${params}`, { signal: abort.signal }).then(async response => {
      if (!response.ok) throw new Error(`表现核验失败（${response.status}）`);
      const data: PerformanceData = await response.json();
      if (!abort.signal.aborted) { setResult({ key, loading: false, error: "", data }); setBenchmarkOptions(data.benchmarkOptions); }
    }).catch(error => { if (!abort.signal.aborted) setResult({ key, loading: false, error: String(error.message || error), data: null }); });
    return () => abort.abort();
  }, [selection, key, benchmarkCode, attempt.refresh]);
  const state = useMemo(() => selection ? { selection, benchmarkCode, benchmarkOptions, ...(result.key === key ? result : { loading: true, error: "", data: null }) } : null,
    [selection, result, key, benchmarkCode, benchmarkOptions]);
  return { state, selectBenchmark: (code: string) => { setBenchmarkCode(code); setAttempt(value => ({ nonce: value.nonce + 1, refresh: false })); },
    retry: () => setAttempt(value => ({ nonce: value.nonce + 1, refresh: true })) };
}

const value = (n: number | null, unit = "%") => n == null ? "—" : `${n.toLocaleString("zh-CN", { maximumFractionDigits: 2 })}${unit}`;
export function CandidatePerformance({ state, close, retry, selectBenchmark }: { state: PerformanceState; close: () => void; retry: () => void; selectBenchmark: (code: string) => void }) {
  const { selection, loading, error, data } = state;
  const panel = useRef<HTMLElement>(null);
  useEffect(() => { panel.current?.scrollIntoView({ block: "start" }); }, [selection.code, selection.signalDate]);
  return <section ref={panel} className="candidate-performance" aria-label="候选表现核验">
    <div className="section-title"><h3>表现核验 · {selection.name || selection.code}</h3><button type="button" onClick={close}>关闭表现核验</button></div>
    <p>{selection.code} · 信号日 {selection.signalDate} · {data ? `数据截至 ${data.asOf}` : "按需读取行情"}</p>
    {state.benchmarkOptions.length > 0 && <div className="liquidity-toolbar"><label>对照基准 <select aria-label="候选表现对照基准" value={state.benchmarkCode} onChange={event => selectBenchmark(event.target.value)}>{state.benchmarkOptions.map(item => <option key={item.code} value={item.code}>{item.name} · {item.code}</option>)}</select></label><span>手动选择，不是自动匹配；比较时请保持基准一致。</span></div>}
    {loading && <p role="status">正在核验复权、基准和开盘参考，旧结果已撤下…</p>}
    {error && <p role="alert">{error}；旧结果已撤下。</p>}
    {data && <>
      <p className="research-source">{data.benchmark.name}（{data.benchmark.code}）：{data.benchmark.note}。超额列为百分点差，不是风险调整收益。</p>
      {data.reason && <p role="alert">{data.reason}</p>}
      <div className="research-table-scroll"><table className="research-table" aria-label="复权与基准对照"><thead><tr><th>期限 / 截止</th><th>复权参考</th><th>未复权</th><th>{data.benchmark.name}</th><th>超额 / 百分点</th><th>次日开盘参考</th><th>核验状态</th></tr></thead>
        <tbody>{data.windows.map(row => <tr key={row.days}><td>后{row.days}日<small className="candidate-code">{row.end || "未到期"}</small></td><td>{value(row.adjustedReturnPct)}</td><td>{value(row.rawReturnPct)}</td><td>{value(row.benchmarkReturnPct)}</td><td>{value(row.excessPp, "pp")}</td><td>{value(row.nextOpenReturnPct)}</td><td title={[row.reason, row.executionNote].filter(Boolean).join("；")}>{row.status === "pending" ? "未到期" : row.status === "missing" ? "行情缺口" : row.status === "review" ? "公司行动待核验" : row.execution === "t-plus-one" ? "T+1限制" : row.execution === "blocked" ? "成交条件待核验" : "仅观察，非成交确认"}</td></tr>)}</tbody></table></div>
      {data.windows.filter(row => row.status !== "pending").map(row => <p className="research-source" key={row.days}>后{row.days}日：{[row.reason, row.executionNote].filter(Boolean).join("；")}</p>)}
      {Object.entries(data.feeds).filter(([, feed]) => feed.status !== "ready" || feed.usingSaved).map(([name, feed]) => <p className="turnover-warning" key={name}>{({ calendar: "日历", price: "行情", adjustment: "复权因子", benchmark: "基准" } as Record<string, string>)[name]}：{feed.reason || "更新未确认"}；不使用保留值计算。</p>)}
      <details className="research-details"><summary>核验公式与来源</summary><p>{data.source}</p><p>{data.method}</p></details>
    </>}
    <button type="button" disabled={loading} onClick={retry}>重新核验表现</button>
  </section>;
}
