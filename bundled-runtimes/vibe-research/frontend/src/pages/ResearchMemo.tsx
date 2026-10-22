import { useEffect, useMemo, useRef, useState } from "react";
import {
  Archive,
  BookOpenCheck,
  FileSymlink,
  ExternalLink,
  Link2,
  Plus,
  Save,
  ShieldCheck,
  Trash2,
} from "lucide-react";

import { Disclaimer } from "@/components/ui/Disclaimer";
import { GlassCard } from "@/components/ui/GlassCard";
import { PageHeader } from "@/components/ui/PageHeader";
import {
  blankResearchMemo,
  createResearchId,
  emptyResearchMemoWorkspace,
  hydrateResearchMemoWorkspace,
  persistResearchMemoWorkspace,
  researchMemoScope,
  ResearchMemoStorageError,
  researchReferenceCheck,
  researchReferenceFromEntry,
  type ArtifactKind,
  type ResearchArtifactReference,
  type ResearchBias,
  type ResearchConviction,
  type ResearchMemo,
  type ResearchMemoSource,
  type ResearchMemoWorkspace,
  type ResearchMemoSession,
  type ResearchRisk,
} from "@/lib/researchMemo";
import { ARCHIVE_KIND_LABELS, loadResearchArchive, researchArchiveSourceUrl, ResearchArchiveError, type ResearchArchiveEntry, type ResearchArchiveIndex } from "@/lib/researchArchive";
import {
  publishVibeDeskContext,
  registerVibeDeskContextProvider,
  subscribeVibeDeskEvent,
  subscribeVibeDeskConfig,
  type VibeDeskPageContext,
} from "@/lib/vibedesk";

const inputClass = "w-full rounded-lg border border-border bg-card/70 px-3 py-2 text-sm text-foreground outline-none transition focus:border-primary/60 focus:ring-2 focus:ring-primary/15";
const labelClass = "mb-1.5 block text-xs font-semibold text-muted-foreground";
const areaClass = `${inputClass} min-h-24 resize-y`;

const BIAS_LABEL: Record<ResearchBias, string> = {
  constructive: "偏积极研究",
  neutral: "中性研究",
  cautious: "偏谨慎研究",
  watch: "观察中",
};
const CONVICTION_LABEL: Record<ResearchConviction, string> = { high: "高", medium: "中", low: "低" };
const KIND_LABEL: Record<ArtifactKind, string> = {
  thesis: "投资逻辑", earnings: "财报", "peer-comparison": "同业", valuation: "估值",
  catalyst: "催化剂", "industry-chain": "产业链", macro: "宏观", news: "资讯", other: "其他",
};

function copyMemo(memo: ResearchMemo) { return structuredClone(memo); }
function currencyForMarket(market: string) { return market === "US" ? "USD" : market === "HK" ? "HKD" : "CNY"; }
function splitLines(value: string) { return value.split("\n").map((item) => item.trim()).filter(Boolean); }
function joinLines(value: string[]) { return value.join("\n"); }

function memoContext(workspace: ResearchMemoWorkspace, memo: ResearchMemo, dirty: boolean, storage: { mode?: string; state: string; revision?: number; error: string }): VibeDeskPageContext {
  return {
    view: { id: "research-memo", title: "研究备忘录" },
    visibleBlocks: [
      { id: "executive-view", type: "research-synthesis", title: "执行研究结论" },
      { id: "artifact-links", type: "artifact-references", title: "关联研究档案" },
      { id: "drivers-scenarios", type: "scenario-analysis", title: "关键驱动与三情景" },
      { id: "risks-catalysts", type: "falsification", title: "风险、催化剂与证伪" },
      { id: "monitoring", type: "monitoring-dashboard", title: "跟踪面板" },
      { id: "sources-versions", type: "evidence-ledger", title: "来源与版本记录" },
    ],
    selection: {
      market: memo.security.market,
      symbol: memo.security.symbol,
      name: memo.security.name,
      memoId: memo.id,
      status: memo.status,
    },
    filters: { asOf: memo.boundary.asOf, horizon: memo.boundary.horizon, nextReviewAt: memo.nextReviewAt },
    data: {
      asOf: memo.boundary.asOf || undefined,
      source: workspace.schemaVersion,
      freshness: memo.sources.some((source) => source.status === "stale") ? "stale" : "unknown",
      summary: {
        researchBoundary: memo.boundary,
        executiveView: memo.executiveView,
        linkedArtifacts: memo.linkedArtifacts,
        keyDrivers: memo.keyDrivers,
        scenarios: memo.scenarios,
        catalysts: memo.catalysts,
        risks: memo.risks,
        monitoring: memo.monitoring,
        sources: memo.sources,
        gaps: memo.gaps,
        versions: memo.versions,
        unsavedChanges: dirty,
        storage,
      },
    },
    actions: [
      { id: "memo.audit-evidence", label: "审计来源与未核验信息", available: true },
      { id: "memo.challenge-thesis", label: "从反方挑战研究结论", available: Boolean(memo.executiveView.coreThesis) },
      { id: "memo.refresh-artifacts", label: "刷新关联研究档案", available: memo.linkedArtifacts.length > 0 },
      { id: "memo.prepare-committee", label: "整理为投委会讨论材料", available: memo.status !== "draft" },
    ],
    tasks: [],
  };
}

export function ResearchMemo() {
  const [scope, setScope] = useState(researchMemoScope);
  useEffect(() => {
    const update = () => setScope(researchMemoScope());
    const unsubscribe = subscribeVibeDeskConfig(update);
    update();
    return unsubscribe;
  }, []);
  return <ResearchMemoEditor key={scope} />;
}

function ResearchMemoEditor() {
  const initial = useMemo(emptyResearchMemoWorkspace, []);
  const [session, setSession] = useState<ResearchMemoSession | null>(null);
  const workspace = session?.workspace || initial;
  const [selectedId, setSelectedId] = useState("__new__");
  const [draft, setDraft] = useState(blankResearchMemo);
  const baseline = useRef(JSON.stringify(draft));
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [needsReload, setNeedsReload] = useState(false);
  const [readAttempt, setReadAttempt] = useState(0);
  const controller = useRef<AbortController | null>(null);
  const [versionNote, setVersionNote] = useState("");
  const [archive, setArchive] = useState<ResearchArchiveIndex | null>(null);
  const [archiveError, setArchiveError] = useState("");
  const [discovering, setDiscovering] = useState(false);
  const [artifactQuery, setArtifactQuery] = useState("");
  const artifacts = (archive?.entries || []).filter((entry) => !(entry.sourceModId === "research-memo" && entry.artifactId === draft.id)
    && `${entry.title} ${entry.artifactId} ${entry.security?.symbol || ""} ${entry.security?.name || ""}`.toLowerCase().includes(artifactQuery.trim().toLowerCase()));
  const referenceChecks = draft.linkedArtifacts.map((reference) => ({ reference, ...researchReferenceCheck(reference, archiveError || discovering ? null : archive) }));
  const dirty = baseline.current !== JSON.stringify(draft) || Boolean(versionNote.trim());
  const busy = loading || saving;
  const latest = useRef({ dirty, busy, selectedId });
  latest.current = { dirty, busy, selectedId };

  const showMemo = (memo?: ResearchMemo) => {
    const next = memo ? copyMemo(memo) : blankResearchMemo();
    baseline.current = JSON.stringify(next);
    setSelectedId(memo?.id || "__new__");
    setDraft(next);
    setVersionNote("");
  };

  useEffect(() => {
    const abort = new AbortController();
    controller.current = abort;
    setLoading(true);
    setDiscovering(false);
    setError("");
    void hydrateResearchMemoWorkspace(abort.signal).then((value) => {
      if (abort.signal.aborted) return;
      setSession(value);
      setNeedsReload(false);
      showMemo(value.workspace.memos[0]);
      setArchive(null);
      setArchiveError("");
      setMessage("");
    }).catch((failure: unknown) => {
      if (!abort.signal.aborted) setError(failure instanceof ResearchMemoStorageError ? failure.message : "读取未确认，原记录未改动，请重试。");
    }).finally(() => {
      if (!abort.signal.aborted) setLoading(false);
    });
    return () => abort.abort();
  }, [readAttempt]);

  const storageState = { mode: session?.mode, state: loading ? "loading" : saving ? "saving" : error ? "error" : dirty ? "unsaved" : "loaded", revision: session?.mode === "desk" ? session.revision : undefined, error };
  const contextRef = useRef<VibeDeskPageContext>(memoContext(workspace, draft, dirty, storageState));
  contextRef.current = memoContext(workspace, draft, dirty, storageState);
  Object.assign(contextRef.current.data.summary!, {
    referenceChecks: referenceChecks.map(({ reference, source, ...check }) => ({ id: reference.id, ...check, observedRevision: source?.sourceRevision, observedUpdatedAt: source?.updatedAt })),
    archiveRead: { loading: discovering, error: archiveError, generatedAt: archive?.generatedAt, unavailableSources: archive?.unavailableSources, truncated: archive?.truncated },
  });
  useEffect(() => registerVibeDeskContextProvider(() => contextRef.current), []);
  useEffect(() => { void publishVibeDeskContext(); }, [draft, dirty, workspace, loading, saving, error, archive, archiveError, discovering]);
  useEffect(() => {
    const warn = (event: BeforeUnloadEvent) => {
      if (latest.current.dirty || latest.current.busy) { event.preventDefault(); event.returnValue = ""; }
    };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, []);
  useEffect(() => {
    const unsubscribe = subscribeVibeDeskEvent((event) => {
      if (event.event !== "security.selected") return;
      if (latest.current.busy || latest.current.dirty || latest.current.selectedId !== "__new__") {
        setMessage("收到新的证券选择。为保留当前研究对象和草稿，请先保存，再新建备忘录。");
        return;
      }
      const symbol = typeof event.payload.symbol === "string" ? event.payload.symbol.slice(0, 40).toUpperCase() : "";
      if (!symbol) return;
      const market = typeof event.payload.market === "string" ? event.payload.market.slice(0, 20).toUpperCase() : "CN";
      const name = typeof event.payload.name === "string" ? event.payload.name.slice(0, 120) : "";
      setDraft((current) => ({
        ...current,
        security: { ...current.security, market, symbol, name, currency: currencyForMarket(market) },
        boundary: { ...current.boundary, reportingCurrency: currencyForMarket(market) },
      }));
    });
    return () => { unsubscribe(); };
  }, []);

  const commit = async (next: ResearchMemoWorkspace) => {
    if (latest.current.busy || !session || !session.writable || needsReload) return null;
    latest.current.busy = true;
    setSaving(true);
    setError("");
    setMessage("");
    const signal = controller.current!.signal;
    try {
      const saved = await persistResearchMemoWorkspace(next, session, signal);
      if (signal.aborted) return null;
      setSession(saved);
      return saved;
    } catch (failure) {
      if (!signal.aborted) {
        setError(failure instanceof ResearchMemoStorageError ? failure.message : "保存未确认，草稿仍在；请先导出，再重新读取核对。");
        if (session.mode === "desk") setNeedsReload(true);
      }
      return null;
    } finally {
      if (!signal.aborted) { latest.current.busy = false; setSaving(false); }
    }
  };

  const reload = () => {
    if (busy || (dirty && !confirm("重新读取会替换当前未保存的草稿。请先导出保留，确定继续吗？"))) return;
    setLoading(true);
    setReadAttempt((attempt) => attempt + 1);
  };

  const exportDraft = () => {
    const url = URL.createObjectURL(new Blob([JSON.stringify({ ...workspace, memos: [draft], pendingVersionNote: versionNote }, null, 2)], { type: "application/json" }));
    const link = document.createElement("a");
    link.href = url;
    link.download = "research-memo-draft.json";
    link.click();
    window.setTimeout(() => URL.revokeObjectURL(url), 1_000);
    setMessage("已发起草稿导出，请确认浏览器下载完成；这不代表工作区已保存。");
  };

  const startNew = () => {
    if (dirty && !confirm("当前研究备忘录尚未保存，确定新建吗？")) return;
    showMemo();
    setMessage("");
    setVersionNote("");
  };

  const choose = (memo: ResearchMemo) => {
    if (dirty && !confirm("当前研究备忘录尚未保存，确定切换吗？")) return;
    showMemo(memo);
    setMessage("");
    setVersionNote("");
  };

  const save = async () => {
    const required = [
      [draft.title, "备忘录标题"], [draft.security.symbol, "证券代码"], [draft.security.name, "公司名称"],
      [draft.executiveView.conclusion, "研究结论"], [draft.executiveView.coreThesis, "核心论点"],
      [draft.executiveView.keyDebate, "关键争议"], [draft.executiveView.variantPerception, "差异认知"],
      [draft.executiveView.whatMayBeMissing, "市场可能遗漏"], [draft.executiveView.breakpoint, "逻辑断点"],
    ] as const;
    const missing = required.find(([value]) => !value.trim());
    if (missing) { setMessage(`请填写${missing[1]}`); return; }
    if (draft.scenarios.some((scenario) => !Number.isFinite(scenario.probabilityPct) || scenario.probabilityPct < 0 || scenario.probabilityPct > 100)) {
      setMessage("每个情景的概率必须在 0–100% 之间"); return;
    }
    const totalProbability = draft.scenarios.reduce((sum, scenario) => sum + scenario.probabilityPct, 0);
    if (Math.abs(totalProbability - 100) > 0.01) { setMessage("悲观、基准和乐观情景概率合计必须为 100%"); return; }
    const timestamp = new Date().toISOString();
    const isExisting = workspace.memos.some((item) => item.id === draft.id);
    const previousVersion = draft.versions[draft.versions.length - 1]?.version ?? 0;
    const nextVersion = isExisting ? previousVersion + 1 : Math.max(1, previousVersion);
    const versions = isExisting ? [...draft.versions, {
      version: nextVersion,
      createdAt: timestamp,
      summary: versionNote.trim() || `更新至第 ${nextVersion} 版`,
      changedSections: ["执行结论", "驱动与情景", "风险与跟踪"],
    }].slice(-100) : draft.versions;
    const saved: ResearchMemo = {
      ...draft,
      title: draft.title.trim(),
      status: draft.status === "draft" ? "current" : draft.status,
      security: {
        ...draft.security,
        market: draft.security.market.trim().toUpperCase(),
        symbol: draft.security.symbol.trim().toUpperCase(),
        name: draft.security.name.trim(),
        currency: draft.security.currency.trim().toUpperCase(),
      },
      boundary: { ...draft.boundary, disclosureLimits: draft.boundary.disclosureLimits.map((item) => item.trim()).filter(Boolean) },
      gaps: draft.gaps.map((item) => item.trim()).filter(Boolean),
      versions,
      updatedAt: timestamp,
    };
    const memos = isExisting ? workspace.memos.map((item) => item.id === saved.id ? saved : item) : [saved, ...workspace.memos];
    const result = await commit({ ...workspace, updatedAt: timestamp, memos });
    if (!result) return;
    showMemo(result.workspace.memos.find((memo) => memo.id === saved.id));
    setMessage(result.mode === "desk" ? "Desk 已确认保存" : "已保存到本机浏览器，未同步到 Desk");
  };

  const remove = async () => {
    if (selectedId === "__new__") { startNew(); return; }
    if (!confirm(`删除“${draft.title}”研究备忘录？`)) return;
    const memos = workspace.memos.filter((item) => item.id !== selectedId);
    const next = { ...workspace, updatedAt: new Date().toISOString(), memos };
    const result = await commit(next);
    if (!result) return;
    showMemo(result.workspace.memos[0]);
    setMessage(result.mode === "desk" ? "Desk 已确认删除该备忘录" : "已从本机档案删除该备忘录");
  };

  const discover = async () => {
    if (discovering || busy) return;
    const signal = controller.current!.signal;
    setDiscovering(true);
    setArchiveError("");
    try {
      const result = await loadResearchArchive([], signal);
      if (signal.aborted) return;
      setArchive(result);
    } catch (failure) {
      if (!signal.aborted) setArchiveError(failure instanceof ResearchArchiveError ? failure.message : "档案读取未确认，已有引用未改动。");
    } finally {
      if (!signal.aborted) setDiscovering(false);
    }
  };

  const linkArtifact = (entry: ResearchArchiveEntry) => {
    if (archiveError || discovering || draft.linkedArtifacts.some((item) => item.sourceModId === entry.sourceModId && item.artifactId === entry.artifactId)) return;
    setDraft({ ...draft, linkedArtifacts: [...draft.linkedArtifacts, researchReferenceFromEntry(entry)].slice(0, 50) });
  };

  const addManualArtifact = () => {
    const artifact: ResearchArtifactReference = {
      id: createResearchId("artifact"), kind: "other", sourceModId: "research-notes",
      artifactId: "待填写档案ID", title: "待命名研究档案", status: "unverified",
      note: "手工引用；请补充来源 Mod、档案 ID 和截至日期。",
    };
    setDraft({ ...draft, linkedArtifacts: [...draft.linkedArtifacts, artifact].slice(0, 50) });
  };

  const editReference = (id: string, patch: Partial<ResearchArtifactReference>) => setDraft((current) => ({
    ...current,
    linkedArtifacts: current.linkedArtifacts.map((item) => item.id === id
      ? { ...item, ...patch, status: "unverified", sourceRevision: undefined, sourceUpdatedAt: undefined }
      : item),
  }));

  const addSource = () => {
    const source: ResearchMemoSource = {
      id: createResearchId("source"), label: "待命名来源", kind: "user", claimType: "inference",
      asOf: draft.boundary.asOf, status: "available", note: "请区分事实、管理层指引、市场预期和研究推断。",
    };
    setDraft({ ...draft, sources: [...draft.sources, source].slice(0, 150) });
  };

  const addCatalyst = () => setDraft({
    ...draft,
    catalysts: [...draft.catalysts, {
      id: createResearchId("catalyst"), title: "待补充催化剂", window: "待确认",
      expectedPath: "待补充事件如何影响当前研究结论", confirmationConditions: ["待补充确认条件"],
      invalidationConditions: ["待补充失效条件"],
    }].slice(0, 20),
  });

  return (
    <div className="mx-auto max-w-[1500px] px-4 py-6 md:px-6">
      <PageHeader
        title="研究备忘录"
        subtitle="用引用而非复制收敛投资逻辑、财报、同业、估值、催化剂与反方证据；保留来源、截至日期和版本变化。"
        actions={<>
          <button disabled={busy} onClick={startNew} className="inline-flex items-center gap-1.5 rounded-lg border border-border bg-card/70 px-3 py-2 text-sm disabled:opacity-50"><Plus className="h-4 w-4" />新建</button>
          <button disabled={busy || !session?.writable || needsReload} onClick={save} className="inline-flex items-center gap-1.5 rounded-lg bg-primary px-3 py-2 text-sm font-semibold text-primary-foreground disabled:opacity-50"><Save className="h-4 w-4" />{saving ? "保存中…" : "保存"}</button>
        </>}
      />

      <div className="mb-4 flex flex-wrap items-center gap-3 text-xs text-muted-foreground">
        <span role="status">{loading ? "正在读取备忘录…" : saving ? "正在等待保存确认…" : session ? `${session.mode === "desk" ? "Desk 工作区" : "本机浏览器"} · ${error ? "存储未确认" : dirty ? "有未保存修改" : "已读取档案"}${!session.writable ? " · 只读" : ""}` : "尚未读取档案"}</span>
        <button disabled={busy} onClick={reload} className="rounded-lg border border-border px-3 py-1.5 disabled:opacity-50">重新读取</button>
        <button disabled={busy} onClick={exportDraft} className="rounded-lg border border-border px-3 py-1.5 disabled:opacity-50">导出当前草稿</button>
      </div>
      {error && <div role="alert" className="mb-4 rounded-lg border border-destructive/40 bg-destructive/5 px-3 py-2 text-sm">{error}</div>}
      {message && <div role="status" className="mb-4 rounded-lg border border-primary/25 bg-primary/8 px-3 py-2 text-sm text-foreground">{message}</div>}

      <fieldset disabled={busy} aria-busy={busy} className="m-0 grid min-w-0 gap-5 border-0 p-0 xl:grid-cols-[250px_minmax(0,1fr)]">
        <aside className="space-y-4">
          <GlassCard className="p-3">
            <div className="mb-2 flex items-center justify-between"><h2 className="text-sm font-bold">备忘录档案</h2><span className="text-xs text-muted-foreground">{workspace.memos.length}</span></div>
            <div className="space-y-1.5">
              {workspace.memos.map((memo) => (
                <button key={memo.id} onClick={() => choose(memo)} className={`w-full rounded-lg border px-3 py-2 text-left text-sm ${memo.id === selectedId ? "border-primary/40 bg-primary/10" : "border-border bg-card/40"}`}>
                  <div className="truncate font-semibold">{memo.title}</div>
                  <div className="mt-1 truncate text-xs text-muted-foreground">{memo.security.symbol} · v{memo.versions[memo.versions.length - 1]?.version ?? 1}</div>
                </button>
              ))}
              {!workspace.memos.length && <p className="rounded-lg border border-dashed border-border p-3 text-xs text-muted-foreground">还没有备忘录。先建立研究边界，再收敛结论。</p>}
            </div>
          </GlassCard>
          <GlassCard className="p-3 text-xs text-muted-foreground">
            <div className="mb-2 flex items-center gap-2 font-semibold text-foreground"><ShieldCheck className="h-4 w-4 text-primary" />中立研究边界</div>
            保存研究偏向、确信度、情景和证伪条件，不生成买卖评级、仓位或个性化建议。估值结果只引用来源模型。
          </GlassCard>
        </aside>

        <main className="space-y-5">
          <GlassCard>
            <div className="mb-4 flex items-center justify-between gap-3"><h2 className="flex items-center gap-2 font-bold"><BookOpenCheck className="h-4 w-4 text-primary" />研究边界与执行结论</h2><button disabled={!session?.writable || needsReload} onClick={remove} className="text-muted-foreground hover:text-destructive disabled:opacity-50" aria-label="删除备忘录"><Trash2 className="h-4 w-4" /></button></div>
            <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-4">
              <label><span className={labelClass}>备忘录标题</span><input aria-label="备忘录标题" className={inputClass} value={draft.title} onChange={(event) => setDraft({ ...draft, title: event.target.value })} /></label>
              <label><span className={labelClass}>证券代码</span><input aria-label="证券代码" className={inputClass} value={draft.security.symbol} onChange={(event) => setDraft({ ...draft, security: { ...draft.security, symbol: event.target.value } })} /></label>
              <label><span className={labelClass}>公司名称</span><input aria-label="公司名称" className={inputClass} value={draft.security.name} onChange={(event) => setDraft({ ...draft, security: { ...draft.security, name: event.target.value } })} /></label>
              <label><span className={labelClass}>截至日期</span><input type="date" className={inputClass} value={draft.boundary.asOf} onChange={(event) => setDraft({ ...draft, boundary: { ...draft.boundary, asOf: event.target.value } })} /></label>
              <label><span className={labelClass}>研究偏向（非评级）</span><select className={inputClass} value={draft.executiveView.bias} onChange={(event) => setDraft({ ...draft, executiveView: { ...draft.executiveView, bias: event.target.value as ResearchBias } })}>{Object.entries(BIAS_LABEL).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
              <label><span className={labelClass}>确信度</span><select className={inputClass} value={draft.executiveView.conviction} onChange={(event) => setDraft({ ...draft, executiveView: { ...draft.executiveView, conviction: event.target.value as ResearchConviction } })}>{Object.entries(CONVICTION_LABEL).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
              <label><span className={labelClass}>下一次复核</span><input type="date" className={inputClass} value={draft.nextReviewAt} onChange={(event) => setDraft({ ...draft, nextReviewAt: event.target.value })} /></label>
              <label><span className={labelClass}>报告币种</span><input className={inputClass} value={draft.security.currency} onChange={(event) => setDraft({ ...draft, security: { ...draft.security, currency: event.target.value }, boundary: { ...draft.boundary, reportingCurrency: event.target.value } })} /></label>
            </div>
            <div className="mt-4 grid gap-4 lg:grid-cols-2">
              {([
                ["研究结论", "conclusion", "先给当前最重要的研究判断，不写公司简介。"],
                ["核心论点", "coreThesis", "用 3–5 句说明价值驱动与判断链路。"],
                ["关键争议", "keyDebate", "当前最需要讨论的分歧是什么？"],
                ["差异认知", "variantPerception", "事实、预期与研究推断在哪些地方存在偏差？"],
                ["市场可能遗漏", "whatMayBeMissing", "哪些变量或传导链可能尚未充分反映？"],
                ["逻辑断点", "breakpoint", "什么可观察事实会迫使重新研究或作废当前判断？"],
              ] as const).map(([label, key, placeholder]) => (
                <label key={key}><span className={labelClass}>{label}</span><textarea aria-label={label} className={areaClass} placeholder={placeholder} value={draft.executiveView[key]} onChange={(event) => setDraft({ ...draft, executiveView: { ...draft.executiveView, [key]: event.target.value } })} /></label>
              ))}
            </div>
          </GlassCard>

          <GlassCard>
            <div className="mb-4 flex flex-wrap items-center justify-between gap-2"><h2 className="flex items-center gap-2 font-bold"><FileSymlink className="h-4 w-4 text-primary" />关联研究档案</h2><div className="flex flex-wrap gap-2"><button disabled={!session || discovering} onClick={discover} className="rounded-lg border border-border px-3 py-1.5 text-xs disabled:opacity-50">{discovering ? "正在核对…" : session?.mode === "desk" ? "发现 / 核对工作区档案" : "发现本机缓存"}</button><button disabled={draft.linkedArtifacts.length >= 50} onClick={addManualArtifact} className="rounded-lg border border-border px-3 py-1.5 text-xs disabled:opacity-50">手工引用</button></div></div>
            <p className="mb-3 text-xs text-muted-foreground">{session?.mode === "desk" ? "仅发现当前授权工作区的档案。来源变化不会自动改写引用或研究结论；确认后采纳，再保存备忘录。" : "本机旧缓存的工作区归属与资料时效尚未核验，引用前请确认来源。"} 索引版本一致不代表证据内容已核验。</p>
            {archiveError && <p role="alert" className="mb-3 rounded-lg border border-destructive/40 p-3 text-sm">{archiveError}</p>}
            {archive && <div className="mb-4 space-y-3">
              <div className="text-xs text-muted-foreground">索引读取时间：{archive.generatedAt} · 共 {archive.entries.length} 项 · 匹配 {artifacts.length} 项</div>
              {(archive.truncated || !archive.unavailableSources || archive.unavailableSources.length > 0) && <p className="text-xs text-muted-foreground">覆盖不完整，未找到不等于已删除。{archive.unavailableSources?.length ? ` 未读取来源：${archive.unavailableSources.join("、")}` : " 本机缓存或截断结果不能证明全量覆盖。"}</p>}
              <input aria-label="筛选研究档案" className={inputClass} placeholder="搜索标题、证券或档案 ID" value={artifactQuery} onChange={(event) => setArtifactQuery(event.target.value)} />
              <div className="grid max-h-80 gap-2 overflow-y-auto md:grid-cols-2">{artifacts.map((artifact) => {
                const linked = draft.linkedArtifacts.some((item) => item.sourceModId === artifact.sourceModId && item.artifactId === artifact.artifactId);
                return <button key={artifact.id} disabled={linked || discovering || Boolean(archiveError) || draft.linkedArtifacts.length >= 50} onClick={() => linkArtifact(artifact)} className="min-w-0 break-words rounded-lg border border-border bg-muted/20 p-3 text-left text-xs disabled:opacity-50">
                  <span className="font-semibold text-foreground">{ARCHIVE_KIND_LABELS[artifact.kind]} · {artifact.title}{linked ? " · 已引用" : " · 添加引用"}</span>
                  <span className="mt-1 block text-muted-foreground">{artifact.sourceModId} / {artifact.artifactId}</span>
                  <span className="mt-1 block text-muted-foreground">{artifact.security?.symbol} {artifact.security?.name} · 数据截至 {artifact.asOf || "未知"} · 索引版本 {artifact.sourceRevision ?? "未知"}</span>
                </button>;
              })}</div>
              {!artifacts.length && <p className="text-xs text-muted-foreground">当前结果没有匹配档案，请调整搜索或核对来源范围。</p>}
            </div>}
            <div className="space-y-3">{referenceChecks.map(({ reference: artifact, state, label, source }) => <div key={artifact.id} className="min-w-0 space-y-3 rounded-xl border border-border bg-muted/15 p-3">
              <div className="flex flex-wrap items-center justify-between gap-2 text-xs"><span>{artifact.status === "unverified" ? "待核验 · " : ""}{label}</span><div className="flex flex-wrap gap-3">
                {source && <a className="inline-flex items-center gap-1 text-primary" href={researchArchiveSourceUrl(source)} target="_blank" rel="noopener noreferrer">打开来源模块<ExternalLink className="h-3 w-3" /></a>}
                {source && state !== "current" && <button disabled={discovering || Boolean(archiveError)} onClick={() => setDraft((current) => ({ ...current, linkedArtifacts: current.linkedArtifacts.map((item) => item.id === artifact.id ? researchReferenceFromEntry(source, item) : item) }))} className="text-primary disabled:opacity-50">{source.sourceRevision ? "采纳当前引用版本" : "更新引用信息（未核验）"}</button>}
                <button aria-label={`移除引用 ${artifact.title}`} onClick={() => setDraft({ ...draft, linkedArtifacts: draft.linkedArtifacts.filter((item) => item.id !== artifact.id) })} className="text-muted-foreground hover:text-destructive"><Trash2 className="h-4 w-4" /></button>
              </div></div>
              <div className="grid gap-2 md:grid-cols-2">
                <label><span className={labelClass}>引用类型</span><select className={inputClass} value={artifact.kind} onChange={(event) => editReference(artifact.id, { kind: event.target.value as ArtifactKind })}>{Object.entries(KIND_LABEL).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
                <label><span className={labelClass}>来源 Mod ID</span><input className={inputClass} value={artifact.sourceModId} onChange={(event) => editReference(artifact.id, { sourceModId: event.target.value })} /></label>
                <label><span className={labelClass}>档案 ID</span><input className={inputClass} value={artifact.artifactId} onChange={(event) => editReference(artifact.id, { artifactId: event.target.value })} /></label>
                <label><span className={labelClass}>引用标题</span><input className={inputClass} value={artifact.title} onChange={(event) => editReference(artifact.id, { title: event.target.value })} /></label>
              </div>
              <div className="break-words text-xs text-muted-foreground">已引用：版本 {artifact.sourceRevision ?? "未知"} · 修改时间 {artifact.sourceUpdatedAt || "未知"} · 数据截至 {artifact.asOf || "未知"}{source && <><br />当前索引：版本 {source.sourceRevision ?? "未知"} · 修改时间 {source.updatedAt} · 数据截至 {source.asOf || "未知"}</>}</div>
              <label className="block"><span className={labelClass}>引用备注</span><textarea className={inputClass} value={artifact.note || ""} onChange={(event) => setDraft({ ...draft, linkedArtifacts: draft.linkedArtifacts.map((item) => item.id === artifact.id ? { ...item, note: event.target.value } : item) })} /></label>
            </div>)}{!draft.linkedArtifacts.length && <p className="text-sm text-muted-foreground">当前没有引用。备忘录只记录来源、档案身份和引用版本，不复制底层研究。</p>}</div>
          </GlassCard>

          <div className="grid gap-5 2xl:grid-cols-2">
            <GlassCard>
              <div className="mb-4 flex items-center justify-between"><h2 className="font-bold">关键价值驱动（3–7 项）</h2><button onClick={() => setDraft({ ...draft, keyDrivers: [...draft.keyDrivers, { id: createResearchId("driver"), name: "新增驱动", whyItMatters: "待补充", currentView: "待补充", monitorMetric: "待补充", confirmationCondition: "待补充", falsificationCondition: "待补充", sourceIds: [] }].slice(0, 7) })} className="text-xs text-primary">添加</button></div>
              <div className="space-y-3">{draft.keyDrivers.map((driver, index) => <div key={driver.id} className="rounded-xl border border-border bg-muted/15 p-3"><div className="mb-2 flex items-center gap-2"><span className="text-xs font-bold text-primary">{index + 1}</span><input className={inputClass} value={driver.name} onChange={(event) => setDraft({ ...draft, keyDrivers: draft.keyDrivers.map((item) => item.id === driver.id ? { ...item, name: event.target.value } : item) })} /></div><textarea className={`${inputClass} min-h-16 resize-y`} value={driver.currentView} onChange={(event) => setDraft({ ...draft, keyDrivers: draft.keyDrivers.map((item) => item.id === driver.id ? { ...item, currentView: event.target.value } : item) })} placeholder="当前事实、预期和推断" /><div className="mt-2 grid gap-2 md:grid-cols-2"><input className={inputClass} value={driver.monitorMetric} onChange={(event) => setDraft({ ...draft, keyDrivers: draft.keyDrivers.map((item) => item.id === driver.id ? { ...item, monitorMetric: event.target.value } : item) })} placeholder="跟踪指标" /><input className={inputClass} value={driver.falsificationCondition} onChange={(event) => setDraft({ ...draft, keyDrivers: draft.keyDrivers.map((item) => item.id === driver.id ? { ...item, falsificationCondition: event.target.value } : item) })} placeholder="证伪条件" /></div></div>)}</div>
            </GlassCard>

            <GlassCard>
              <h2 className="mb-4 font-bold">悲观 / 基准 / 乐观情景</h2>
              <div className="space-y-3">{draft.scenarios.map((scenario) => <div key={scenario.id} className="rounded-xl border border-border bg-muted/15 p-3"><div className="mb-2 grid grid-cols-[1fr_100px] gap-2"><div className="font-semibold">{scenario.label}</div><label className="flex items-center gap-1 text-xs"><input aria-label={`${scenario.label}概率`} type="number" className={inputClass} value={scenario.probabilityPct} onChange={(event) => setDraft({ ...draft, scenarios: draft.scenarios.map((item) => item.id === scenario.id ? { ...item, probabilityPct: Number(event.target.value) || 0 } : item) })} />%</label></div><textarea className={`${inputClass} min-h-16 resize-y`} value={scenario.operatingPath} onChange={(event) => setDraft({ ...draft, scenarios: draft.scenarios.map((item) => item.id === scenario.id ? { ...item, operatingPath: event.target.value } : item) })} placeholder="经营路径与假设" /><input className={`${inputClass} mt-2`} value={scenario.valuationReference} onChange={(event) => setDraft({ ...draft, scenarios: draft.scenarios.map((item) => item.id === scenario.id ? { ...item, valuationReference: event.target.value } : item) })} placeholder="引用估值工作台对应情景，不在此伪造目标价" /></div>)}</div>
            </GlassCard>
          </div>

          <div className="grid gap-5 2xl:grid-cols-2">
            <GlassCard>
              <div className="mb-4 flex items-center justify-between"><h2 className="font-bold">反方风险与证伪</h2><button onClick={() => { const risk: ResearchRisk = { id: createResearchId("risk"), type: "other", statement: "新增风险", severity: "medium", likelihood: "unknown", earlyWarnings: ["待补充"], breakCondition: "待补充", sourceIds: [] }; setDraft({ ...draft, risks: [...draft.risks, risk].slice(0, 12) }); }} className="text-xs text-primary">添加</button></div>
              <div className="space-y-3">{draft.risks.map((risk) => <div key={risk.id} className="rounded-xl border border-border bg-muted/15 p-3"><div className="grid gap-2 md:grid-cols-[130px_1fr]"><select className={inputClass} value={risk.type} onChange={(event) => setDraft({ ...draft, risks: draft.risks.map((item) => item.id === risk.id ? { ...item, type: event.target.value as ResearchRisk["type"] } : item) })}><option value="fundamental">基本面</option><option value="valuation">估值</option><option value="competition">竞争</option><option value="cycle">周期</option><option value="regulation">监管</option><option value="technology">技术替代</option><option value="execution">执行</option><option value="accounting">会计质量</option><option value="macro">宏观</option><option value="other">其他</option></select><input className={inputClass} value={risk.statement} onChange={(event) => setDraft({ ...draft, risks: draft.risks.map((item) => item.id === risk.id ? { ...item, statement: event.target.value } : item) })} /></div><textarea className={`${inputClass} mt-2 min-h-16 resize-y`} value={risk.breakCondition} onChange={(event) => setDraft({ ...draft, risks: draft.risks.map((item) => item.id === risk.id ? { ...item, breakCondition: event.target.value } : item) })} placeholder="什么可观察事实会打破当前逻辑" /></div>)}</div>
            </GlassCard>
            <GlassCard>
              <div className="mb-4 flex items-center justify-between"><h2 className="font-bold">未来 3–6 个月催化剂</h2><button onClick={addCatalyst} className="inline-flex items-center gap-1 text-xs text-primary"><Plus className="h-3.5 w-3.5" />添加</button></div>
              <div className="space-y-3">{draft.catalysts.map((item) => <div key={item.id} className="rounded-xl border border-border bg-muted/15 p-3"><div className="grid gap-2 md:grid-cols-[1fr_130px_auto]"><input className={inputClass} value={item.title} onChange={(event) => setDraft({ ...draft, catalysts: draft.catalysts.map((row) => row.id === item.id ? { ...row, title: event.target.value } : row) })} /><input className={inputClass} value={item.window} onChange={(event) => setDraft({ ...draft, catalysts: draft.catalysts.map((row) => row.id === item.id ? { ...row, window: event.target.value } : row) })} /><button onClick={() => setDraft({ ...draft, catalysts: draft.catalysts.filter((row) => row.id !== item.id) })}><Trash2 className="h-4 w-4 text-muted-foreground" /></button></div><textarea className={`${inputClass} mt-2 min-h-16 resize-y`} value={item.expectedPath} onChange={(event) => setDraft({ ...draft, catalysts: draft.catalysts.map((row) => row.id === item.id ? { ...row, expectedPath: event.target.value } : row) })} /></div>)}{!draft.catalysts.length && <p className="text-sm text-muted-foreground">尚未添加催化剂。可以引用催化剂日历中的档案 ID。</p>}</div>
            </GlassCard>
          </div>

          <GlassCard>
            <h2 className="mb-4 font-bold">监控面板</h2>
            <div className="overflow-x-auto"><table className="w-full min-w-[760px] text-sm"><thead className="text-left text-xs text-muted-foreground"><tr><th className="pb-2">指标</th><th className="pb-2">最新状态</th><th className="pb-2">趋势</th><th className="pb-2">复核阈值</th><th className="pb-2">频率</th></tr></thead><tbody>{draft.monitoring.map((item) => <tr key={item.id} className="border-t border-border"><td className="py-2 pr-2"><input className={inputClass} value={item.metric} onChange={(event) => setDraft({ ...draft, monitoring: draft.monitoring.map((row) => row.id === item.id ? { ...row, metric: event.target.value } : row) })} /></td><td className="py-2 pr-2"><input className={inputClass} value={item.latest} onChange={(event) => setDraft({ ...draft, monitoring: draft.monitoring.map((row) => row.id === item.id ? { ...row, latest: event.target.value } : row) })} /></td><td className="py-2 pr-2"><select className={inputClass} value={item.trend} onChange={(event) => setDraft({ ...draft, monitoring: draft.monitoring.map((row) => row.id === item.id ? { ...row, trend: event.target.value as typeof item.trend } : row) })}><option value="improving">改善</option><option value="stable">稳定</option><option value="deteriorating">恶化</option><option value="unknown">待核验</option></select></td><td className="py-2 pr-2"><input className={inputClass} value={item.threshold} onChange={(event) => setDraft({ ...draft, monitoring: draft.monitoring.map((row) => row.id === item.id ? { ...row, threshold: event.target.value } : row) })} /></td><td className="py-2"><input className={inputClass} value={item.frequency} onChange={(event) => setDraft({ ...draft, monitoring: draft.monitoring.map((row) => row.id === item.id ? { ...row, frequency: event.target.value } : row) })} /></td></tr>)}</tbody></table></div>
          </GlassCard>

          <GlassCard>
            <div className="mb-4 flex flex-wrap items-center justify-between gap-2"><h2 className="flex items-center gap-2 font-bold"><Link2 className="h-4 w-4 text-primary" />来源、缺口与版本</h2><button onClick={addSource} className="rounded-lg border border-border px-3 py-1.5 text-xs">添加来源</button></div>
            <div className="space-y-2">{draft.sources.map((source) => <div key={source.id} className="grid gap-2 rounded-xl border border-border bg-muted/15 p-3 md:grid-cols-[1fr_130px_130px_140px_auto]"><input className={inputClass} value={source.label} onChange={(event) => setDraft({ ...draft, sources: draft.sources.map((item) => item.id === source.id ? { ...item, label: event.target.value } : item) })} /><select className={inputClass} value={source.claimType} onChange={(event) => setDraft({ ...draft, sources: draft.sources.map((item) => item.id === source.id ? { ...item, claimType: event.target.value as ResearchMemoSource["claimType"] } : item) })}><option value="reported">报告事实</option><option value="guidance">管理层指引</option><option value="consensus">市场预期</option><option value="inference">研究推断</option></select><select className={inputClass} value={source.status} onChange={(event) => setDraft({ ...draft, sources: draft.sources.map((item) => item.id === source.id ? { ...item, status: event.target.value as ResearchMemoSource["status"] } : item) })}><option value="verified">已核验</option><option value="available">可用</option><option value="stale">陈旧</option><option value="unavailable">不可用</option></select><input className={inputClass} value={source.asOf} onChange={(event) => setDraft({ ...draft, sources: draft.sources.map((item) => item.id === source.id ? { ...item, asOf: event.target.value } : item) })} /><button onClick={() => setDraft({ ...draft, sources: draft.sources.filter((item) => item.id !== source.id) })}><Trash2 className="h-4 w-4 text-muted-foreground" /></button></div>)}{!draft.sources.length && <p className="text-sm text-muted-foreground">尚未登记来源。所有未核验数字和判断都应保留缺口标记。</p>}</div>
            <div className="mt-4 grid gap-4 lg:grid-cols-2"><label><span className={labelClass}>研究缺口（每行一项）</span><textarea className={areaClass} value={joinLines(draft.gaps)} onChange={(event) => setDraft({ ...draft, gaps: splitLines(event.target.value) })} /></label><label><span className={labelClass}>本次版本说明</span><textarea className={areaClass} value={versionNote} onChange={(event) => setVersionNote(event.target.value)} placeholder="本次新增、删除或改变了哪些判断？" /></label></div>
            <div className="mt-4 flex flex-wrap gap-2">{draft.versions.slice().reverse().slice(0, 8).map((version) => <span key={`${version.version}-${version.createdAt}`} className="inline-flex items-center gap-1 rounded-full border border-border bg-muted/20 px-2.5 py-1 text-xs"><Archive className="h-3 w-3" />v{version.version} · {version.summary}</span>)}</div>
          </GlassCard>

          <Disclaimer />
        </main>
      </fieldset>
    </div>
  );
}
