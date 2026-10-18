import { lazy, Suspense, useEffect, useMemo, useState } from "react";
import { CandidatePerformance, useCandidatePerformance, type PerformanceSelection, type PerformanceState } from "./CandidatePerformance";
import type { CandidateCohortData } from "./CandidateCohort";
import type { CandidateComparisonData } from "./CandidateComparison";
import type { CandidateTrackingData } from "./CandidateTracking";
import { useCandidateArchive } from "./useCandidateArchive";

const CandidateCohort = lazy(() => import("./CandidateCohort").then(module => ({ default: module.CandidateCohort })));
const CandidateComparison = lazy(() => import("./CandidateComparison").then(module => ({ default: module.CandidateComparison })));
const CandidateTracking = lazy(() => import("./CandidateTracking").then(module => ({ default: module.CandidateTracking })));
const CandidateArchive = lazy(() => import("./CandidateArchive").then(module => ({ default: module.CandidateArchive })));

interface Candidate {
  code: string; name?: string | null; amountYi: number; baselineYi: number; ownRatio: number; marketAdjustedRatio: number; signalPct: number | null;
  forward: Array<{ days: number; status: "ready" | "pending" | "missing"; end: string | null; changePct: number | null; reason: string }>;
}
interface CandidateData {
  current: boolean; signalDate: string | null; signalDates: string[]; asOf: string | null;
  mode: "recorded" | "retrospective"; capturedAt: string | null; generatedAt: string;
  completed: number; expected: number; canContinue: boolean; reason: string;
  baselineStart?: string; baselineEnd?: string; eligibleCount?: number; excludedCount?: number;
  marketMedianRatio?: number | null; candidates: Candidate[]; candidateCount: number; displayLimit: number;
  nameCatalog?: { receivedAt: string | null; usingSaved: boolean; reason: string; matched: number; note: string };
  pagination?: { page: number; pageSize: number; pageCount: number; start: number; end: number };
  source: string; note: string;
  cohort?: CandidateCohortData | null;
  comparison?: CandidateComparisonData | null;
  tracking?: CandidateTrackingData | null;
}
export interface CandidateState { enabled: boolean; loading: boolean; error: string; data: CandidateData | null; performance?: PerformanceState | null; archive?: ReturnType<typeof useCandidateArchive>["state"] }

export function useTurnoverCandidates(active: boolean, refreshKey: number) {
  const [enabled, setEnabled] = useState(false), [signalDate, setSignalDate] = useState("");
  const archive = useCandidateArchive(active && enabled);
  const [page, setPage] = useState(1);
  const [selection, setSelection] = useState<PerformanceSelection | null>(null);
  const [request, setRequest] = useState({ nonce: 0, refresh: false }), [state, setState] = useState<Omit<CandidateState, "enabled">>({ loading: false, error: "", data: null });
  useEffect(() => {
    if (!active || !enabled) return;
    const controller = new AbortController();
    setPage(1);
    setSelection(null);
    setState({ loading: true, error: "", data: null });
    const params = new URLSearchParams({ refresh: String(refreshKey > 0 || request.refresh) });
    if (signalDate) params.set("signal_date", signalDate);
    void fetch(`/api/capital-flow/turnover-candidates?${params}`, { signal: controller.signal }).then(async response => {
      if (!response.ok) throw new Error(`异常成交研究读取失败（${response.status}）`);
      const data: CandidateData = await response.json();
      if (!controller.signal.aborted) setState({ loading: false, error: "", data });
    }).catch(reason => { if (!controller.signal.aborted) setState({ loading: false, error: String(reason.message || reason), data: null }); });
    return () => controller.abort();
  }, [active, enabled, signalDate, refreshKey, request]);
  const pageSize = 50, pageCount = Math.max(1, Math.ceil((state.data?.candidates.length ?? 0) / pageSize));
  const currentPage = Math.min(page, pageCount), offset = (currentPage - 1) * pageSize;
  const data = useMemo(() => state.data ? { ...state.data, candidates: state.data.candidates.slice(offset, offset + pageSize),
    pagination: { page: currentPage, pageSize, pageCount, start: state.data.candidates.length ? offset + 1 : 0,
      end: Math.min(offset + pageSize, state.data.candidates.length) } } : null, [state.data, offset, currentPage, pageCount]);
  const performance = useCandidatePerformance(active && enabled && data?.current && !state.loading && selection?.signalDate === data.signalDate ? selection : null);
  return { state: { ...state, data, performance: performance.state, archive: archive.state, enabled: active && enabled }, archive, toggle: () => { setSelection(null); setEnabled(value => !value); },
    selectPage: (value: number) => { setSelection(null); setPage(Math.max(1, Math.min(pageCount, value))); },
    inspect: (row: Candidate) => setSelection({ code: row.code, name: row.name, signalDate: data!.signalDate! }),
    closePerformance: () => setSelection(null), retryPerformance: performance.retry, selectBenchmark: performance.selectBenchmark,
    selectDate: (value: string) => { setSelection(null); setSignalDate(value); }, retry: () => { setSelection(null); setRequest(value => ({ nonce: value.nonce + 1, refresh: !state.data?.canContinue })); } };
}

export function candidateContext(state?: CandidateState) {
  return state?.enabled ? state : null;
}
const fmt = (value: number | null | undefined, suffix = "") => value == null ? "—" : `${value.toLocaleString("zh-CN", { maximumFractionDigits: 2 })}${suffix}`;

export function TurnoverCandidates({ research, select }: { research: ReturnType<typeof useTurnoverCandidates>; select: (code: string) => void }) {
  const { enabled, loading, error, data } = research.state;
  return <section className="turnover-panel turnover-candidates" aria-label="异常成交候选研究">
    <div className="section-title"><h2>异常成交 · 日终线索</h2><button type="button" aria-expanded={enabled} onClick={research.toggle}>{enabled ? "收起异常成交研究" : "启用异常成交研究"}</button></div>
    <p className="research-source">筛选相对自身历史的放量，并与同日市场普遍放量区分；不是净流入、账户识别或买卖指令。</p>
    {enabled && <>
      <Suspense fallback={<p role="status">正在加载归档入口…</p>}><CandidateArchive archive={research.archive} /></Suspense>
      {loading && <p role="status">正在核对历史窗口；旧候选及Agent旧证据已撤下…</p>}
      {error && <p role="alert" className="turnover-warning">{error}；旧候选已撤下。</p>}
      {data && <>
        <div className="liquidity-toolbar"><label>信号日 <select aria-label="异常成交信号日" value={data.signalDate ?? ""} onChange={event => research.selectDate(event.target.value)}>{data.signalDates.map(day => <option key={day} value={day}>{day}</option>)}</select></label><span>后续数据截至 {data.asOf ?? "—"} · 历史 {data.completed}/{data.expected} 日</span></div>
        <p className="turnover-scope">当日≥1亿元 · 自身前20日均值≥2倍 · 相对市场中位倍数≥1.5倍；阈值未做收益有效性验证。</p>
        {data.reason && <p className="turnover-warning">{data.reason}</p>}
        {data.tracking && <Suspense fallback={<p role="status">正在加载信号追踪…</p>}><CandidateTracking data={data.tracking} selectedDate={data.signalDate} selectDate={research.selectDate} /></Suspense>}
        {data.current && <>
          <div className="turnover-summary"><div><small>命中 / 可比较股票</small><strong>{data.candidateCount} / {data.eligibleCount}</strong></div><div><small>市场中位放量倍数</small><strong>{fmt(data.marketMedianRatio, "×")}</strong></div><div><small>当前日排除样本</small><strong>{data.excludedCount}</strong></div></div>
          <p>{data.mode === "recorded" ? `首次观察记录 · ${data.capturedAt} · 触发条件已冻结` : "事后重算 · 不代表当时已发现"}；基线 {data.baselineStart} → {data.baselineEnd}</p>
          <Suspense fallback={<p role="status">正在加载组间统计…</p>}>
            {data.cohort && <CandidateCohort data={data.cohort} />}
            {data.cohort && data.comparison && <CandidateComparison data={data.comparison} cohort={data.cohort} />}
          </Suspense>
          <div className="research-table-scroll" key={`${data.signalDate}-${data.pagination?.page}`}><table className="research-table" aria-label="异常成交候选与后续变化"><thead><tr><th>证券 / 研究</th><th>成交额 / 20日均额</th><th>自身 / 市场相对倍数</th><th>信号日涨跌</th><th>后1日</th><th>后3日</th><th>后5日</th></tr></thead><tbody>{data.candidates.map(row => <tr key={row.code}>
            <td><button type="button" onClick={() => select(row.code)}>{row.name || row.code} ↗</button>{row.name && <small className="candidate-code">{row.code}</small>}<button type="button" className="candidate-inspect" aria-label={`核验${row.code}表现`} onClick={() => research.inspect(row)}>核验表现</button></td><td>{fmt(row.amountYi)} / {fmt(row.baselineYi)} 亿</td><td>{fmt(row.ownRatio, "×")} / {fmt(row.marketAdjustedRatio, "×")}</td><td>{fmt(row.signalPct, "%")}</td>
            {row.forward.map(path => <td key={path.days} title={path.reason || `截至${path.end}，日涨跌幅链式变化，非策略收益`}>{path.status === "ready" ? fmt(path.changePct, "%") : path.status === "pending" ? "未到期" : "数据缺口"}</td>)}
          </tr>)}</tbody></table></div>
          {!data.candidateCount && <p>窗口完整，但没有命中当前规则的候选；不是数据读取失败。</p>}
          {data.pagination && <nav className="candidate-pagination" aria-label="异常成交候选分页">
            <span aria-live="polite">第{data.pagination.page}/{data.pagination.pageCount}页 · 第{data.pagination.start}–{data.pagination.end}条 / 共{data.candidateCount}条</span>
            <button type="button" disabled={data.pagination.page === 1} onClick={() => research.selectPage(data.pagination!.page - 1)}>上一页</button>
            <button type="button" disabled={data.pagination.page === data.pagination.pageCount} onClick={() => research.selectPage(data.pagination!.page + 1)}>下一页</button>
          </nav>}
          {research.state.performance && <CandidatePerformance state={research.state.performance} close={research.closePerformance} retry={research.retryPerformance} selectBenchmark={research.selectBenchmark} />}
          <p className="research-source">按市场相对倍数排序；Agent接收当前页明细及整组统计，当前页不代表全部候选。后续列为日涨跌幅链式变化，未扣费用和滑点。</p>
          {data.nameCatalog && <p className="research-source">{data.nameCatalog.note} · 名称匹配{data.nameCatalog.matched}/{data.candidateCount} · 目录更新于 {data.nameCatalog.receivedAt ?? "—"}{data.nameCatalog.reason && ` · ${data.nameCatalog.reason}`}</p>}
        </>}
        <details className="research-details"><summary>数据来源、筛选偏差与追踪口径</summary><p>{data.source}</p><p>{data.note}</p></details>
      </>}
      <button type="button" disabled={loading} onClick={research.retry}>{data?.canContinue ? "补齐下一批历史" : "重新核验"}</button>
    </>}
  </section>;
}
