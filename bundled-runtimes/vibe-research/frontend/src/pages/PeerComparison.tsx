import { useEffect, useMemo, useRef, useState, useSyncExternalStore } from "react";
import { flushSync } from 'react-dom';
import {
  BarChart3,
  BookOpenCheck,
  Database,
  Layers3,
  Loader2,
  Plus,
  RefreshCw,
  Save,
  Scale,
  SearchCheck,
  Trash2,
} from "lucide-react";

import { Disclaimer } from "@/components/ui/Disclaimer";
import { GlassCard } from "@/components/ui/GlassCard";
import { PageHeader } from "@/components/ui/PageHeader";
import { ResearchAnalysisPanel, useResearchAnalysis } from '@/components/ResearchAnalysisPanel';
import { canRefreshResearchData, fetchPeerSnapshot } from '@/lib/researchData';
import { analyzePeerComparison, peerAnalysisActions, peerRequestSymbol, peerRowFromSnapshot, peerSecurityKey, reviewPeerComparison } from '@/lib/peerReview';
import {
  blankPeerComparisonCase,
  hydratePeerComparisonWorkspace,
  emptyPeerComparisonWorkspace,
  peerComparisonScope,
  PeerStorageError,
  persistPeerComparisonWorkspace,
  type PeerComparisonSession,
  type PeerComparisonCase,
  type PeerComparisonWorkspace,
  type PeerMember,
  type PeerQuestion,
  type PeerRole,
  type StrategicDimension,
} from "@/lib/peerComparison";
import { cn } from "@/lib/utils";
import {
  publishVibeDeskContext,
  registerVibeDeskContextProvider,
  subscribeVibeDeskEvent,
  subscribeVibeDeskConfig,
  type VibeDeskPageContext,
} from "@/lib/vibedesk";

const inputClass = "w-full rounded-lg border border-border bg-card/70 px-3 py-2 text-sm text-foreground outline-none transition focus:border-primary/60 focus:ring-2 focus:ring-primary/15";
const labelClass = "mb-1.5 block text-xs font-semibold text-muted-foreground";
const QUESTION_LABEL: Record<PeerQuestion, string> = {
  valuation: "估值差异",
  growth: "增长比较",
  quality: "盈利质量",
  efficiency: "经营效率",
  "competitive-positioning": "竞争定位",
};
const ROLE_LABEL: Record<PeerRole, string> = {
  target: "目标公司",
  direct: "直接同业",
  adjacent: "相邻对手",
  emerging: "新进入者",
};
const TRAJECTORY_LABEL = { improving: "改善", stable: "稳定", deteriorating: "恶化", unknown: "待判断" } as const;
const MOAT_LABEL = {
  "network-effects": "网络效应",
  "switching-costs": "转换成本",
  "scale-economies": "规模经济",
  "intangible-assets": "无形资产",
  other: "其他",
} as const;

function copyCase(value: PeerComparisonCase) {
  return structuredClone(value);
}

function createId(prefix: string) {
  const suffix = globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(16).slice(2)}`;
  return `${prefix}:${suffix}`;
}

function currencyForMarket(market: string) {
  return market.toUpperCase() === "US" ? "USD" : market.toUpperCase() === "HK" ? "HKD" : "CNY";
}

function comparisonContext(workspace: PeerComparisonWorkspace, draft: PeerComparisonCase, loading: boolean): VibeDeskPageContext {
  const review = reviewPeerComparison(draft);
  const target = draft.members.find(member => member.included && member.role === 'target')?.security;
  return {
    view: { id: "peer-comparison", title: "同业比较" },
    visibleBlocks: [
      { id: "peer-set", type: "peer-set", title: "可比公司集合" },
      { id: "comparability-audit", type: "comparability-audit", title: "可比性审计" },
      { id: "operating-comparison", type: "peer-metrics", title: "经营与估值指标" },
      { id: "peer-statistics", type: "peer-statistics", title: "统计分布" },
      { id: "competitive-synthesis", type: "competitive-synthesis", title: "竞争优势与脆弱点" },
    ],
    selection: {
      symbol: target?.symbol || '',
      market: target?.market || '',
      name: target?.name || '',
      currency: target?.currency || '',
      caseId: draft.id,
      peerSymbols: draft.members.filter((item) => item.included).map((item) => item.security.symbol),
    },
    filters: {
      researchQuestion: draft.researchQuestion,
      period: draft.period,
    },
    data: {
      // Research reference date is user input, not a market-data timestamp.
      asOf: undefined,
      source: workspace.schemaVersion,
      freshness: "unknown",
      summary: {
        members: draft.members,
        metrics: draft.metrics,
        rows: review.rows,
        statistics: review.statistics,
        metricReview: review.metrics,
        comparabilityIssues: review.issues,
        interpretation: review.policy,
        researchReferenceDate: draft.period.asOf,
        strategicDimensions: draft.strategicDimensions,
        synthesis: draft.synthesis,
        sources: draft.sourceMaterials,
        gaps: draft.gaps,
      },
    },
    actions: [
      { id: "peer.refresh", label: "刷新同业证据与统计", available: false },
      { id: "peer.audit-comparability", label: "核对同业样本与口径", available: false },
      { id: "peer.explain-premium", label: "解释估值差异（尚未接通）", available: false },
      { id: "peer.update-thesis", label: "映射到投资逻辑（尚未接通）", available: false },
    ],
    tasks: loading ? [{ id: `peer-refresh:${draft.id}`, status: "running", actionId: "peer.refresh" }] : [],
  };
}

function formatMetric(value: number | null | undefined, unit: string) {
  if (value === null || value === undefined || !Number.isFinite(value)) return "—";
  if (unit === "%") return `${value.toFixed(1)}%`;
  if (unit === "x") return `${value.toFixed(1)}x`;
  return value.toFixed(1);
}

function blankMember(role: PeerRole = "direct"): PeerMember {
  return {
    security: { market: "CN", symbol: "", name: "", currency: "CNY" },
    role,
    included: true,
    rationale: "待说明业务模式、区域、客户或产品的可比性",
    exceptions: [],
  };
}

export function PeerComparison() {
  const scope = useSyncExternalStore(subscribeVibeDeskConfig, peerComparisonScope);
  return <PeerComparisonContent key={scope} />;
}

function PeerActionDialog({ message, confirm, cancel }: { message: string; confirm: () => void; cancel: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null);
  useEffect(() => { dialog.current?.showModal(); return () => dialog.current?.close(); }, []);
  return <dialog ref={dialog} aria-label="同业操作确认" onCancel={event => { event.preventDefault(); cancel(); }} className="max-w-md rounded-lg border border-border bg-card p-5 text-foreground backdrop:bg-black/50">
    <p>{message}</p><div className="mt-4 flex justify-end gap-3"><button autoFocus onClick={cancel}>取消操作</button><button onClick={confirm}>确认继续</button></div>
  </dialog>;
}

function PeerComparisonContent() {
  const initial = useMemo(emptyPeerComparisonWorkspace, []);
  const [workspace, setWorkspace] = useState(initial);
  const [selectedId, setSelectedId] = useState(initial.cases[0]?.id || "__new__");
  const [draft, setDraft] = useState(() => initial.cases[0] ? copyCase(initial.cases[0]) : blankPeerComparisonCase());
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState("");
  const [reading, setReading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [hydrated, setHydrated] = useState(false);
  const [storageError, setStorageError] = useState('');
  const [pending, setPending] = useState<{ message: string; run: () => void | Promise<void> } | null>(null);
  const session = useRef<PeerComparisonSession | null>(null);
  const operation = useRef<AbortController | null>(null);
  const busyRef = useRef(false);
  const alive = useRef(true);
  const baseline = useRef(JSON.stringify(draft));
  const draftRef = useRef(draft); draftRef.current = draft;
  const dirty = JSON.stringify(draft) !== baseline.current;
  const busy = reading || saving || loading;
  const review = useMemo(() => reviewPeerComparison(draft), [draft]);

  const adoptDraft = (value?: PeerComparisonCase) => {
    const next = value ? copyCase(value) : blankPeerComparisonCase();
    baseline.current = JSON.stringify(next); setDraft(next); setSelectedId(value?.id || '__new__');
  };
  const readWorkspace = async () => {
    if (busyRef.current) return;
    busyRef.current = true;
    const controller = new AbortController(); operation.current = controller;
    setReading(true); setHydrated(false); setStorageError('');
    try {
      const loaded = await hydratePeerComparisonWorkspace(controller.signal);
      if (!alive.current || controller.signal.aborted) return;
      session.current = loaded; setWorkspace(loaded.workspace);
      adoptDraft(loaded.workspace.cases.find(item => item.id === selectedId) || loaded.workspace.cases[0]);
      setHydrated(true); setMessage(loaded.mode === 'local' ? '仅使用本机浏览器档案，未同步到 Desk' : '已读取当前 Desk 工作区');
    } catch (error) {
      if (alive.current && !controller.signal.aborted) setStorageError(error instanceof PeerStorageError ? error.message : '档案读取失败，当前草稿保留。');
    } finally {
      if (alive.current && !controller.signal.aborted) { busyRef.current = false; setReading(false); }
    }
  };
  useEffect(() => {
    alive.current = true; busyRef.current = false; void readWorkspace();
    return () => { alive.current = false; operation.current?.abort(); };
  }, []);

  const refreshAvailable = hydrated && !busy && !pending && canRefreshResearchData('peer-comparison');
  const analysis = useResearchAnalysis({ moduleId: 'peer-comparison', draft, enabled: hydrated && !busy && !pending,
    isBusy: () => busyRef.current, actions: peerAnalysisActions, calculate: analyzePeerComparison,
    refresh: { id: 'peer.refresh', label: '刷新当前同业集合（不自动保存）', available: refreshAvailable, run: () => refresh() },
  });

  const contextRef = useRef<VibeDeskPageContext>(comparisonContext(workspace, draft, loading));
  contextRef.current = comparisonContext(workspace, draft, loading);
  contextRef.current.filters = { ...contextRef.current.filters, unsavedChanges: dirty };
  contextRef.current.actions = contextRef.current.actions?.map(action => analysis.refreshAction?.id === action.id ? analysis.refreshAction : analysis.actions.find(item => item.id === action.id) || action);
  contextRef.current.data.summary = { ...contextRef.current.data.summary, currentAnalysis: analysis.report,
    storage: { mode: session.current?.mode || 'unavailable', revision: session.current?.revision ?? null, status: reading ? 'reading' : saving ? 'saving' : storageError ? 'error' : 'ready', error: storageError || undefined } };
  useEffect(() => registerVibeDeskContextProvider(() => contextRef.current), []);
  useEffect(() => {
    const unsubscribe = subscribeVibeDeskEvent((event) => {
      if (event.event !== "security.selected") return;
      const symbol = typeof event.payload.symbol === "string" ? event.payload.symbol.slice(0, 40).toUpperCase() : "";
      if (!symbol) return;
      if (busyRef.current || JSON.stringify(draftRef.current) !== baseline.current || draftRef.current.rows.length || session.current?.workspace.cases.some(item => item.id === draftRef.current.id)) {
        setMessage('当前比较已有输入，未替换目标证券；研究其他公司请新建比较。'); return;
      }
      const market = typeof event.payload.market === "string" ? event.payload.market.slice(0, 20).toUpperCase() : "CN";
      const name = typeof event.payload.name === "string" ? event.payload.name.slice(0, 120) : "";
      setDraft((current) => {
        const target = { market, symbol, name, currency: currencyForMarket(market) };
        return {
          ...current,
          target,
          members: current.members.map((member, index) => index === 0 || member.role === "target"
            ? { ...member, security: target, role: "target" }
            : member),
        };
      });
    });
    return () => { unsubscribe(); };
  }, []);
  useEffect(() => { void publishVibeDeskContext(); }, [draft, loading, workspace, reading, saving, storageError, hydrated, pending, analysis.report]);

  const commit = async (next: PeerComparisonWorkspace) => {
    if (!session.current || !hydrated || busyRef.current) return null;
    busyRef.current = true;
    const controller = new AbortController(); operation.current = controller;
    setSaving(true); setMessage('');
    try {
      const result = await persistPeerComparisonWorkspace(next, session.current, controller.signal);
      if (!alive.current || controller.signal.aborted) return null;
      session.current = result; setWorkspace(result.workspace); return result;
    } catch (error) {
      if (alive.current && !controller.signal.aborted) { setHydrated(false); setStorageError(error instanceof PeerStorageError ? error.message : '保存未确认，请导出草稿并重新读取核对。'); }
      return null;
    } finally { if (alive.current && !controller.signal.aborted) { busyRef.current = false; setSaving(false); } }
  };

  const requestAction = (message: string, run: () => void | Promise<void>, confirmation = dirty) => {
    if (busyRef.current || pending) return;
    if (confirmation) setPending({ message, run }); else void run();
  };

  const startNew = () => {
    requestAction('新建会放弃未保存修改，请先保存或导出。确定新建吗？', () => { adoptDraft(); setMessage(''); });
  };

  const choose = (item: PeerComparisonCase) => {
    requestAction('切换会放弃未保存修改，请先保存或导出。确定切换吗？', () => { adoptDraft(item); setMessage(''); });
  };

  const updateMember = (index: number, update: Partial<PeerMember>) => {
    setDraft((current) => ({
      ...current,
      members: current.members.map((member, memberIndex) => memberIndex === index ? { ...member, ...update } : member),
    }));
  };

  const updateMemberSecurity = (index: number, field: keyof PeerMember["security"], value: string) => {
    setDraft((current) => {
      const members = current.members.map((member, memberIndex) => {
        if (memberIndex !== index) return member;
        const security = {
          ...member.security,
          [field]: value,
          ...(field === "market" ? { currency: currencyForMarket(value) } : {}),
        };
        return { ...member, security };
      });
      const targetMember = members.find((item) => item.role === "target") || members[0];
      return { ...current, members, ...(targetMember ? { target: targetMember.security } : {}) };
    });
  };

  const validate = () => {
    if (!draft.name.trim()) return "请填写同业比较名称";
    const included = draft.members.filter((item) => item.included);
    if (included.length < 2) return "至少需要两家纳入比较的公司";
    if (included.some((item) => !item.security.symbol.trim() || !item.security.name.trim())) return "每家纳入比较的公司都需要证券代码和名称";
    if (included.some((item) => !item.rationale.trim())) return "请为每家同业说明可比性理由";
    if (included.filter((item) => item.role === "target").length !== 1) return "同业集合必须且只能有一家目标公司";
    if (new Set(included.map(member => peerSecurityKey(member.security))).size !== included.length) return '同一证券不能重复纳入，请删除重复公司';
    if (draft.strategicDimensions.some((item) => !item.label.trim() || !item.targetAssessment.trim() || !item.peerObservation.trim())) return "竞争维度需要名称、目标公司判断和同业观察";
    return "";
  };

  const save = async () => {
    if (busyRef.current || pending || !hydrated || !session.current?.writable) return;
    const error = validate();
    if (error) {
      setMessage(error);
      return;
    }
    const timestamp = new Date().toISOString();
    const targetMember = draft.members.find((item) => item.included && item.role === "target")!;
    const saved: PeerComparisonCase = {
      ...draft,
      name: draft.name.trim(),
      target: targetMember.security,
      members: draft.members.map((member) => ({
        ...member,
        security: {
          market: member.security.market.trim().toUpperCase(),
          symbol: member.security.symbol.trim().toUpperCase(),
          name: member.security.name.trim(),
          currency: member.security.currency.trim().toUpperCase() || currencyForMarket(member.security.market),
        },
        rationale: member.rationale.trim(),
        exceptions: member.exceptions.map((item) => item.trim()).filter(Boolean).slice(0, 10),
      })),
      statistics: review.statistics,
      gaps: draft.gaps.map((item) => item.trim()).filter(Boolean).slice(0, 30),
      updatedAt: timestamp,
    };
    const exists = workspace.cases.some((item) => item.id === saved.id);
    const cases = exists ? workspace.cases.map((item) => item.id === saved.id ? saved : item) : [saved, ...workspace.cases];
    const result = await commit({ ...workspace, updatedAt: timestamp, cases });
    if (!result) return;
    adoptDraft(result.workspace.cases.find(item => item.id === saved.id));
    setMessage(result.mode === 'local' ? '已保存到本机浏览器，未同步到 Desk' : `已保存到 Desk 工作区 · 修订 ${result.revision}`);
  };

  const remove = () => {
    if (selectedId === "__new__") {
      startNew();
      return;
    }
    requestAction(`删除“${draft.name}”同业比较？未保存修改也会丢失，请先导出需要保留的内容。`, async () => {
      const next = { ...workspace, updatedAt: new Date().toISOString(), cases: workspace.cases.filter(item => item.id !== selectedId) };
      const result = await commit(next);
      if (result) { adoptDraft(result.workspace.cases[0]); setMessage(result.mode === 'local' ? '已从本机档案删除' : '已从当前 Desk 工作区删除'); }
    }, true);
  };

  const refresh = async () => {
    if (busyRef.current || !refreshAvailable) throw new Error('请先完成档案读取或待确认操作，再刷新比较');
    const error = validate();
    if (error) throw new Error(error);
    const members = draft.members.filter((item) => item.included);
    const symbols = members.map(peerRequestSymbol);
    const controller = new AbortController(); operation.current = controller; busyRef.current = true;
    setLoading(true); setMessage('');
    try {
      const results = await Promise.allSettled(members.map(async (member, index) => peerRowFromSnapshot(member, await fetchPeerSnapshot(symbols[index]!, controller.signal))));
      if (!alive.current || controller.signal.aborted) throw new Error('当前读取已停止，旧结果未采用');
      const rows = results.flatMap(result => result.status === 'fulfilled' ? [result.value] : []);
      const gaps = results.flatMap((result, index) => result.status === 'rejected' ? [`${symbols[index]}：${result.reason instanceof Error ? result.reason.message : '读取失败'}`] : []);
      if (!rows.length) throw new Error(`所有公司读取失败，旧比较保留。${gaps.join('；')}`);
      const periods = new Set(rows.map(row => row.period));
      const next: PeerComparisonCase = { ...draft, target: members.find(member => member.role === 'target')!.security, rows,
        sourceMaterials: rows.map(row => ({ id: row.sourceIds[0]!, label: `${row.security.name} 供应商证据（未核验原文）`, symbol: row.security.symbol,
          asOf: /^\d{4}-\d{2}-\d{2}/.test(row.period) ? row.period : '', status: 'available' })),
        period: { ...draft.period, fiscalAlignment: periods.size > 1 ? 'mixed' : 'unknown' },
        gaps: [...new Set([...draft.gaps, ...gaps, '相同报告期末不代表财年、单季/累计或会计口径已核验；未提供历史时点快照。'])].slice(0, 30),
        updatedAt: new Date().toISOString(),
      };
      next.statistics = reviewPeerComparison(next).statistics;
      flushSync(() => { setDraft(next); setMessage(`已读取 ${rows.length}/${members.length} 家公司；${gaps.length ? '部分失败，' : ''}来源未核验，未自动保存。`); });
      return { status: gaps.length ? 'partial' : 'draft-updated', received: rows.length, requested: members.length, errors: gaps, saved: false };
    } catch (error) {
      if (alive.current && !controller.signal.aborted) setMessage(error instanceof Error ? error.message : '刷新失败，旧比较保留');
      throw error;
    } finally {
      if (alive.current && !controller.signal.aborted) flushSync(() => { setLoading(false); busyRef.current = false; });
    }
  };

  const addDimension = () => {
    const row: StrategicDimension = {
      id: createId("dimension"),
      label: "",
      moat: "other",
      targetAssessment: "",
      peerObservation: "",
      trajectory: "unknown",
      sourceIds: [],
    };
    setDraft((current) => ({ ...current, strategicDimensions: [...current.strategicDimensions, row].slice(0, 10) }));
  };

  const includedCount = draft.members.filter((item) => item.included).length;
  const targetRow = review.target;

  return (
    <div>
      <fieldset disabled={busy || Boolean(pending)} className="min-w-0 border-0 p-0">
      <PageHeader
        title="同业比较"
        subtitle="先审计可比性，再用统一报告期、指标口径、统计分布与 Evidence Ledger 解释经营质量和估值差异。"
        actions={(
          <>
            <button onClick={startNew} className="inline-flex items-center gap-1.5 rounded-lg border border-border bg-card/70 px-3 py-2 text-sm hover:border-primary/40"><Plus className="h-4 w-4" /> 新建</button>
            <button onClick={() => void refresh().catch(error => setMessage(error instanceof Error ? error.message : '刷新失败，旧比较保留'))} disabled={!refreshAvailable} className="inline-flex items-center gap-1.5 rounded-lg border border-border bg-card/70 px-3 py-2 text-sm hover:border-primary/40 disabled:opacity-50">{loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />} 刷新比较</button>
            <button onClick={() => void save()} disabled={!hydrated || !session.current?.writable} className="inline-flex items-center gap-1.5 rounded-lg bg-primary px-3 py-2 text-sm font-semibold text-primary-foreground hover:opacity-90 disabled:opacity-50"><Save className="h-4 w-4" /> 保存</button>
          </>
        )}
      />

      <div aria-label="同业档案存储状态" className="mb-4 flex flex-wrap items-center gap-3 text-xs text-muted-foreground">
        <span>{reading ? '正在读取档案…' : saving ? '正在保存…' : session.current?.mode === 'desk' ? `Desk 工作区 · 修订 ${session.current.revision}` : session.current?.mode === 'local' ? '本机浏览器 · 未同步 Desk' : '存储未连接'}</span>
        <button className="rounded border border-border px-3 py-2" onClick={() => requestAction('重新读取会放弃未保存修改，请先导出草稿。确定继续吗？', readWorkspace)}>重新读取档案</button>
        <a download="peer-comparison-draft.json" href={`data:application/json;charset=utf-8,${encodeURIComponent(JSON.stringify({ schemaVersion: 'newma-desk.peer-draft-export.v1', exportedAt: new Date().toISOString(), draft }, null, 2))}`} className="rounded border border-border px-3 py-2">导出当前草稿</a>
      </div>
      {storageError && <p role="alert" className="mb-4 text-sm text-destructive">{storageError}</p>}
      {message && <p role="status" className="mb-4 rounded-lg border border-border px-3 py-2 text-sm">{message}</p>}
      <ResearchAnalysisPanel analysis={analysis} />

      <div className="mb-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {[
          { label: "比较档案", value: workspace.cases.length, icon: BookOpenCheck },
          { label: "纳入公司", value: includedCount, icon: Layers3 },
          { label: "标准化指标", value: draft.metrics.length, icon: BarChart3 },
          { label: "来源 / 缺口", value: `${draft.sourceMaterials.length}/${draft.gaps.length}`, icon: SearchCheck },
        ].map(({ label, value, icon: Icon }) => <GlassCard key={label} className="flex items-center justify-between p-4"><div><div className="text-xs text-muted-foreground">{label}</div><div className="mt-1 text-2xl font-bold">{value}</div></div><Icon className="h-5 w-5 text-primary" /></GlassCard>)}
      </div>

      <div className="grid items-start gap-4 xl:grid-cols-[240px_minmax(0,1fr)]">
        <GlassCard className="p-3 xl:sticky xl:top-3">
          <div className="mb-2 flex items-center justify-between px-2"><span className="text-xs font-semibold uppercase tracking-[0.14em] text-muted-foreground">比较档案</span><button onClick={startNew} className="rounded-md p-1 text-muted-foreground hover:bg-muted"><Plus className="h-4 w-4" /></button></div>
          <div className="space-y-1.5">{workspace.cases.length === 0 && <div className="rounded-lg border border-dashed border-border px-3 py-8 text-center text-xs text-muted-foreground">尚无同业比较。先建立目标公司和可比公司集合。</div>}{workspace.cases.map((item) => <button key={item.id} onClick={() => choose(item)} className={cn("w-full rounded-lg border px-3 py-2.5 text-left", selectedId === item.id ? "border-primary/45 bg-primary/10" : "border-transparent hover:border-border hover:bg-muted/45")}><div className="truncate text-sm font-semibold">{item.name}</div><div className="mt-1 text-[11px] text-muted-foreground">{item.target.market}:{item.target.symbol} · {item.members.filter((row) => row.included).length} 家</div></button>)}</div>
        </GlassCard>

        <div className="min-w-0 space-y-4">
          <GlassCard glow>
            <div className="mb-4 flex flex-wrap items-center justify-between gap-3"><div><div className="text-xs font-semibold uppercase tracking-[0.14em] text-primary">Peer scope</div><h2 className="mt-1 text-lg font-bold">比较范围与关键问题</h2></div><div className="flex items-center gap-2">{dirty && <span className="text-xs text-warning">有未保存修改</span>}<button onClick={remove} className="rounded-lg border border-border p-2 text-muted-foreground hover:border-destructive/40 hover:text-destructive"><Trash2 className="h-4 w-4" /></button></div></div>
            <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
              <label className="xl:col-span-2"><span className={labelClass}>比较名称</span><input className={inputClass} value={draft.name} onChange={(event) => setDraft({ ...draft, name: event.target.value })} placeholder="例如：光模块核心公司比较" /></label>
              <label><span className={labelClass}>核心问题</span><select className={inputClass} value={draft.researchQuestion} onChange={(event) => setDraft({ ...draft, researchQuestion: event.target.value as PeerQuestion })}>{Object.entries(QUESTION_LABEL).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
              <label><span className={labelClass}>研究基准日（非历史查询）</span><input className={inputClass} value={draft.period.asOf} onChange={(event) => setDraft({ ...draft, period: { ...draft.period, asOf: event.target.value } })} placeholder="YYYY-MM-DD" /></label>
            </div>
            <div className="mt-3 grid gap-3 md:grid-cols-3">
              <label><span className={labelClass}>期间口径</span><input className={inputClass} value={draft.period.label} onChange={(event) => setDraft({ ...draft, period: { ...draft.period, label: event.target.value } })} /></label>
              <label><span className={labelClass}>财年对齐</span><select className={inputClass} value={draft.period.fiscalAlignment} onChange={(event) => setDraft({ ...draft, period: { ...draft.period, fiscalAlignment: event.target.value as PeerComparisonCase["period"]["fiscalAlignment"] } })}><option value="unknown">待核验</option><option value="aligned">已对齐</option><option value="mixed">存在错位</option></select></label>
              <label><span className={labelClass}>金额单位</span><input className={inputClass} value={draft.period.unitScale} onChange={(event) => setDraft({ ...draft, period: { ...draft.period, unitScale: event.target.value } })} /></label>
            </div>
          </GlassCard>

          <GlassCard>
            <div className="mb-4 flex items-center justify-between gap-3"><div><div className="text-xs font-semibold uppercase tracking-[0.14em] text-primary">Comparability first</div><h2 className="mt-1 text-lg font-bold">可比公司集合与口径例外</h2></div><button disabled={draft.members.length >= 8} onClick={() => setDraft({ ...draft, members: [...draft.members, blankMember()].slice(0, 8) })} className="inline-flex items-center gap-1 rounded-lg border border-border px-2.5 py-1.5 text-xs disabled:opacity-40"><Plus className="h-3.5 w-3.5" /> 添加公司</button></div>
            <div className="space-y-3">{draft.members.map((member, index) => <div key={`${member.role}-${index}`} className={cn("rounded-xl border p-3", member.role === "target" ? "border-primary/35 bg-primary/7" : "border-border bg-muted/20")}>
              <div className="grid gap-2 md:grid-cols-[78px_120px_1fr_100px_120px_auto]">
                <input aria-label={`公司${index + 1}市场`} className={inputClass} value={member.security.market} onChange={(event) => updateMemberSecurity(index, "market", event.target.value)} placeholder="CN" />
                <input aria-label={`公司${index + 1}代码`} className={inputClass} value={member.security.symbol} onChange={(event) => updateMemberSecurity(index, "symbol", event.target.value)} placeholder="证券代码" />
                <input aria-label={`公司${index + 1}名称`} className={inputClass} value={member.security.name} onChange={(event) => updateMemberSecurity(index, "name", event.target.value)} placeholder="公司名称" />
                <input aria-label={`公司${index + 1}币种`} className={inputClass} value={member.security.currency} onChange={(event) => updateMemberSecurity(index, "currency", event.target.value)} placeholder="CNY" />
                <select aria-label={`公司${index + 1}角色`} className={inputClass} value={member.role} onChange={(event) => {
                  const role = event.target.value as PeerRole;
                  setDraft((current) => ({ ...current, members: current.members.map((item, itemIndex) => ({ ...item, role: itemIndex === index ? role : role === "target" && item.role === "target" ? "direct" : item.role })) }));
                }}>{Object.entries(ROLE_LABEL).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select>
                <div className="flex items-center gap-2"><label className="flex items-center gap-1 text-xs text-muted-foreground"><input aria-label={`纳入公司${index + 1}`} type="checkbox" checked={member.included} onChange={(event) => updateMember(index, { included: event.target.checked })} /> 纳入</label><button aria-label={`移除公司${index + 1}`} disabled={draft.members.length <= 2} onClick={() => setDraft({ ...draft, members: draft.members.filter((_, itemIndex) => itemIndex !== index) })} className="text-muted-foreground hover:text-destructive disabled:opacity-30"><Trash2 className="h-4 w-4" /></button></div>
              </div>
              <div className="mt-2 grid gap-2 md:grid-cols-2"><input className={inputClass} value={member.rationale} onChange={(event) => updateMember(index, { rationale: event.target.value })} placeholder="为什么可比：业务模式、客户、产品、区域或规模" /><input className={inputClass} value={member.exceptions.join("；")} onChange={(event) => updateMember(index, { exceptions: event.target.value.split(/[；;]/).slice(0, 10) })} placeholder="口径例外：财年、币种、并购、业务结构等" /></div>
            </div>)}</div>
          </GlassCard>

          <GlassCard>
            <div className="mb-4 flex flex-wrap items-center justify-between gap-3"><div><div className="text-xs font-semibold uppercase tracking-[0.14em] text-primary">Operating & valuation</div><h2 className="mt-1 text-lg font-bold">经营质量与估值指标</h2></div><div className="text-xs text-muted-foreground">缺失值显示为 N/A，不用估算值静默填补</div></div>
            <div className="overflow-x-auto"><table aria-label="当前纳入公司指标" className="w-full min-w-[980px] text-left text-xs"><thead className="text-muted-foreground"><tr className="border-b border-border"><th className="px-2 py-2">公司</th><th className="px-2 py-2">财务期末</th><th className="px-2 py-2 text-right">有值指标覆盖</th>{draft.metrics.map((metric) => <th key={metric.id} className="px-2 py-2 text-right">{metric.label}<div className="font-normal opacity-70">{metric.unit}</div></th>)}</tr></thead><tbody>{review.rows.map((row) => <tr key={peerSecurityKey(row.security)} className={cn("border-b border-border/60", row.isTarget && "bg-primary/7")}><td className="px-2 py-2"><div className="font-semibold">{row.security.name}{row.isTarget ? " · 目标" : ""}</div><div className="text-[10px] text-muted-foreground">{row.security.market}:{row.security.symbol}</div></td><td className="px-2 py-2 text-muted-foreground">{row.period}</td><td className="px-2 py-2 text-right">{(draft.metrics.filter(metric => typeof row.values[metric.id] === 'number').length / Math.max(draft.metrics.length, 1) * 100).toFixed(0)}%</td>{draft.metrics.map((metric) => <td key={metric.id} className="px-2 py-2 text-right font-medium"><div>{formatMetric(row.values[metric.id], metric.unit)}</div><div className="mt-1 text-[10px] font-normal text-muted-foreground">{row.metricEvidence?.[metric.id]?.asOf?.slice(0, 10) || '日期待核对'}</div></td>)}</tr>)}{review.rows.length === 0 && <tr><td colSpan={draft.metrics.length + 3} className="px-3 py-10 text-center text-muted-foreground">完善可比公司集合后点击“刷新比较”；旧证券或已排除公司不会混入当前集合。</td></tr>}</tbody></table></div>
          </GlassCard>

          {review.rows.length > 0 && <details className="rounded-lg border border-border bg-card p-4 text-xs">
            <summary className="cursor-pointer font-semibold">逐指标来源、日期与定义（供应商证据，未核验原文）</summary>
            <div className="mt-3 overflow-x-auto"><table aria-label="逐指标来源" className="w-full min-w-[740px] text-left"><thead><tr>{['公司', '指标', '来源', '来源日期', '原始单位', '定义 / 备注'].map(label => <th key={label} className="px-2 py-2">{label}</th>)}</tr></thead><tbody>
              {review.rows.flatMap(row => draft.metrics.map(metric => {
                const evidence = row.metricEvidence?.[metric.id];
                return <tr key={`${peerSecurityKey(row.security)}:${metric.id}`} className="border-t border-border"><td className="px-2 py-2">{row.security.name}</td><td className="px-2 py-2">{metric.label}</td><td className="px-2 py-2">{evidence?.source || '来源待核对'}</td><td className="px-2 py-2">{evidence?.asOf || '日期待核对'}</td><td className="px-2 py-2">{evidence?.unit || '单位待核对'}</td><td className="max-w-80 px-2 py-2">{evidence?.id || '定义待核对'}{evidence?.note && <div className="mt-1 text-muted-foreground">{evidence.note}</div>}</td></tr>;
              }))}
            </tbody></table></div>
          </details>}

          {draft.rows.length > 0 && <GlassCard>
            <div className="mb-4 flex items-center gap-2"><Scale className="h-4 w-4 text-primary" /><div><h2 className="font-bold">统计分布与目标公司位置</h2><p className="mt-0.5 text-xs text-muted-foreground">{review.policy}</p></div></div>
            {review.issues.map(issue => <p key={issue} className="mb-2 text-xs text-warning">{issue}</p>)}
            <div className="overflow-x-auto"><table aria-label="有效同业统计" className="w-full min-w-[980px] text-xs"><thead className="text-muted-foreground"><tr className="border-b border-border">{['指标', '目标公司', '有效同业', '最大', '75分位', '中位数', '25分位', '最小', '目标－中位数', '限制与排除'].map(label => <th key={label} className="px-2 py-2 text-right">{label}</th>)}</tr></thead><tbody>{review.metrics.map(metric => <tr key={metric.id} className="border-b border-border/60"><td className="px-2 py-2 font-medium">{metric.label}</td><td className="px-2 py-2 text-right">{formatMetric(targetRow?.values[metric.id], metric.unit)}</td><td className="px-2 py-2 text-right">{metric.sampleSize}/{metric.requestedPeers}</td>{(['max', 'q75', 'median', 'q25', 'min'] as const).map(key => <td key={key} className="px-2 py-2 text-right">{formatMetric(metric.statistics[key], metric.unit)}</td>)}<td className="px-2 py-2 text-right">{metric.difference === null ? '—' : `${metric.difference.toFixed(1)} ${metric.differenceUnit}`}</td><td className="max-w-64 px-2 py-2 text-muted-foreground">{metric.note}{metric.exclusions.length > 0 && <details><summary>排除说明（{metric.exclusions.length}）</summary>{metric.exclusions.map(reason => <p key={reason}>{reason}</p>)}</details>}</td></tr>)}</tbody></table></div>
          </GlassCard>}

          <GlassCard>
            <div className="mb-4 flex items-center justify-between gap-3"><div><div className="text-xs font-semibold uppercase tracking-[0.14em] text-primary">Competitive synthesis</div><h2 className="mt-1 text-lg font-bold">竞争优势、脆弱点与轨迹</h2></div><button onClick={addDimension} className="inline-flex items-center gap-1 rounded-lg border border-border px-2.5 py-1.5 text-xs"><Plus className="h-3.5 w-3.5" /> 添加维度</button></div>
            <div className="space-y-3">{draft.strategicDimensions.map((dimension) => <div key={dimension.id} className="rounded-xl border border-border bg-muted/20 p-3"><div className="grid gap-2 md:grid-cols-[1fr_150px_120px_auto]"><input className={inputClass} value={dimension.label} onChange={(event) => setDraft({ ...draft, strategicDimensions: draft.strategicDimensions.map((item) => item.id === dimension.id ? { ...item, label: event.target.value } : item) })} placeholder="竞争维度" /><select className={inputClass} value={dimension.moat} onChange={(event) => setDraft({ ...draft, strategicDimensions: draft.strategicDimensions.map((item) => item.id === dimension.id ? { ...item, moat: event.target.value as StrategicDimension["moat"] } : item) })}>{Object.entries(MOAT_LABEL).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select><select className={inputClass} value={dimension.trajectory} onChange={(event) => setDraft({ ...draft, strategicDimensions: draft.strategicDimensions.map((item) => item.id === dimension.id ? { ...item, trajectory: event.target.value as StrategicDimension["trajectory"] } : item) })}>{Object.entries(TRAJECTORY_LABEL).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select><button onClick={() => setDraft({ ...draft, strategicDimensions: draft.strategicDimensions.filter((item) => item.id !== dimension.id) })} className="text-muted-foreground hover:text-destructive"><Trash2 className="h-4 w-4" /></button></div><div className="mt-2 grid gap-2 md:grid-cols-2"><textarea className={`${inputClass} min-h-20 resize-y`} value={dimension.targetAssessment} onChange={(event) => setDraft({ ...draft, strategicDimensions: draft.strategicDimensions.map((item) => item.id === dimension.id ? { ...item, targetAssessment: event.target.value } : item) })} placeholder="目标公司的现状、证据和难以复制之处" /><textarea className={`${inputClass} min-h-20 resize-y`} value={dimension.peerObservation} onChange={(event) => setDraft({ ...draft, strategicDimensions: draft.strategicDimensions.map((item) => item.id === dimension.id ? { ...item, peerObservation: event.target.value } : item) })} placeholder="同业的相对优势、差距和变化方向" /></div></div>)}{draft.strategicDimensions.length === 0 && <div className="rounded-lg border border-dashed border-border px-3 py-6 text-center text-xs text-muted-foreground">可以从规模经济、转换成本、网络效应、品牌、专利、数据或渠道等维度解释财务差异。</div>}</div>
            <div className="mt-4 grid gap-3 md:grid-cols-2"><label><span className={labelClass}>难以复制的优势（每行一项）</span><textarea className={`${inputClass} min-h-28 resize-y`} value={draft.synthesis.durableAdvantages.join("\n")} onChange={(event) => setDraft({ ...draft, synthesis: { ...draft.synthesis, durableAdvantages: event.target.value.split("\n").slice(0, 10) } })} /></label><label><span className={labelClass}>结构性脆弱点（每行一项）</span><textarea className={`${inputClass} min-h-28 resize-y`} value={draft.synthesis.structuralVulnerabilities.join("\n")} onChange={(event) => setDraft({ ...draft, synthesis: { ...draft.synthesis, structuralVulnerabilities: event.target.value.split("\n").slice(0, 10) } })} /></label></div>
            <label className="mt-3 block"><span className={labelClass}>当前状态与变化轨迹</span><textarea className={`${inputClass} min-h-24 resize-y`} value={draft.synthesis.currentVsTrajectory} onChange={(event) => setDraft({ ...draft, synthesis: { ...draft.synthesis, currentVsTrajectory: event.target.value } })} placeholder="区分当前领先/落后与未来正在改善/恶化的方向。" /></label>
          </GlassCard>

          <div className="grid gap-4 2xl:grid-cols-2">
            <GlassCard><div className="mb-3 flex items-center gap-2"><Database className="h-4 w-4 text-primary" /><h2 className="font-bold">来源与期间</h2></div><div className="space-y-2">{draft.sourceMaterials.length === 0 && <p className="text-xs text-muted-foreground">刷新比较后将显示每家公司的 Evidence Ledger、截至时间和覆盖状态。</p>}{draft.sourceMaterials.map((source) => <div key={source.id} className="rounded-lg bg-muted/35 px-3 py-2 text-sm"><div className="font-medium">{source.label}</div><div className="mt-0.5 text-[11px] text-muted-foreground">截至 {source.asOf.replace("T", " ").slice(0, 16)} · {source.status}</div></div>)}</div></GlassCard>
            <GlassCard><div className="mb-3 flex items-center gap-2"><SearchCheck className="h-4 w-4 text-primary" /><h2 className="font-bold">可比性与数据缺口</h2></div><textarea className={`${inputClass} min-h-48 resize-y`} value={draft.gaps.join("\n")} onChange={(event) => setDraft({ ...draft, gaps: event.target.value.split("\n").slice(0, 30) })} placeholder="每行一项，例如：目标公司与同业财年结束日期不同" /></GlassCard>
          </div>

          <Disclaimer />
        </div>
      </div>
      </fieldset>
      {pending && <PeerActionDialog message={pending.message} cancel={() => setPending(null)} confirm={() => { const action = pending.run; setPending(null); void action(); }} />}
    </div>
  );
}
