import { useEffect, useMemo, useRef, useState } from "react";
import {
  BarChart3,
  BookOpenCheck,
  CalendarClock,
  CheckCircle2,
  Database,
  FileCheck2,
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
import { api, type EquityResearchEvidence, type EquityResearchSnapshot, type Financials } from "@/lib/api";
import {
  blankEarningsWorkbook,
  calculateVariance,
  hydrateEarningsWorkspace,
  loadLocalEarningsWorkspace,
  persistEarningsWorkspace,
  type EarningsImpact,
  type EarningsMetric,
  type EarningsSource,
  type EarningsWorkbook,
  type EarningsWorkspace,
  type EstimateRevision,
  type GuidanceComparison,
} from "@/lib/earningsWorkbench";
import { cn } from "@/lib/utils";
import {
  publishVibeDeskContext,
  registerVibeDeskContextProvider,
  subscribeVibeDeskEvent,
  type VibeDeskPageContext,
} from "@/lib/vibedesk";

const inputClass = "w-full rounded-lg border border-border bg-card/70 px-3 py-2 text-sm text-foreground outline-none transition focus:border-primary/60 focus:ring-2 focus:ring-primary/15";
const compactInputClass = "w-full min-w-20 rounded-md border border-border bg-card/75 px-2 py-1.5 text-right text-xs text-foreground outline-none focus:border-primary/60";
const labelClass = "mb-1.5 block text-xs font-semibold text-muted-foreground";
const MODE_LABEL = { preview: "财报前", reported: "财报后" } as const;
const IMPACT_LABEL = {
  strengthened: "增强",
  weakened: "削弱",
  neutral: "中性",
  invalidated: "证伪",
} as const;
const SCENARIO_LABEL = { above: "高于预期", inline: "符合预期", below: "低于预期" } as const;

function copyWorkbook(value: EarningsWorkbook) {
  return structuredClone(value);
}

function createId(prefix: string) {
  const suffix = globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(16).slice(2)}`;
  return `${prefix}:${suffix}`;
}

function today() {
  return new Date().toISOString().slice(0, 10);
}

function parseNumber(value: string) {
  const trimmed = value.trim();
  if (!trimmed) return null;
  const parsed = Number(trimmed.replace(/,/g, ""));
  return Number.isFinite(parsed) ? parsed : null;
}

function metricValue(value: unknown, money = false) {
  if (typeof value === "number" && Number.isFinite(value)) {
    return money && Math.abs(value) >= 1_000_000 ? value / 100_000_000 : value;
  }
  if (typeof value !== "string") return null;
  const parsed = Number(value.replace(/,/g, "").match(/-?\d+(?:\.\d+)?/)?.[0]);
  if (!Number.isFinite(parsed)) return null;
  if (!money) return parsed;
  if (value.includes("万亿")) return parsed * 10_000;
  if (value.includes("亿")) return parsed;
  if (value.includes("万")) return parsed / 10_000;
  return Math.abs(parsed) >= 1_000_000 ? parsed / 100_000_000 : parsed;
}

function slug(value: string) {
  return value.toLowerCase().replace(/[^a-z0-9\u4e00-\u9fa5]+/g, "-").replace(/^-|-$/g, "").slice(0, 100) || "source";
}

function latestPeriod(snapshot: EquityResearchSnapshot | null, financials: Financials | null) {
  if (financials?.period) return financials.period;
  return snapshot?.evidenceLedger.find((item) => item.asOf && ["growth", "profitability", "cash_flow"].includes(item.dimension))?.asOf || "";
}

function evidenceById(snapshot: EquityResearchSnapshot | null) {
  return new Map((snapshot?.evidenceLedger || []).map((item) => [item.id, item]));
}

function sourceForEvidence(evidence: EquityResearchEvidence | undefined) {
  return evidence ? `source:${slug(evidence.source)}` : "";
}

function buildSources(snapshot: EquityResearchSnapshot | null, checkedAt: string): EarningsSource[] {
  const rows = new Map<string, EarningsSource>();
  for (const evidence of snapshot?.evidenceLedger || []) {
    const id = sourceForEvidence(evidence);
    if (!id || rows.has(id)) continue;
    rows.set(id, {
      id,
      label: evidence.source,
      kind: evidence.sourceType === "filing" ? "filing" : evidence.sourceType === "derived" ? "derived" : "company",
      ...(evidence.url ? { url: evidence.url } : {}),
      asOf: evidence.asOf || checkedAt.slice(0, 10),
      status: evidence.confidence === "high" ? "verified" : "available",
    });
  }
  return [...rows.values()].slice(0, 80);
}

function applyFetchedEvidence(
  workbook: EarningsWorkbook,
  snapshot: EquityResearchSnapshot | null,
  financials: Financials | null,
  extraSources: EarningsSource[],
  errors: string[],
) {
  const checkedAt = new Date().toISOString();
  const evidence = evidenceById(snapshot);
  const period = latestPeriod(snapshot, financials);
  const mapping: Record<string, { financialKey: keyof Financials; evidenceId: string; money?: boolean }> = {
    revenue: { financialKey: "revenue", evidenceId: "growth.revenue", money: true },
    "revenue-yoy": { financialKey: "revenue_yoy", evidenceId: "growth.revenue_yoy" },
    "net-profit": { financialKey: "net_profit", evidenceId: "growth.net_profit", money: true },
    "net-profit-yoy": { financialKey: "net_profit_yoy", evidenceId: "growth.net_profit_yoy" },
    eps: { financialKey: "eps", evidenceId: "profitability.eps" },
    "gross-margin": { financialKey: "gross_margin", evidenceId: "profitability.gross_margin" },
    "net-margin": { financialKey: "net_margin", evidenceId: "profitability.net_margin" },
    roe: { financialKey: "roe", evidenceId: "profitability.roe" },
    "op-cf-ps": { financialKey: "op_cf_ps", evidenceId: "cash_flow.op_cf_ps" },
  };
  const metrics = workbook.metrics.map((metric) => {
    const config = mapping[metric.id];
    if (!config) return metric;
    const ledger = evidence.get(config.evidenceId);
    const raw = financials?.[config.financialKey] ?? ledger?.value;
    const reported = metricValue(raw, config.money);
    const sourceId = sourceForEvidence(ledger);
    return calculateVariance({
      ...metric,
      reported: reported ?? metric.reported,
      sourceIds: sourceId ? [sourceId] : metric.sourceIds,
      ...(ledger?.asOf || period ? { asOf: ledger?.asOf || period } : {}),
    });
  });
  const sources = [...buildSources(snapshot, checkedAt), ...extraSources]
    .filter((source, index, list) => list.findIndex((item) => item.id === source.id) === index);
  const primarySourceIds = metrics.flatMap((metric) => metric.sourceIds).filter((id, index, list) => list.indexOf(id) === index);
  return {
    ...workbook,
    security: snapshot
      ? {
          ...workbook.security,
          market: snapshot.identity.market,
          symbol: snapshot.identity.symbol,
          name: snapshot.identity.name,
          currency: snapshot.identity.currency,
        }
      : workbook.security,
    mode: period ? "reported" as const : workbook.mode,
    fiscalPeriod: {
      ...workbook.fiscalPeriod,
      label: workbook.fiscalPeriod.label || period || "待确认报告期",
      ...(period && /^\d{4}-\d{2}-\d{2}$/.test(period) ? { periodEnd: period } : {}),
    },
    verification: {
      status: snapshot && period ? "verified" as const : snapshot ? "partial" as const : "unverified" as const,
      latestPeriodChecked: Boolean(snapshot),
      checkedAt,
      primarySourceIds,
    },
    metrics,
    sourceMaterials: sources,
    gaps: [...new Set([...(snapshot?.gaps || []), ...errors])].slice(0, 30),
    updatedAt: checkedAt,
  };
}

function varianceLabel(metric: EarningsMetric) {
  const value = metric.varianceVsConsensus;
  if (value.bps !== null) return `${value.bps >= 0 ? "+" : ""}${value.bps.toFixed(0)}bp`;
  if (value.percent !== null) return `${value.percent >= 0 ? "+" : ""}${value.percent.toFixed(1)}%`;
  return "—";
}

function workbookContext(workspace: EarningsWorkspace, workbook: EarningsWorkbook, loading: boolean): VibeDeskPageContext {
  return {
    view: { id: "earnings-workbench", title: "财报研究" },
    visibleBlocks: [
      { id: "earnings-verification", type: "source-verification", title: "报告期与来源核验" },
      { id: "earnings-variance", type: "earnings-variance", title: "实际与预期差" },
      { id: "earnings-guidance", type: "guidance-comparison", title: "指引变化" },
      { id: "earnings-scenarios", type: "conditional-scenarios", title: "条件情景" },
      { id: "earnings-revisions", type: "estimate-revisions", title: "预测修订" },
      { id: "earnings-thesis", type: "thesis-impact", title: "投资逻辑影响" },
    ],
    selection: {
      symbol: workbook.security.symbol,
      market: workbook.security.market,
      name: workbook.security.name,
      workbookId: workbook.id,
      fiscalPeriod: workbook.fiscalPeriod.label,
      mode: workbook.mode,
    },
    filters: {
      reportingDate: workbook.fiscalPeriod.reportingDate,
      reportingTime: workbook.fiscalPeriod.reportingTime,
    },
    data: {
      asOf: workbook.verification.checkedAt || workspace.updatedAt,
      source: workspace.schemaVersion,
      freshness: loading ? "unknown" : workbook.verification.status === "verified" ? "fresh" : "unknown",
      summary: {
        verification: workbook.verification,
        headline: workbook.headline,
        metrics: workbook.metrics,
        operatingMetrics: workbook.operatingMetrics,
        guidance: workbook.guidance,
        scenarios: workbook.scenarios,
        estimateRevisions: workbook.estimateRevisions,
        thesisImpacts: workbook.thesisImpacts,
        sourceMaterials: workbook.sourceMaterials,
        gaps: workbook.gaps,
      },
    },
    actions: [
      { id: "earnings.refresh-evidence", label: "刷新财务、公告、研报与新闻证据", available: true },
      { id: "earnings.compare", label: "分析实际与预期差", available: workbook.mode === "reported" },
      { id: "earnings.revise-estimates", label: "记录预测修订", available: true },
      { id: "earnings.update-thesis", label: "记录投资逻辑影响", available: true },
    ],
    tasks: loading ? [{ id: `earnings-refresh:${workbook.security.symbol}`, status: "running", actionId: "earnings.refresh-evidence" }] : [],
  };
}

function NumberInput({ value, onChange, ariaLabel }: { value: number | null; onChange: (value: number | null) => void; ariaLabel: string }) {
  return (
    <input
      className={compactInputClass}
      inputMode="decimal"
      aria-label={ariaLabel}
      value={value ?? ""}
      onChange={(event) => onChange(parseNumber(event.target.value))}
      placeholder="—"
    />
  );
}

export function EarningsWorkbench() {
  const initial = useMemo(loadLocalEarningsWorkspace, []);
  const [workspace, setWorkspace] = useState(initial);
  const [selectedId, setSelectedId] = useState(initial.workbooks[0]?.id || "__new__");
  const [draft, setDraft] = useState(() => initial.workbooks[0] ? copyWorkbook(initial.workbooks[0]) : blankEarningsWorkbook());
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState("");

  const selected = workspace.workbooks.find((item) => item.id === selectedId);
  const dirty = selectedId === "__new__"
    ? Boolean(draft.security.symbol || draft.security.name || draft.fiscalPeriod.label)
    : JSON.stringify(selected) !== JSON.stringify(draft);

  useEffect(() => {
    let active = true;
    void hydrateEarningsWorkspace().then((value) => {
      if (!active) return;
      setWorkspace(value);
      const first = value.workbooks[0];
      setSelectedId(first?.id || "__new__");
      setDraft(first ? copyWorkbook(first) : blankEarningsWorkbook());
    });
    return () => { active = false; };
  }, []);

  const contextRef = useRef<VibeDeskPageContext>(workbookContext(workspace, draft, loading));
  contextRef.current = workbookContext(workspace, draft, loading);
  useEffect(() => registerVibeDeskContextProvider(() => contextRef.current), []);
  useEffect(() => {
    const unsubscribe = subscribeVibeDeskEvent((event) => {
      if (event.event !== "security.selected") return;
      const symbol = typeof event.payload.symbol === "string" ? event.payload.symbol.slice(0, 40).toUpperCase() : "";
      if (!symbol) return;
      const market = typeof event.payload.market === "string" ? event.payload.market.slice(0, 20).toUpperCase() : "CN";
      const name = typeof event.payload.name === "string" ? event.payload.name.slice(0, 120) : "";
      setDraft((current) => ({
        ...current,
        security: {
          ...current.security,
          symbol,
          market,
          ...(name ? { name } : {}),
          currency: market === "US" ? "USD" : market === "HK" ? "HKD" : "CNY",
        },
      }));
    });
    return () => { unsubscribe(); };
  }, []);
  useEffect(() => { void publishVibeDeskContext(); }, [draft, loading, workspace]);

  const commit = (next: EarningsWorkspace) => {
    setWorkspace(next);
    void persistEarningsWorkspace(next);
  };

  const startNew = () => {
    if (dirty && !confirm("当前财报研究尚未保存，确定新建吗？")) return;
    setSelectedId("__new__");
    setDraft(blankEarningsWorkbook());
    setMessage("");
  };

  const choose = (workbook: EarningsWorkbook) => {
    if (dirty && !confirm("当前财报研究尚未保存，确定切换吗？")) return;
    setSelectedId(workbook.id);
    setDraft(copyWorkbook(workbook));
    setMessage("");
  };

  const save = () => {
    if (!draft.security.symbol.trim() || !draft.security.name.trim()) {
      setMessage("请补充证券代码与公司名称");
      return;
    }
    if (!draft.fiscalPeriod.label.trim()) {
      setMessage("请确认财报所属报告期");
      return;
    }
    if (draft.scenarios.some((item) => !item.condition.trim() || !item.operatingPath.trim() || !item.researchResponse.trim())) {
      setMessage("三种条件情景都需要条件、经营路径和研究响应");
      return;
    }
    if (draft.operatingMetrics.some((item) => !item.label.trim() || !item.unit.trim())) {
      setMessage("公司特定经营指标需要名称和单位");
      return;
    }
    if (draft.guidance.some((item) => !item.label.trim() || !item.period.trim() || !item.unit.trim())) {
      setMessage("每项管理层指引都需要指标、期间和单位");
      return;
    }
    if (draft.estimateRevisions.some((item) => !item.label.trim() || !item.period.trim() || !item.unit.trim() || !item.reason.trim())) {
      setMessage("每项预测修订都需要指标、期间、单位和调整原因");
      return;
    }
    if (draft.thesisImpacts.some((item) => !item.summary.trim())) {
      setMessage("请说明每项财报证据如何影响投资逻辑");
      return;
    }
    const timestamp = new Date().toISOString();
    const saved: EarningsWorkbook = {
      ...draft,
      security: {
        market: draft.security.market.trim().toUpperCase(),
        symbol: draft.security.symbol.trim().toUpperCase(),
        name: draft.security.name.trim(),
        ...(draft.security.exchange?.trim() ? { exchange: draft.security.exchange.trim().toUpperCase() } : {}),
        currency: draft.security.currency.trim().toUpperCase() || "CNY",
      },
      fiscalPeriod: { ...draft.fiscalPeriod, label: draft.fiscalPeriod.label.trim() },
      headline: draft.headline.trim(),
      metrics: draft.metrics.map(calculateVariance),
      operatingMetrics: draft.operatingMetrics.map(calculateVariance),
      gaps: draft.gaps.map((item) => item.trim()).filter(Boolean).slice(0, 30),
      updatedAt: timestamp,
    };
    const exists = workspace.workbooks.some((item) => item.id === saved.id);
    const workbooks = exists
      ? workspace.workbooks.map((item) => item.id === saved.id ? saved : item)
      : [saved, ...workspace.workbooks];
    commit({ ...workspace, updatedAt: timestamp, workbooks });
    setSelectedId(saved.id);
    setDraft(copyWorkbook(saved));
    setMessage("已保存到 Desk 工作区");
  };

  const remove = () => {
    if (selectedId === "__new__") {
      startNew();
      return;
    }
    if (!confirm(`删除“${draft.security.name} ${draft.fiscalPeriod.label}”的财报研究？`)) return;
    const workbooks = workspace.workbooks.filter((item) => item.id !== selectedId);
    const next = { ...workspace, updatedAt: new Date().toISOString(), workbooks };
    commit(next);
    const first = workbooks[0];
    setSelectedId(first?.id || "__new__");
    setDraft(first ? copyWorkbook(first) : blankEarningsWorkbook());
  };

  const refreshEvidence = async () => {
    const symbol = draft.security.symbol.trim().toUpperCase();
    if (!symbol) {
      setMessage("请先填写证券代码");
      return;
    }
    setLoading(true);
    setMessage("");
    const calls = await Promise.allSettled([
      api.equityResearch(symbol),
      draft.security.market.toUpperCase() === "CN" ? api.financials(symbol) : Promise.resolve(null),
      api.announcements(symbol),
      api.reports(symbol),
      api.news(symbol),
    ]);
    const snapshot = calls[0].status === "fulfilled" ? calls[0].value : null;
    const financials = calls[1].status === "fulfilled" ? calls[1].value : null;
    const checkedAt = new Date().toISOString();
    const extras: EarningsSource[] = [];
    if (calls[2].status === "fulfilled" && calls[2].value.length) {
      extras.push({ id: "source:announcements", label: "公司公告", kind: "filing", asOf: calls[2].value[0]?.date || today(), status: "available" });
    }
    if (calls[3].status === "fulfilled" && calls[3].value.length) {
      extras.push({ id: "source:research-reports", label: "研究报告", kind: "research", asOf: calls[3].value[0]?.publishDate || today(), status: "available" });
    }
    if (calls[4].status === "fulfilled" && calls[4].value.length) {
      extras.push({ id: "source:company-news", label: "公司新闻", kind: "news", asOf: calls[4].value[0]?.发布时间 || today(), status: "available" });
    }
    const names = ["个股研究快照", "财务摘要", "公司公告", "研究报告", "公司新闻"];
    const errors = calls.flatMap((result, index) => result.status === "rejected" ? [`${names[index]}读取失败`] : []);
    const next = applyFetchedEvidence(draft, snapshot, financials, extras, errors);
    setDraft(next);
    setLoading(false);
    setMessage(snapshot ? `已核验最新报告期和来源（${checkedAt.slice(0, 10)}）` : "研究快照读取失败，已保留当前草稿并记录数据缺口");
  };

  const updateMetric = (id: string, field: "reported" | "internalEstimate" | "consensus", value: number | null, operating = false) => {
    const key = operating ? "operatingMetrics" : "metrics";
    setDraft((current) => ({
      ...current,
      [key]: current[key].map((metric) => metric.id === id ? calculateVariance({ ...metric, [field]: value }) : metric),
    }));
  };

  const addOperatingMetric = () => {
    const metric: EarningsMetric = {
      id: createId("operating"),
      label: "",
      category: "operating",
      unit: "原始口径",
      reported: null,
      internalEstimate: null,
      consensus: null,
      varianceVsConsensus: { amount: null, percent: null, bps: null },
      sourceIds: [],
    };
    setDraft((current) => ({
      ...current,
      operatingMetrics: [...current.operatingMetrics, metric].slice(0, 50),
    }));
  };

  const addGuidance = () => {
    const row: GuidanceComparison = {
      id: createId("guidance"), label: "", period: "", unit: "", priorLow: null, priorHigh: null,
      currentLow: null, currentHigh: null, sourceIds: [],
    };
    setDraft((current) => ({ ...current, guidance: [...current.guidance, row].slice(0, 30) }));
  };

  const addRevision = () => {
    const row: EstimateRevision = {
      id: createId("revision"), label: "", period: "", unit: "", previous: null, current: null,
      reason: "", sourceIds: [],
    };
    setDraft((current) => ({ ...current, estimateRevisions: [...current.estimateRevisions, row].slice(0, 30) }));
  };

  const addThesisImpact = () => {
    const row: EarningsWorkbook["thesisImpacts"][number] = {
      id: createId("thesis-impact"),
      impact: "neutral",
      summary: "",
      evidenceIds: [],
    };
    setDraft((current) => ({ ...current, thesisImpacts: [...current.thesisImpacts, row].slice(0, 30) }));
  };

  const verifiedMetricCount = draft.metrics.filter((metric) => metric.reported !== null).length;
  const varianceCount = draft.metrics.filter((metric) => metric.varianceVsConsensus.percent !== null || metric.varianceVsConsensus.bps !== null).length;

  return (
    <div>
      <PageHeader
        title="财报研究"
        subtitle="把财报前预期、财报后实际、Beat/Miss、指引变化、预测修订和投资逻辑影响放进同一套可追溯研究底稿。"
        actions={(
          <>
            <button onClick={startNew} className="inline-flex items-center gap-1.5 rounded-lg border border-border bg-card/70 px-3 py-2 text-sm hover:border-primary/40"><Plus className="h-4 w-4" /> 新建</button>
            <button onClick={refreshEvidence} disabled={loading} className="inline-flex items-center gap-1.5 rounded-lg border border-border bg-card/70 px-3 py-2 text-sm hover:border-primary/40 disabled:opacity-50">
              {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />} 刷新证据
            </button>
            <button onClick={save} className="inline-flex items-center gap-1.5 rounded-lg bg-primary px-3 py-2 text-sm font-semibold text-primary-foreground hover:opacity-90"><Save className="h-4 w-4" /> 保存</button>
          </>
        )}
      />

      {message && <div className="mb-4 flex items-center gap-2 rounded-lg border border-primary/20 bg-primary/8 px-3 py-2 text-sm"><CheckCircle2 className="h-4 w-4 text-primary" /> {message}</div>}

      <div className="mb-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {[
          { label: "研究底稿", value: workspace.workbooks.length, icon: BookOpenCheck },
          { label: "已回填指标", value: verifiedMetricCount, icon: Database },
          { label: "可计算预期差", value: varianceCount, icon: BarChart3 },
          { label: "来源与缺口", value: `${draft.sourceMaterials.length}/${draft.gaps.length}`, icon: SearchCheck },
        ].map(({ label, value, icon: Icon }) => (
          <GlassCard key={label} className="flex items-center justify-between p-4"><div><div className="text-xs text-muted-foreground">{label}</div><div className="mt-1 text-2xl font-bold">{value}</div></div><Icon className="h-5 w-5 text-primary" /></GlassCard>
        ))}
      </div>

      <div className="grid items-start gap-4 xl:grid-cols-[240px_minmax(0,1fr)]">
        <GlassCard className="p-3 xl:sticky xl:top-3">
          <div className="mb-2 flex items-center justify-between px-2"><span className="text-xs font-semibold uppercase tracking-[0.14em] text-muted-foreground">财报底稿</span><button onClick={startNew} className="rounded-md p-1 text-muted-foreground hover:bg-muted"><Plus className="h-4 w-4" /></button></div>
          <div className="space-y-1.5">
            {workspace.workbooks.length === 0 && <div className="rounded-lg border border-dashed border-border px-3 py-8 text-center text-xs text-muted-foreground">还没有底稿。先填写证券并核验最新报告期。</div>}
            {workspace.workbooks.map((item) => (
              <button key={item.id} onClick={() => choose(item)} className={cn("w-full rounded-lg border px-3 py-2.5 text-left", selectedId === item.id ? "border-primary/45 bg-primary/10" : "border-transparent hover:border-border hover:bg-muted/45")}>
                <div className="flex items-start justify-between gap-2"><div className="min-w-0"><div className="truncate text-sm font-semibold">{item.security.name}</div><div className="text-[11px] text-muted-foreground">{item.security.market}:{item.security.symbol}</div></div><span className="rounded border border-border px-1.5 py-0.5 text-[10px] text-muted-foreground">{MODE_LABEL[item.mode]}</span></div>
                <div className="mt-2 truncate text-xs text-muted-foreground">{item.fiscalPeriod.label}</div>
              </button>
            ))}
          </div>
        </GlassCard>

        <div className="min-w-0 space-y-4">
          <GlassCard glow>
            <div className="mb-4 flex flex-wrap items-center justify-between gap-3"><div><div className="text-xs font-semibold uppercase tracking-[0.14em] text-primary">Earnings identity</div><h2 className="mt-1 text-lg font-bold">研究对象与报告期</h2></div><div className="flex items-center gap-2">{dirty && <span className="text-xs text-warning">有未保存修改</span>}<button onClick={remove} className="rounded-lg border border-border p-2 text-muted-foreground hover:border-destructive/40 hover:text-destructive"><Trash2 className="h-4 w-4" /></button></div></div>
            <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-5">
              <label><span className={labelClass}>市场</span><input className={inputClass} value={draft.security.market} onChange={(event) => setDraft({ ...draft, security: { ...draft.security, market: event.target.value } })} placeholder="CN / HK / US" /></label>
              <label><span className={labelClass}>证券代码</span><input className={inputClass} value={draft.security.symbol} onChange={(event) => setDraft({ ...draft, security: { ...draft.security, symbol: event.target.value } })} placeholder="600519 / AAPL" /></label>
              <label><span className={labelClass}>公司名称</span><input className={inputClass} value={draft.security.name} onChange={(event) => setDraft({ ...draft, security: { ...draft.security, name: event.target.value } })} placeholder="公司名称" /></label>
              <label><span className={labelClass}>币种</span><input className={inputClass} value={draft.security.currency} onChange={(event) => setDraft({ ...draft, security: { ...draft.security, currency: event.target.value } })} placeholder="CNY" /></label>
              <label><span className={labelClass}>模式</span><select className={inputClass} value={draft.mode} onChange={(event) => setDraft({ ...draft, mode: event.target.value as EarningsWorkbook["mode"] })}><option value="preview">财报前</option><option value="reported">财报后</option></select></label>
            </div>
            <div className="mt-3 grid gap-3 md:grid-cols-2 xl:grid-cols-4">
              <label><span className={labelClass}>报告期</span><input className={inputClass} value={draft.fiscalPeriod.label} onChange={(event) => setDraft({ ...draft, fiscalPeriod: { ...draft.fiscalPeriod, label: event.target.value } })} placeholder="2026 半年报" /></label>
              <label><span className={labelClass}>期末日期</span><input type="date" className={inputClass} value={draft.fiscalPeriod.periodEnd || ""} onChange={(event) => setDraft({ ...draft, fiscalPeriod: { ...draft.fiscalPeriod, ...(event.target.value ? { periodEnd: event.target.value } : { periodEnd: undefined }) } })} /></label>
              <label><span className={labelClass}>披露日期</span><input type="date" className={inputClass} value={draft.fiscalPeriod.reportingDate || ""} onChange={(event) => setDraft({ ...draft, fiscalPeriod: { ...draft.fiscalPeriod, ...(event.target.value ? { reportingDate: event.target.value } : { reportingDate: undefined }) } })} /></label>
              <label><span className={labelClass}>披露时段</span><select className={inputClass} value={draft.fiscalPeriod.reportingTime} onChange={(event) => setDraft({ ...draft, fiscalPeriod: { ...draft.fiscalPeriod, reportingTime: event.target.value as EarningsWorkbook["fiscalPeriod"]["reportingTime"] } })}><option value="unknown">待确认</option><option value="before-open">开盘前</option><option value="after-close">收盘后</option><option value="during-session">盘中</option></select></label>
            </div>
            <label className="mt-3 block"><span className={labelClass}>一句话结论</span><textarea className={`${inputClass} min-h-20 resize-y`} value={draft.headline} onChange={(event) => setDraft({ ...draft, headline: event.target.value })} placeholder="用中性语言概括核心预期差、驱动与待验证问题，不写评级或买卖建议。" /></label>
          </GlassCard>

          <GlassCard>
            <div className="mb-4 flex flex-wrap items-center justify-between gap-3"><div className="flex items-center gap-2"><FileCheck2 className="h-4 w-4 text-primary" /><div><h2 className="font-bold">报告期与来源核验</h2><p className="mt-0.5 text-xs text-muted-foreground">先确认最新报告期，再解释数字。模型记忆不能替代原始来源。</p></div></div><span className={cn("rounded-full border px-2.5 py-1 text-xs", draft.verification.status === "verified" ? "border-success/30 bg-success/10 text-success" : draft.verification.status === "partial" ? "border-warning/30 bg-warning/10 text-warning" : "border-border text-muted-foreground")}>{draft.verification.status === "verified" ? "已核验" : draft.verification.status === "partial" ? "部分核验" : "未核验"}</span></div>
            <div className="grid gap-3 md:grid-cols-3">
              <div className="rounded-xl border border-border bg-muted/20 p-3"><div className="text-xs text-muted-foreground">最新报告期已检查</div><div className="mt-1 font-semibold">{draft.verification.latestPeriodChecked ? "是" : "否"}</div></div>
              <div className="rounded-xl border border-border bg-muted/20 p-3"><div className="text-xs text-muted-foreground">截至时间</div><div className="mt-1 font-semibold">{draft.verification.checkedAt?.replace("T", " ").slice(0, 16) || "—"}</div></div>
              <div className="rounded-xl border border-border bg-muted/20 p-3"><div className="text-xs text-muted-foreground">主要来源</div><div className="mt-1 font-semibold">{draft.verification.primarySourceIds.length} 个</div></div>
            </div>
          </GlassCard>

          <GlassCard>
            <div className="mb-4"><div className="text-xs font-semibold uppercase tracking-[0.14em] text-primary">Reported vs estimate</div><h2 className="mt-1 text-lg font-bold">核心财务指标与预期差</h2></div>
            <div className="overflow-x-auto">
              <table className="w-full min-w-[780px] text-left text-xs">
                <thead className="text-muted-foreground"><tr className="border-b border-border"><th className="px-2 py-2">指标</th><th className="px-2 py-2">单位</th><th className="px-2 py-2 text-right">实际</th><th className="px-2 py-2 text-right">内部预期</th><th className="px-2 py-2 text-right">一致预期</th><th className="px-2 py-2 text-right">Vs. 一致预期</th><th className="px-2 py-2">截至日期</th></tr></thead>
                <tbody>{draft.metrics.map((metric) => <tr key={metric.id} className="border-b border-border/60"><td className="px-2 py-2 font-medium">{metric.label}</td><td className="px-2 py-2 text-muted-foreground">{metric.unit}</td><td className="px-2 py-2"><NumberInput ariaLabel={`${metric.label} 实际`} value={metric.reported} onChange={(value) => updateMetric(metric.id, "reported", value)} /></td><td className="px-2 py-2"><NumberInput ariaLabel={`${metric.label} 内部预期`} value={metric.internalEstimate} onChange={(value) => updateMetric(metric.id, "internalEstimate", value)} /></td><td className="px-2 py-2"><NumberInput ariaLabel={`${metric.label} 一致预期`} value={metric.consensus} onChange={(value) => updateMetric(metric.id, "consensus", value)} /></td><td className={cn("px-2 py-2 text-right font-semibold", (metric.varianceVsConsensus.percent || metric.varianceVsConsensus.bps || 0) > 0 ? "text-success" : (metric.varianceVsConsensus.percent || metric.varianceVsConsensus.bps || 0) < 0 ? "text-destructive" : "text-muted-foreground")}>{varianceLabel(metric)}</td><td className="px-2 py-2 text-muted-foreground">{metric.asOf || "—"}</td></tr>)}</tbody>
              </table>
            </div>
          </GlassCard>

          <GlassCard>
            <div className="mb-4 flex items-center justify-between gap-3"><div><div className="text-xs font-semibold uppercase tracking-[0.14em] text-primary">Company-specific KPIs</div><h2 className="mt-1 text-lg font-bold">公司特定经营指标</h2></div><button onClick={addOperatingMetric} className="inline-flex items-center gap-1 rounded-lg border border-border px-2.5 py-1.5 text-xs"><Plus className="h-3.5 w-3.5" /> 添加指标</button></div>
            <div className="space-y-2">
              {draft.operatingMetrics.length === 0 && <div className="rounded-lg border border-dashed border-border px-3 py-6 text-center text-xs text-muted-foreground">例如出货量、客单价、门店数、订阅用户、ARPU、产能利用率或订单等公司特定指标。</div>}
              {draft.operatingMetrics.map((metric) => <div key={metric.id} className="grid gap-2 rounded-xl border border-border bg-muted/20 p-3 md:grid-cols-[1.4fr_100px_repeat(3,1fr)_90px_auto]">
                <input className={inputClass} value={metric.label} onChange={(event) => setDraft({ ...draft, operatingMetrics: draft.operatingMetrics.map((item) => item.id === metric.id ? { ...item, label: event.target.value } : item) })} placeholder="指标名称" />
                <input className={inputClass} value={metric.unit} onChange={(event) => setDraft({ ...draft, operatingMetrics: draft.operatingMetrics.map((item) => item.id === metric.id ? { ...item, unit: event.target.value } : item) })} placeholder="单位" />
                <NumberInput ariaLabel={`${metric.label || "经营指标"} 实际`} value={metric.reported} onChange={(value) => updateMetric(metric.id, "reported", value, true)} />
                <NumberInput ariaLabel={`${metric.label || "经营指标"} 内部预期`} value={metric.internalEstimate} onChange={(value) => updateMetric(metric.id, "internalEstimate", value, true)} />
                <NumberInput ariaLabel={`${metric.label || "经营指标"} 一致预期`} value={metric.consensus} onChange={(value) => updateMetric(metric.id, "consensus", value, true)} />
                <div className="self-center text-right text-xs font-semibold text-muted-foreground">{varianceLabel(metric)}</div>
                <button onClick={() => setDraft({ ...draft, operatingMetrics: draft.operatingMetrics.filter((item) => item.id !== metric.id) })} className="text-muted-foreground hover:text-destructive"><Trash2 className="h-4 w-4" /></button>
              </div>)}
            </div>
          </GlassCard>

          <GlassCard>
            <div className="mb-4 flex items-center justify-between gap-3"><div><div className="text-xs font-semibold uppercase tracking-[0.14em] text-primary">Guidance</div><h2 className="mt-1 text-lg font-bold">当前指引与上次指引</h2></div><button onClick={addGuidance} className="inline-flex items-center gap-1 rounded-lg border border-border px-2.5 py-1.5 text-xs"><Plus className="h-3.5 w-3.5" /> 添加指引</button></div>
            <div className="space-y-2">
              {draft.guidance.length === 0 && <div className="rounded-lg border border-dashed border-border px-3 py-6 text-center text-xs text-muted-foreground">未提供指引不等于没有变化；需要记录管理层是否维持、上调、下调或撤回原口径。</div>}
              {draft.guidance.map((row) => <div key={row.id} className="grid gap-2 rounded-xl border border-border bg-muted/20 p-3 lg:grid-cols-[1.2fr_110px_80px_repeat(4,1fr)_auto]">
                <input className={inputClass} value={row.label} onChange={(event) => setDraft({ ...draft, guidance: draft.guidance.map((item) => item.id === row.id ? { ...item, label: event.target.value } : item) })} placeholder="指引指标" />
                <input className={inputClass} value={row.period} onChange={(event) => setDraft({ ...draft, guidance: draft.guidance.map((item) => item.id === row.id ? { ...item, period: event.target.value } : item) })} placeholder="2026E" />
                <input className={inputClass} value={row.unit} onChange={(event) => setDraft({ ...draft, guidance: draft.guidance.map((item) => item.id === row.id ? { ...item, unit: event.target.value } : item) })} placeholder="单位" />
                {(["priorLow", "priorHigh", "currentLow", "currentHigh"] as const).map((field) => <NumberInput key={field} ariaLabel={`${row.label || "指引"} ${field}`} value={row[field]} onChange={(value) => setDraft({ ...draft, guidance: draft.guidance.map((item) => item.id === row.id ? { ...item, [field]: value } : item) })} />)}
                <button onClick={() => setDraft({ ...draft, guidance: draft.guidance.filter((item) => item.id !== row.id) })} className="text-muted-foreground hover:text-destructive"><Trash2 className="h-4 w-4" /></button>
              </div>)}
              {draft.guidance.length > 0 && <div className="grid grid-cols-4 gap-2 px-3 text-center text-[10px] text-muted-foreground lg:ml-[calc(1.2fr+110px+80px)]"><span>上次下限</span><span>上次上限</span><span>当前下限</span><span>当前上限</span></div>}
            </div>
          </GlassCard>

          <GlassCard>
            <div className="mb-4"><div className="text-xs font-semibold uppercase tracking-[0.14em] text-primary">Conditional paths</div><h2 className="mt-1 text-lg font-bold">三种条件情景</h2><p className="mt-1 text-xs text-muted-foreground">情景只描述经营与研究路径，不预测财报后的股价反应。</p></div>
            <div className="grid gap-3 md:grid-cols-3">
              {draft.scenarios.map((scenario) => <div key={scenario.id} className="rounded-xl border border-border bg-muted/20 p-3"><div className="mb-3 font-semibold">{SCENARIO_LABEL[scenario.type]}</div><label><span className={labelClass}>触发条件</span><textarea className={`${inputClass} min-h-20 resize-y`} value={scenario.condition} onChange={(event) => setDraft({ ...draft, scenarios: draft.scenarios.map((item) => item.id === scenario.id ? { ...item, condition: event.target.value } : item) })} /></label><label className="mt-3 block"><span className={labelClass}>经营路径</span><textarea className={`${inputClass} min-h-20 resize-y`} value={scenario.operatingPath} onChange={(event) => setDraft({ ...draft, scenarios: draft.scenarios.map((item) => item.id === scenario.id ? { ...item, operatingPath: event.target.value } : item) })} /></label><label className="mt-3 block"><span className={labelClass}>研究响应</span><textarea className={`${inputClass} min-h-20 resize-y`} value={scenario.researchResponse} onChange={(event) => setDraft({ ...draft, scenarios: draft.scenarios.map((item) => item.id === scenario.id ? { ...item, researchResponse: event.target.value } : item) })} /></label></div>)}
            </div>
          </GlassCard>

          <div className="grid gap-4 2xl:grid-cols-2">
            <GlassCard>
              <div className="mb-4 flex items-center justify-between gap-3"><div><div className="text-xs font-semibold uppercase tracking-[0.14em] text-primary">Estimate revisions</div><h2 className="mt-1 text-lg font-bold">估值与预测修订</h2></div><button onClick={addRevision} className="inline-flex items-center gap-1 rounded-lg border border-border px-2.5 py-1.5 text-xs"><Plus className="h-3.5 w-3.5" /> 添加修订</button></div>
              <div className="space-y-3">{draft.estimateRevisions.length === 0 && <div className="rounded-lg border border-dashed border-border px-3 py-6 text-center text-xs text-muted-foreground">记录旧值、新值和调整原因；不在此生成评级或目标价。</div>}{draft.estimateRevisions.map((row) => <div key={row.id} className="rounded-xl border border-border bg-muted/20 p-3"><div className="grid gap-2 sm:grid-cols-[1fr_100px_80px_auto]"><input className={inputClass} value={row.label} onChange={(event) => setDraft({ ...draft, estimateRevisions: draft.estimateRevisions.map((item) => item.id === row.id ? { ...item, label: event.target.value } : item) })} placeholder="指标，如 EPS" /><input className={inputClass} value={row.period} onChange={(event) => setDraft({ ...draft, estimateRevisions: draft.estimateRevisions.map((item) => item.id === row.id ? { ...item, period: event.target.value } : item) })} placeholder="2026E" /><input className={inputClass} value={row.unit} onChange={(event) => setDraft({ ...draft, estimateRevisions: draft.estimateRevisions.map((item) => item.id === row.id ? { ...item, unit: event.target.value } : item) })} placeholder="单位" /><button onClick={() => setDraft({ ...draft, estimateRevisions: draft.estimateRevisions.filter((item) => item.id !== row.id) })} className="text-muted-foreground hover:text-destructive"><Trash2 className="h-4 w-4" /></button></div><div className="mt-2 grid grid-cols-2 gap-2"><NumberInput ariaLabel={`${row.label || "预测"} 旧值`} value={row.previous} onChange={(value) => setDraft({ ...draft, estimateRevisions: draft.estimateRevisions.map((item) => item.id === row.id ? { ...item, previous: value } : item) })} /><NumberInput ariaLabel={`${row.label || "预测"} 新值`} value={row.current} onChange={(value) => setDraft({ ...draft, estimateRevisions: draft.estimateRevisions.map((item) => item.id === row.id ? { ...item, current: value } : item) })} /></div><textarea className={`${inputClass} mt-2 min-h-16 resize-y`} value={row.reason} onChange={(event) => setDraft({ ...draft, estimateRevisions: draft.estimateRevisions.map((item) => item.id === row.id ? { ...item, reason: event.target.value } : item) })} placeholder="调整原因和依据" /></div>)}</div>
            </GlassCard>

            <GlassCard>
              <div className="mb-4"><div className="text-xs font-semibold uppercase tracking-[0.14em] text-primary">Thesis impact</div><h2 className="mt-1 text-lg font-bold">投资逻辑影响</h2></div>
              <div className="space-y-3">{draft.thesisImpacts.map((row) => <div key={row.id} className="rounded-xl border border-border bg-muted/20 p-3"><div className="mb-2 flex items-center justify-between gap-2"><select className={inputClass} value={row.impact} onChange={(event) => setDraft({ ...draft, thesisImpacts: draft.thesisImpacts.map((item) => item.id === row.id ? { ...item, impact: event.target.value as EarningsImpact } : item) })}>{Object.entries(IMPACT_LABEL).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select><button onClick={() => setDraft({ ...draft, thesisImpacts: draft.thesisImpacts.filter((item) => item.id !== row.id) })} className="text-muted-foreground hover:text-destructive"><Trash2 className="h-4 w-4" /></button></div><textarea className={`${inputClass} min-h-20 resize-y`} value={row.summary} onChange={(event) => setDraft({ ...draft, thesisImpacts: draft.thesisImpacts.map((item) => item.id === row.id ? { ...item, summary: event.target.value } : item) })} placeholder="说明财报证据增强、削弱、不改变或证伪了哪一项研究命题。" /></div>)}<button onClick={addThesisImpact} className="inline-flex items-center gap-1 rounded-lg border border-border px-2.5 py-1.5 text-xs"><Plus className="h-3.5 w-3.5" /> 添加逻辑影响</button></div>
            </GlassCard>
          </div>

          <div className="grid gap-4 2xl:grid-cols-2">
            <GlassCard>
              <div className="mb-3 flex items-center gap-2"><Database className="h-4 w-4 text-primary" /><h2 className="font-bold">来源材料</h2></div>
              <div className="space-y-2">{draft.sourceMaterials.length === 0 && <p className="text-xs text-muted-foreground">点击“刷新证据”读取个股研究、财务、公告、研报和新闻来源。</p>}{draft.sourceMaterials.slice(0, 20).map((source) => <div key={source.id} className="flex items-start justify-between gap-3 rounded-lg bg-muted/35 px-3 py-2 text-sm"><div className="min-w-0"><div className="truncate font-medium">{source.label}</div><div className="mt-0.5 text-[11px] text-muted-foreground">截至 {source.asOf} · {source.status}</div></div>{source.url && <a href={source.url} target="_blank" rel="noreferrer" className="text-xs text-primary">原文</a>}</div>)}</div>
            </GlassCard>
            <GlassCard>
              <div className="mb-3 flex items-center gap-2"><CalendarClock className="h-4 w-4 text-primary" /><h2 className="font-bold">数据缺口与后续核验</h2></div>
              <textarea className={`${inputClass} min-h-52 resize-y`} value={draft.gaps.join("\n")} onChange={(event) => setDraft({ ...draft, gaps: event.target.value.split("\n").slice(0, 30) })} placeholder="每行一项，例如：缺少管理层对下一财年毛利率区间的明确指引" />
            </GlassCard>
          </div>

          <Disclaimer />
        </div>
      </div>
    </div>
  );
}
