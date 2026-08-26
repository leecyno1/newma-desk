import { useEffect, useMemo, useRef, useState } from "react";
import {
  Archive,
  BookOpenCheck,
  CalendarClock,
  CheckCircle2,
  CircleAlert,
  FileSearch,
  Link2,
  Plus,
  Save,
  ShieldAlert,
  Target,
  Trash2,
  type LucideIcon,
} from "lucide-react";

import { Disclaimer } from "@/components/ui/Disclaimer";
import { GlassCard } from "@/components/ui/GlassCard";
import { PageHeader } from "@/components/ui/PageHeader";
import {
  hydrateThesisPortfolio,
  loadLocalThesisPortfolio,
  persistThesisPortfolio,
  type InvestmentThesis,
  type InvestmentThesisPortfolio,
  type ThesisConviction,
  type ThesisImpact,
  type ThesisTrend,
} from "@/lib/thesisTracker";
import { cn } from "@/lib/utils";
import {
  publishVibeDeskContext,
  registerVibeDeskContextProvider,
  type VibeDeskPageContext,
} from "@/lib/vibedesk";

const STATUS_LABEL = {
  draft: "草稿",
  active: "持续验证",
  watch: "重点观察",
  invalidated: "已证伪",
  archived: "已归档",
} as const;
const CONVICTION_LABEL = { high: "高", medium: "中", low: "低" } as const;
const TREND_LABEL = {
  improving: "改善",
  stable: "稳定",
  deteriorating: "恶化",
  pending: "待验证",
} as const;
const IMPACT_LABEL = {
  strengthened: "增强",
  weakened: "削弱",
  neutral: "中性",
  invalidated: "证伪",
} as const;

const inputClass = "w-full rounded-lg border border-border bg-card/70 px-3 py-2 text-sm text-foreground outline-none transition focus:border-primary/60 focus:ring-2 focus:ring-primary/15";
const labelClass = "mb-1.5 block text-xs font-semibold text-muted-foreground";

function createId(prefix: string) {
  const suffix = globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(16).slice(2)}`;
  return `${prefix}:${suffix}`;
}

function today() {
  return new Date().toISOString().slice(0, 10);
}

function nextQuarter() {
  const value = new Date();
  value.setMonth(value.getMonth() + 3);
  return value.toISOString().slice(0, 10);
}

function blankPillar(index: number) {
  return {
    id: createId(`pillar-${index + 1}`),
    title: "",
    expectation: "",
    currentStatus: "等待证据更新",
    trend: "pending" as ThesisTrend,
    evidenceIds: [],
  };
}

function blankRisk(index: number) {
  return {
    id: createId(`risk-${index + 1}`),
    statement: "",
    invalidationCondition: "",
    status: "monitoring" as const,
    evidenceIds: [],
  };
}

function blankThesis(): InvestmentThesis {
  const timestamp = new Date().toISOString();
  return {
    id: createId("thesis"),
    security: { market: "CN", symbol: "", name: "", exchange: "" },
    title: "",
    statement: "",
    status: "draft",
    conviction: "low",
    pillars: [0, 1, 2].map(blankPillar),
    invalidationRisks: [0, 1, 2].map(blankRisk),
    linkedCatalysts: [],
    evidence: [],
    updates: [],
    nextReviewAt: nextQuarter(),
    gaps: [],
    createdAt: timestamp,
    updatedAt: timestamp,
  };
}

function copyThesis(value: InvestmentThesis) {
  return structuredClone(value);
}

function validateThesis(value: InvestmentThesis) {
  if (!value.security.name.trim() || !value.security.symbol.trim()) return "请补充公司名称和证券代码";
  if (!value.title.trim() || !value.statement.trim()) return "请补充逻辑标题和可证伪的核心论点";
  if (value.pillars.length < 3 || value.pillars.length > 5) return "核心支柱应保持 3–5 项";
  if (value.pillars.some((item) => !item.title.trim() || !item.expectation.trim() || !item.currentStatus.trim())) {
    return "每个核心支柱都需要标题、原始预期和当前状态";
  }
  if (value.invalidationRisks.length < 3 || value.invalidationRisks.length > 5) return "证伪风险应保持 3–5 项";
  if (value.invalidationRisks.some((item) => !item.statement.trim() || !item.invalidationCondition.trim())) {
    return "每项风险都需要风险描述和可观察的证伪条件";
  }
  return "";
}

function statusTone(status: InvestmentThesis["status"]) {
  if (status === "invalidated") return "border-destructive/30 bg-destructive/10 text-destructive";
  if (status === "active") return "border-success/30 bg-success/10 text-success";
  if (status === "watch") return "border-warning/30 bg-warning/10 text-warning";
  return "border-border bg-muted/45 text-muted-foreground";
}

function impactTone(impact: ThesisImpact) {
  if (impact === "strengthened") return "text-success";
  if (impact === "weakened" || impact === "invalidated") return "text-destructive";
  return "text-muted-foreground";
}

function thesisContext(
  portfolio: InvestmentThesisPortfolio,
  selected: InvestmentThesis | undefined,
  draft: InvestmentThesis,
  dirty: boolean,
): VibeDeskPageContext {
  const active = selected || draft;
  return {
    view: { id: "thesis-tracker", title: "投资逻辑" },
    visibleBlocks: [
      { id: "thesis-core", type: "investment-thesis", title: "核心论点" },
      { id: "thesis-scorecard", type: "pillar-scorecard", title: "支柱计分卡" },
      { id: "thesis-risks", type: "invalidation-risks", title: "证伪条件" },
      { id: "thesis-evidence", type: "evidence-ledger", title: "证据与更新" },
    ],
    selection: {
      symbol: active.security.symbol,
      market: active.security.market,
      name: active.security.name,
      thesisId: active.id,
      status: active.status,
      conviction: active.conviction,
    },
    filters: {
      nextReviewAt: active.nextReviewAt,
      unsavedChanges: dirty,
    },
    data: {
      asOf: selected?.updatedAt || portfolio.updatedAt,
      source: portfolio.schemaVersion,
      freshness: "fresh",
      summary: {
        thesisCount: portfolio.theses.length,
        selectedThesis: {
          title: active.title,
          statement: active.statement,
          status: active.status,
          conviction: active.conviction,
          pillars: active.pillars,
          invalidationRisks: active.invalidationRisks,
          linkedCatalysts: active.linkedCatalysts,
          evidence: active.evidence.slice(0, 40),
          updates: active.updates.slice(0, 40),
          valuation: active.valuation,
          nextReviewAt: active.nextReviewAt,
          gaps: active.gaps,
        },
      },
    },
    actions: [
      { id: "thesis.create", label: "新建投资逻辑", available: true },
      { id: "thesis.add-evidence", label: "新增证据并判断影响", available: true },
      { id: "thesis.review", label: "记录阶段复盘", available: true },
      { id: "thesis.invalidate", label: "标记已证伪", available: active.status !== "invalidated" },
    ],
    tasks: [],
  };
}

export function ThesisTracker() {
  const initial = useMemo(loadLocalThesisPortfolio, []);
  const [portfolio, setPortfolio] = useState(initial);
  const [selectedId, setSelectedId] = useState(initial.theses[0]?.id || "__new__");
  const [draft, setDraft] = useState(() => initial.theses[0] ? copyThesis(initial.theses[0]) : blankThesis());
  const [message, setMessage] = useState("");
  const [catalystDraft, setCatalystDraft] = useState({ id: "", title: "", date: "" });
  const [evidenceDraft, setEvidenceDraft] = useState({
    source: "",
    url: "",
    asOf: today(),
    summary: "",
    freshness: "fresh" as "live" | "fresh" | "stale" | "unknown",
    confidence: "medium" as ThesisConviction,
    impact: "neutral" as ThesisImpact,
    pillarId: "",
  });
  const [reviewDraft, setReviewDraft] = useState({
    date: today(),
    dataPoint: "",
    impact: "neutral" as ThesisImpact,
    pillarId: "",
  });

  const selected = portfolio.theses.find((item) => item.id === selectedId);
  const dirty = selectedId === "__new__"
    ? Boolean(draft.security.symbol || draft.security.name || draft.title || draft.statement)
    : JSON.stringify(selected) !== JSON.stringify(draft);

  useEffect(() => {
    let active = true;
    void hydrateThesisPortfolio().then((value) => {
      if (!active) return;
      setPortfolio(value);
      const first = value.theses[0];
      setSelectedId(first?.id || "__new__");
      setDraft(first ? copyThesis(first) : blankThesis());
    });
    return () => { active = false; };
  }, []);

  const contextRef = useRef<VibeDeskPageContext>(thesisContext(portfolio, selected, draft, dirty));
  contextRef.current = thesisContext(portfolio, selected, draft, dirty);
  useEffect(() => registerVibeDeskContextProvider(() => contextRef.current), []);
  useEffect(() => {
    void publishVibeDeskContext();
  }, [dirty, draft, portfolio, selectedId]);

  const commit = (next: InvestmentThesisPortfolio) => {
    setPortfolio(next);
    void persistThesisPortfolio(next);
  };

  const choose = (thesis: InvestmentThesis) => {
    if (dirty && !confirm("当前修改尚未保存，确定切换吗？")) return;
    setSelectedId(thesis.id);
    setDraft(copyThesis(thesis));
    setMessage("");
  };

  const startNew = () => {
    if (dirty && !confirm("当前修改尚未保存，确定新建吗？")) return;
    setSelectedId("__new__");
    setDraft(blankThesis());
    setMessage("");
  };

  const save = () => {
    const error = validateThesis(draft);
    if (error) {
      setMessage(error);
      return;
    }
    const timestamp = new Date().toISOString();
    const saved: InvestmentThesis = {
      ...draft,
      security: {
        market: draft.security.market.trim().toUpperCase(),
        symbol: draft.security.symbol.trim().toUpperCase(),
        name: draft.security.name.trim(),
        ...(draft.security.exchange?.trim() ? { exchange: draft.security.exchange.trim().toUpperCase() } : {}),
      },
      title: draft.title.trim(),
      statement: draft.statement.trim(),
      gaps: draft.gaps.map((item) => item.trim()).filter(Boolean).slice(0, 20),
      updatedAt: timestamp,
    };
    const exists = portfolio.theses.some((item) => item.id === saved.id);
    const theses = exists
      ? portfolio.theses.map((item) => item.id === saved.id ? saved : item)
      : [saved, ...portfolio.theses];
    commit({ ...portfolio, updatedAt: timestamp, theses });
    setSelectedId(saved.id);
    setDraft(copyThesis(saved));
    setMessage("已保存到 Desk 工作区");
  };

  const remove = () => {
    if (selectedId === "__new__") {
      startNew();
      return;
    }
    if (!confirm(`删除“${draft.title || draft.security.name}”的投资逻辑？`)) return;
    const theses = portfolio.theses.filter((item) => item.id !== selectedId);
    const next = { ...portfolio, updatedAt: new Date().toISOString(), theses };
    commit(next);
    const first = theses[0];
    setSelectedId(first?.id || "__new__");
    setDraft(first ? copyThesis(first) : blankThesis());
    setMessage("");
  };

  const addCatalyst = () => {
    if (!catalystDraft.id.trim() && !catalystDraft.title.trim()) return;
    const id = catalystDraft.id.trim() || createId("catalyst-link");
    setDraft((current) => ({
      ...current,
      linkedCatalysts: [
        ...current.linkedCatalysts,
        {
          id,
          title: catalystDraft.title.trim() || id,
          ...(catalystDraft.date ? { date: catalystDraft.date } : {}),
        },
      ].slice(0, 20),
    }));
    setCatalystDraft({ id: "", title: "", date: "" });
  };

  const addEvidence = () => {
    if (!evidenceDraft.source.trim() || !evidenceDraft.summary.trim() || !evidenceDraft.asOf) {
      setMessage("新增证据需要来源、截至日期和摘要");
      return;
    }
    if (evidenceDraft.url.trim()) {
      try {
        new URL(evidenceDraft.url.trim());
      } catch {
        setMessage("证据链接需要是完整的 HTTP(S) URL");
        return;
      }
    }
    const createdAt = new Date().toISOString();
    const evidenceId = createId("evidence");
    const sourceLabel = evidenceDraft.source.trim();
    const evidence = {
      id: evidenceId,
      source: {
        id: sourceLabel.toLowerCase().replace(/[^a-z0-9\u4e00-\u9fa5]+/g, "-").replace(/^-|-$/g, "") || "user-source",
        label: sourceLabel,
        ...(evidenceDraft.url.trim() ? { url: evidenceDraft.url.trim() } : {}),
      },
      summary: evidenceDraft.summary.trim(),
      asOf: evidenceDraft.asOf,
      freshness: { status: evidenceDraft.freshness },
      confidence: {
        level: evidenceDraft.confidence,
        rationale: "用户录入，需结合原始来源和交叉证据复核",
      },
      impact: evidenceDraft.impact,
      ...(evidenceDraft.pillarId ? { pillarId: evidenceDraft.pillarId } : {}),
      createdAt,
    };
    setDraft((current) => ({
      ...current,
      evidence: [evidence, ...current.evidence].slice(0, 100),
      updates: [{
        id: createId("update"),
        date: evidenceDraft.asOf,
        dataPoint: evidenceDraft.summary.trim(),
        impact: evidenceDraft.impact,
        ...(evidenceDraft.pillarId ? { pillarId: evidenceDraft.pillarId } : {}),
        evidenceIds: [evidenceId],
        conviction: current.conviction,
        note: "由证据记录自动生成",
      }, ...current.updates].slice(0, 100),
      pillars: current.pillars.map((pillar) => pillar.id === evidenceDraft.pillarId
        ? { ...pillar, evidenceIds: [...new Set([evidenceId, ...pillar.evidenceIds])].slice(0, 100) }
        : pillar),
    }));
    setEvidenceDraft({
      source: "",
      url: "",
      asOf: today(),
      summary: "",
      freshness: "fresh",
      confidence: "medium",
      impact: "neutral",
      pillarId: "",
    });
    setMessage("证据已加入草稿，请保存投资逻辑");
  };

  const addReview = () => {
    if (!reviewDraft.dataPoint.trim()) return;
    setDraft((current) => ({
      ...current,
      updates: [{
        id: createId("review"),
        date: reviewDraft.date,
        dataPoint: reviewDraft.dataPoint.trim(),
        impact: reviewDraft.impact,
        ...(reviewDraft.pillarId ? { pillarId: reviewDraft.pillarId } : {}),
        evidenceIds: [],
        conviction: current.conviction,
        note: "阶段复盘",
      }, ...current.updates].slice(0, 100),
    }));
    setReviewDraft({ date: today(), dataPoint: "", impact: "neutral", pillarId: "" });
  };

  const evidenceById = useMemo(
    () => new Map(draft.evidence.map((item) => [item.id, item])),
    [draft.evidence],
  );
  const summaryCards: Array<{ label: string; value: number; icon: LucideIcon }> = [
    { label: "逻辑档案", value: portfolio.theses.length, icon: BookOpenCheck },
    { label: "持续验证", value: portfolio.theses.filter((item) => item.status === "active").length, icon: Target },
    { label: "待复盘", value: portfolio.theses.filter((item) => item.nextReviewAt <= today() && !["archived", "invalidated"].includes(item.status)).length, icon: CalendarClock },
    { label: "已证伪", value: portfolio.theses.filter((item) => item.status === "invalidated").length, icon: ShieldAlert },
  ];

  return (
    <div>
      <PageHeader
        title="投资逻辑"
        subtitle="把核心论点、支柱、反方证据、催化与复盘固化为可证伪、可持续更新的研究档案。"
        actions={(
          <>
            <button onClick={startNew} className="inline-flex items-center gap-1.5 rounded-lg border border-border bg-card/70 px-3 py-2 text-sm hover:border-primary/40">
              <Plus className="h-4 w-4" /> 新建
            </button>
            <button onClick={save} className="inline-flex items-center gap-1.5 rounded-lg bg-primary px-3 py-2 text-sm font-semibold text-primary-foreground hover:opacity-90">
              <Save className="h-4 w-4" /> 保存
            </button>
          </>
        )}
      />

      {message && (
        <div className="mb-4 flex items-center gap-2 rounded-lg border border-primary/20 bg-primary/8 px-3 py-2 text-sm text-foreground">
          <CheckCircle2 className="h-4 w-4 text-primary" /> {message}
        </div>
      )}

      <div className="mb-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {summaryCards.map(({ label, value, icon: Icon }) => (
          <GlassCard key={label} className="flex items-center justify-between p-4">
            <div><div className="text-xs text-muted-foreground">{label}</div><div className="mt-1 text-2xl font-bold">{value}</div></div>
            <Icon className="h-5 w-5 text-primary" />
          </GlassCard>
        ))}
      </div>

      <div className="grid items-start gap-4 xl:grid-cols-[250px_minmax(0,1fr)]">
        <GlassCard className="p-3 xl:sticky xl:top-3">
          <div className="mb-2 flex items-center justify-between px-2">
            <span className="text-xs font-semibold uppercase tracking-[0.14em] text-muted-foreground">研究对象</span>
            <button onClick={startNew} className="rounded-md p-1 text-muted-foreground hover:bg-muted hover:text-foreground" title="新建">
              <Plus className="h-4 w-4" />
            </button>
          </div>
          <div className="space-y-1.5">
            {portfolio.theses.length === 0 && (
              <div className="rounded-lg border border-dashed border-border px-3 py-8 text-center text-xs text-muted-foreground">
                还没有投资逻辑。先建立一个可证伪的研究框架。
              </div>
            )}
            {portfolio.theses.map((item) => (
              <button
                key={item.id}
                onClick={() => choose(item)}
                className={cn(
                  "w-full rounded-lg border px-3 py-2.5 text-left transition",
                  selectedId === item.id ? "border-primary/45 bg-primary/10" : "border-transparent hover:border-border hover:bg-muted/45",
                )}
              >
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <div className="truncate text-sm font-semibold">{item.security.name}</div>
                    <div className="mt-0.5 text-[11px] text-muted-foreground">{item.security.market}:{item.security.symbol}</div>
                  </div>
                  <span className={cn("rounded border px-1.5 py-0.5 text-[10px]", statusTone(item.status))}>{STATUS_LABEL[item.status]}</span>
                </div>
                <div className="mt-2 line-clamp-2 text-xs text-muted-foreground">{item.title}</div>
              </button>
            ))}
          </div>
        </GlassCard>

        <div className="min-w-0 space-y-4">
          <GlassCard glow>
            <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
              <div>
                <div className="text-xs font-semibold uppercase tracking-[0.14em] text-primary">Core thesis</div>
                <h2 className="mt-1 text-lg font-bold">核心论点</h2>
              </div>
              <div className="flex items-center gap-2">
                {dirty && <span className="text-xs text-warning">有未保存修改</span>}
                <button onClick={remove} className="rounded-lg border border-border p-2 text-muted-foreground hover:border-destructive/40 hover:text-destructive" title="删除">
                  <Trash2 className="h-4 w-4" />
                </button>
              </div>
            </div>
            <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
              <label><span className={labelClass}>市场</span><input className={inputClass} value={draft.security.market} onChange={(event) => setDraft({ ...draft, security: { ...draft.security, market: event.target.value } })} placeholder="CN / HK / US" /></label>
              <label><span className={labelClass}>证券代码</span><input className={inputClass} value={draft.security.symbol} onChange={(event) => setDraft({ ...draft, security: { ...draft.security, symbol: event.target.value } })} placeholder="600519" /></label>
              <label><span className={labelClass}>公司名称</span><input className={inputClass} value={draft.security.name} onChange={(event) => setDraft({ ...draft, security: { ...draft.security, name: event.target.value } })} placeholder="贵州茅台" /></label>
              <label><span className={labelClass}>交易所（可选）</span><input className={inputClass} value={draft.security.exchange || ""} onChange={(event) => setDraft({ ...draft, security: { ...draft.security, exchange: event.target.value } })} placeholder="SH" /></label>
            </div>
            <div className="mt-3 grid gap-3 md:grid-cols-3">
              <label className="md:col-span-2"><span className={labelClass}>逻辑标题</span><input className={inputClass} value={draft.title} onChange={(event) => setDraft({ ...draft, title: event.target.value })} placeholder="用一句话概括研究命题" /></label>
              <div className="grid grid-cols-2 gap-2">
                <label><span className={labelClass}>状态</span><select className={inputClass} value={draft.status} onChange={(event) => setDraft({ ...draft, status: event.target.value as InvestmentThesis["status"] })}>{Object.entries(STATUS_LABEL).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
                <label><span className={labelClass}>确信度</span><select className={inputClass} value={draft.conviction} onChange={(event) => setDraft({ ...draft, conviction: event.target.value as ThesisConviction })}>{Object.entries(CONVICTION_LABEL).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
              </div>
            </div>
            <label className="mt-3 block"><span className={labelClass}>可证伪的核心论点</span><textarea className={`${inputClass} min-h-24 resize-y`} value={draft.statement} onChange={(event) => setDraft({ ...draft, statement: event.target.value })} placeholder="说明为什么该判断可能成立，以及什么事实会让它不再成立。避免无法被证伪的泛化表达。" /></label>
          </GlassCard>

          <GlassCard>
            <div className="mb-4 flex items-center justify-between gap-3">
              <div><div className="text-xs font-semibold uppercase tracking-[0.14em] text-primary">Scorecard</div><h2 className="mt-1 text-lg font-bold">核心支柱（3–5 项）</h2></div>
              <button disabled={draft.pillars.length >= 5} onClick={() => setDraft({ ...draft, pillars: [...draft.pillars, blankPillar(draft.pillars.length)] })} className="inline-flex items-center gap-1 rounded-lg border border-border px-2.5 py-1.5 text-xs disabled:opacity-40"><Plus className="h-3.5 w-3.5" /> 添加支柱</button>
            </div>
            <div className="space-y-3">
              {draft.pillars.map((pillar, index) => (
                <div key={pillar.id} className="rounded-xl border border-border/80 bg-muted/20 p-3">
                  <div className="mb-2 flex items-center justify-between">
                    <span className="text-xs font-semibold text-muted-foreground">支柱 {index + 1}</span>
                    <button disabled={draft.pillars.length <= 3} onClick={() => setDraft({ ...draft, pillars: draft.pillars.filter((item) => item.id !== pillar.id) })} className="text-muted-foreground hover:text-destructive disabled:opacity-30"><Trash2 className="h-3.5 w-3.5" /></button>
                  </div>
                  <div className="grid gap-2 md:grid-cols-[1fr_1.4fr_1.4fr_120px]">
                    <input className={inputClass} value={pillar.title} onChange={(event) => setDraft({ ...draft, pillars: draft.pillars.map((item) => item.id === pillar.id ? { ...item, title: event.target.value } : item) })} placeholder="支柱名称" />
                    <input className={inputClass} value={pillar.expectation} onChange={(event) => setDraft({ ...draft, pillars: draft.pillars.map((item) => item.id === pillar.id ? { ...item, expectation: event.target.value } : item) })} placeholder="原始预期 / 可跟踪指标" />
                    <input className={inputClass} value={pillar.currentStatus} onChange={(event) => setDraft({ ...draft, pillars: draft.pillars.map((item) => item.id === pillar.id ? { ...item, currentStatus: event.target.value } : item) })} placeholder="当前状态" />
                    <select className={inputClass} value={pillar.trend} onChange={(event) => setDraft({ ...draft, pillars: draft.pillars.map((item) => item.id === pillar.id ? { ...item, trend: event.target.value as ThesisTrend } : item) })}>{Object.entries(TREND_LABEL).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select>
                  </div>
                  {pillar.evidenceIds.length > 0 && <div className="mt-2 text-[11px] text-muted-foreground">已关联 {pillar.evidenceIds.length} 条证据</div>}
                </div>
              ))}
            </div>
          </GlassCard>

          <GlassCard>
            <div className="mb-4 flex items-center justify-between gap-3">
              <div><div className="text-xs font-semibold uppercase tracking-[0.14em] text-destructive">Falsification</div><h2 className="mt-1 text-lg font-bold">风险与证伪条件（3–5 项）</h2></div>
              <button disabled={draft.invalidationRisks.length >= 5} onClick={() => setDraft({ ...draft, invalidationRisks: [...draft.invalidationRisks, blankRisk(draft.invalidationRisks.length)] })} className="inline-flex items-center gap-1 rounded-lg border border-border px-2.5 py-1.5 text-xs disabled:opacity-40"><Plus className="h-3.5 w-3.5" /> 添加风险</button>
            </div>
            <div className="space-y-3">
              {draft.invalidationRisks.map((risk, index) => (
                <div key={risk.id} className="grid gap-2 rounded-xl border border-border/80 bg-muted/20 p-3 md:grid-cols-[1fr_1.4fr_120px_auto]">
                  <input className={inputClass} value={risk.statement} onChange={(event) => setDraft({ ...draft, invalidationRisks: draft.invalidationRisks.map((item) => item.id === risk.id ? { ...item, statement: event.target.value } : item) })} placeholder={`风险 ${index + 1}`} />
                  <input className={inputClass} value={risk.invalidationCondition} onChange={(event) => setDraft({ ...draft, invalidationRisks: draft.invalidationRisks.map((item) => item.id === risk.id ? { ...item, invalidationCondition: event.target.value } : item) })} placeholder="什么可观察事实会证伪逻辑" />
                  <select className={inputClass} value={risk.status} onChange={(event) => setDraft({ ...draft, invalidationRisks: draft.invalidationRisks.map((item) => item.id === risk.id ? { ...item, status: event.target.value as typeof risk.status } : item) })}><option value="monitoring">监测中</option><option value="triggered">已触发</option><option value="cleared">已消除</option></select>
                  <button disabled={draft.invalidationRisks.length <= 3} onClick={() => setDraft({ ...draft, invalidationRisks: draft.invalidationRisks.filter((item) => item.id !== risk.id) })} className="px-1 text-muted-foreground hover:text-destructive disabled:opacity-30"><Trash2 className="h-4 w-4" /></button>
                </div>
              ))}
            </div>
          </GlassCard>

          <div className="grid gap-4 2xl:grid-cols-2">
            <GlassCard>
              <div className="mb-3 flex items-center gap-2"><Link2 className="h-4 w-4 text-primary" /><h2 className="font-bold">关联催化剂</h2></div>
              <div className="grid gap-2 sm:grid-cols-[1fr_1.4fr_130px_auto]">
                <input className={inputClass} value={catalystDraft.id} onChange={(event) => setCatalystDraft({ ...catalystDraft, id: event.target.value })} placeholder="催化剂 ID" />
                <input className={inputClass} value={catalystDraft.title} onChange={(event) => setCatalystDraft({ ...catalystDraft, title: event.target.value })} placeholder="事件标题" />
                <input type="date" className={inputClass} value={catalystDraft.date} onChange={(event) => setCatalystDraft({ ...catalystDraft, date: event.target.value })} />
                <button onClick={addCatalyst} className="rounded-lg border border-border px-3 text-sm hover:border-primary/40">添加</button>
              </div>
              <div className="mt-3 space-y-2">
                {draft.linkedCatalysts.length === 0 && <div className="rounded-lg border border-dashed border-border px-3 py-5 text-center text-xs text-muted-foreground">可填入催化剂日历中的事件 ID，建立跨 Mod 引用。</div>}
                {draft.linkedCatalysts.map((item) => (
                  <div key={item.id} className="flex items-center justify-between gap-3 rounded-lg bg-muted/35 px-3 py-2 text-sm">
                    <div className="min-w-0"><div className="truncate font-medium">{item.title}</div><div className="text-[11px] text-muted-foreground">{item.id}{item.date ? ` · ${item.date}` : ""}</div></div>
                    <button onClick={() => setDraft({ ...draft, linkedCatalysts: draft.linkedCatalysts.filter((row) => row.id !== item.id) })} className="text-muted-foreground hover:text-destructive"><Trash2 className="h-3.5 w-3.5" /></button>
                  </div>
                ))}
              </div>
            </GlassCard>

            <GlassCard>
              <div className="mb-3 flex items-center gap-2"><CalendarClock className="h-4 w-4 text-primary" /><h2 className="font-bold">复盘节奏与信息缺口</h2></div>
              <label><span className={labelClass}>下次正式复盘</span><input type="date" className={inputClass} value={draft.nextReviewAt} onChange={(event) => setDraft({ ...draft, nextReviewAt: event.target.value })} /></label>
              <label className="mt-3 block"><span className={labelClass}>仍缺少的证据（每行一项）</span><textarea className={`${inputClass} min-h-28 resize-y`} value={draft.gaps.join("\n")} onChange={(event) => setDraft({ ...draft, gaps: event.target.value.split("\n").slice(0, 20) })} placeholder="例如：缺少渠道库存的一手数据" /></label>
            </GlassCard>
          </div>

          <GlassCard>
            <div className="mb-4 flex items-center gap-2"><FileSearch className="h-4 w-4 text-primary" /><div><h2 className="font-bold">新增证据并判断影响</h2><p className="mt-0.5 text-xs text-muted-foreground">证据会同步写入更新日志，并可绑定到一个核心支柱。</p></div></div>
            <div className="grid gap-2 md:grid-cols-2 xl:grid-cols-4">
              <input className={inputClass} value={evidenceDraft.source} onChange={(event) => setEvidenceDraft({ ...evidenceDraft, source: event.target.value })} placeholder="来源名称（必填）" />
              <input className={inputClass} value={evidenceDraft.url} onChange={(event) => setEvidenceDraft({ ...evidenceDraft, url: event.target.value })} placeholder="原始来源 URL（可选）" />
              <input type="date" className={inputClass} value={evidenceDraft.asOf} onChange={(event) => setEvidenceDraft({ ...evidenceDraft, asOf: event.target.value })} />
              <select className={inputClass} value={evidenceDraft.pillarId} onChange={(event) => setEvidenceDraft({ ...evidenceDraft, pillarId: event.target.value })}><option value="">不绑定支柱</option>{draft.pillars.map((item) => <option key={item.id} value={item.id}>{item.title || "未命名支柱"}</option>)}</select>
              <select className={inputClass} value={evidenceDraft.freshness} onChange={(event) => setEvidenceDraft({ ...evidenceDraft, freshness: event.target.value as typeof evidenceDraft.freshness })}><option value="live">实时</option><option value="fresh">新鲜</option><option value="stale">陈旧</option><option value="unknown">未知</option></select>
              <select className={inputClass} value={evidenceDraft.confidence} onChange={(event) => setEvidenceDraft({ ...evidenceDraft, confidence: event.target.value as ThesisConviction })}>{Object.entries(CONVICTION_LABEL).map(([value, label]) => <option key={value} value={value}>可信度：{label}</option>)}</select>
              <select className={inputClass} value={evidenceDraft.impact} onChange={(event) => setEvidenceDraft({ ...evidenceDraft, impact: event.target.value as ThesisImpact })}>{Object.entries(IMPACT_LABEL).map(([value, label]) => <option key={value} value={value}>影响：{label}</option>)}</select>
              <button onClick={addEvidence} className="rounded-lg bg-primary px-3 py-2 text-sm font-semibold text-primary-foreground hover:opacity-90">加入证据</button>
            </div>
            <textarea className={`${inputClass} mt-2 min-h-20 resize-y`} value={evidenceDraft.summary} onChange={(event) => setEvidenceDraft({ ...evidenceDraft, summary: event.target.value })} placeholder="数据点、公告、新闻或调研结论；说明它如何增强、削弱或不改变当前逻辑。" />

            <div className="mt-4 space-y-2">
              {draft.evidence.length === 0 && <div className="rounded-lg border border-dashed border-border px-3 py-6 text-center text-xs text-muted-foreground">尚未记录证据。确认性与反方证据应使用同一标准记录。</div>}
              {draft.evidence.slice(0, 20).map((item) => (
                <div key={item.id} className="rounded-xl border border-border/80 bg-muted/20 p-3">
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-2 text-xs"><span className="font-semibold">{item.source.label}</span><span className="text-muted-foreground">截至 {item.asOf}</span><span className={impactTone(item.impact)}>{IMPACT_LABEL[item.impact]}</span><span className="text-muted-foreground">可信度 {CONVICTION_LABEL[item.confidence.level]}</span></div>
                      <p className="mt-1.5 text-sm leading-6">{item.summary}</p>
                      <div className="mt-1 text-[11px] text-muted-foreground">证据 ID：{item.id}{item.pillarId ? ` · 支柱：${draft.pillars.find((pillar) => pillar.id === item.pillarId)?.title || item.pillarId}` : ""}</div>
                    </div>
                    <button onClick={() => setDraft({ ...draft, evidence: draft.evidence.filter((row) => row.id !== item.id), pillars: draft.pillars.map((pillar) => ({ ...pillar, evidenceIds: pillar.evidenceIds.filter((id) => id !== item.id) })) })} className="text-muted-foreground hover:text-destructive"><Trash2 className="h-4 w-4" /></button>
                  </div>
                </div>
              ))}
            </div>
          </GlassCard>

          <div className="grid gap-4 2xl:grid-cols-2">
            <GlassCard>
              <div className="mb-3 flex items-center gap-2"><BookOpenCheck className="h-4 w-4 text-primary" /><h2 className="font-bold">阶段复盘</h2></div>
              <div className="grid gap-2 sm:grid-cols-3">
                <input type="date" className={inputClass} value={reviewDraft.date} onChange={(event) => setReviewDraft({ ...reviewDraft, date: event.target.value })} />
                <select className={inputClass} value={reviewDraft.pillarId} onChange={(event) => setReviewDraft({ ...reviewDraft, pillarId: event.target.value })}><option value="">整体逻辑</option>{draft.pillars.map((item) => <option key={item.id} value={item.id}>{item.title || "未命名支柱"}</option>)}</select>
                <select className={inputClass} value={reviewDraft.impact} onChange={(event) => setReviewDraft({ ...reviewDraft, impact: event.target.value as ThesisImpact })}>{Object.entries(IMPACT_LABEL).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select>
              </div>
              <textarea className={`${inputClass} mt-2 min-h-20 resize-y`} value={reviewDraft.dataPoint} onChange={(event) => setReviewDraft({ ...reviewDraft, dataPoint: event.target.value })} placeholder="本次复盘的新变化、判断与下一项待验证证据" />
              <button onClick={addReview} className="mt-2 rounded-lg border border-border px-3 py-2 text-sm hover:border-primary/40">记录复盘</button>
            </GlassCard>

            <GlassCard>
              <div className="mb-3 flex items-center gap-2"><Archive className="h-4 w-4 text-primary" /><h2 className="font-bold">估值上下文（可选）</h2></div>
              <div className="grid gap-2 sm:grid-cols-2">
                <input className={inputClass} value={draft.valuation?.method || ""} onChange={(event) => setDraft({ ...draft, valuation: event.target.value ? { method: event.target.value, referenceValue: draft.valuation?.referenceValue ?? null, currency: draft.valuation?.currency || "CNY", asOf: draft.valuation?.asOf, assumptions: draft.valuation?.assumptions || [] } : undefined })} placeholder="方法 / 参照框架" />
                <input className={inputClass} value={draft.valuation?.currency || "CNY"} onChange={(event) => setDraft({ ...draft, valuation: { method: draft.valuation?.method || "待补充", referenceValue: draft.valuation?.referenceValue ?? null, currency: event.target.value, asOf: draft.valuation?.asOf, assumptions: draft.valuation?.assumptions || [] } })} placeholder="币种" />
                <input type="number" className={inputClass} value={draft.valuation?.referenceValue ?? ""} onChange={(event) => setDraft({ ...draft, valuation: { method: draft.valuation?.method || "待补充", referenceValue: event.target.value ? Number(event.target.value) : null, currency: draft.valuation?.currency || "CNY", asOf: draft.valuation?.asOf, assumptions: draft.valuation?.assumptions || [] } })} placeholder="参考值（非目标价）" />
                <input type="date" className={inputClass} value={draft.valuation?.asOf || ""} onChange={(event) => setDraft({ ...draft, valuation: { method: draft.valuation?.method || "待补充", referenceValue: draft.valuation?.referenceValue ?? null, currency: draft.valuation?.currency || "CNY", asOf: event.target.value || undefined, assumptions: draft.valuation?.assumptions || [] } })} />
              </div>
              <textarea className={`${inputClass} mt-2 min-h-20 resize-y`} value={draft.valuation?.assumptions.join("\n") || ""} onChange={(event) => setDraft({ ...draft, valuation: { method: draft.valuation?.method || "待补充", referenceValue: draft.valuation?.referenceValue ?? null, currency: draft.valuation?.currency || "CNY", asOf: draft.valuation?.asOf, assumptions: event.target.value.split("\n").filter(Boolean).slice(0, 20) } })} placeholder="每行一项估值假设；仅用于研究上下文，不构成目标价或买卖建议。" />
            </GlassCard>
          </div>

          <GlassCard>
            <div className="mb-3 flex items-center gap-2"><CircleAlert className="h-4 w-4 text-primary" /><h2 className="font-bold">更新日志</h2></div>
            <div className="space-y-2">
              {draft.updates.length === 0 && <div className="text-sm text-muted-foreground">暂无更新。至少按季度复盘一次，即使没有重大变化。</div>}
              {draft.updates.slice(0, 30).map((item) => {
                const linkedEvidence = item.evidenceIds.map((id) => evidenceById.get(id)).filter(Boolean);
                return (
                  <div key={item.id} className="grid gap-2 rounded-lg border border-border/70 px-3 py-2.5 sm:grid-cols-[100px_80px_minmax(0,1fr)_auto]">
                    <span className="text-xs text-muted-foreground">{item.date}</span>
                    <span className={cn("text-xs font-semibold", impactTone(item.impact))}>{IMPACT_LABEL[item.impact]}</span>
                    <div className="text-sm"><div>{item.dataPoint}</div>{linkedEvidence.length > 0 && <div className="mt-1 text-[11px] text-muted-foreground">关联 {linkedEvidence.length} 条证据</div>}</div>
                    <button onClick={() => setDraft({ ...draft, updates: draft.updates.filter((row) => row.id !== item.id) })} className="text-muted-foreground hover:text-destructive"><Trash2 className="h-3.5 w-3.5" /></button>
                  </div>
                );
              })}
            </div>
          </GlassCard>

          <div className="flex items-start gap-2 rounded-xl border border-warning/25 bg-warning/8 px-4 py-3 text-xs text-muted-foreground">
            <ShieldAlert className="mt-0.5 h-4 w-4 shrink-0 text-warning" />
            本模块只维护可核验的研究命题、证据与证伪条件，不提供仓位、增减持、止损或买卖时机建议。状态变化应由新增证据驱动，并保留来源、截至日期和信息缺口。
          </div>
          <Disclaimer />
        </div>
      </div>
    </div>
  );
}
