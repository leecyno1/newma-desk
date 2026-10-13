import { useCallback, useEffect, useState, type ReactNode } from 'react';
import { RiskActionEditor } from './RiskActionEditor';
import { portfolioClient } from './api';
import type { PortfolioDashboard, PortfolioPerformanceInput, PortfolioPerformanceResult, PortfolioRiskAction, PortfolioRiskReport } from './types';
import { evaluateRisk, historyValidity, lossPct, RISK_LABELS, type RiskCheck } from './risk';
import { ConcentrationAnalysis, DrawdownAnalysis, ExposureAnalysis, LiquidityEvidence, RiskTable, StressAnalysis } from './RiskAnalytics';
import type { Market } from './types';
import { PortfolioDiagnosis, type ImportDiagnosis } from './PortfolioDiagnosis';

type View = 'overview' | 'limits' | 'concentration' | 'exposure' | 'drawdown' | 'liquidity' | 'stress' | 'alerts' | 'actions';
const TABS: Array<[View, string]> = [['overview','风险总览'],['limits','风险限额'],['concentration','集中度'],['exposure','市场 / 币种暴露'],['drawdown','回撤与 VaR'],['liquidity','流动性'],['stress','压力测试'],['alerts','预警'],['actions','处置记录']];
const fmt = (value: number | null | undefined) => value == null ? '—' : Number(value.toFixed(2)).toLocaleString('zh-CN');
const date = (value?: string | null) => value ? new Date(value).toLocaleString('zh-CN', { hour12: false }) : '未提供';
const errorText = (error: unknown) => error instanceof Error ? error.message : '操作失败，请重试';

function Checks({ checks, dashboard, onRefresh }: { checks: RiskCheck[]; dashboard?: PortfolioDashboard; onRefresh?(): void }) {
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');
  const [filter,setFilter] = useState('all');
  const [search,setSearch] = useState('');
  const register = async (check: RiskCheck) => {
    if (!dashboard) return;
    setBusy(check.id); setError('');
    try {
      await portfolioClient(dashboard).createRiskAction({ ruleId: check.id, title: check.label, detail: `${check.detail}；登记时 ${RISK_LABELS[check.status]}，值 ${check.value}`, severity: check.severity });
      onRefresh?.();
    } catch (reason) { setError(errorText(reason)); } finally { setBusy(''); }
  };
  const visible=checks.filter(c=>(filter==='all'||(filter==='gaps'?!['passed','triggered'].includes(c.status):c.status===filter))&&`${c.label} ${c.detail}`.includes(search));
  return <>{error && <p role="alert" className="inline-error">{error}</p>}<div className="risk-register-controls"><label>核验状态<select value={filter} onChange={e=>setFilter(e.target.value)}><option value="all">全部 {checks.length}</option><option value="triggered">已触发</option><option value="gaps">数据缺口 / 未评估</option><option value="passed">已通过</option></select></label><label>查找规则<input value={search} onChange={e=>setSearch(e.target.value)} placeholder="证券限额、币种、现金…"/></label><span>{visible.length} / {checks.length} 项 · 展开规则查看方法</span></div><div className="risk-check-table"><RiskTable label="风险核验台账" heads={['规则 / 范围','当前值','状态','优先级','处置']}>{visible.map(check => {
    const active = dashboard?.riskActions.some(action => action.ruleId === check.id && !['resolved','waived'].includes(action.status));
    return <tr key={check.id} data-risk-status={check.status}><td><details><summary>{check.label}</summary><p>{check.detail}</p></details></td><td>{check.value}</td><td><span className="risk-badge">{RISK_LABELS[check.status]}</span></td><td>{({critical:'紧急',high:'高',medium:'中'})[check.severity]}</td><td>{dashboard && check.status !== 'passed' && check.status !== 'unassessed' ? (active ? <span>处置中</span> : <button className="secondary-button" disabled={!!busy} onClick={() => void register(check)}>登记处置</button>) : '—'}</td></tr>;
  })}</RiskTable>{!visible.length&&<p className="method-note">当前筛选无匹配记录。</p>}</div></>;
}


export function RiskView({ dashboard, view, onView, result, onResult, input, onInput, onRefresh, limits, report, onReport, now, shocks, onShocks, onImportContext }: {
  dashboard: PortfolioDashboard; view: View; onView(view: View, restored?: { input: PortfolioPerformanceInput; result: PortfolioPerformanceResult }): void; result?: PortfolioPerformanceResult; onResult(result: PortfolioPerformanceResult): void;
  input: PortfolioPerformanceInput; onInput(input: PortfolioPerformanceInput): void; onRefresh(): void; limits: ReactNode;
  report?: PortfolioRiskReport; onReport(report?: PortfolioRiskReport): void; now: number;
  shocks: Record<Market,number>; onShocks(value:Record<Market,number>):void;
  onImportContext(value:ImportDiagnosis|undefined):void;
}) {
  const [importSelected,setImportSelected]=useState<boolean>();
  const selectImport=useCallback((value:ImportDiagnosis|undefined)=>{setImportSelected(!!value);onImportContext(value)},[onImportContext]);
  const [running, setRunning] = useState(false);
  const [message,setMessage] = useState('');
  const [reports,setReports] = useState<PortfolioRiskReport[]>([]);
  const [reportsError,setReportsError] = useState('');
  const [saving,setSaving] = useState(false);
  const [actionFilter,setActionFilter]=useState('all');
  const currencies = [...new Set(dashboard.positions.map(p => p.currency))];
  const assessment = evaluateRisk(dashboard, input, result, now);
  const historical = historyValidity(dashboard, input, result, now);
  const selectedResult = result?.currency === input.currency ? result : undefined;
  useEffect(() => {
    if (currencies.length && !currencies.includes(input.currency)) onInput({ ...input, currency: currencies[0] });
  }, [currencies.join('|'), input.currency]);
  useEffect(() => {
    let active = true;
    void portfolioClient(dashboard).riskReports().then(items => { if (active) { setReports(items); setReportsError(''); } }).catch(reason => { if (active) setReportsError(errorText(reason)); });
    return () => { active = false; };
  }, [dashboard.userId, dashboard.workspaceId, result?.reportId, dashboard.updatedAt]);
  const run = async () => {
    setRunning(true); setMessage('');
    try { onResult(await portfolioClient(dashboard).analyzePerformance(input)); }
    catch (reason) { setMessage(errorText(reason)); } finally { setRunning(false); }
  };
  const save = async () => {
    setSaving(true); setMessage('');
    try { const saved = await portfolioClient(dashboard).saveRiskReport(input, result?.reportId); setReports(items => [saved,...items].slice(0,50)); onReport(saved); setMessage('风险评估已留档；未完成项也会如实保存。'); }
    catch (reason) { setMessage(errorText(reason)); } finally { setSaving(false); }
  };
  const archivedInput = report?.analysisInput || input;
  return <div className="workspace-shell risk-workbench">
    {window.self === window.top && <nav className="workspace-tabs" aria-label="组合风控标签">{TABS.map(([id,label]) => <button key={id} className={view === id ? 'active' : ''} aria-current={view === id ? 'page' : undefined} onClick={() => { onReport(undefined); setMessage(''); onView(id); }}>{label}</button>)}</nav>}
    {message && <p role="status" className="status-message">{message}</p>}
    <PortfolioDiagnosis identity={dashboard} onContext={selectImport} view={view}/>
    {importSelected===undefined&&<p className="method-note">正在恢复评估对象…</p>}
    {importSelected===false&&<>
    {view !== 'overview' && <p className="method-note">当前评估对象为原股票账本；可在上方选择已保存的混合组合快照。</p>}
    {view === 'overview' && !importSelected && <div className="workbench-stack">
      <section className="workbench-metrics"><article data-risk-status={assessment.status}><span>风险状态</span><strong>{assessment.label}</strong><small>{assessment.triggered} 项触发 · {assessment.gaps} 项未完成</small></article><article><span>已完成规则</span><strong>{assessment.passed + assessment.triggered} / {assessment.checks.length}</strong><small>通过与触发均计入已评估</small></article><article><span>持仓范围</span><strong>{dashboard.positions.length} 笔</strong><small>{currencies.join(' / ') || '尚无持仓'} · 同证券跨账户合并</small></article><article><span>未结处置</span><strong>{dashboard.riskActions.filter(a => !['resolved','waived'].includes(a.status)).length}</strong><small>处置不改变客观风险状态</small></article></section>
      <section className="folio-panel"><div className="panel-title"><h2>风险核验清单</h2><button className="secondary-button" onClick={() => onView('alerts')}>预警与登记处置</button></div><Checks checks={assessment.checks}/><p className="method-note">{assessment.note} 行情 4 天、周线 10 天、评估 24 小时为当前保守时效阈值，按自然日计算。</p></section>
      <section className="folio-panel"><div className="panel-title"><h2>评估留档</h2><button className="primary-button" disabled={saving} onClick={() => void save()}>{saving ? '保存中…' : '保存风险评估'}</button></div><p className="method-note">历史分析自动留档。快照固定持仓、限额、方法和数据日期，可供配置 / 投决引用，不等于复核通过。最近 50 份。</p>{reportsError && <p role="alert" className="inline-error">留档读取失败：{reportsError}</p>}<label>查看历史评估<select aria-label="查看历史评估" value={report?.id || ''} onChange={e => onReport(reports.find(r => r.id === e.target.value))}><option value="">当前核验（非历史快照）</option>{reports.map(r => <option key={r.id} value={r.id}>{date(r.savedAt)} · {r.performance ? `${r.performance.currency} ${r.performance.observations} 周` : '静态风险'} · {r.id.slice(0,8)}</option>)}</select></label>
        {report && <div className="risk-archive"><h3>历史快照 · 只读，不作为当前通过结论</h3><p>引用编号：{report.id}<br/>保存：{date(report.savedAt)} · {report.dashboard.positions.length} 笔持仓 · 方法：{report.performance?.method || '账本静态规则'}</p><Checks checks={evaluateRisk(report.dashboard, archivedInput, report.performance, Date.parse(report.savedAt)).checks}/>{report.performance && <button className="secondary-button" onClick={() => { onReport(undefined); onView('drawdown', { input: archivedInput, result: { ...report.performance!, reportId: report.id } }); }}>载入历史结果并校验当前条件</button>}</div>}
      </section>
    </div>}
    {view === 'limits' && <div className="workbench-stack">{limits}<section className="folio-panel"><div className="risk-section-heading"><strong>当前组合 · 限额核验</strong><span>调整限额不会自动消除风险；保存后重新核验</span></div><Checks checks={assessment.checks.filter(c=>c.id!=='liquidity'&&c.id!=='fx')}/></section></div>}
    {view === 'concentration' && <ConcentrationAnalysis dashboard={dashboard} now={now}/>}
    {view === 'exposure' && <ExposureAnalysis dashboard={dashboard} now={now}/>}
    {view === 'drawdown' && <div className="workbench-stack"><section className="folio-panel"><h2>回撤与尾部风险</h2><div className="inline-controls"><label>分析币种<select value={input.currency} onChange={e => onInput({ ...input, currency: e.target.value })}>{(currencies.length ? currencies : ['CNY']).map(c => <option key={c}>{c}</option>)}</select></label><label>历史窗口<select value={input.lookbackWeeks} onChange={e => onInput({ ...input, lookbackWeeks: Number(e.target.value) })}>{[52,104,156,260].map(w => <option key={w} value={w}>{w / 52} 年 · {w} 周</option>)}</select></label><button className="primary-button" disabled={running || !currencies.length} onClick={() => void run()}>{running ? '计算中…' : '计算历史风险'}</button></div><p data-risk-status={historical.status}>{historical.status === 'passed' ? '数据核验通过' : RISK_LABELS[historical.status]} · {historical.reason}</p><p className="method-note">当前权重、同币种、自然周对齐的历史模拟；不包含现金流和实际调仓，不是账户实际净值回撤。VaR / CVaR 以下行损失正值显示；正收益分位对应损失 0%。</p></section>
      {selectedResult && <section className="folio-panel"><h3>{historical.status === 'passed' ? '当前条件的历史模拟结果' : '参考结果 · 不用于当前限额通过判断'}</h3><p>截止 {selectedResult.asOf || '未知'} · 生成 {date(selectedResult.generatedAt)} · {selectedResult.observations} / {selectedResult.lookbackWeeks} 周 · 持仓权重覆盖 {fmt(selectedResult.coverageWeightPct)}%</p><p>方法 {selectedResult.method} · 来源 {selectedResult.dataSources.join(' / ') || '未返回'}</p>{selectedResult.metrics && <section className="workbench-metrics"><article><span>最大回撤损失</span><strong>{fmt(lossPct(selectedResult.metrics.maxDrawdownPct))}%</strong><small>{selectedResult.metrics.maxDrawdownDurationWeeks} 周</small></article><article><span>95% 周度 VaR</span><strong>{fmt(lossPct(selectedResult.metrics.valueAtRisk95Pct))}%</strong><small>历史收益 5% 分位的下行损失</small></article><article><span>95% 周度 CVaR</span><strong>{fmt(lossPct(selectedResult.metrics.conditionalValueAtRisk95Pct))}%</strong><small>最差 5% 尾部平均损失</small></article><article><span>年化波动</span><strong>{fmt(selectedResult.metrics.annualizedVolatilityPct)}%</strong><small>周度波动 × √52</small></article></section>}{selectedResult.series.length>0&&<DrawdownAnalysis result={selectedResult}/>}<Checks checks={assessment.checks.filter(c => c.id === `drawdown-${input.currency}` || c.id === `var95-${input.currency}`)}/>{selectedResult.warnings.map((w,i) => <p className="method-note" key={i}>{w}</p>)}{selectedResult.missingAssets.map(p => <p key={`${p.market}:${p.symbol}`}>{p.market}:{p.symbol}：{p.reason}</p>)}</section>}
    </div>}
    {view === 'liquidity' && <LiquidityEvidence dashboard={dashboard} now={now}/>}
    {view === 'stress' && <StressAnalysis dashboard={dashboard} now={now} shocks={shocks} onShocks={onShocks}/>}
    {view === 'alerts' && <section className="folio-panel"><h2>预警与限额核验</h2><Checks checks={assessment.checks} dashboard={dashboard} onRefresh={onRefresh}/><p className="method-note">触发、数据缺口、过期均可登记处置；豁免不改写规则判断，也不会执行交易。</p></section>}
    {view === 'actions' && <section className="folio-panel"><div className="risk-section-heading"><strong>风险处置台账</strong><span>待处理 {dashboard.riskActions.filter(a=>a.status==='open').length} · 处理中 {dashboard.riskActions.filter(a=>a.status==='acknowledged').length} · 逾期 {dashboard.riskActions.filter(a=>!['resolved','waived'].includes(a.status)&&a.dueAt&&Date.parse(a.dueAt)<now).length}</span></div><label className="risk-register-controls">处置状态<select value={actionFilter} onChange={e=>setActionFilter(e.target.value)}><option value="all">全部</option><option value="open">待处理</option><option value="acknowledged">处理中</option><option value="overdue">已逾期</option><option value="resolved">已复核结案</option><option value="waived">已豁免</option></select></label>{dashboard.riskActions.filter(a=>actionFilter==='all'||(actionFilter==='overdue'?!['resolved','waived'].includes(a.status)&&a.dueAt&&Date.parse(a.dueAt)<now:a.status===actionFilter)).map(action=><details className="risk-action-row" key={action.id}><summary><strong>{action.title}</strong><span>{action.owner||'未分配'}</span><span>{({open:'待处理',acknowledged:'处理中',resolved:'已复核结案',waived:'已豁免'})[action.status]}</span><span>期限 {date(action.dueAt)}</span></summary><RiskActionEditor key={action.updatedAt} action={action} identity={dashboard} onRefresh={onRefresh}/></details>)}{!dashboard.riskActions.length&&<p className="empty-copy">暂无处置记录；从“预警”页面登记风险或数据缺口。</p>}</section>}
    </>}
  </div>;
}
