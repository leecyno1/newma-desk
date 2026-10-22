import { useEffect, useRef, useState } from 'react';
import { flushSync } from 'react-dom';
import { getVibeDeskConfig, isVibeDeskEmbedded, publishVibeDeskContext, registerVibeDeskUiActionHandler } from '@/lib/vibedesk';
import type { ResearchAnalysis } from '@/lib/researchAnalysis';

// A report belongs to one immutable draft. Editing or selecting another draft
// immediately removes it from both the UI and the page context.
export function useResearchAnalysis<T>(options: {
  moduleId: string; draft: T; enabled: boolean; isBusy: () => boolean;
  actions: { id: string; label: string }[];
  calculate: (draft: T, actionId: string) => ResearchAnalysis;
  refresh?: { id: string; label: string; available: boolean; run: () => Promise<unknown> };
}) {
  const [snapshot, setSnapshot] = useState<{ draft: T; report: ResearchAnalysis } | null>(null);
  const current = useRef(options);
  current.current = options;
  const config = getVibeDeskConfig();
  const allowed = !isVibeDeskEmbedded || Boolean(config?.moduleId === options.moduleId && config.instanceId && config.permissions?.includes('storage.read'));
  const execute = (actionId: string, input: Record<string, unknown>, fromAgent = false) => {
    const active = current.current;
    const session = getVibeDeskConfig();
    if ((fromAgent || isVibeDeskEmbedded) && (!session?.instanceId || session.moduleId !== active.moduleId || !session.permissions?.includes('storage.read'))) {
      throw new Error('当前页面尚未获得读取授权');
    }
    if (!active.enabled || active.isBusy()) throw new Error('请先完成读取、保存或待确认操作，再核对当前底稿');
    if (Object.keys(input).length || !active.actions.some(action => action.id === actionId)) throw new Error('不支持此操作或输入；此分析仅使用当前底稿');
    const report = active.calculate(active.draft, actionId);
    flushSync(() => setSnapshot({ draft: active.draft, report }));
    return report;
  };
  const executeRef = useRef(execute);
  executeRef.current = execute;
  useEffect(() => registerVibeDeskUiActionHandler(async (id, input) => {
    const active = current.current;
    let result: unknown;
    if (active.refresh?.id === id) {
      const session = getVibeDeskConfig();
      if (!session?.instanceId || session.moduleId !== active.moduleId || !session.permissions?.includes('market.read')) throw new Error('当前页面尚未获得行情读取授权');
      if (Object.keys(input).length) throw new Error('不支持额外输入；刷新仅使用当前底稿的证券与口径');
      if (!active.refresh.available || active.isBusy()) throw new Error('请先完成读取、保存或待确认操作，再刷新当前底稿');
      result = await active.refresh.run();
    } else {
      result = executeRef.current(id, input, true);
    }
    await publishVibeDeskContext();
    return result;
  }), []);
  const report = allowed && snapshot?.draft === options.draft ? snapshot.report : null;
  return { report, stale: Boolean(snapshot && !report),
    refreshAction: options.refresh ? { id: options.refresh.id, label: options.refresh.label, available: options.refresh.available,
      inputSchema: { type: 'object', additionalProperties: false } } : undefined,
    actions: options.actions.map(action => ({ ...action, available: options.enabled && allowed, inputSchema: { type: 'object', additionalProperties: false } })),
    run: (id: string) => executeRef.current(id, {}),
  };
}

export function ResearchAnalysisPanel({ analysis }: { analysis: ReturnType<typeof useResearchAnalysis> }) {
  const [error, setError] = useState('');
  const report = analysis.report;
  return <section aria-label="当前底稿核对" data-vibe-block="research-analysis" className="mb-4 rounded-lg border border-border bg-card/70 p-4 text-sm">
    <div className="flex flex-wrap items-center gap-2">
      <h2 className="mr-2 font-semibold">当前底稿核对</h2>
      {analysis.actions.map(action => <button key={action.id} disabled={!action.available}
        className="rounded border border-border px-3 py-2 hover:border-primary/40 disabled:opacity-50"
        onClick={() => { setError(''); try { analysis.run(action.id); } catch (reason) { setError(reason instanceof Error ? reason.message : '核对失败'); } }}>{action.label}</button>)}
    </div>
    <p className="mt-2 text-xs text-muted-foreground">页面与 Agent 共用同一核对操作，仅分析当前已录入底稿，不自动取数、保存或确认。</p>
    {error && <p role="alert" className="mt-2 text-destructive">{error}</p>}
    {analysis.stale && <p role="status" className="mt-2 text-warning">底稿已变化，上次核对结果已失效，请重新核对。</p>}
    {report && <div className="mt-4" aria-live="polite">
      <h3 className="font-semibold">{report.title}</h3>
      <p className="my-2">{report.summary}</p>
      <p className="text-xs text-muted-foreground">{report.subject.market}:{report.subject.symbol || '未填证券'} · 基期 {report.subject.asOf || '未填'} · {report.subject.currency} · 核对时间 {report.generatedAt}</p>
      <div className="my-3 overflow-x-auto"><table className="w-full text-left text-xs">
        <thead><tr>{report.columns.map(column => <th key={column} className="whitespace-nowrap border-b border-border p-2">{column}</th>)}</tr></thead>
        <tbody>{report.rows.map((row, index) => <tr key={index}>{row.map((value, col) => <td key={col} className="border-b border-border/50 p-2">{value === null ? '—' : typeof value === 'number' ? value.toLocaleString('zh-CN', { maximumFractionDigits: 4 }) : value}</td>)}</tr>)}</tbody>
      </table></div>
      {report.warnings.map(warning => <p key={warning} className="mt-1 text-xs text-muted-foreground">{warning}</p>)}
    </div>}
  </section>;
}
