import { useEffect, useMemo, useRef, useState } from "react";
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
import { api, type EquityResearchEvidence, type EquityResearchSnapshot } from "@/lib/api";
import { cn } from "@/lib/utils";
import {
  blankValuationModel,
  calculateValuationModel,
  calculateWacc,
  hydrateValuationWorkspace,
  loadLocalValuationWorkspace,
  persistValuationWorkspace,
  type AuditCheck,
  type ForecastDriver,
  type HistoricalDriver,
  type ValuationModel,
  type ValuationScenario,
  type ValuationScenarioId,
  type ValuationSource,
  type ValuationWorkspace,
} from "@/lib/valuationWorkbench";
import {
  publishVibeDeskContext,
  registerVibeDeskContextProvider,
  subscribeVibeDeskEvent,
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

function amountToMillions(evidence: EquityResearchEvidence | undefined) {
  if (!evidence) return null;
  const raw = evidence.value;
  if (typeof raw === "number" && Number.isFinite(raw)) {
    if (evidence.id === "valuation.mcap_yi") return raw * 100;
    return evidence.unit && evidence.currency && evidence.unit === evidence.currency ? raw / 1_000_000 : raw;
  }
  if (typeof raw !== "string") return null;
  const parsed = Number(raw.replace(/,/g, "").match(/-?\d+(?:\.\d+)?/)?.[0]);
  if (!Number.isFinite(parsed)) return null;
  if (raw.includes("万亿")) return parsed * 1_000_000;
  if (raw.includes("亿")) return parsed * 100;
  if (raw.includes("万")) return parsed * 0.01;
  return parsed;
}

function evidenceNumber(snapshot: EquityResearchSnapshot, id: string) {
  const evidence = snapshot.evidenceLedger.find((item) => item.id === id);
  if (!evidence) return null;
  const value = typeof evidence.value === "number"
    ? evidence.value
    : Number(String(evidence.value).replace(/,/g, "").match(/-?\d+(?:\.\d+)?/)?.[0]);
  return Number.isFinite(value) ? value : null;
}

function sourceFromEvidence(evidence: EquityResearchEvidence): ValuationSource {
  return {
    id: evidence.id,
    label: evidence.label,
    asOf: evidence.asOf || "待核验",
    source: evidence.source,
    ...(evidence.url ? { url: evidence.url } : {}),
    status: evidence.confidence === "high" ? "verified" : "available",
  };
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
      modelId: model.id,
      scenario: model.selectedScenario,
    },
    filters: { asOf: model.asOf, unitScale: model.unitScale, modelScope: model.modelScope },
    data: {
      asOf: model.asOf || workspace.updatedAt,
      source: workspace.schemaVersion,
      freshness: loading ? "unknown" : model.sourceMaterials.length ? "fresh" : "unknown",
      summary: {
        historicals: model.historicals,
        capitalInputs: model.capitalInputs,
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
      { id: "valuation.refresh-evidence", label: "刷新财务与市场证据", available: true },
      { id: "valuation.audit-inputs", label: "审计历史与资本输入", available: true },
      { id: "valuation.test-scenarios", label: "比较三种情景", available: model.projections.length > 0 },
      { id: "valuation.explain-sensitivity", label: "解释敏感性和主要驱动", available: model.result.impliedPrice !== null },
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

export function ValuationWorkbench() {
  const initial = useMemo(loadLocalValuationWorkspace, []);
  const [workspace, setWorkspace] = useState(initial);
  const [selectedId, setSelectedId] = useState(initial.models[0]?.id || "__new__");
  const [draft, setDraft] = useState(() => initial.models[0] ? copyModel(initial.models[0]) : blankValuationModel());
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState("");
  const calculated = useMemo(() => calculateValuationModel(draft), [draft]);
  const selected = workspace.models.find((item) => item.id === selectedId);
  const dirty = selectedId === "__new__"
    ? Boolean(draft.name || draft.security.symbol || draft.historicals.some((item) => item.revenue !== null))
    : JSON.stringify(selected) !== JSON.stringify(calculated);

  useEffect(() => {
    let active = true;
    void hydrateValuationWorkspace().then((value) => {
      if (!active) return;
      setWorkspace(value);
      const first = value.models[0];
      setSelectedId(first?.id || "__new__");
      setDraft(first ? copyModel(first) : blankValuationModel());
    });
    return () => { active = false; };
  }, []);

  const contextRef = useRef<VibeDeskPageContext>(contextFor(workspace, calculated, loading));
  contextRef.current = contextFor(workspace, calculated, loading);
  useEffect(() => registerVibeDeskContextProvider(() => contextRef.current), []);
  useEffect(() => {
    const unsubscribe = subscribeVibeDeskEvent((event) => {
      if (event.event !== "security.selected") return;
      const symbol = typeof event.payload.symbol === "string" ? event.payload.symbol.slice(0, 40).toUpperCase() : "";
      if (!symbol) return;
      const market = typeof event.payload.market === "string" ? event.payload.market.slice(0, 20).toUpperCase() : "CN";
      const name = typeof event.payload.name === "string" ? event.payload.name.slice(0, 120) : "";
      setDraft((current) => ({ ...current, security: { market, symbol, name, currency: currencyForMarket(market) } }));
    });
    return () => { unsubscribe(); };
  }, []);
  useEffect(() => { void publishVibeDeskContext(); }, [calculated, loading, workspace]);

  const commit = (next: ValuationWorkspace) => {
    setWorkspace(next);
    void persistValuationWorkspace(next);
  };

  const startNew = () => {
    if (dirty && !confirm("当前估值模型尚未保存，确定新建吗？")) return;
    setSelectedId("__new__");
    setDraft(blankValuationModel());
    setMessage("");
  };

  const choose = (model: ValuationModel) => {
    if (dirty && !confirm("当前估值模型尚未保存，确定切换吗？")) return;
    setSelectedId(model.id);
    setDraft(copyModel(model));
    setMessage("");
  };

  const validate = () => {
    if (!draft.name.trim()) return "请填写模型名称";
    if (!draft.security.symbol.trim() || !draft.security.name.trim()) return "请填写证券代码和公司名称";
    if (draft.scenarios.some((scenario) => scenario.terminalGrowthPct >= scenario.waccPct)) return "每个情景的终值增长必须低于 WACC";
    return "";
  };

  const save = () => {
    const error = validate();
    if (error) {
      setMessage(error);
      return;
    }
    const timestamp = new Date().toISOString();
    const saved = calculateValuationModel({
      ...draft,
      name: draft.name.trim(),
      security: {
        market: draft.security.market.trim().toUpperCase(),
        symbol: draft.security.symbol.trim().toUpperCase(),
        name: draft.security.name.trim(),
        currency: draft.security.currency.trim().toUpperCase() || currencyForMarket(draft.security.market),
      },
      gaps: draft.gaps.map((item) => item.trim()).filter(Boolean).slice(0, 30),
      updatedAt: timestamp,
    });
    const exists = workspace.models.some((item) => item.id === saved.id);
    const models = exists ? workspace.models.map((item) => item.id === saved.id ? saved : item) : [saved, ...workspace.models];
    commit({ ...workspace, updatedAt: timestamp, models });
    setSelectedId(saved.id);
    setDraft(copyModel(saved));
    setMessage("已保存到 Desk 工作区");
  };

  const remove = () => {
    if (selectedId === "__new__") {
      startNew();
      return;
    }
    if (!confirm(`删除“${draft.name}”估值模型？`)) return;
    const models = workspace.models.filter((item) => item.id !== selectedId);
    const next = { ...workspace, updatedAt: new Date().toISOString(), models };
    commit(next);
    const first = models[0];
    setSelectedId(first?.id || "__new__");
    setDraft(first ? copyModel(first) : blankValuationModel());
  };

  const refreshEvidence = async () => {
    const symbol = draft.security.symbol.trim().toUpperCase();
    if (!symbol) {
      setMessage("先填写证券代码再刷新证据");
      return;
    }
    setLoading(true);
    setMessage("");
    try {
      const snapshot = await api.equityResearch(symbol);
      const revenueEvidence = snapshot.evidenceLedger.find((item) => ["growth.revenue", "disclosure.edgar_revenue"].includes(item.id));
      const priceEvidence = snapshot.evidenceLedger.find((item) => item.id === "valuation.price");
      const marketCapEvidence = snapshot.evidenceLedger.find((item) => ["valuation.mcap_yi", "valuation.mcap"].includes(item.id));
      const growth = evidenceNumber(snapshot, "growth.revenue_yoy");
      const revenue = amountToMillions(revenueEvidence);
      const price = amountToMillions(priceEvidence);
      const marketCap = amountToMillions(marketCapEvidence);
      const sourceEvidence = snapshot.evidenceLedger.filter((item) =>
        [revenueEvidence?.id, priceEvidence?.id, marketCapEvidence?.id, "growth.revenue_yoy", "profitability.gross_margin", "profitability.net_margin"].includes(item.id));
      const sourceMaterials = Array.from(new Map([
        ...draft.sourceMaterials,
        ...sourceEvidence.map(sourceFromEvidence),
      ].map((item) => [item.id, item])).values());
      const firstGrowth = growth === null ? null : Math.max(-20, Math.min(80, growth));
      const scenarios = draft.scenarios.map((scenario) => {
        if (firstGrowth === null) return scenario;
        const offset = scenario.id === "bear" ? -5 : scenario.id === "bull" ? 5 : 0;
        return {
          ...scenario,
          drivers: scenario.drivers.map((driver, index) => ({
            ...driver,
            revenueGrowthPct: Number(Math.max(-20, firstGrowth + offset - index * 1.5).toFixed(1)),
          })),
        };
      });
      const historical: HistoricalDriver = {
        ...draft.historicals[0]!,
        period: revenueEvidence?.asOf || draft.historicals[0]!.period,
        revenue: revenue ?? draft.historicals[0]!.revenue,
        sourceIds: revenueEvidence ? [revenueEvidence.id] : draft.historicals[0]!.sourceIds,
      };
      const gaps = [
        ...draft.gaps,
        ...snapshot.gaps,
        ...(revenue === null ? ["统一历史收入金额未能自动读取，请手工核验"] : []),
        ...(marketCap === null || price === null ? ["稀释股数未能由市值与现价推导，请回到财报附注核验"] : []),
        "EBIT、折旧摊销、资本开支、营运资本、债务与现金仍需回到财报及附注核验",
      ];
      const next = calculateValuationModel({
        ...draft,
        security: snapshot.identity,
        asOf: snapshot.generatedAt.slice(0, 10),
        historicals: [historical, ...draft.historicals.slice(1)],
        capitalInputs: {
          ...draft.capitalInputs,
          currentPrice: price ?? draft.capitalInputs.currentPrice,
          dilutedSharesM: marketCap !== null && price !== null && price > 0 ? marketCap / price : draft.capitalInputs.dilutedSharesM,
        },
        scenarios,
        sourceMaterials,
        gaps: [...new Set(gaps)].slice(0, 30),
        updatedAt: new Date().toISOString(),
      });
      setDraft(next);
      setMessage(`已接入 ${sourceEvidence.length} 项 Evidence Ledger 输入；未覆盖的建模字段保持待核验，不会静默估算`);
    } catch {
      setDraft((current) => ({ ...current, gaps: [...new Set([...current.gaps, "Equity Research Evidence Ledger 读取失败"])].slice(0, 30) }));
      setMessage("财务与市场证据读取失败，已保留当前模型输入");
    } finally {
      setLoading(false);
    }
  };

  const updateScenario = (id: ValuationScenarioId, update: Partial<ValuationScenario>) => {
    setDraft((current) => ({ ...current, scenarios: current.scenarios.map((scenario) => scenario.id === id ? { ...scenario, ...update } : scenario) }));
  };

  const updateDriver = (scenarioId: ValuationScenarioId, index: number, field: keyof Omit<ForecastDriver, "year">, value: number) => {
    setDraft((current) => ({
      ...current,
      scenarios: current.scenarios.map((scenario) => scenario.id !== scenarioId ? scenario : {
        ...scenario,
        drivers: scenario.drivers.map((driver, driverIndex) => driverIndex === index ? { ...driver, [field]: value } : driver),
      }),
    }));
  };

  const activeScenario = draft.scenarios.find((scenario) => scenario.id === draft.selectedScenario) ?? draft.scenarios[1]!;
  const capmWacc = calculateWacc(draft.capitalInputs);
  const passCount = calculated.auditChecks.filter((check) => check.status === "pass").length;

  return (
    <div>
      <PageHeader
        title="预测与估值"
        subtitle="用可追溯的历史基期、三种经营情景、WACC、自由现金流与敏感性矩阵形成轻量驱动式 DCF；不把缺失数据静默估算成精确结论。"
        actions={(
          <>
            <button onClick={startNew} className="inline-flex items-center gap-1.5 rounded-lg border border-border bg-card/70 px-3 py-2 text-sm hover:border-primary/40"><Plus className="h-4 w-4" /> 新建</button>
            <button onClick={refreshEvidence} disabled={loading} className="inline-flex items-center gap-1.5 rounded-lg border border-border bg-card/70 px-3 py-2 text-sm hover:border-primary/40 disabled:opacity-50">{loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />} 刷新证据</button>
            <button onClick={save} className="inline-flex items-center gap-1.5 rounded-lg bg-primary px-3 py-2 text-sm font-semibold text-primary-foreground hover:opacity-90"><Save className="h-4 w-4" /> 保存</button>
          </>
        )}
      />

      {message && <div className="mb-4 flex items-center gap-2 rounded-lg border border-primary/20 bg-primary/8 px-3 py-2 text-sm"><CheckCircle2 className="h-4 w-4 text-primary" /> {message}</div>}

      <div className="mb-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {[
          { label: "模型档案", value: workspace.models.length, icon: BookOpenCheck },
          { label: "当前情景", value: SCENARIO_LABEL[draft.selectedScenario], icon: BarChart3 },
          { label: "隐含每股价值", value: calculated.result.impliedPrice === null ? "待补输入" : `${draft.security.currency} ${formatNumber(calculated.result.impliedPrice, 2)}`, icon: Calculator },
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
            <div className="mb-4 flex flex-wrap items-center justify-between gap-3"><div><div className="text-xs font-semibold uppercase tracking-[0.14em] text-primary">Model scope</div><h2 className="mt-1 text-lg font-bold">公司、口径与模型边界</h2></div><div className="flex items-center gap-2">{dirty && <span className="text-xs text-warning">有未保存修改</span>}<button onClick={remove} className="rounded-lg border border-border p-2 text-muted-foreground hover:border-destructive/40 hover:text-destructive"><Trash2 className="h-4 w-4" /></button></div></div>
            <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-6">
              <label className="xl:col-span-2"><span className={labelClass}>模型名称</span><input aria-label="模型名称" className={inputClass} value={draft.name} onChange={(event) => setDraft({ ...draft, name: event.target.value })} placeholder="例如：中际旭创五年驱动式 DCF" /></label>
              <label><span className={labelClass}>市场</span><input aria-label="市场" className={inputClass} value={draft.security.market} onChange={(event) => setDraft({ ...draft, security: { ...draft.security, market: event.target.value, currency: currencyForMarket(event.target.value) } })} /></label>
              <label><span className={labelClass}>证券代码</span><input aria-label="证券代码" className={inputClass} value={draft.security.symbol} onChange={(event) => setDraft({ ...draft, security: { ...draft.security, symbol: event.target.value } })} /></label>
              <label><span className={labelClass}>公司名称</span><input aria-label="公司名称" className={inputClass} value={draft.security.name} onChange={(event) => setDraft({ ...draft, security: { ...draft.security, name: event.target.value } })} /></label>
              <label><span className={labelClass}>币种</span><input className={inputClass} value={draft.security.currency} onChange={(event) => setDraft({ ...draft, security: { ...draft.security, currency: event.target.value } })} /></label>
            </div>
            <div className="mt-3 grid gap-3 md:grid-cols-3"><label><span className={labelClass}>数据截至</span><input className={inputClass} value={draft.asOf} onChange={(event) => setDraft({ ...draft, asOf: event.target.value })} /></label><label><span className={labelClass}>金额单位</span><input className={inputClass} value={draft.unitScale} onChange={(event) => setDraft({ ...draft, unitScale: event.target.value })} /></label><div className="rounded-lg border border-border bg-muted/25 px-3 py-2"><div className="text-xs font-semibold">模型边界</div><div className="mt-1 text-xs text-muted-foreground">驱动式 DCF，不等同于完整三表模型或正式估值意见。</div></div></div>
          </GlassCard>

          <GlassCard>
            <div className="mb-4 flex items-center justify-between"><div><div className="text-xs font-semibold uppercase tracking-[0.14em] text-primary">Historical base</div><h2 className="mt-1 text-lg font-bold">历史基期与经营驱动</h2></div><button disabled={draft.historicals.length >= 5} onClick={() => setDraft({ ...draft, historicals: [...draft.historicals, { period: "", revenue: null, ebitMarginPct: null, daPctRevenue: null, capexPctRevenue: null, nwcPctDeltaRevenue: null, sourceIds: [] }] })} className="inline-flex items-center gap-1 rounded-lg border border-border px-2.5 py-1.5 text-xs disabled:opacity-40"><Plus className="h-3.5 w-3.5" /> 添加历史期</button></div>
            <div className="overflow-x-auto"><table className="w-full min-w-[880px] text-xs"><thead className="text-muted-foreground"><tr className="border-b border-border"><th className="px-2 py-2 text-left">期间</th><th className="px-2 py-2 text-right">收入</th><th className="px-2 py-2 text-right">EBIT 率</th><th className="px-2 py-2 text-right">D&A / 收入</th><th className="px-2 py-2 text-right">CapEx / 收入</th><th className="px-2 py-2 text-right">ΔNWC / Δ收入</th><th className="px-2 py-2 text-left">来源编号</th><th /></tr></thead><tbody>{draft.historicals.map((row, index) => <tr key={index} className="border-b border-border/60"><td className="px-2 py-2"><input aria-label={index === 0 ? "历史期间" : `历史期间 ${index + 1}`} className={inputClass} value={row.period} onChange={(event) => setDraft({ ...draft, historicals: draft.historicals.map((item, itemIndex) => itemIndex === index ? { ...item, period: event.target.value } : item) })} /></td>{(["revenue", "ebitMarginPct", "daPctRevenue", "capexPctRevenue", "nwcPctDeltaRevenue"] as const).map((field) => <td key={field} className="px-2 py-2"><input aria-label={index === 0 && field === "revenue" ? "历史收入" : `${row.period || index + 1} ${field}`} type="number" step="0.1" className={`${inputClass} text-right`} value={row[field] ?? ""} onChange={(event) => setDraft({ ...draft, historicals: draft.historicals.map((item, itemIndex) => itemIndex === index ? { ...item, [field]: parseNumber(event.target.value) } : item) })} /></td>)}<td className="px-2 py-2"><input className={inputClass} value={row.sourceIds.join("；")} onChange={(event) => setDraft({ ...draft, historicals: draft.historicals.map((item, itemIndex) => itemIndex === index ? { ...item, sourceIds: event.target.value.split(/[；;]/).filter(Boolean).slice(0, 20) } : item) })} placeholder="Evidence ID" /></td><td className="px-2 py-2"><button disabled={draft.historicals.length <= 1} onClick={() => setDraft({ ...draft, historicals: draft.historicals.filter((_, itemIndex) => itemIndex !== index) })} className="text-muted-foreground hover:text-destructive disabled:opacity-30"><Trash2 className="h-4 w-4" /></button></td></tr>)}</tbody></table></div>
          </GlassCard>

          <GlassCard>
            <div className="mb-4"><div className="text-xs font-semibold uppercase tracking-[0.14em] text-primary">Capital & WACC</div><h2 className="mt-1 text-lg font-bold">资本结构与折现率输入</h2><p className="mt-1 text-xs text-muted-foreground">蓝本采用 CAPM 与税后债务成本；情景 WACC 可单独覆盖，但需解释原因。</p></div>
            <div className="grid gap-3 md:grid-cols-3 xl:grid-cols-5">{([
              ["currentPrice", "当前股价"], ["dilutedSharesM", "稀释股数（百万股）"], ["totalDebtM", "总债务"], ["cashM", "现金及等价物"], ["riskFreeRatePct", "无风险利率 %"], ["beta", "Beta"], ["equityRiskPremiumPct", "权益风险溢价 %"], ["preTaxCostDebtPct", "税前债务成本 %"], ["taxRatePct", "资本结构税率 %"],
            ] as const).map(([field, label]) => <label key={field}><span className={labelClass}>{label}</span><input aria-label={label} type="number" step="0.1" className={inputClass} value={draft.capitalInputs[field] ?? ""} onChange={(event) => setDraft({ ...draft, capitalInputs: { ...draft.capitalInputs, [field]: parseNumber(event.target.value) } })} /></label>)}<div className="rounded-lg border border-primary/25 bg-primary/8 px-3 py-2"><div className="text-xs text-muted-foreground">CAPM 推导 WACC</div><div className="mt-1 text-xl font-bold text-primary">{capmWacc === null ? "待补输入" : `${capmWacc.toFixed(2)}%`}</div><div className="mt-1 text-[10px] text-muted-foreground">用于审计情景 WACC，不自动覆盖用户假设。</div></div></div>
          </GlassCard>

          <GlassCard>
            <div className="mb-4 flex flex-wrap items-center justify-between gap-3"><div><div className="text-xs font-semibold uppercase tracking-[0.14em] text-primary">Scenario assumptions</div><h2 className="mt-1 text-lg font-bold">三情景预测驱动</h2></div><div className="flex rounded-lg border border-border bg-muted/25 p-1">{draft.scenarios.map((scenario) => <button key={scenario.id} onClick={() => setDraft({ ...draft, selectedScenario: scenario.id })} className={cn("rounded-md px-3 py-1.5 text-xs font-semibold", draft.selectedScenario === scenario.id ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:text-foreground")}>{scenario.label}</button>)}</div></div>
            <div className="grid gap-3 md:grid-cols-3"><label><span className={labelClass}>情景 WACC %</span><input aria-label="情景 WACC" type="number" step="0.1" className={inputClass} value={activeScenario.waccPct} onChange={(event) => updateScenario(activeScenario.id, { waccPct: Number(event.target.value) || 0 })} /></label><label><span className={labelClass}>终值增长 %</span><input aria-label="终值增长" type="number" step="0.1" className={inputClass} value={activeScenario.terminalGrowthPct} onChange={(event) => updateScenario(activeScenario.id, { terminalGrowthPct: Number(event.target.value) || 0 })} /></label><label><span className={labelClass}>情景依据</span><input className={inputClass} value={activeScenario.rationale} onChange={(event) => updateScenario(activeScenario.id, { rationale: event.target.value })} /></label></div>
            <div className="mt-4 overflow-x-auto"><table className="w-full min-w-[760px] text-xs"><thead className="text-muted-foreground"><tr className="border-b border-border"><th className="px-2 py-2 text-left">驱动</th>{activeScenario.drivers.map((driver) => <th key={driver.year} className="px-2 py-2 text-right">{driver.year}E</th>)}</tr></thead><tbody>{([
              ["revenueGrowthPct", "收入增长 %"], ["ebitMarginPct", "EBIT 率 %"], ["taxRatePct", "税率 %"], ["daPctRevenue", "D&A / 收入 %"], ["capexPctRevenue", "CapEx / 收入 %"], ["nwcPctDeltaRevenue", "ΔNWC / Δ收入 %"],
            ] as const).map(([field, label]) => <tr key={field} className="border-b border-border/60"><td className="px-2 py-2 font-medium">{label}</td>{activeScenario.drivers.map((driver, index) => <td key={driver.year} className="px-2 py-2 text-right">{driverCell(driver, field, (value) => updateDriver(activeScenario.id, index, field, value))}</td>)}</tr>)}</tbody></table></div>
          </GlassCard>

          <GlassCard>
            <div className="mb-4"><div className="text-xs font-semibold uppercase tracking-[0.14em] text-primary">FCF build</div><h2 className="mt-1 text-lg font-bold">自由现金流预测与折现</h2></div>
            <div className="overflow-x-auto"><table className="w-full min-w-[980px] text-xs"><thead className="text-muted-foreground"><tr className="border-b border-border"><th className="px-2 py-2 text-left">年度</th><th className="px-2 py-2 text-right">收入</th><th className="px-2 py-2 text-right">增长</th><th className="px-2 py-2 text-right">EBIT</th><th className="px-2 py-2 text-right">NOPAT</th><th className="px-2 py-2 text-right">D&A</th><th className="px-2 py-2 text-right">CapEx</th><th className="px-2 py-2 text-right">ΔNWC</th><th className="px-2 py-2 text-right">UFCF</th><th className="px-2 py-2 text-right">折现因子</th><th className="px-2 py-2 text-right">PV FCF</th></tr></thead><tbody>{calculated.projections.map((row) => <tr key={row.year} className="border-b border-border/60"><td className="px-2 py-2 font-semibold">{row.year}E</td><td className="px-2 py-2 text-right">{formatNumber(row.revenue)}</td><td className="px-2 py-2 text-right">{row.revenueGrowthPct.toFixed(1)}%</td><td className="px-2 py-2 text-right">{formatNumber(row.ebit)}</td><td className="px-2 py-2 text-right">{formatNumber(row.nopat)}</td><td className="px-2 py-2 text-right">{formatNumber(row.depreciationAmortization)}</td><td className="px-2 py-2 text-right">{formatNumber(row.capex)}</td><td className="px-2 py-2 text-right">{formatNumber(row.changeNwc)}</td><td className="px-2 py-2 text-right font-semibold text-primary">{formatNumber(row.unleveredFcf)}</td><td className="px-2 py-2 text-right">{formatNumber(row.discountFactor, 4)}</td><td className="px-2 py-2 text-right">{formatNumber(row.pvFcf)}</td></tr>)}{calculated.projections.length === 0 && <tr><td colSpan={11} className="px-3 py-10 text-center text-muted-foreground">录入历史收入基期后自动生成完整 FCF 预测。</td></tr>}</tbody></table></div>
          </GlassCard>

          <div className="grid gap-4 2xl:grid-cols-[1fr_1.25fr]">
            <GlassCard>
              <div className="mb-4"><div className="text-xs font-semibold uppercase tracking-[0.14em] text-primary">Valuation bridge</div><h2 className="mt-1 text-lg font-bold">企业价值到每股价值</h2></div>
              <div className="space-y-2 text-sm">{([
                ["显式期 FCF 现值", calculated.result.pvExplicitFcfM], ["终值现值", calculated.result.pvTerminalValueM], ["企业价值", calculated.result.enterpriseValueM], ["减：净债务", calculated.result.netDebtM], ["股权价值", calculated.result.equityValueM],
              ] as const).map(([label, value]) => <div key={label} className="flex items-center justify-between border-b border-border/60 py-2"><span className="text-muted-foreground">{label}</span><span className="font-semibold">{formatNumber(value)}</span></div>)}<div className="mt-3 rounded-xl border border-primary/25 bg-primary/8 p-4"><div className="flex items-center justify-between"><span className="font-semibold">隐含每股价值</span><span className="text-2xl font-bold text-primary">{formatNumber(calculated.result.impliedPrice, 2)}</span></div><div className="mt-2 flex justify-between text-xs text-muted-foreground"><span>当前价格 {formatNumber(calculated.result.currentPrice, 2)}</span><span>模型差异 {calculated.result.impliedReturnPct === null ? "—" : `${calculated.result.impliedReturnPct.toFixed(1)}%`}</span></div></div></div>
            </GlassCard>

            <GlassCard>
              <div className="mb-4"><div className="text-xs font-semibold uppercase tracking-[0.14em] text-primary">Sensitivity</div><h2 className="mt-1 text-lg font-bold">WACC × 终值增长敏感性</h2><p className="mt-1 text-xs text-muted-foreground">5×5 奇数矩阵，中心格严格对应当前情景基准值；每格完整重算 DCF。</p></div>
              <div className="overflow-x-auto"><table className="w-full min-w-[560px] text-center text-xs"><thead><tr><th className="px-2 py-2 text-left text-muted-foreground">WACC \ g</th>{calculated.sensitivity.terminalGrowthPct.map((growth, column) => <th key={column} className="px-2 py-2 text-muted-foreground">{growth.toFixed(1)}%</th>)}</tr></thead><tbody>{calculated.sensitivity.waccPct.map((wacc, row) => <tr key={row}><th className="px-2 py-2 text-left text-muted-foreground">{wacc.toFixed(1)}%</th>{calculated.sensitivity.impliedPrices[row]?.map((value, column) => <td key={column} className={cn("border border-border/70 px-2 py-2", row === 2 && column === 2 ? "bg-primary text-primary-foreground font-bold" : "bg-muted/20")}>{formatNumber(value, 2)}</td>)}</tr>)}</tbody></table></div>
            </GlassCard>
          </div>

          <div className="grid gap-4 2xl:grid-cols-3">
            <GlassCard><div className="mb-3 flex items-center gap-2"><SearchCheck className="h-4 w-4 text-primary" /><h2 className="font-bold">模型审计</h2></div><div className="space-y-2">{calculated.auditChecks.map((check) => <div key={check.id} className={cn("rounded-lg border px-3 py-2", CHECK_STYLE[check.status])}><div className="flex items-center gap-1.5 text-xs font-semibold">{check.status === "pass" ? <CheckCircle2 className="h-3.5 w-3.5" /> : <CircleAlert className="h-3.5 w-3.5" />}{check.label}</div><div className="mt-1 text-[11px] opacity-85">{check.message}</div></div>)}</div></GlassCard>
            <GlassCard><div className="mb-3 flex items-center gap-2"><Database className="h-4 w-4 text-primary" /><h2 className="font-bold">来源与截至时间</h2></div><div className="max-h-72 space-y-2 overflow-y-auto">{calculated.sourceMaterials.length === 0 && <p className="text-xs text-muted-foreground">点击“刷新证据”或手工关联 Evidence ID。</p>}{calculated.sourceMaterials.map((source) => <div key={source.id} className="rounded-lg bg-muted/35 px-3 py-2 text-xs"><div className="font-semibold">{source.label}</div><div className="mt-1 text-[11px] text-muted-foreground">{source.source} · {source.asOf} · {source.status}</div></div>)}</div></GlassCard>
            <GlassCard><div className="mb-3 flex items-center gap-2"><CircleAlert className="h-4 w-4 text-primary" /><h2 className="font-bold">数据缺口与核验事项</h2></div><textarea className={`${inputClass} min-h-64 resize-y`} value={draft.gaps.join("\n")} onChange={(event) => setDraft({ ...draft, gaps: event.target.value.split("\n").slice(0, 30) })} placeholder="每行一项" /></GlassCard>
          </div>

          <Disclaimer />
        </div>
      </div>
    </div>
  );
}
