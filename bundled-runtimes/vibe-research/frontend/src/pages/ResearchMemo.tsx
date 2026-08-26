import { useEffect, useMemo, useRef, useState } from "react";
import {
  Archive,
  BookOpenCheck,
  FileSymlink,
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
  discoverCachedResearchArtifacts,
  hydrateResearchMemoWorkspace,
  loadLocalResearchMemoWorkspace,
  persistResearchMemoWorkspace,
  type ArtifactKind,
  type ResearchArtifactReference,
  type ResearchBias,
  type ResearchConviction,
  type ResearchMemo,
  type ResearchMemoSource,
  type ResearchMemoWorkspace,
  type ResearchRisk,
} from "@/lib/researchMemo";
import {
  publishVibeDeskContext,
  registerVibeDeskContextProvider,
  subscribeVibeDeskEvent,
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

function memoContext(workspace: ResearchMemoWorkspace, memo: ResearchMemo, dirty: boolean): VibeDeskPageContext {
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
      asOf: memo.boundary.asOf || workspace.updatedAt,
      source: workspace.schemaVersion,
      freshness: memo.sources.length ? "fresh" : "unknown",
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
  const initial = useMemo(loadLocalResearchMemoWorkspace, []);
  const [workspace, setWorkspace] = useState(initial);
  const [selectedId, setSelectedId] = useState(initial.memos[0]?.id || "__new__");
  const [draft, setDraft] = useState(() => initial.memos[0] ? copyMemo(initial.memos[0]) : blankResearchMemo());
  const [message, setMessage] = useState("");
  const [versionNote, setVersionNote] = useState("");
  const [artifacts, setArtifacts] = useState<ResearchArtifactReference[]>([]);
  const selected = workspace.memos.find((item) => item.id === selectedId);
  const dirty = selectedId === "__new__"
    ? Boolean(draft.title || draft.security.symbol || draft.executiveView.conclusion)
    : JSON.stringify(selected) !== JSON.stringify(draft);

  useEffect(() => {
    let active = true;
    void hydrateResearchMemoWorkspace().then((value) => {
      if (!active) return;
      setWorkspace(value);
      const first = value.memos[0];
      setSelectedId(first?.id || "__new__");
      setDraft(first ? copyMemo(first) : blankResearchMemo());
    });
    return () => { active = false; };
  }, []);

  const contextRef = useRef<VibeDeskPageContext>(memoContext(workspace, draft, dirty));
  contextRef.current = memoContext(workspace, draft, dirty);
  useEffect(() => registerVibeDeskContextProvider(() => contextRef.current), []);
  useEffect(() => { void publishVibeDeskContext(); }, [draft, dirty, workspace]);
  useEffect(() => {
    const unsubscribe = subscribeVibeDeskEvent((event) => {
      if (event.event !== "security.selected") return;
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

  const commit = (next: ResearchMemoWorkspace) => {
    setWorkspace(next);
    void persistResearchMemoWorkspace(next);
  };

  const startNew = () => {
    if (dirty && !confirm("当前研究备忘录尚未保存，确定新建吗？")) return;
    setSelectedId("__new__");
    setDraft(blankResearchMemo());
    setMessage("");
    setVersionNote("");
  };

  const choose = (memo: ResearchMemo) => {
    if (dirty && !confirm("当前研究备忘录尚未保存，确定切换吗？")) return;
    setSelectedId(memo.id);
    setDraft(copyMemo(memo));
    setMessage("");
    setVersionNote("");
  };

  const save = () => {
    const required = [
      [draft.title, "备忘录标题"], [draft.security.symbol, "证券代码"], [draft.security.name, "公司名称"],
      [draft.executiveView.conclusion, "研究结论"], [draft.executiveView.coreThesis, "核心论点"],
      [draft.executiveView.keyDebate, "关键争议"], [draft.executiveView.variantPerception, "差异认知"],
      [draft.executiveView.whatMayBeMissing, "市场可能遗漏"], [draft.executiveView.breakpoint, "逻辑断点"],
    ] as const;
    const missing = required.find(([value]) => !value.trim());
    if (missing) { setMessage(`请填写${missing[1]}`); return; }
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
    commit({ ...workspace, updatedAt: timestamp, memos });
    setSelectedId(saved.id);
    setDraft(copyMemo(saved));
    setVersionNote("");
    setMessage("已保存到 Desk 工作区");
  };

  const remove = () => {
    if (selectedId === "__new__") { startNew(); return; }
    if (!confirm(`删除“${draft.title}”研究备忘录？`)) return;
    const memos = workspace.memos.filter((item) => item.id !== selectedId);
    const next = { ...workspace, updatedAt: new Date().toISOString(), memos };
    commit(next);
    const first = memos[0];
    setSelectedId(first?.id || "__new__");
    setDraft(first ? copyMemo(first) : blankResearchMemo());
  };

  const discover = () => {
    const found = discoverCachedResearchArtifacts();
    setArtifacts(found);
    setMessage(found.length ? `发现 ${found.length} 项本地研究档案，可按需关联` : "当前缓存未发现可关联档案；仍可手工录入档案 ID");
  };

  const linkArtifact = (artifact: ResearchArtifactReference) => {
    if (draft.linkedArtifacts.some((item) => item.sourceModId === artifact.sourceModId && item.artifactId === artifact.artifactId)) return;
    setDraft({ ...draft, linkedArtifacts: [...draft.linkedArtifacts, artifact].slice(0, 50) });
  };

  const addManualArtifact = () => {
    const artifact: ResearchArtifactReference = {
      id: createResearchId("artifact"), kind: "other", sourceModId: "research-notes",
      artifactId: createResearchId("manual"), title: "待命名研究档案", status: "linked",
      note: "手工引用；请补充来源 Mod、档案 ID 和截至日期。",
    };
    setDraft({ ...draft, linkedArtifacts: [...draft.linkedArtifacts, artifact].slice(0, 50) });
  };

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
          <button onClick={startNew} className="inline-flex items-center gap-1.5 rounded-lg border border-border bg-card/70 px-3 py-2 text-sm"><Plus className="h-4 w-4" />新建</button>
          <button onClick={save} className="inline-flex items-center gap-1.5 rounded-lg bg-primary px-3 py-2 text-sm font-semibold text-primary-foreground"><Save className="h-4 w-4" />保存</button>
        </>}
      />

      <div className="grid gap-5 xl:grid-cols-[250px_minmax(0,1fr)]">
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
          {message && <div className="rounded-lg border border-primary/25 bg-primary/8 px-3 py-2 text-sm text-foreground">{message}</div>}

          <GlassCard>
            <div className="mb-4 flex items-center justify-between gap-3"><h2 className="flex items-center gap-2 font-bold"><BookOpenCheck className="h-4 w-4 text-primary" />研究边界与执行结论</h2><button onClick={remove} className="text-muted-foreground hover:text-destructive" aria-label="删除备忘录"><Trash2 className="h-4 w-4" /></button></div>
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
            <div className="mb-4 flex flex-wrap items-center justify-between gap-2"><h2 className="flex items-center gap-2 font-bold"><FileSymlink className="h-4 w-4 text-primary" />关联研究档案</h2><div className="flex gap-2"><button onClick={discover} className="rounded-lg border border-border px-3 py-1.5 text-xs">发现工作区档案</button><button onClick={addManualArtifact} className="rounded-lg border border-border px-3 py-1.5 text-xs">手工引用</button></div></div>
            {artifacts.length > 0 && <div className="mb-4 grid gap-2 md:grid-cols-2">{artifacts.map((artifact) => <button key={artifact.id} onClick={() => linkArtifact(artifact)} className="rounded-lg border border-border bg-muted/20 p-3 text-left text-xs"><span className="font-semibold text-foreground">{KIND_LABEL[artifact.kind]} · {artifact.title}</span><span className="mt-1 block text-muted-foreground">{artifact.sourceModId} / {artifact.artifactId}</span></button>)}</div>}
            <div className="space-y-3">{draft.linkedArtifacts.map((artifact) => <div key={artifact.id} className="grid gap-2 rounded-xl border border-border bg-muted/15 p-3 md:grid-cols-[130px_150px_1fr_1fr_auto]">
              <select className={inputClass} value={artifact.kind} onChange={(event) => setDraft({ ...draft, linkedArtifacts: draft.linkedArtifacts.map((item) => item.id === artifact.id ? { ...item, kind: event.target.value as ArtifactKind } : item) })}>{Object.entries(KIND_LABEL).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select>
              <input className={inputClass} value={artifact.sourceModId} onChange={(event) => setDraft({ ...draft, linkedArtifacts: draft.linkedArtifacts.map((item) => item.id === artifact.id ? { ...item, sourceModId: event.target.value } : item) })} placeholder="来源 Mod ID" />
              <input className={inputClass} value={artifact.artifactId} onChange={(event) => setDraft({ ...draft, linkedArtifacts: draft.linkedArtifacts.map((item) => item.id === artifact.id ? { ...item, artifactId: event.target.value } : item) })} placeholder="档案 ID" />
              <input className={inputClass} value={artifact.title} onChange={(event) => setDraft({ ...draft, linkedArtifacts: draft.linkedArtifacts.map((item) => item.id === artifact.id ? { ...item, title: event.target.value } : item) })} placeholder="引用标题" />
              <button onClick={() => setDraft({ ...draft, linkedArtifacts: draft.linkedArtifacts.filter((item) => item.id !== artifact.id) })} className="text-muted-foreground hover:text-destructive"><Trash2 className="h-4 w-4" /></button>
            </div>)}{!draft.linkedArtifacts.length && <p className="text-sm text-muted-foreground">当前没有引用。备忘录不会复制底层数据，只保存来源 Mod 和档案 ID。</p>}</div>
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
      </div>
    </div>
  );
}
