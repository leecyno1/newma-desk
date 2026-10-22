import { useEffect, useMemo, useRef, useState, useSyncExternalStore } from "react";
import {
  BarChart3,
  BookOpenCheck,
  Calculator,
  CheckCircle2,
  CircleAlert,
  Database,
  Loader2,
  Plus,
  RefreshCw,
  Save,
  SearchCheck,
  Trash2,
} from "lucide-react";

import { Disclaimer } from "@/components/ui/Disclaimer";
import { GlassCard } from "@/components/ui/GlassCard";
import { PageHeader } from "@/components/ui/PageHeader";
import { ValuationCapitalEvidence } from '@/components/ValuationCapitalEvidence';
import { ResearchBackupRecovery } from '@/components/ResearchBackupRecovery';
import { ResearchAnalysisPanel, useResearchAnalysis } from '@/components/ResearchAnalysisPanel';
import { flushSync } from 'react-dom';
import { canRefreshResearchData, fetchValuationPrice } from '@/lib/researchData';
import { analyzeValuation, valuationAnalysisActions } from '@/lib/researchAnalysis';
import { recoverValuationBackup, type ResearchBackupRow } from '@/lib/researchBackup';
import { alignValuationYears, attachCapitalEvidence, stageCapitalEvidence, confirmScenario, eligibleCash, priceComparisonIssue, scenarioReviewIssue, valuationReadiness } from '@/lib/valuationReview';
import { applyMarketPrice, hasValuationFacts, loadSavedEarningsInputs, previewEarningsInput, valuationFromEarnings, type SavedEarningsInput } from "@/lib/valuationInputs";
import { cn } from "@/lib/utils";
import {
  blankValuationModel,
  calculateValuationModel,
  calculateWacc,
  hydrateValuationWorkspace,
  emptyValuationWorkspace,
  persistValuationWorkspace,
  valuationScope,
  ValuationStorageError,
  type ValuationSession,
  type AuditCheck,
  type ForecastDriver,
  type ValuationModel,
  type ValuationScenario,
  type ValuationScenarioId,
  type ValuationWorkspace,
} from "@/lib/valuationWorkbench";
import {
  publishVibeDeskContext,
  registerVibeDeskContextProvider,
  subscribeVibeDeskEvent,
  subscribeVibeDeskConfig,
  type VibeDeskPageContext,
} from "@/lib/vibedesk";

const inputClass = "w-full rounded-lg border border-border bg-card/70 px-3 py-2 text-sm text-foreground outline-none transition focus:border-primary/60 focus:ring-2 focus:ring-primary/15";
const labelClass = "mb-1.5 block text-xs font-semibold text-muted-foreground";
const SCENARIO_LABEL: Record<ValuationScenarioId, string> = { bear: "悲观", base: "基准", bull: "乐观" };
const CHECK_STYLE: Record<AuditCheck["status"], string> = {
  pass: "border-success/25 bg-success/8 text-success",
  warning: "border-warning/25 bg-warning/8 text-warning",
  fail: "border-destructive/25 bg-destructive/8 text-destructive",
};

function copyModel(model: ValuationModel) {
  return structuredClone(model);
}

function parseNumber(value: string) {
  if (!value.trim()) return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function formatNumber(value: number | null | undefined, digits = 1) {
  return value === null || value === undefined || !Number.isFinite(value)
    ? "—"
    : value.toLocaleString("zh-CN", { maximumFractionDigits: digits, minimumFractionDigits: digits });
}

function currencyForMarket(market: string) {
  return market.toUpperCase() === "US" ? "USD" : market.toUpperCase() === "HK" ? "HKD" : "CNY";
}

function contextFor(workspace: ValuationWorkspace, model: ValuationModel, loading: boolean): VibeDeskPageContext {
  return {
    view: { id: "valuation-workbench", title: "预测与估值" },
    visibleBlocks: [
      { id: "historical-drivers", type: "financial-model-inputs", title: "历史基期与驱动" },
      { id: "scenario-assumptions", type: "scenario-model", title: "悲观、基准与乐观情景" },
      { id: "fcf-projection", type: "cash-flow-projection", title: "自由现金流预测" },
      { id: "valuation-bridge", type: "valuation-bridge", title: "企业价值到每股价值" },
      { id: "sensitivity", type: "sensitivity-grid", title: "WACC 与终值增长敏感性" },
      { id: "model-audit", type: "model-audit", title: "模型审计与数据缺口" },
    ],
    selection: {
      market: model.security.market,
      symbol: model.security.symbol,
      name: model.security.name,
      currency: model.security.currency,
      modelId: model.id,
      scenario: model.selectedScenario,
    },
    filters: { asOf: model.asOf, unitScale: model.unitScale, modelScope: model.modelScope },
    data: {
      asOf: model.asOf || undefined,
      source: workspace.schemaVersion,
      freshness: "unknown",
      summary: {
        historicals: model.historicals,
        capitalInputs: model.capitalInputs,
        capitalEvidence: model.capitalEvidence,
        pendingCapitalEdits: Object.entries(model.capitalEvidenceDrafts || {}).map(([field,edit])=>({field,savedAt:edit.savedAt,status:'已暂存但未核验、未采用；不属于当前数值或已确认依据'})),
        capitalLinePolicy: 'capitalEvidence 中的 lineItems 是用户核对采用的明细，不是自动财报解析。amountM 单位百万元；add 相加、deduct 仅扣已纳入的金额、exclude 仅记录不计入（不是减项）。各行 locator、reason 与共用来源原文一并解释。合计行与组成项不可重复纳入；gross 现金余额明细不得扣受限资金，剔除统一归入 excludedCashM；adjusted 已是净额不再扣剔除额。未采用的编辑明细不属于当前模型。',
        reviewStatus: valuationReadiness(model),
        priceComparisonIssue: priceComparisonIssue(model),
        equityBridgePolicy: '普通股价值 = 经营 EV - 有息债务 + 可用现金 + 非经营性资产价值 - 少数股东权益价值 - 其他优先权益。已调整现金不重复剔除；原始余额先扣剔除额。调整项目缺失不是零。少数权益须匹配合并预测范围且不能直接用账面值；非经营资产不得已含于 FCF 或现金；其他索偿不得与债务、稀释股数重计。所有值仍为用户输入和人工核验，非独立估值审计。',
        interpretation: '现金流和价值桥接为研究试算；资本依据为用户手工关联，非机器审计。确认不足时每股结果为空，不得绕过确认生成目标价。',
        scenarios: model.scenarios,
        projections: model.projections,
        valuation: model.result,
        sensitivity: model.sensitivity,
        auditChecks: model.auditChecks,
        sources: model.sourceMaterials,
        gaps: model.gaps,
      },
    },
    actions: [
      { id: "valuation.refresh-evidence", label: "刷新股价（页面按钮可用，Agent动作尚未接通）", available: false },
      { id: "valuation.audit-inputs", label: "审计历史与资本输入（尚未接通）", available: false },
      { id: "valuation.test-scenarios", label: "比较三种情景（尚未接通）", available: false },
      { id: "valuation.explain-sensitivity", label: "解释敏感性和主要驱动（尚未接通）", available: false },
    ],
    tasks: loading ? [{ id: `valuation-refresh:${model.id}`, status: "running", actionId: "valuation.refresh-evidence" }] : [],
  };
}

function driverCell(
  driver: ForecastDriver,
  field: keyof Omit<ForecastDriver, "year">,
  onChange: (value: number) => void,
) {
  return (
    <input
      aria-label={`${driver.year} ${field}`}
      type="number"
      step="0.1"
      className="w-20 rounded-md border border-border bg-card/70 px-2 py-1.5 text-right text-xs outline-none focus:border-primary/60"
      value={driver[field]}
      onChange={(event) => onChange(Number(event.target.value) || 0)}
    />
  );
}

function ValuationActionDialog({message,onConfirm,onCancel}: {message:string;onConfirm:()=>void;onCancel:()=>void}) {
  const dialog=useRef<HTMLDialogElement>(null);
  useEffect(()=>{const element=dialog.current; element?.showModal(); return()=>element?.close()},[]);
  return <dialog ref={dialog} aria-label="估值操作确认" onCancel={event=>{event.preventDefault();onCancel()}}
    className="max-w-md rounded-lg border border-border bg-card p-5 text-foreground shadow-xl backdrop:bg-black/50">
    <p className="text-sm">{message}</p>
    <div className="mt-4 flex justify-end gap-3">
      <button autoFocus className="rounded border border-border px-3 py-2 text-sm" onClick={onCancel}>取消操作</button>
      <button className="rounded bg-primary px-3 py-2 text-sm text-primary-foreground" onClick={onConfirm}>确认继续</button>
    </div>
  </dialog>;
}

export function ValuationWorkbench() {
  const scope = useSyncExternalStore(subscribeVibeDeskConfig, valuationScope);
  return <ValuationWorkbenchContent key={scope} />;
}

function ValuationWorkbenchContent() {
  const inputRead = useRef<AbortController | null>(null);
  useEffect(() => () => inputRead.current?.abort(), []);
  const initial = useMemo(emptyValuationWorkspace, []);
  const [workspace, setWorkspace] = useState(initial);
  const [selectedId, setSelectedId] = useState(initial.models[0]?.id || "__new__");
  const [draft, setDraft] = useState(() => initial.models[0] ? copyModel(initial.models[0]) : blankValuationModel());
  const baseline = useRef(JSON.stringify(draft));
  const session = useRef<ValuationSession | null>(null);
  const operation = useRef<AbortController | null>(null);
  const refreshRead = useRef<AbortController | null>(null);
  const refreshBusy = useRef(false);
  const alive = useRef(true);
  const operationBusy = useRef(false);
  const [reading, setReading] = useState(true);
  const [storageError, setStorageError] = useState("");
  const [editorSnapshot, setEditorSnapshot] = useState<unknown>(null);
  const [loading, setLoading] = useState(false);
  const [hydrated, setHydrated] = useState(false);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");
  const [pendingAction,setPendingAction] = useState<{message:string;run:()=>void|Promise<void>}|null>(null);
  const recoveryResolve = useRef<((accepted: boolean) => void) | null>(null);
  const [recoveredFrom, setRecoveredFrom] = useState<{ id: string; updatedAt: string } | null>(null);
  const [editorDirty,setEditorDirty] = useState(false);
  const [editorVersion,setEditorVersion] = useState(0);
  const editorDirtyRef = useRef(editorDirty);
  editorDirtyRef.current = editorDirty;
  const [earningsInputs, setEarningsInputs] = useState<SavedEarningsInput[] | null>(null);
  const [earningsLoading, setEarningsLoading] = useState(false);
  const draftRef = useRef(draft);
  draftRef.current = draft;
  const identityLocked = draft.sourceMaterials.length > 0 || (selectedId !== '__new__' && hasValuationFacts(draft));
  const calculated = useMemo(() => calculateValuationModel(draft), [draft]);
  const dirty = JSON.stringify(draft) !== baseline.current;
  const busy = reading || saving || loading;

  const readWorkspace = async () => {
    if (operationBusy.current) return;
    operationBusy.current = true;
    const controller = new AbortController();
    operation.current = controller;
    inputRead.current?.abort();
    setEarningsLoading(false);
    setReading(true); setHydrated(false); setStorageError("");
    try {
      const loaded = await hydrateValuationWorkspace(controller.signal);
      if (!alive.current || controller.signal.aborted) return;
      session.current = loaded;
      setWorkspace(loaded.workspace);
      const first = loaded.workspace.models.find(model => model.id === selectedId) ?? loaded.workspace.models[0];
      const next = first ? copyModel(first) : blankValuationModel();
      baseline.current = JSON.stringify(next);
      setSelectedId(first?.id ?? "__new__"); setDraft(next);
      setRecoveredFrom(null);
      setEditorVersion(version => version + 1); setEarningsInputs(null);
      setHydrated(true); setMessage(loaded.mode === "local" ? "仅使用本机浏览器档案，未同步到 Desk" : "已读取当前 Desk 工作区");
    } catch (error) {
      if (alive.current && !controller.signal.aborted) setStorageError(error instanceof ValuationStorageError ? error.message : "读取失败，现有草稿保留");
    } finally {
      if (alive.current && !controller.signal.aborted) { setReading(false); operationBusy.current = false; }
    }
  };

  useEffect(() => {
    alive.current = true;
    operationBusy.current = false;
    void readWorkspace();
    return () => { alive.current = false; operation.current?.abort(); refreshRead.current?.abort(); recoveryResolve.current?.(false); };
  }, []);

  const refreshAvailable = hydrated && !storageError && !busy && !pendingAction && !earningsLoading && !editorDirty
    && Boolean(draft.security.symbol.trim()) && canRefreshResearchData('valuation-workbench');
  const analysis = useResearchAnalysis({ moduleId: 'valuation-workbench', draft,
    enabled: hydrated && !storageError && !busy && !pendingAction && !earningsLoading && !editorDirty,
    isBusy: () => operationBusy.current || refreshBusy.current,
    actions: valuationAnalysisActions, calculate: analyzeValuation,
    refresh: { id: 'valuation.refresh-evidence', label: '刷新股价（保留预测假设，不自动保存）', available: refreshAvailable, run: () => refreshEvidence() },
  });
  const contextRef = useRef<VibeDeskPageContext>(contextFor(workspace, calculated, loading));
  contextRef.current = contextFor(workspace, calculated, loading);
  contextRef.current.filters = { ...contextRef.current.filters, unsavedChanges: dirty || editorDirty };
  contextRef.current.actions = contextRef.current.actions?.map(action => analysis.refreshAction?.id === action.id ? analysis.refreshAction : analysis.actions.find(item => item.id === action.id) ?? action);
  if (analysis.report) contextRef.current.visibleBlocks?.push({ id: 'research-analysis', type: 'table', title: analysis.report.title });
  contextRef.current.data.summary = { ...contextRef.current.data.summary,
    currentAnalysis: analysis.report,
    storage: { mode: session.current?.mode ?? 'unavailable', revision: session.current?.revision ?? null,
      status: reading ? 'reading' : saving ? 'saving' : storageError ? 'error' : 'ready', error: storageError || undefined },
    unsavedCapitalEditor: editorSnapshot,
    backupRecovery: recoveredFrom ? { ...recoveredFrom, status: dirty ? 'unsaved-copy' : 'saved-copy', requiresReview: true } : null,
  };
  useEffect(() => registerVibeDeskContextProvider(() => contextRef.current), []);
  useEffect(() => {
    const unsubscribe = subscribeVibeDeskEvent((event) => {
      if (event.event !== "security.selected") return;
      const symbol = typeof event.payload.symbol === "string" ? event.payload.symbol.slice(0, 40).toUpperCase() : "";
      if (!symbol) return;
      const market = typeof event.payload.market === "string" ? event.payload.market.slice(0, 20).toUpperCase() : "CN";
      const name = typeof event.payload.name === "string" ? event.payload.name.slice(0, 120) : "";
      if (operationBusy.current || hasValuationFacts(draftRef.current) || editorDirtyRef.current
        || JSON.stringify(draftRef.current) !== baseline.current || session.current?.workspace.models.some(model => model.id === draftRef.current.id)) {
        setMessage("当前模型已有财务输入，未替换证券；研究其他公司请新建模型");
        return;
      }
      setDraft((current) => ({ ...current, security: { market, symbol, name, currency: currencyForMarket(market) } }));
    });
    return () => { unsubscribe(); };
  }, []);
  useEffect(() => { void publishVibeDeskContext(); }, [calculated, loading, workspace, reading, saving, storageError, editorDirty, editorSnapshot,pendingAction,earningsLoading,hydrated,analysis.report]);

  const commit = async (next: ValuationWorkspace) => {
    if (!session.current || !hydrated || operationBusy.current) return null;
    operationBusy.current = true;
    const controller = new AbortController();
    operation.current = controller;
    setSaving(true);
    try {
      const result = await persistValuationWorkspace(next, session.current, controller.signal);
      if (!alive.current || controller.signal.aborted) return null;
      session.current = result;
      setWorkspace(result.workspace);
      return result;
    } catch (error) {
      if (alive.current && !controller.signal.aborted) {
        setHydrated(false);
        setStorageError(error instanceof ValuationStorageError ? error.message : "保存未确认，请保留草稿并重新读取核对，勿重复提交。");
      }
      return null;
    } finally {
      if (alive.current && !controller.signal.aborted) { setSaving(false); operationBusy.current = false; }
    }
  };

  const requestAction = (message:string,run:()=>void|Promise<void>,needsConfirmation=true) => {
    if(operationBusy.current||loading||pendingAction)return;
    if(needsConfirmation)setPendingAction({message,run});else void run();
  };
  const startNew = () => requestAction('新建会放弃未保存修改，包括未暂存的资本编辑。需要保留请取消并先暂存、保存。确定新建吗？',()=>{
    setSelectedId("__new__");
    const next = blankValuationModel();
    baseline.current = JSON.stringify(next);
    setEditorVersion(version => version + 1);
    setDraft(next);
    setRecoveredFrom(null);
    setMessage("");
  },dirty||editorDirty);

  const choose = (model: ValuationModel) => requestAction('切换会放弃未保存修改，包括未暂存的资本编辑。需要保留请取消并先暂存、保存。确定切换吗？',()=>{
    setEditorVersion(version=>version+1);
    setSelectedId(model.id);
    baseline.current = JSON.stringify(model);
    setDraft(copyModel(model));
    setRecoveredFrom(null);
    setMessage("");
  },dirty||editorDirty);

  const recoverBackup = (row: ResearchBackupRow): Promise<boolean> => {
    if (busy || operationBusy.current || pendingAction || !hydrated || !session.current?.writable) return Promise.resolve(false);
    const next = recoverValuationBackup(row);
    return new Promise(resolve => {
      recoveryResolve.current = resolve;
      const run = () => {
        if (!alive.current || operationBusy.current) { resolve(false); return; }
        inputRead.current?.abort(); setEarningsLoading(false); setEarningsInputs(null);
        setSelectedId('__new__'); setDraft(next);
        setEditorVersion(version => version + 1); setEditorDirty(false); setEditorSnapshot(null);
        setRecoveredFrom({ id: row.id, updatedAt: row.updatedAt });
        setMessage('已恢复为新草稿，尚未保存；来源与情景须重新核验，资本编辑未自动采用为金额。');
        recoveryResolve.current = null; resolve(true);
      };
      if (dirty || editorDirty) setPendingAction({message:'恢复会替换当前未保存模型与资本编辑，但不覆盖已保存档案。请先导出需保留内容，确定继续吗？',run});
      else run();
    });
  };

  const validate = (candidate: ValuationModel) => {
    if (!candidate.name.trim()) return "请填写模型名称";
    if (!candidate.security.symbol.trim() || !candidate.security.name.trim()) return "请填写证券代码和公司名称";
    if (candidate.scenarios.some((scenario) => scenario.terminalGrowthPct >= scenario.waccPct)) return "每个情景的终值增长必须低于 WACC";
    return "";
  };

  const save = async (candidate = draft) => {
    if (operationBusy.current || loading || !hydrated || !session.current?.writable) return;
    const error = validate(candidate);
    if (error) {
      setMessage(error);
      return;
    }
    const timestamp = new Date().toISOString();
    const saved = calculateValuationModel({
      ...candidate,
      name: candidate.name.trim(),
      security: {
        market: candidate.security.market.trim().toUpperCase(),
        symbol: candidate.security.symbol.trim().toUpperCase(),
        name: candidate.security.name.trim(),
        currency: candidate.security.currency.trim().toUpperCase() || currencyForMarket(candidate.security.market),
      },
      gaps: candidate.gaps.map((item) => item.trim()).filter(Boolean).slice(0, 30),
      updatedAt: timestamp,
    });
    const exists = workspace.models.some((item) => item.id === saved.id);
    const models = exists ? workspace.models.map((item) => item.id === saved.id ? saved : item) : [saved, ...workspace.models];
    const original = candidate;
    try {
      const result = await commit({ ...workspace, updatedAt: timestamp, models });
      if (!result) return;
      const confirmed = result.workspace.models.find(model => model.id === saved.id);
      if (draftRef.current === original) {
        if (confirmed) {
          baseline.current = JSON.stringify(confirmed);
          setSelectedId(confirmed.id);
          setDraft(copyModel(confirmed));
        }
      }
      setMessage(result.mode === "desk" ? "Desk 已确认保存" : "仅保存到本机浏览器，尚未同步到 Desk");
      return result.mode;
    } catch {
      setStorageError("保存未确认，当前草稿仍保留，请重新读取核对");
      setHydrated(false);
    }
  };

  const remove = async () => {
    if (operationBusy.current || loading || !hydrated || !session.current?.writable) return;
    if (selectedId === "__new__") {
      startNew();
      return;
    }
    requestAction(`删除“${draft.name}”估值模型及其暂存编辑？该操作不能在页面内撤销。`,async()=>{
      const models = workspace.models.filter((item) => item.id !== selectedId);
      const next = { ...workspace, updatedAt: new Date().toISOString(), models };
      const result = await commit(next);
      if (!result) return;
      const first = result.workspace.models[0];
      const nextDraft = first ? copyModel(first) : blankValuationModel();
      baseline.current = JSON.stringify(nextDraft);
      setSelectedId(first?.id || "__new__");
      setEditorVersion(version => version + 1);
      setDraft(nextDraft);
      setRecoveredFrom(null);
      setMessage(result.mode==='desk'?'模型已从 Desk 工作区移除':'仅本机移除，尚未同步到 Desk');
    });
  };

  const refreshEvidence = async () => {
    if (operationBusy.current || refreshBusy.current || !refreshAvailable) throw new Error('当前模型尚不可刷新，请先完成读取、保存或待确认操作');
    const symbol = draft.security.symbol.trim().toUpperCase();
    const controller = new AbortController(); refreshRead.current = controller; refreshBusy.current = true;
    setLoading(true);
    setMessage("");
    try {
      const snapshot = await fetchValuationPrice(symbol, controller.signal);
      if (!alive.current || controller.signal.aborted) throw new Error('页面已切换，旧结果未采用');
      if (draftRef.current !== draft) throw new Error("读取期间模型已修改，未覆盖输入；可重新刷新股价");
      const next = applyMarketPrice(draft, snapshot);
      flushSync(() => { setDraft(next); setMessage("已刷新股价；历史基期、稀释股数与预测假设均保持不变，尚未保存"); });
      return { status: 'draft-updated', modelId: next.id, symbol, currency: next.security.currency,
        currentPrice: next.capitalInputs.currentPrice, asOf: next.capitalInputs.currentPriceAsOf, assumptionsChanged: false, saved: false };
    } catch (error) {
      if (alive.current) setMessage(error instanceof Error ? error.message : "行情读取失败，已保留当前输入");
      throw error;
    } finally {
      refreshBusy.current = false;
      if (alive.current) flushSync(() => setLoading(false));
    }
  };

  const loadEarnings = async () => {
    inputRead.current?.abort();
    const controller = new AbortController();
    inputRead.current = controller;
    setEarningsLoading(true);
    try { setEarningsInputs(await loadSavedEarningsInputs(controller.signal)); }
    catch (error) { if (!controller.signal.aborted) setMessage(error instanceof Error ? error.message : "读取失败"); }
    finally { if (!controller.signal.aborted) setEarningsLoading(false); }
  };
  const adoptEarnings = (workbook: SavedEarningsInput) => requestAction('从财报新建会放弃未保存修改，包括未暂存的资本编辑。需要保留请取消并先暂存、保存。确定继续吗？',()=>{
    setRecoveredFrom(null);
    setDraft(valuationFromEarnings(workbook));
    setSelectedId("__new__");
    setEarningsInputs(null);
    setMessage("年度收入已接入新草稿，尚未保存；预测参数为模板，须逐项确认");
  },dirty||editorDirty);

  const updateScenario = (id: ValuationScenarioId, update: Partial<ValuationScenario>) => {
    setDraft((current) => ({ ...current, scenarios: current.scenarios.map((scenario) => scenario.id === id ? { ...scenario, ...update, review: undefined } : scenario) }));
  };

  const updateDriver = (scenarioId: ValuationScenarioId, index: number, field: keyof Omit<ForecastDriver, "year">, value: number) => {
    setDraft((current) => ({
      ...current,
      scenarios: current.scenarios.map((scenario) => scenario.id !== scenarioId ? scenario : {
        ...scenario,
        review: undefined,
        drivers: scenario.drivers.map((driver, driverIndex) => driverIndex === index ? { ...driver, [field]: value } : driver),
      }),
    }));
  };

  const activeScenario = draft.scenarios.find((scenario) => scenario.id === draft.selectedScenario) ?? draft.scenarios[1]!;
  const reviewStatus = valuationReadiness(draft);
  const assumptionIssue = scenarioReviewIssue(draft, activeScenario);
  const capmWacc = calculateWacc(draft.capitalInputs);
  const passCount = calculated.auditChecks.filter((check) => check.status === "pass").length;

  return (
    <div>
      {pendingAction&&<ValuationActionDialog message={pendingAction.message} onCancel={()=>{
        setPendingAction(null); recoveryResolve.current?.(false); recoveryResolve.current=null;
      }} onConfirm={()=>{
        const action=pendingAction;setPendingAction(null);void action.run();
      }}/>}
      <PageHeader
        title="预测与估值"
        subtitle="用可追溯的历史基期、三种经营情景、WACC、自由现金流与敏感性矩阵形成轻量驱动式 DCF；不把缺失数据静默估算成精确结论。"
        actions={(
          <>
            <button onClick={startNew} disabled={busy} className="inline-flex items-center gap-1.5 rounded-lg border border-border bg-card/70 px-3 py-2 text-sm hover:border-primary/40 disabled:opacity-50"><Plus className="h-4 w-4" /> 新建</button>
            <button onClick={loadEarnings} disabled={earningsLoading || busy} className="rounded-lg border border-border px-3 py-2 text-sm disabled:opacity-50">{earningsLoading ? "读取中…" : "从已保存财报接入"}</button>
            <button onClick={() => { void refreshEvidence().catch(() => {}); }} disabled={!refreshAvailable} className="inline-flex items-center gap-1.5 rounded-lg border border-border bg-card/70 px-3 py-2 text-sm hover:border-primary/40 disabled:opacity-50">{loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />} 刷新股价</button>
            <button onClick={()=>{
              if(editorDirty){setMessage('资本编辑尚未暂存，请先在编辑区暂存或确认采用，再保存模型');return;}
              void save();
            }} disabled={busy || !hydrated || !session.current?.writable} className="inline-flex items-center gap-1.5 rounded-lg bg-primary px-3 py-2 text-sm font-semibold text-primary-foreground hover:opacity-90 disabled:opacity-50"><Save className="h-4 w-4" /> {saving ? "保存中…" : "保存"}</button>
          </>
        )}
      />

      <div className="mb-4 flex flex-wrap items-center gap-3 text-sm" aria-label="估值存储状态">
        <span>{reading ? '正在读取估值档案…' : saving ? '正在等待保存回执…' : session.current?.mode === 'desk' ? `Desk 工作区 · 修订 ${session.current.revision}${session.current.writable ? '' : ' · 只读'}` : session.current?.mode === 'local' ? '本机档案，不代表 Desk 同步' : '存储尚未连接'}</span>
        <button disabled={busy} className="rounded border border-border px-3 py-2 disabled:opacity-50" onClick={() => {
          const run = async () => { await readWorkspace(); };
          if (dirty || editorDirty) setPendingAction({ message: '重新读取将替换当前草稿与未暂存资本编辑，请先导出保留。确定继续吗？', run });
          else void run();
        }}>重新读取档案</button>
        <a className="rounded border border-border px-3 py-2" download="valuation-draft.json"
          href={`data:application/json;charset=utf-8,${encodeURIComponent(JSON.stringify({ model: draft, unsavedCapitalEditor: editorSnapshot, note: '草稿备份，不代表已保存或已核验；未暂存资本编辑不属于已采用数值' }, null, 2))}`}>导出当前草稿</a>
      </div>
      {storageError && <div role="alert" className="mb-4 rounded-lg border border-destructive/40 p-3 text-sm text-destructive">{storageError}</div>}
      {message && !storageError && <div role="status" className="mb-4 rounded-lg border border-border px-3 py-2 text-sm">{message}</div>}
      <ResearchAnalysisPanel analysis={analysis}/>
      <ResearchBackupRecovery kind="valuation" disabled={busy||Boolean(pendingAction)||earningsLoading} canRecover={hydrated&&Boolean(session.current?.writable)} onRecover={recoverBackup}/>
      <fieldset disabled={busy} className="m-0 min-w-0 border-0 p-0">
      {earningsInputs !== null && <section aria-label="财报收入接入预览" className="mb-4 rounded-lg border border-border p-4 text-sm">
        <div className="mb-2 flex justify-between"><h2 className="font-bold">已保存财报 → 独立估值草稿</h2><button onClick={() => setEarningsInputs(null)}>关闭预览</button></div>
        <p className="mb-3 text-muted-foreground">只采用已确认的年度营业收入，保留来源。不带入净利润、经营现金流或预测假设。旧估值模型和原财报不受影响。</p>
        {!earningsInputs.length && <p>当前工作区没有已保存财报，请先在“财报研究”上传、确认并保存。</p>}
        {earningsInputs.map(workbook => { const preview = previewEarningsInput(workbook); return <div key={workbook.id} className="border-t border-border py-3">
          <div className="font-semibold">{workbook.security?.name} · {workbook.security?.symbol} · {workbook.fiscalPeriod?.label}</div>
          {preview.issues.length ? <p className="mt-1 text-warning">{preview.issues.join("；")}</p> : <>
            <p className="mt-1">营业收入：{formatNumber(preview.metric!.reported, 4)} {preview.metric!.unit} → {formatNumber(preview.revenueM, 4)} 百万元</p>
            <p className="mt-1 text-muted-foreground">{preview.source!.label} · 基期 {preview.period} · 底稿保存 {workbook.updatedAt}</p>
            <button className="mt-2 rounded border border-primary px-3 py-1.5 text-primary" onClick={() => adoptEarnings(workbook)}>确认新建估值草稿</button>
          </>}
        </div>; })}
      </section>}

      <div className="mb-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {[
          { label: "模型档案", value: workspace.models.length, icon: BookOpenCheck },
          { label: "当前情景", value: SCENARIO_LABEL[draft.selectedScenario], icon: BarChart3 },
          { label: "每股试算价值", value: calculated.result.impliedPrice === null ? "待补齐与确认" : `${draft.security.currency} ${formatNumber(calculated.result.impliedPrice, 2)}`, icon: Calculator },
          { label: "审计通过", value: `${passCount}/${calculated.auditChecks.length}`, icon: SearchCheck },
        ].map(({ label, value, icon: Icon }) => <GlassCard key={label} className="flex items-center justify-between p-4"><div><div className="text-xs text-muted-foreground">{label}</div><div className="mt-1 text-xl font-bold">{value}</div></div><Icon className="h-5 w-5 text-primary" /></GlassCard>)}
      </div>

      <div className="grid items-start gap-4 xl:grid-cols-[240px_minmax(0,1fr)]">
        <GlassCard className="p-3 xl:sticky xl:top-3">
          <div className="mb-2 flex items-center justify-between px-2"><span className="text-xs font-semibold uppercase tracking-[0.14em] text-muted-foreground">估值档案</span><button onClick={startNew} className="rounded-md p-1 text-muted-foreground hover:bg-muted"><Plus className="h-4 w-4" /></button></div>
          <div className="space-y-1.5">{workspace.models.length === 0 && <div className="rounded-lg border border-dashed border-border px-3 py-8 text-center text-xs text-muted-foreground">尚无模型。先录入公司、历史基期和资本结构。</div>}{workspace.models.map((model) => <button key={model.id} onClick={() => choose(model)} className={cn("w-full rounded-lg border px-3 py-2.5 text-left", selectedId === model.id ? "border-primary/45 bg-primary/10" : "border-transparent hover:border-border hover:bg-muted/45")}><div className="truncate text-sm font-semibold">{model.name}</div><div className="mt-1 text-[11px] text-muted-foreground">{model.security.market}:{model.security.symbol} · {SCENARIO_LABEL[model.selectedScenario]}</div></button>)}</div>
        </GlassCard>

        <div className="min-w-0 space-y-4">
          <GlassCard glow>
            <div className="mb-4 flex flex-wrap items-center justify-between gap-3"><div><div className="text-xs font-semibold uppercase tracking-[0.14em] text-primary">Model scope</div><h2 className="mt-1 text-lg font-bold">公司、口径与模型边界</h2></div><div className="flex items-center gap-2">{dirty && <span className="text-xs text-warning">有未保存修改</span>}<button aria-label="删除当前估值模型" disabled={saving||!hydrated} onClick={remove} className="rounded-lg border border-border p-2 text-muted-foreground hover:border-destructive/40 hover:text-destructive disabled:opacity-50"><Trash2 className="h-4 w-4" /></button></div></div>
            <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-6">
              <label className="xl:col-span-2"><span className={labelClass}>模型名称</span><input aria-label="模型名称" className={inputClass} value={draft.name} onChange={(event) => setDraft({ ...draft, name: event.target.value })} placeholder="例如：中际旭创五年驱动式 DCF" /></label>
              <label><span className={labelClass}>市场</span><input aria-label="市场" disabled={identityLocked} className={inputClass} value={draft.security.market} onChange={(event) => setDraft({ ...draft, security: { ...draft.security, market: event.target.value, currency: currencyForMarket(event.target.value) } })} /></label>
              <label><span className={labelClass}>证券代码</span><input aria-label="证券代码" disabled={identityLocked} className={inputClass} value={draft.security.symbol} onChange={(event) => setDraft({ ...draft, security: { ...draft.security, symbol: event.target.value } })} /></label>
              <label><span className={labelClass}>公司名称</span><input aria-label="公司名称" className={inputClass} value={draft.security.name} onChange={(event) => setDraft({ ...draft, security: { ...draft.security, name: event.target.value } })} /></label>
              <label><span className={labelClass}>币种</span><input disabled={identityLocked} className={inputClass} value={draft.security.currency} onChange={(event) => setDraft({ ...draft, security: { ...draft.security, currency: event.target.value } })} /></label>
            </div>
            <div className="mt-3 grid gap-3 md:grid-cols-3"><label><span className={labelClass}>估值基期末（非行情日期）</span><input aria-label="估值基期末" className={inputClass} value={draft.asOf} onChange={(event) => setDraft({ ...draft, asOf: event.target.value })} /></label><label><span className={labelClass}>金额单位（固定）</span><input readOnly className={inputClass} value={draft.unitScale} /></label><div className="rounded-lg border border-border bg-muted/25 px-3 py-2"><div className="text-xs font-semibold">模型边界</div><div className="mt-1 text-xs text-muted-foreground">驱动式 DCF；三情景初始值为模板假设，须研究确认，不是正式估值意见。已绑定来源或保存的模型切换证券请新建；手录草稿可先补齐身份。</div></div></div>
          </GlassCard>

          <GlassCard>
            <div className="mb-4 flex items-center justify-between"><div><div className="text-xs font-semibold uppercase tracking-[0.14em] text-primary">Historical base</div><h2 className="mt-1 text-lg font-bold">历史基期与经营驱动</h2></div><button disabled={draft.historicals.length >= 5} onClick={() => setDraft({ ...draft, historicals: [...draft.historicals, { period: "", revenue: null, ebitMarginPct: null, daPctRevenue: null, capexPctRevenue: null, nwcPctDeltaRevenue: null, sourceIds: [] }] })} className="inline-flex items-center gap-1 rounded-lg border border-border px-2.5 py-1.5 text-xs disabled:opacity-40"><Plus className="h-3.5 w-3.5" /> 添加历史期</button></div>
            <div className="overflow-x-auto"><table className="w-full min-w-[880px] text-xs"><thead className="text-muted-foreground"><tr className="border-b border-border"><th className="px-2 py-2 text-left">期间</th><th className="px-2 py-2 text-right">收入</th><th className="px-2 py-2 text-right">EBIT 率</th><th className="px-2 py-2 text-right">D&A / 收入</th><th className="px-2 py-2 text-right">CapEx / 收入</th><th className="px-2 py-2 text-right">ΔNWC / Δ收入</th><th className="px-2 py-2 text-left">来源编号</th><th /></tr></thead><tbody>{draft.historicals.map((row, index) => <tr key={index} className="border-b border-border/60"><td className="px-2 py-2"><input aria-label={index === 0 ? "历史期间" : `历史期间 ${index + 1}`} className={inputClass} value={row.period} onChange={(event) => setDraft({ ...draft, historicals: draft.historicals.map((item, itemIndex) => itemIndex === index ? { ...item, period: event.target.value, sourceIds: [] } : item) })} /></td>{(["revenue", "ebitMarginPct", "daPctRevenue", "capexPctRevenue", "nwcPctDeltaRevenue"] as const).map((field) => <td key={field} className="px-2 py-2"><input aria-label={index === 0 && field === "revenue" ? "历史收入" : `${row.period || index + 1} ${field}`} type="number" step="0.1" className={`${inputClass} text-right`} value={row[field] ?? ""} onChange={(event) => setDraft({ ...draft, historicals: draft.historicals.map((item, itemIndex) => itemIndex === index ? { ...item, [field]: parseNumber(event.target.value), ...(field === "revenue" ? { sourceIds: [] } : {}) } : item) })} /></td>)}<td className="px-2 py-2"><input className={inputClass} value={row.sourceIds.join("；")} onChange={(event) => setDraft({ ...draft, historicals: draft.historicals.map((item, itemIndex) => itemIndex === index ? { ...item, sourceIds: event.target.value.split(/[；;]/).filter(Boolean).slice(0, 20) } : item) })} placeholder="Evidence ID" /></td><td className="px-2 py-2"><button disabled={draft.historicals.length <= 1} onClick={() => setDraft({ ...draft, historicals: draft.historicals.filter((_, itemIndex) => itemIndex !== index) })} className="text-muted-foreground hover:text-destructive disabled:opacity-30"><Trash2 className="h-4 w-4" /></button></td></tr>)}</tbody></table></div>
          </GlassCard>

          <GlassCard>
            <div className="mb-4"><div className="text-xs font-semibold uppercase tracking-[0.14em] text-primary">Capital & WACC</div><h2 className="mt-1 text-lg font-bold">资本结构与折现率输入</h2><p className="mt-1 text-xs text-muted-foreground">CAPM 权重以股价×稀释股数及录入债务近似，并非已核验市值权重。债务与现金均按百万元；股数按百万股。情景 WACC 需单独确认。</p></div>
            <div className="grid gap-3 md:grid-cols-3 xl:grid-cols-5">{([
              ["currentPrice", "当前股价"], ["dilutedSharesM", "稀释股数（百万股）"], ["totalDebtM", "总债务"], ["cashM", "现金及等价物"], ["riskFreeRatePct", "无风险利率 %"], ["beta", "Beta"], ["equityRiskPremiumPct", "权益风险溢价 %"], ["preTaxCostDebtPct", "税前债务成本 %"], ["taxRatePct", "资本结构税率 %"],
            ] as const).map(([field, label]) => <label key={field}><span className={labelClass}>{label}</span><input aria-label={label} type="number" step="0.1" className={inputClass} value={draft.capitalInputs[field] ?? ""} onChange={(event) => setDraft({ ...draft, capitalInputs: { ...draft.capitalInputs, [field]: parseNumber(event.target.value), ...(field === 'currentPrice' ? {currentPriceAsOf:''} : {}) }, ...(field === 'currentPrice' ? {sourceMaterials:draft.sourceMaterials.filter(source=>source.id!=='valuation.price')} : {}) })} /></label>)}<div className="rounded-lg border border-primary/25 bg-primary/8 px-3 py-2"><div className="text-xs text-muted-foreground">CAPM 推导 WACC</div><div className="mt-1 text-xl font-bold text-primary">{capmWacc === null ? "待补输入" : `${capmWacc.toFixed(2)}%`}</div><div className="mt-1 text-[10px] text-muted-foreground">用于审计情景 WACC，不自动覆盖用户假设。</div></div></div>
            <div className="mt-3 flex flex-wrap items-end gap-3 text-sm"><label><span className={labelClass}>股价日期（手改价格后须重新核对）</span><input aria-label="股价日期" type="date" className={inputClass} value={draft.capitalInputs.currentPriceAsOf || ''} onChange={event=>setDraft({...draft,capitalInputs:{...draft.capitalInputs,currentPriceAsOf:event.target.value}})}/></label>
              <p aria-label="股价可比性" className="text-muted-foreground">{priceComparisonIssue(draft) || '仅比较同一时点的价格与模型价值，不代表未来收益。'}</p></div>
          </GlassCard>

          <section aria-label="股权桥接调整" className="border-y border-border py-4 text-sm">
            <h3 className="font-semibold">股权桥接调整 · 百万元</h3>
            <p className="my-2 text-muted-foreground">普通股价值 = 经营 EV − 有息债务 + 可用现金 + 非经营资产 − 少数股东权益 − 其他优先权益。下面项目均需核验，确认不适用时填 0。</p>
            <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
              <label><span className={labelClass}>现金口径</span><select aria-label="现金口径" className={inputClass} value={draft.capitalInputs.cashBasis || 'adjusted'} onChange={event=>{
                const capitalEvidence={...draft.capitalEvidence};
                for(const field of ['cashM','excludedCashM'] as const){
                  const evidence=capitalEvidence[field];
                  if(evidence)capitalEvidence[field]={...evidence,inputSnapshot:JSON.stringify({invalidatedBy:'cash-basis-change'})};
                }
                setDraft({...draft,capitalEvidence,capitalInputs:{...draft.capitalInputs,cashBasis:event.target.value as 'adjusted'|'gross'}});
                setMessage('现金口径已切换，原金额与原文保留，请核对现金输入并重新确认；未自动换算金额');
              }}><option value="adjusted">已调整可用现金净额</option><option value="gross">原始现金余额，再扣剔除额</option></select></label>
              {draft.capitalInputs.cashBasis === 'gross' && <label><span className={labelClass}>需剔除现金</span><input aria-label="需剔除现金" type="number" min="0" className={inputClass} value={draft.capitalInputs.excludedCashM ?? ''} onChange={event=>setDraft({...draft,capitalInputs:{...draft.capitalInputs,excludedCashM:parseNumber(event.target.value)}})}/></label>}
              {([['nonOperatingAssetsM','非经营性资产'],['minorityInterestM','少数股东权益调整'],['otherClaimsM','其他优先权益']] as const).map(([field,label])=><label key={field}><span className={labelClass}>{label}</span><input aria-label={label} type="number" min="0" className={inputClass} value={draft.capitalInputs[field] ?? ''} onChange={event=>setDraft({...draft,capitalInputs:{...draft.capitalInputs,[field]:parseNumber(event.target.value)}})}/></label>)}
            </div>
            <p className="mt-3" aria-label="可用现金试算">可用现金试算：{formatNumber(eligibleCash(draft))} 百万元 · {draft.capitalInputs.cashBasis === 'gross' ? '原始余额减剔除额；剔除额不能超过余额' : '沿用已调整金额，不再次剔除现金'}</p>
            <p className="mt-1 text-muted-foreground">非经营资产只加回未含于现金或经营预测的价值；少数股东权益按与预测一致的范围估值，不直接照搬账面值；其他索偿不能与债务或稀释股数重复计入。具体依据在下方逐项核验。</p>
          </section>

          <ValuationCapitalEvidence key={`${draft.id}:${editorVersion}`} model={draft} disabled={busy} editorDirty={editorDirty} onDirtyChange={setEditorDirty} onEditSnapshot={setEditorSnapshot}
            requestDiscard={run=>requestAction('资本编辑尚未暂存，继续会放弃本次未暂存修改；已暂存和已采用的内容不变。需要保留请取消并先暂存。',run)} onSaveDraft={async(field,input)=>{
            const next=stageCapitalEvidence(draftRef.current,field,input);
            draftRef.current=next;setDraft(next);
            return Boolean(await save(next));
          }} onDiscardDraft={async field=>{
            const capitalEvidenceDrafts={...draftRef.current.capitalEvidenceDrafts};delete capitalEvidenceDrafts[field];
            const next={...draftRef.current,capitalEvidenceDrafts};draftRef.current=next;setDraft(next);
            return Boolean(await save(next));
          }} onAttach={(field, input) => {
            try { setDraft(attachCapitalEvidence(draft, field, input)); setMessage('资本依据已关联到草稿，请保存；这是人工确认，不是系统审计'); return true; }
            catch (error) { setMessage(error instanceof Error ? error.message : '关联失败'); return false; }
          }} onRevoke={field => {
            const capitalEvidence = { ...draft.capitalEvidence }; delete capitalEvidence[field];
            setDraft({ ...draft, capitalEvidence }); setMessage('已撤销资本确认，数值与原来源档案保留；请保存');
          }} />

          <GlassCard>
            <div className="mb-4 flex flex-wrap items-center justify-between gap-3"><div><div className="text-xs font-semibold uppercase tracking-[0.14em] text-primary">Scenario assumptions</div><h2 className="mt-1 text-lg font-bold">三情景预测驱动</h2></div><div className="flex rounded-lg border border-border bg-muted/25 p-1">{draft.scenarios.map((scenario) => <button key={scenario.id} onClick={() => setDraft({ ...draft, selectedScenario: scenario.id })} className={cn("rounded-md px-3 py-1.5 text-xs font-semibold", draft.selectedScenario === scenario.id ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:text-foreground")}>{scenario.label}</button>)}</div></div>
            <div aria-label="情景确认状态" className="mb-3 border-l-2 border-primary pl-3 text-sm">
              <p>{reviewStatus.assumptionsConfirmed ? `当前情景已人工确认 · ${activeScenario.review?.confirmedAt}` : '当前情景尚未确认或输入已变化'}</p>
              <p className="mt-1 text-muted-foreground">{assumptionIssue || '确认表示你已核对当前基期、逐年驱动、WACC、终值增长和研究依据，不代表系统批准估值。修改后需重新确认。'}</p>
              <button className="mr-2 mt-2 rounded border border-border px-3 py-1.5" disabled={saving} onClick={() => {
                try { setDraft(alignValuationYears(draft)); setMessage('已对齐估值基期末和预测年度，增长率等数值未变；请重新确认情景及日期变化后的资本依据'); }
                catch (error) { setMessage(error instanceof Error ? error.message : '对齐失败'); }
              }}>按历史基期对齐预测年度</button>
              {reviewStatus.assumptionsConfirmed ? <button className="mt-2 rounded border border-border px-3 py-1.5" disabled={saving} onClick={() => updateScenario(activeScenario.id, { review: undefined })}>撤销当前情景确认</button>
                : <button className="mt-2 rounded border border-border px-3 py-1.5 disabled:opacity-50" disabled={saving || Boolean(assumptionIssue)} onClick={() => {
                  try { setDraft(confirmScenario(draft)); setMessage('当前情景假设已确认到草稿，请保存；其他情景仍需单独确认'); }
                  catch (error) { setMessage(error instanceof Error ? error.message : '确认失败'); }
                }}>确认当前情景假设</button>}
            </div>
            <div className="grid gap-3 md:grid-cols-3"><label><span className={labelClass}>情景 WACC %</span><input aria-label="情景 WACC" type="number" step="0.1" className={inputClass} value={activeScenario.waccPct} onChange={(event) => updateScenario(activeScenario.id, { waccPct: Number(event.target.value) || 0 })} /></label><label><span className={labelClass}>终值增长 %</span><input aria-label="终值增长" type="number" step="0.1" className={inputClass} value={activeScenario.terminalGrowthPct} onChange={(event) => updateScenario(activeScenario.id, { terminalGrowthPct: Number(event.target.value) || 0 })} /></label><label><span className={labelClass}>情景依据</span><input aria-label="情景依据" className={inputClass} value={activeScenario.rationale} onChange={(event) => updateScenario(activeScenario.id, { rationale: event.target.value })} /></label></div>
            <div className="mt-4 overflow-x-auto"><table className="w-full min-w-[760px] text-xs"><thead className="text-muted-foreground"><tr className="border-b border-border"><th className="px-2 py-2 text-left">驱动</th>{activeScenario.drivers.map((driver) => <th key={driver.year} className="px-2 py-2 text-right">{driver.year}E</th>)}</tr></thead><tbody>{([
              ["revenueGrowthPct", "收入增长 %"], ["ebitMarginPct", "EBIT 率 %"], ["taxRatePct", "税率 %"], ["daPctRevenue", "D&A / 收入 %"], ["capexPctRevenue", "CapEx / 收入 %"], ["nwcPctDeltaRevenue", "ΔNWC / Δ收入 %"],
            ] as const).map(([field, label]) => <tr key={field} className="border-b border-border/60"><td className="px-2 py-2 font-medium">{label}</td>{activeScenario.drivers.map((driver, index) => <td key={driver.year} className="px-2 py-2 text-right">{driverCell(driver, field, (value) => updateDriver(activeScenario.id, index, field, value))}</td>)}</tr>)}</tbody></table></div>
          </GlassCard>

          <GlassCard>
            <div className="mb-4"><div className="text-xs font-semibold uppercase tracking-[0.14em] text-primary">FCF build</div><h2 className="mt-1 text-lg font-bold">自由现金流试算与折现</h2></div>
            <div className="overflow-x-auto"><table className="w-full min-w-[980px] text-xs"><thead className="text-muted-foreground"><tr className="border-b border-border"><th className="px-2 py-2 text-left">年度</th><th className="px-2 py-2 text-right">收入</th><th className="px-2 py-2 text-right">增长</th><th className="px-2 py-2 text-right">EBIT</th><th className="px-2 py-2 text-right">NOPAT</th><th className="px-2 py-2 text-right">D&A</th><th className="px-2 py-2 text-right">CapEx</th><th className="px-2 py-2 text-right">ΔNWC</th><th className="px-2 py-2 text-right">UFCF</th><th className="px-2 py-2 text-right">折现因子</th><th className="px-2 py-2 text-right">PV FCF</th></tr></thead><tbody>{calculated.projections.map((row) => <tr key={row.year} className="border-b border-border/60"><td className="px-2 py-2 font-semibold">{row.year}E</td><td className="px-2 py-2 text-right">{formatNumber(row.revenue)}</td><td className="px-2 py-2 text-right">{row.revenueGrowthPct.toFixed(1)}%</td><td className="px-2 py-2 text-right">{formatNumber(row.ebit)}</td><td className="px-2 py-2 text-right">{formatNumber(row.nopat)}</td><td className="px-2 py-2 text-right">{formatNumber(row.depreciationAmortization)}</td><td className="px-2 py-2 text-right">{formatNumber(row.capex)}</td><td className="px-2 py-2 text-right">{formatNumber(row.changeNwc)}</td><td className="px-2 py-2 text-right font-semibold text-primary">{formatNumber(row.unleveredFcf)}</td><td className="px-2 py-2 text-right">{formatNumber(row.discountFactor, 4)}</td><td className="px-2 py-2 text-right">{formatNumber(row.pvFcf)}</td></tr>)}{calculated.projections.length === 0 && <tr><td colSpan={11} className="px-3 py-10 text-center text-muted-foreground">录入历史收入基期后自动生成完整 FCF 预测。</td></tr>}</tbody></table></div>
          </GlassCard>

          <div className="grid gap-4 2xl:grid-cols-[1fr_1.25fr]">
            <GlassCard>
              <div className="mb-4"><div className="text-xs font-semibold uppercase tracking-[0.14em] text-primary">Valuation bridge</div><h2 className="mt-1 text-lg font-bold">企业价值到每股价值（研究试算）</h2></div>
              <div className="space-y-2 text-sm">{([
                ["显式期 FCF 现值", calculated.result.pvExplicitFcfM], ["终值现值", calculated.result.pvTerminalValueM], ["经营企业价值", calculated.result.enterpriseValueM],
                ["减：有息债务", calculated.capitalInputs.totalDebtM], ["加：可用现金", calculated.result.eligibleCashM ?? null],
                ["加：非经营性资产", calculated.capitalInputs.nonOperatingAssetsM ?? null], ["减：少数股东权益", calculated.capitalInputs.minorityInterestM ?? null],
                ["减：其他优先权益", calculated.capitalInputs.otherClaimsM ?? null], ["普通股股权价值", calculated.result.equityValueM],
              ] as const).map(([label, value]) => <div key={label} className="flex items-center justify-between border-b border-border/60 py-2"><span className="text-muted-foreground">{label}</span><span className="font-semibold">{formatNumber(value)}</span></div>)}<div className="mt-3 rounded-xl border border-primary/25 bg-primary/8 p-4"><div className="flex items-center justify-between"><span className="font-semibold">每股试算价值</span><span aria-label="每股试算结果" className="text-2xl font-bold text-primary">{calculated.result.impliedPrice === null ? "待补齐与确认" : formatNumber(calculated.result.impliedPrice, 2)}</span></div><div className="mt-2 flex justify-between text-xs text-muted-foreground"><span>当前价格 {formatNumber(calculated.result.currentPrice, 2)}</span><span>模型差异 {calculated.result.impliedReturnPct === null ? "—" : `${calculated.result.impliedReturnPct.toFixed(1)}%`}</span></div></div></div>
            </GlassCard>

            <GlassCard>
              <div className="mb-4"><div className="text-xs font-semibold uppercase tracking-[0.14em] text-primary">Sensitivity</div><h2 className="mt-1 text-lg font-bold">WACC × 终值增长敏感性</h2><p className="mt-1 text-xs text-muted-foreground">5×5 奇数矩阵，中心格严格对应当前情景基准值；每格完整重算 DCF。</p></div>
              <div className="overflow-x-auto"><table className="w-full min-w-[560px] text-center text-xs"><thead><tr><th className="px-2 py-2 text-left text-muted-foreground">WACC \ g</th>{calculated.sensitivity.terminalGrowthPct.map((growth, column) => <th key={column} className="px-2 py-2 text-muted-foreground">{growth.toFixed(1)}%</th>)}</tr></thead><tbody>{calculated.sensitivity.waccPct.map((wacc, row) => <tr key={row}><th className="px-2 py-2 text-left text-muted-foreground">{wacc.toFixed(1)}%</th>{calculated.sensitivity.impliedPrices[row]?.map((value, column) => <td key={column} className={cn("border border-border/70 px-2 py-2", row === 2 && column === 2 ? "bg-primary text-primary-foreground font-bold" : "bg-muted/20")}>{formatNumber(value, 2)}</td>)}</tr>)}</tbody></table></div>
            </GlassCard>
          </div>

          <div className="grid gap-4 2xl:grid-cols-3">
            <GlassCard><div className="mb-3 flex items-center gap-2"><SearchCheck className="h-4 w-4 text-primary" /><h2 className="font-bold">模型审计</h2></div><div className="space-y-2">{calculated.auditChecks.map((check) => <div key={check.id} className={cn("rounded-lg border px-3 py-2", CHECK_STYLE[check.status])}><div className="flex items-center gap-1.5 text-xs font-semibold">{check.status === "pass" ? <CheckCircle2 className="h-3.5 w-3.5" /> : <CircleAlert className="h-3.5 w-3.5" />}{check.label}</div><div className="mt-1 text-[11px] opacity-85">{check.message}</div></div>)}</div></GlassCard>
            <GlassCard><div className="mb-3 flex items-center gap-2"><Database className="h-4 w-4 text-primary" /><h2 className="font-bold">来源与截至时间</h2></div><div className="max-h-72 space-y-2 overflow-y-auto">{calculated.sourceMaterials.length === 0 && <p className="text-xs text-muted-foreground">从已保存财报接入收入，或手工关联来源；刷新股价不补财务。</p>}{calculated.sourceMaterials.map((source) => <div key={source.id} className="rounded-lg bg-muted/35 px-3 py-2 text-xs"><div className="font-semibold">{source.label}</div>{source.url && /^https?:\/\//.test(source.url) && <a href={source.url} target="_blank" rel="noreferrer" className="text-primary underline">查看来源原文</a>}<div className="mt-1 text-[11px] text-muted-foreground">{source.source} · {source.asOf} · {source.status}</div></div>)}</div></GlassCard>
            <GlassCard><div className="mb-3 flex items-center gap-2"><CircleAlert className="h-4 w-4 text-primary" /><h2 className="font-bold">数据缺口与核验事项</h2></div><textarea className={`${inputClass} min-h-64 resize-y`} value={draft.gaps.join("\n")} onChange={(event) => setDraft({ ...draft, gaps: event.target.value.split("\n").slice(0, 30) })} placeholder="每行一项" /></GlassCard>
          </div>

          <Disclaimer />
        </div>
      </div>
      </fieldset>
    </div>
  );
}
