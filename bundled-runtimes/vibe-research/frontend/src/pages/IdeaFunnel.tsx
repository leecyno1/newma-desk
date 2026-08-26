import { useEffect, useMemo, useRef, useState } from "react";
import {
  ArrowRight,
  Filter,
  Lightbulb,
  Link2,
  Plus,
  Save,
  SearchCheck,
  ShieldAlert,
  Trash2,
} from "lucide-react";

import { Disclaimer } from "@/components/ui/Disclaimer";
import { GlassCard } from "@/components/ui/GlassCard";
import { PageHeader } from "@/components/ui/PageHeader";
import { ResearchCoverageView } from "@/pages/ResearchCoverageView";
import {
  blankResearchIdea,
  calculateIdeaScore,
  createIdeaId,
  discoverWatchlistCandidates,
  hydrateIdeaFunnelWorkspace,
  loadLocalIdeaFunnelWorkspace,
  persistIdeaFunnelWorkspace,
  splitIdeaList,
  type IdeaArtifactReference,
  type IdeaFunnelWorkspace,
  type IdeaPriority,
  type IdeaResearchStyle,
  type IdeaSource,
  type IdeaStage,
  type ResearchIdea,
  type WatchlistCandidate,
} from "@/lib/ideaFunnel";
import {
  buildResearchCoverageSnapshot,
  type CoverageModId,
  type ResearchCoverageSnapshot,
} from "@/lib/researchCoverage";
import {
  getVibeDeskConfig,
  isVibeDeskEmbedded,
  publishVibeDeskContext,
  registerVibeDeskContextProvider,
  subscribeVibeDeskEvent,
  type VibeDeskPageContext,
} from "@/lib/vibedesk";

const inputClass = "w-full rounded-lg border border-border bg-card/70 px-3 py-2 text-sm text-foreground outline-none transition focus:border-primary/60 focus:ring-2 focus:ring-primary/15";
const labelClass = "mb-1.5 block text-xs font-semibold text-muted-foreground";
const areaClass = `${inputClass} min-h-24 resize-y`;
const STAGE_LABEL: Record<IdeaStage, string> = { inbox: "线索箱", triage: "初筛", shortlist: "短名单", "deep-dive": "深度研究", handoff: "已交接", deferred: "暂缓", closed: "关闭" };
const STYLE_LABEL: Record<IdeaResearchStyle, string> = { value: "价值", growth: "成长", quality: "质量", event: "事件驱动", "special-situation": "特殊情形", risk: "风险线索", other: "其他" };
const PRIORITY_LABEL: Record<IdeaPriority, string> = { high: "高", medium: "中", low: "低" };

function copyIdea(idea: ResearchIdea) { return structuredClone(idea); }
function join(value: string[]) { return value.join("、"); }
function currencyForMarket(market: string) { return market === "US" ? "USD" : market === "HK" ? "HKD" : "CNY"; }

function contextFor(workspace: IdeaFunnelWorkspace, idea: ResearchIdea, dirty: boolean): VibeDeskPageContext {
  return {
    view: { id: "idea-funnel", title: "研究机会池" },
    visibleBlocks: [
      { id: "search-criteria", type: "screen-methodology", title: "搜索条件与筛选方法" },
      { id: "two-sided-hypothesis", type: "research-hypothesis", title: "正反假设与关键问题" },
      { id: "signals-score", type: "candidate-scorecard", title: "信号、证据与优先级" },
      { id: "catalysts-risks", type: "falsification", title: "催化剂、风险与证伪" },
      { id: "next-actions", type: "research-pipeline", title: "下一步与研究交接" },
    ],
    selection: { market: idea.security.market, symbol: idea.security.symbol, name: idea.security.name, ideaId: idea.id, stage: idea.stage },
    filters: { priority: idea.priority, style: idea.researchStyle, themes: idea.searchCriteria.themes },
    data: {
      asOf: idea.origin.asOf || workspace.updatedAt,
      source: workspace.schemaVersion,
      freshness: idea.sources.length ? "fresh" : "unknown",
      summary: {
        origin: idea.origin, searchCriteria: idea.searchCriteria, researchQuestion: idea.researchQuestion,
        initialHypothesis: idea.initialHypothesis, opposingHypothesis: idea.opposingHypothesis,
        whyNow: idea.whyNow, marketMayMiss: idea.marketMayMiss, signals: idea.signals,
        scorecard: idea.scorecard, catalysts: idea.catalysts, risks: idea.risks,
        nextActions: idea.nextActions, handoff: idea.handoff, linkedArtifacts: idea.linkedArtifacts,
        sources: idea.sources, gaps: idea.gaps, unsavedChanges: dirty,
      },
    },
    actions: [
      { id: "idea.audit-screen", label: "审计筛选条件与来源", available: true },
      { id: "idea.find-counter-evidence", label: "搜索反方证据", available: Boolean(idea.initialHypothesis) },
      { id: "idea.rank-candidates", label: "比较机会池候选", available: workspace.ideas.length > 1 },
      { id: "idea.prepare-handoff", label: "准备深度研究交接", available: idea.stage === "shortlist" || idea.stage === "deep-dive" },
    ],
    tasks: [],
  };
}

function coverageContextFor(snapshot: ResearchCoverageSnapshot): VibeDeskPageContext {
  return {
    view: { id: "idea-funnel:coverage", title: "研究流程总览" },
    visibleBlocks: [
      { id: "coverage-summary", type: "research-workflow-summary", title: "流程调度摘要" },
      { id: "coverage-items", type: "research-coverage-list", title: "研究对象覆盖状态" },
      { id: "coverage-attention", type: "research-attention-queue", title: "复核、逾期与缺口" },
    ],
    selection: {},
    filters: { orderBy: "due-review,overdue-task,coverage-gap" },
    data: {
      asOf: snapshot.asOf,
      source: "newma-desk.research-coverage.derived",
      freshness: snapshot.totals.staleSources || snapshot.totals.dueReviews ? "stale" : "fresh",
      summary: {
        totals: snapshot.totals,
        items: snapshot.items.slice(0, 80).map((item) => ({
          security: item.security,
          stage: item.stage,
          latestAt: item.latestAt,
          nextReviewAt: item.nextReviewAt,
          sourceCount: item.sourceCount,
          staleSourceCount: item.staleSourceCount,
          gapCount: item.gapCount,
          pendingTaskCount: item.pendingTaskCount,
          overdueTaskCount: item.overdueTaskCount,
          modules: item.modules,
          attention: item.attention,
          nextModId: item.nextModId,
        })),
      },
    },
    actions: [
      { id: "coverage.audit", label: "审计研究覆盖与陈旧来源", available: snapshot.items.length > 0 },
      { id: "coverage.prioritize", label: "按到期与缺口排列研究任务", available: snapshot.items.length > 0 },
      { id: "coverage.prepare-review", label: "形成滚动复核清单", available: snapshot.totals.dueReviews > 0 || snapshot.totals.pendingTasks > 0 },
    ],
    tasks: [],
  };
}

export function IdeaFunnel() {
  const initial = useMemo(loadLocalIdeaFunnelWorkspace, []);
  const [workspace, setWorkspace] = useState(initial);
  const [selectedId, setSelectedId] = useState(initial.ideas[0]?.id || "__new__");
  const [draft, setDraft] = useState(() => initial.ideas[0] ? copyIdea(initial.ideas[0]) : blankResearchIdea());
  const [message, setMessage] = useState("");
  const [watchlist, setWatchlist] = useState<WatchlistCandidate[]>([]);
  const [activeView, setActiveView] = useState<"pipeline" | "coverage">("pipeline");
  const [coverageRevision, setCoverageRevision] = useState(0);
  const selected = workspace.ideas.find((item) => item.id === selectedId);
  const scored = useMemo(() => ({ ...draft, scorecard: { ...draft.scorecard, total: calculateIdeaScore(draft.scorecard) } }), [draft]);
  const coverage = useMemo(() => buildResearchCoverageSnapshot(workspace), [coverageRevision, workspace]);
  const dirty = selectedId === "__new__"
    ? Boolean(draft.title || draft.security.symbol || draft.researchQuestion)
    : JSON.stringify(selected) !== JSON.stringify(scored);

  useEffect(() => {
    let active = true;
    void hydrateIdeaFunnelWorkspace().then((value) => {
      if (!active) return;
      setWorkspace(value);
      const first = value.ideas[0];
      setSelectedId(first?.id || "__new__");
      setDraft(first ? copyIdea(first) : blankResearchIdea());
    });
    return () => { active = false; };
  }, []);
  const contextRef = useRef<VibeDeskPageContext>(contextFor(workspace, scored, dirty));
  contextRef.current = activeView === "coverage" ? coverageContextFor(coverage) : contextFor(workspace, scored, dirty);
  useEffect(() => registerVibeDeskContextProvider(() => contextRef.current), []);
  useEffect(() => { void publishVibeDeskContext(); }, [activeView, coverage, dirty, scored, workspace]);
  useEffect(() => {
    const refresh = () => setCoverageRevision((value) => value + 1);
    window.addEventListener("storage", refresh);
    return () => window.removeEventListener("storage", refresh);
  }, []);
  useEffect(() => {
    const unsubscribe = subscribeVibeDeskEvent((event) => {
      if (event.event !== "security.selected") return;
      const symbol = typeof event.payload.symbol === "string" ? event.payload.symbol.slice(0, 40).toUpperCase() : "";
      if (!symbol) return;
      const market = typeof event.payload.market === "string" ? event.payload.market.slice(0, 20).toUpperCase() : "CN";
      const name = typeof event.payload.name === "string" ? event.payload.name.slice(0, 120) : symbol;
      setDraft((current) => ({ ...current, security: { market, symbol, name, currency: currencyForMarket(market) } }));
    });
    return () => { unsubscribe(); };
  }, []);

  const commit = (next: IdeaFunnelWorkspace) => { setWorkspace(next); void persistIdeaFunnelWorkspace(next); };
  const startNew = (candidate?: WatchlistCandidate) => {
    if (dirty && !confirm("当前研究候选尚未保存，确定新建吗？")) return;
    const next = blankResearchIdea();
    if (candidate) {
      next.security = { market: candidate.market, symbol: candidate.symbol, name: candidate.name, currency: candidate.currency };
      next.title = `${candidate.name}研究线索`;
      next.origin = { type: "watchlist", label: candidate.groupName, sourceModId: "watchlist", asOf: new Date().toISOString().slice(0, 10), discoveredAt: new Date().toISOString() };
      next.searchCriteria.markets = [candidate.market];
    }
    setSelectedId("__new__"); setDraft(next); setMessage("");
  };
  const choose = (idea: ResearchIdea) => {
    if (dirty && !confirm("当前研究候选尚未保存，确定切换吗？")) return;
    setSelectedId(idea.id); setDraft(copyIdea(idea)); setMessage("");
  };
  const save = () => {
    const required = [
      [draft.title, "候选标题"], [draft.security.symbol, "证券代码"], [draft.security.name, "公司名称"],
      [draft.researchQuestion, "研究问题"], [draft.initialHypothesis, "初始假设"],
      [draft.opposingHypothesis, "反方假设"], [draft.whyNow, "为何现在"], [draft.marketMayMiss, "市场可能遗漏"],
    ] as const;
    const missing = required.find(([value]) => !value.trim());
    if (missing) { setMessage(`请填写${missing[1]}`); return; }
    const timestamp = new Date().toISOString();
    const previousStage = selected?.stage;
    const reviewLog = previousStage && previousStage !== draft.stage
      ? [...draft.reviewLog, { id: createIdeaId("review"), createdAt: timestamp, stage: draft.stage, summary: `阶段由“${STAGE_LABEL[previousStage]}”变更为“${STAGE_LABEL[draft.stage]}”` }].slice(-100)
      : draft.reviewLog;
    const saved: ResearchIdea = {
      ...scored,
      title: draft.title.trim(),
      security: { market: draft.security.market.trim().toUpperCase(), symbol: draft.security.symbol.trim().toUpperCase(), name: draft.security.name.trim(), currency: draft.security.currency.trim().toUpperCase() },
      reviewLog,
      gaps: draft.gaps.map((item) => item.trim()).filter(Boolean),
      updatedAt: timestamp,
    };
    const exists = workspace.ideas.some((item) => item.id === saved.id);
    const ideas = exists ? workspace.ideas.map((item) => item.id === saved.id ? saved : item) : [saved, ...workspace.ideas];
    commit({ ...workspace, updatedAt: timestamp, ideas });
    setSelectedId(saved.id); setDraft(copyIdea(saved)); setMessage("已保存到 Desk 工作区");
  };
  const remove = () => {
    if (selectedId === "__new__") { startNew(); return; }
    if (!confirm(`删除“${draft.title}”研究候选？`)) return;
    const ideas = workspace.ideas.filter((item) => item.id !== selectedId);
    commit({ ...workspace, updatedAt: new Date().toISOString(), ideas });
    const first = ideas[0]; setSelectedId(first?.id || "__new__"); setDraft(first ? copyIdea(first) : blankResearchIdea());
  };
  const loadWatchlist = () => {
    const candidates = discoverWatchlistCandidates();
    setWatchlist(candidates);
    setMessage(candidates.length ? `发现 ${candidates.length} 个自选候选；点击后建立研究线索` : "当前没有可导入的自选候选");
  };
  const editCoverageIdea = (ideaId: string) => {
    const idea = workspace.ideas.find((item) => item.id === ideaId);
    if (!idea) return;
    setSelectedId(idea.id); setDraft(copyIdea(idea)); setMessage(""); setActiveView("pipeline");
  };
  const openResearchMod = (modId: CoverageModId) => {
    const config = getVibeDeskConfig();
    if (isVibeDeskEmbedded && config?.gatewayOrigin) {
      window.open(`${config.gatewayOrigin}/?mod=${encodeURIComponent(modId)}`, "_top");
      return;
    }
    const base = new URL(import.meta.env.BASE_URL, window.location.origin);
    window.location.assign(new URL(modId, base).toString());
  };

  return (
    <div className="mx-auto max-w-[1500px] px-4 py-6 md:px-6">
      <PageHeader title="研究机会池" subtitle={activeView === "coverage" ? "汇总机会池、投资逻辑、财报、同业、估值与研究备忘录，集中识别复核到期、任务逾期、陈旧来源和下一研究入口。" : "把扫描、主题、新闻、催化剂、产业链和自选线索转成双向假设、可复核评分与深度研究任务。筛选结果只是候选，不是结论。"} actions={activeView === "pipeline" ? <><button onClick={() => startNew()} className="inline-flex items-center gap-1.5 rounded-lg border border-border bg-card/70 px-3 py-2 text-sm"><Plus className="h-4 w-4" />新建</button><button onClick={save} className="inline-flex items-center gap-1.5 rounded-lg bg-primary px-3 py-2 text-sm font-semibold text-primary-foreground"><Save className="h-4 w-4" />保存</button></> : undefined} />
      <div role="tablist" aria-label="研究机会池视图" className="mb-5 inline-flex rounded-xl border border-border bg-card/55 p-1">
        <button role="tab" aria-selected={activeView === "pipeline"} onClick={() => setActiveView("pipeline")} className={`inline-flex items-center gap-1.5 rounded-lg px-3 py-2 text-sm font-semibold ${activeView === "pipeline" ? "bg-primary text-primary-foreground" : "text-muted-foreground"}`}><SearchCheck className="h-4 w-4" />候选与任务</button>
        <button role="tab" aria-selected={activeView === "coverage"} onClick={() => { setCoverageRevision((value) => value + 1); setActiveView("coverage"); }} className={`inline-flex items-center gap-1.5 rounded-lg px-3 py-2 text-sm font-semibold ${activeView === "coverage" ? "bg-primary text-primary-foreground" : "text-muted-foreground"}`}><Filter className="h-4 w-4" />流程总览</button>
      </div>
      {activeView === "coverage" ? (
        <ResearchCoverageView snapshot={coverage} onRefresh={() => setCoverageRevision((value) => value + 1)} onEditIdea={editCoverageIdea} onOpenMod={openResearchMod} />
      ) : (
      <div className="grid gap-5 xl:grid-cols-[250px_minmax(0,1fr)]">
        <aside className="space-y-4">
          <GlassCard className="p-3">
            <div className="mb-2 flex items-center justify-between"><h2 className="text-sm font-bold">研究候选</h2><span className="text-xs text-muted-foreground">{workspace.ideas.length}</span></div>
            <div className="space-y-1.5">{workspace.ideas.map((idea) => <button key={idea.id} onClick={() => choose(idea)} className={`w-full rounded-lg border px-3 py-2 text-left ${idea.id === selectedId ? "border-primary/40 bg-primary/10" : "border-border bg-card/40"}`}><div className="truncate text-sm font-semibold">{idea.title}</div><div className="mt-1 flex justify-between text-xs text-muted-foreground"><span>{idea.security.symbol}</span><span>{STAGE_LABEL[idea.stage]} · {idea.scorecard.total}</span></div></button>)}{!workspace.ideas.length && <p className="rounded-lg border border-dashed border-border p-3 text-xs text-muted-foreground">还没有研究候选。可从自选股导入，也可记录 Agent 或产业链发现的线索。</p>}</div>
          </GlassCard>
          <GlassCard className="p-3"><button onClick={loadWatchlist} className="flex w-full items-center justify-between text-sm font-semibold"><span className="flex items-center gap-2"><SearchCheck className="h-4 w-4 text-primary" />导入自选候选</span><ArrowRight className="h-4 w-4" /></button>{watchlist.length > 0 && <div className="mt-3 max-h-64 space-y-1.5 overflow-auto">{watchlist.map((item) => <button key={`${item.market}:${item.symbol}`} onClick={() => startNew(item)} className="w-full rounded-lg border border-border p-2 text-left text-xs"><span className="font-semibold text-foreground">{item.name} · {item.symbol}</span><span className="mt-0.5 block text-muted-foreground">{item.groupName}</span></button>)}</div>}</GlassCard>
          <GlassCard className="p-3 text-xs text-muted-foreground"><div className="mb-2 flex items-center gap-2 font-semibold text-foreground"><ShieldAlert className="h-4 w-4 text-primary" />机会池边界</div>只记录“为什么值得研究”和“如何证伪”，不生成买卖、目标价或仓位建议。未完成基本面核验的候选不得直接进入研究备忘录。</GlassCard>
        </aside>

        <main className="space-y-5">
          {message && <div className="rounded-lg border border-primary/25 bg-primary/8 px-3 py-2 text-sm">{message}</div>}
          <GlassCard>
            <div className="mb-4 flex items-center justify-between"><h2 className="flex items-center gap-2 font-bold"><Lightbulb className="h-4 w-4 text-primary" />候选身份与流程</h2><button aria-label="删除候选" onClick={remove}><Trash2 className="h-4 w-4 text-muted-foreground hover:text-destructive" /></button></div>
            <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-4">
              <label><span className={labelClass}>候选标题</span><input aria-label="候选标题" className={inputClass} value={draft.title} onChange={(event) => setDraft({ ...draft, title: event.target.value })} /></label>
              <label><span className={labelClass}>证券代码</span><input aria-label="证券代码" className={inputClass} value={draft.security.symbol} onChange={(event) => setDraft({ ...draft, security: { ...draft.security, symbol: event.target.value } })} /></label>
              <label><span className={labelClass}>公司名称</span><input aria-label="公司名称" className={inputClass} value={draft.security.name} onChange={(event) => setDraft({ ...draft, security: { ...draft.security, name: event.target.value } })} /></label>
              <label><span className={labelClass}>市场</span><select className={inputClass} value={draft.security.market} onChange={(event) => { const market = event.target.value; setDraft({ ...draft, security: { ...draft.security, market, currency: currencyForMarket(market) } }); }}><option>CN</option><option>HK</option><option>US</option></select></label>
              <label><span className={labelClass}>阶段</span><select className={inputClass} value={draft.stage} onChange={(event) => setDraft({ ...draft, stage: event.target.value as IdeaStage })}>{Object.entries(STAGE_LABEL).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
              <label><span className={labelClass}>研究优先级</span><select className={inputClass} value={draft.priority} onChange={(event) => setDraft({ ...draft, priority: event.target.value as IdeaPriority })}>{Object.entries(PRIORITY_LABEL).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
              <label><span className={labelClass}>研究风格</span><select className={inputClass} value={draft.researchStyle} onChange={(event) => setDraft({ ...draft, researchStyle: event.target.value as IdeaResearchStyle, searchCriteria: { ...draft.searchCriteria, styles: [event.target.value as IdeaResearchStyle] } })}>{Object.entries(STYLE_LABEL).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
              <label><span className={labelClass}>线索来源</span><input className={inputClass} value={draft.origin.label} onChange={(event) => setDraft({ ...draft, origin: { ...draft.origin, label: event.target.value } })} /></label>
            </div>
          </GlassCard>

          <GlassCard>
            <h2 className="mb-4 flex items-center gap-2 font-bold"><Filter className="h-4 w-4 text-primary" />搜索条件与方法记录</h2>
            <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-4"><label><span className={labelClass}>市场</span><input className={inputClass} value={join(draft.searchCriteria.markets)} onChange={(event) => setDraft({ ...draft, searchCriteria: { ...draft.searchCriteria, markets: splitIdeaList(event.target.value) } })} /></label><label><span className={labelClass}>行业</span><input className={inputClass} value={join(draft.searchCriteria.sectors)} onChange={(event) => setDraft({ ...draft, searchCriteria: { ...draft.searchCriteria, sectors: splitIdeaList(event.target.value) } })} placeholder="通信设备、半导体…" /></label><label><span className={labelClass}>主题</span><input className={inputClass} value={join(draft.searchCriteria.themes)} onChange={(event) => setDraft({ ...draft, searchCriteria: { ...draft.searchCriteria, themes: splitIdeaList(event.target.value) } })} placeholder="AI 算力、出海…" /></label><label><span className={labelClass}>市值范围</span><input className={inputClass} value={draft.searchCriteria.marketCapRange} onChange={(event) => setDraft({ ...draft, searchCriteria: { ...draft.searchCriteria, marketCapRange: event.target.value } })} /></label></div>
            <div className="mt-4 space-y-2">{draft.searchCriteria.rules.map((rule) => <div key={rule.id} className="grid gap-2 rounded-xl border border-border bg-muted/15 p-3 md:grid-cols-[1fr_110px_140px_1.5fr_auto]"><input className={inputClass} value={rule.metric} onChange={(event) => setDraft({ ...draft, searchCriteria: { ...draft.searchCriteria, rules: draft.searchCriteria.rules.map((item) => item.id === rule.id ? { ...item, metric: event.target.value } : item) } })} /><select className={inputClass} value={rule.operator} onChange={(event) => setDraft({ ...draft, searchCriteria: { ...draft.searchCriteria, rules: draft.searchCriteria.rules.map((item) => item.id === rule.id ? { ...item, operator: event.target.value as typeof rule.operator } : item) } })}><option value="gt">大于</option><option value="gte">不低于</option><option value="lt">小于</option><option value="lte">不高于</option><option value="eq">等于</option><option value="between">区间</option><option value="trend">趋势</option></select><input className={inputClass} value={rule.value} onChange={(event) => setDraft({ ...draft, searchCriteria: { ...draft.searchCriteria, rules: draft.searchCriteria.rules.map((item) => item.id === rule.id ? { ...item, value: event.target.value } : item) } })} /><input className={inputClass} value={rule.rationale} onChange={(event) => setDraft({ ...draft, searchCriteria: { ...draft.searchCriteria, rules: draft.searchCriteria.rules.map((item) => item.id === rule.id ? { ...item, rationale: event.target.value } : item) } })} /><button onClick={() => setDraft({ ...draft, searchCriteria: { ...draft.searchCriteria, rules: draft.searchCriteria.rules.filter((item) => item.id !== rule.id) } })}><Trash2 className="h-4 w-4 text-muted-foreground" /></button></div>)}</div>
            <button onClick={() => setDraft({ ...draft, searchCriteria: { ...draft.searchCriteria, rules: [...draft.searchCriteria.rules, { id: createIdeaId("rule"), metric: "新增筛选条件", operator: "trend" as const, value: "待定义", rationale: "说明该条件为什么有研究意义" }].slice(0, 30) } })} className="mt-3 text-xs text-primary">添加筛选条件</button>
          </GlassCard>

          <GlassCard>
            <h2 className="mb-4 font-bold">双向研究假设</h2>
            <div className="grid gap-4 lg:grid-cols-2">{([
              ["研究问题", "researchQuestion", "这条线索真正需要回答什么？"],
              ["为何现在", "whyNow", "为什么当前出现了值得验证的窗口？"],
              ["初始假设", "initialHypothesis", "支持候选值得进一步研究的判断链。"],
              ["反方假设", "opposingHypothesis", "同样合理、但会推翻初始判断的解释。"],
              ["市场可能遗漏", "marketMayMiss", "哪些二阶受益、竞争变化或风险尚未充分连接？"],
            ] as const).map(([label, key, placeholder]) => <label key={key} className={key === "marketMayMiss" ? "lg:col-span-2" : ""}><span className={labelClass}>{label}</span><textarea aria-label={label} className={areaClass} placeholder={placeholder} value={draft[key]} onChange={(event) => setDraft({ ...draft, [key]: event.target.value })} /></label>)}</div>
          </GlassCard>

          <div className="grid gap-5 2xl:grid-cols-2">
            <GlassCard>
              <div className="mb-4 flex items-center justify-between"><h2 className="font-bold">支持与反方信号</h2><button onClick={() => setDraft({ ...draft, signals: [...draft.signals, { id: createIdeaId("signal"), type: "pattern" as const, direction: "neutral" as const, summary: "新增待核验信号", sourceIds: [] }].slice(0, 30) })} className="text-xs text-primary">添加</button></div>
              <div className="space-y-3">{draft.signals.map((signal) => <div key={signal.id} className="grid gap-2 rounded-xl border border-border bg-muted/15 p-3 md:grid-cols-[130px_1fr_auto]"><select className={inputClass} value={signal.direction} onChange={(event) => setDraft({ ...draft, signals: draft.signals.map((item) => item.id === signal.id ? { ...item, direction: event.target.value as typeof signal.direction } : item) })}><option value="supports">支持</option><option value="challenges">挑战</option><option value="neutral">中性</option></select><textarea className={`${inputClass} min-h-16 resize-y`} value={signal.summary} onChange={(event) => setDraft({ ...draft, signals: draft.signals.map((item) => item.id === signal.id ? { ...item, summary: event.target.value } : item) })} /><button disabled={draft.signals.length <= 2} onClick={() => setDraft({ ...draft, signals: draft.signals.filter((item) => item.id !== signal.id) })}><Trash2 className="h-4 w-4 text-muted-foreground" /></button></div>)}</div>
            </GlassCard>
            <GlassCard>
              <div className="mb-4 flex items-center justify-between"><h2 className="font-bold">研究优先级评分</h2><span className="rounded-full bg-primary/12 px-3 py-1 text-lg font-bold text-primary">{scored.scorecard.total}</span></div>
              <div className="grid gap-3 md:grid-cols-2">{([
                ["相关性", "relevance"], ["证据质量", "evidenceQuality"], ["认知新颖度", "novelty"],
                ["催化清晰度", "catalystClarity"], ["可证伪性", "falsifiability"], ["研究成本", "researchEffort"],
              ] as const).map(([label, key]) => <label key={key}><span className={labelClass}>{label} · {draft.scorecard[key]}</span><input aria-label={label} type="range" min="0" max="100" step="5" className="w-full accent-primary" value={draft.scorecard[key]} onChange={(event) => setDraft({ ...draft, scorecard: { ...draft.scorecard, [key]: Number(event.target.value) } })} /></label>)}</div>
              <p className="mt-4 text-xs text-muted-foreground">总分提高于相关性、证据质量、新颖度、催化清晰度和可证伪性，研究成本越高则相应扣分。评分只决定先研究什么，不代表投资结论。</p>
            </GlassCard>
          </div>

          <div className="grid gap-5 2xl:grid-cols-2">
            <GlassCard>
              <div className="mb-4 flex items-center justify-between"><h2 className="font-bold">风险与证伪</h2><button onClick={() => setDraft({ ...draft, risks: [...draft.risks, { id: createIdeaId("risk"), statement: "新增风险", earlyWarning: "待补充领先预警", falsificationCondition: "待补充证伪条件", sourceIds: [] }].slice(0, 20) })} className="text-xs text-primary">添加</button></div>
              <div className="space-y-3">{draft.risks.map((risk) => <div key={risk.id} className="rounded-xl border border-border bg-muted/15 p-3"><input className={inputClass} value={risk.statement} onChange={(event) => setDraft({ ...draft, risks: draft.risks.map((item) => item.id === risk.id ? { ...item, statement: event.target.value } : item) })} /><div className="mt-2 grid gap-2 md:grid-cols-2"><input className={inputClass} value={risk.earlyWarning} onChange={(event) => setDraft({ ...draft, risks: draft.risks.map((item) => item.id === risk.id ? { ...item, earlyWarning: event.target.value } : item) })} placeholder="领先预警" /><input className={inputClass} value={risk.falsificationCondition} onChange={(event) => setDraft({ ...draft, risks: draft.risks.map((item) => item.id === risk.id ? { ...item, falsificationCondition: event.target.value } : item) })} placeholder="证伪条件" /></div></div>)}</div>
            </GlassCard>
            <GlassCard>
              <div className="mb-4 flex items-center justify-between"><h2 className="font-bold">催化剂验证窗口</h2><button onClick={() => setDraft({ ...draft, catalysts: [...draft.catalysts, { id: createIdeaId("catalyst"), title: "新增催化剂", window: "待确认", confirmationCondition: "待补充确认条件", invalidationCondition: "待补充失效条件", sourceIds: [] }].slice(0, 20) })} className="text-xs text-primary">添加</button></div>
              <div className="space-y-3">{draft.catalysts.map((item) => <div key={item.id} className="rounded-xl border border-border bg-muted/15 p-3"><div className="grid gap-2 md:grid-cols-[1fr_140px]"><input className={inputClass} value={item.title} onChange={(event) => setDraft({ ...draft, catalysts: draft.catalysts.map((row) => row.id === item.id ? { ...row, title: event.target.value } : row) })} /><input className={inputClass} value={item.window} onChange={(event) => setDraft({ ...draft, catalysts: draft.catalysts.map((row) => row.id === item.id ? { ...row, window: event.target.value } : row) })} /></div><div className="mt-2 grid gap-2 md:grid-cols-2"><input className={inputClass} value={item.confirmationCondition} onChange={(event) => setDraft({ ...draft, catalysts: draft.catalysts.map((row) => row.id === item.id ? { ...row, confirmationCondition: event.target.value } : row) })} /><input className={inputClass} value={item.invalidationCondition} onChange={(event) => setDraft({ ...draft, catalysts: draft.catalysts.map((row) => row.id === item.id ? { ...row, invalidationCondition: event.target.value } : row) })} /></div></div>)}{!draft.catalysts.length && <p className="text-sm text-muted-foreground">尚未记录催化剂。逆向或争议候选尤其需要明确验证窗口。</p>}</div>
            </GlassCard>
          </div>

          <GlassCard>
            <div className="mb-4 flex items-center justify-between"><h2 className="font-bold">下一步研究与交接</h2><button onClick={() => setDraft({ ...draft, nextActions: [...draft.nextActions, { id: createIdeaId("action"), kind: "other" as const, label: "新增研究任务", status: "pending" as const, completionStandard: "定义可复核的完成标准" }].slice(0, 30) })} className="text-xs text-primary">添加任务</button></div>
            <div className="space-y-2">{draft.nextActions.map((action) => <div key={action.id} className="grid gap-2 rounded-xl border border-border bg-muted/15 p-3 md:grid-cols-[130px_1fr_1.4fr_110px]"><select className={inputClass} value={action.kind} onChange={(event) => setDraft({ ...draft, nextActions: draft.nextActions.map((item) => item.id === action.id ? { ...item, kind: event.target.value as typeof action.kind } : item) })}><option value="data-check">数据核验</option><option value="filing">财报公告</option><option value="model">模型</option><option value="peer">同业</option><option value="industry">产业链</option><option value="catalyst">催化剂</option><option value="expert">专家访谈</option><option value="other">其他</option></select><input className={inputClass} value={action.label} onChange={(event) => setDraft({ ...draft, nextActions: draft.nextActions.map((item) => item.id === action.id ? { ...item, label: event.target.value } : item) })} /><input className={inputClass} value={action.completionStandard} onChange={(event) => setDraft({ ...draft, nextActions: draft.nextActions.map((item) => item.id === action.id ? { ...item, completionStandard: event.target.value } : item) })} /><select className={inputClass} value={action.status} onChange={(event) => setDraft({ ...draft, nextActions: draft.nextActions.map((item) => item.id === action.id ? { ...item, status: event.target.value as typeof action.status } : item) })}><option value="pending">待办</option><option value="done">完成</option><option value="skipped">跳过</option></select></div>)}</div>
            <div className="mt-4 grid gap-3 md:grid-cols-[220px_160px_1fr]"><label><span className={labelClass}>交接目标</span><select className={inputClass} value={draft.handoff.targetModId} onChange={(event) => setDraft({ ...draft, handoff: { ...draft.handoff, targetModId: event.target.value as typeof draft.handoff.targetModId } })}><option value="thesis-tracker">投资逻辑</option><option value="earnings-workbench">财报研究</option><option value="peer-comparison">同业比较</option><option value="valuation-workbench">预测与估值</option><option value="research-memo">研究备忘录</option><option value="other">其他</option></select></label><label><span className={labelClass}>交接状态</span><select className={inputClass} value={draft.handoff.status} onChange={(event) => setDraft({ ...draft, handoff: { ...draft.handoff, status: event.target.value as typeof draft.handoff.status } })}><option value="none">未准备</option><option value="ready">可交接</option><option value="created">已创建档案</option></select></label><label><span className={labelClass}>交接说明</span><input className={inputClass} value={draft.handoff.note} onChange={(event) => setDraft({ ...draft, handoff: { ...draft.handoff, note: event.target.value } })} /></label></div>
          </GlassCard>

          <GlassCard>
            <div className="mb-4 flex items-center justify-between"><h2 className="flex items-center gap-2 font-bold"><Link2 className="h-4 w-4 text-primary" />来源、关联档案与缺口</h2><div className="flex gap-2"><button onClick={() => { const source: IdeaSource = { id: createIdeaId("source"), label: "待命名来源", kind: "user", asOf: draft.origin.asOf, status: "available" }; setDraft({ ...draft, sources: [...draft.sources, source].slice(0, 100) }); }} className="text-xs text-primary">添加来源</button><button onClick={() => { const artifact: IdeaArtifactReference = { id: createIdeaId("artifact"), sourceModId: "market-scanner", artifactId: createIdeaId("manual"), title: "待命名关联档案", status: "linked" }; setDraft({ ...draft, linkedArtifacts: [...draft.linkedArtifacts, artifact].slice(0, 40) }); }} className="text-xs text-primary">引用档案</button></div></div>
            <div className="grid gap-4 lg:grid-cols-2"><div className="space-y-2">{draft.sources.map((source) => <div key={source.id} className="grid grid-cols-[1fr_130px_130px] gap-2"><input className={inputClass} value={source.label} onChange={(event) => setDraft({ ...draft, sources: draft.sources.map((item) => item.id === source.id ? { ...item, label: event.target.value } : item) })} /><input className={inputClass} value={source.asOf} onChange={(event) => setDraft({ ...draft, sources: draft.sources.map((item) => item.id === source.id ? { ...item, asOf: event.target.value } : item) })} /><select className={inputClass} value={source.status} onChange={(event) => setDraft({ ...draft, sources: draft.sources.map((item) => item.id === source.id ? { ...item, status: event.target.value as typeof source.status } : item) })}><option value="verified">已核验</option><option value="available">可用</option><option value="stale">陈旧</option><option value="unavailable">不可用</option></select></div>)}</div><div className="space-y-2">{draft.linkedArtifacts.map((artifact) => <div key={artifact.id} className="grid grid-cols-[150px_1fr_1fr] gap-2"><input className={inputClass} value={artifact.sourceModId} onChange={(event) => setDraft({ ...draft, linkedArtifacts: draft.linkedArtifacts.map((item) => item.id === artifact.id ? { ...item, sourceModId: event.target.value } : item) })} /><input className={inputClass} value={artifact.artifactId} onChange={(event) => setDraft({ ...draft, linkedArtifacts: draft.linkedArtifacts.map((item) => item.id === artifact.id ? { ...item, artifactId: event.target.value } : item) })} /><input className={inputClass} value={artifact.title} onChange={(event) => setDraft({ ...draft, linkedArtifacts: draft.linkedArtifacts.map((item) => item.id === artifact.id ? { ...item, title: event.target.value } : item) })} /></div>)}</div></div>
            <label className="mt-4 block"><span className={labelClass}>待补缺口（每行一项）</span><textarea className={areaClass} value={draft.gaps.join("\n")} onChange={(event) => setDraft({ ...draft, gaps: event.target.value.split("\n").map((item) => item.trim()).filter(Boolean) })} /></label>
          </GlassCard>
          <Disclaimer />
        </main>
      </div>
      )}
    </div>
  );
}
