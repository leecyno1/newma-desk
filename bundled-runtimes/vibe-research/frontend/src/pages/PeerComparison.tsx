import { useEffect, useMemo, useRef, useState } from "react";
import {
  BarChart3,
  BookOpenCheck,
  CheckCircle2,
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
import { api, type EquityResearchSnapshot } from "@/lib/api";
import {
  blankPeerComparisonCase,
  calculatePeerStatistics,
  hydratePeerComparisonWorkspace,
  loadLocalPeerComparisonWorkspace,
  persistPeerComparisonWorkspace,
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

function fiscalPeriod(snapshot: EquityResearchSnapshot | undefined) {
  return snapshot?.evidenceLedger.find((item) =>
    item.asOf && ["growth", "profitability", "cash_flow", "balance_sheet"].includes(item.dimension))?.asOf || "待确认";
}

function comparisonContext(workspace: PeerComparisonWorkspace, draft: PeerComparisonCase, loading: boolean): VibeDeskPageContext {
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
      symbol: draft.target.symbol,
      market: draft.target.market,
      name: draft.target.name,
      caseId: draft.id,
      peerSymbols: draft.members.filter((item) => item.included).map((item) => item.security.symbol),
    },
    filters: {
      researchQuestion: draft.researchQuestion,
      period: draft.period,
    },
    data: {
      asOf: draft.period.asOf || workspace.updatedAt,
      source: workspace.schemaVersion,
      freshness: loading ? "unknown" : draft.rows.length ? "fresh" : "unknown",
      summary: {
        members: draft.members,
        metrics: draft.metrics,
        rows: draft.rows,
        statistics: draft.statistics,
        strategicDimensions: draft.strategicDimensions,
        synthesis: draft.synthesis,
        sources: draft.sourceMaterials,
        gaps: draft.gaps,
      },
    },
    actions: [
      { id: "peer.refresh", label: "刷新同业证据与统计", available: true },
      { id: "peer.audit-comparability", label: "审计可比性和口径", available: true },
      { id: "peer.explain-premium", label: "解释增长、质量与估值差异", available: draft.rows.length >= 2 },
      { id: "peer.update-thesis", label: "映射到投资逻辑", available: draft.rows.length >= 2 },
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
  const initial = useMemo(loadLocalPeerComparisonWorkspace, []);
  const [workspace, setWorkspace] = useState(initial);
  const [selectedId, setSelectedId] = useState(initial.cases[0]?.id || "__new__");
  const [draft, setDraft] = useState(() => initial.cases[0] ? copyCase(initial.cases[0]) : blankPeerComparisonCase());
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState("");

  const selected = workspace.cases.find((item) => item.id === selectedId);
  const dirty = selectedId === "__new__"
    ? Boolean(draft.name || draft.members.some((item) => item.security.symbol || item.security.name))
    : JSON.stringify(selected) !== JSON.stringify(draft);

  useEffect(() => {
    let active = true;
    void hydratePeerComparisonWorkspace().then((value) => {
      if (!active) return;
      setWorkspace(value);
      const first = value.cases[0];
      setSelectedId(first?.id || "__new__");
      setDraft(first ? copyCase(first) : blankPeerComparisonCase());
    });
    return () => { active = false; };
  }, []);

  const contextRef = useRef<VibeDeskPageContext>(comparisonContext(workspace, draft, loading));
  contextRef.current = comparisonContext(workspace, draft, loading);
  useEffect(() => registerVibeDeskContextProvider(() => contextRef.current), []);
  useEffect(() => {
    const unsubscribe = subscribeVibeDeskEvent((event) => {
      if (event.event !== "security.selected") return;
      const symbol = typeof event.payload.symbol === "string" ? event.payload.symbol.slice(0, 40).toUpperCase() : "";
      if (!symbol) return;
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
  useEffect(() => { void publishVibeDeskContext(); }, [draft, loading, workspace]);

  const commit = (next: PeerComparisonWorkspace) => {
    setWorkspace(next);
    void persistPeerComparisonWorkspace(next);
  };

  const startNew = () => {
    if (dirty && !confirm("当前同业比较尚未保存，确定新建吗？")) return;
    setSelectedId("__new__");
    setDraft(blankPeerComparisonCase());
    setMessage("");
  };

  const choose = (item: PeerComparisonCase) => {
    if (dirty && !confirm("当前同业比较尚未保存，确定切换吗？")) return;
    setSelectedId(item.id);
    setDraft(copyCase(item));
    setMessage("");
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
    if (draft.strategicDimensions.some((item) => !item.label.trim() || !item.targetAssessment.trim() || !item.peerObservation.trim())) return "竞争维度需要名称、目标公司判断和同业观察";
    return "";
  };

  const save = () => {
    const error = validate();
    if (error) {
      setMessage(error);
      return;
    }
    const timestamp = new Date().toISOString();
    const targetMember = draft.members.find((item) => item.role === "target")!;
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
      statistics: calculatePeerStatistics(draft.rows, draft.metrics),
      gaps: draft.gaps.map((item) => item.trim()).filter(Boolean).slice(0, 30),
      updatedAt: timestamp,
    };
    const exists = workspace.cases.some((item) => item.id === saved.id);
    const cases = exists ? workspace.cases.map((item) => item.id === saved.id ? saved : item) : [saved, ...workspace.cases];
    commit({ ...workspace, updatedAt: timestamp, cases });
    setSelectedId(saved.id);
    setDraft(copyCase(saved));
    setMessage("已保存到 Desk 工作区");
  };

  const remove = () => {
    if (selectedId === "__new__") {
      startNew();
      return;
    }
    if (!confirm(`删除“${draft.name}”同业比较？`)) return;
    const cases = workspace.cases.filter((item) => item.id !== selectedId);
    const next = { ...workspace, updatedAt: new Date().toISOString(), cases };
    commit(next);
    const first = cases[0];
    setSelectedId(first?.id || "__new__");
    setDraft(first ? copyCase(first) : blankPeerComparisonCase());
  };

  const refresh = async () => {
    const error = validate();
    if (error) {
      setMessage(error);
      return;
    }
    const members = draft.members.filter((item) => item.included);
    const symbols = members.map((item) => item.security.symbol.trim().toUpperCase());
    setLoading(true);
    setMessage("");
    const [comparisonResult, snapshotsResult] = await Promise.all([
      api.equityResearchComparison(symbols).then((value) => ({ value, error: "" })).catch(() => ({ value: null, error: "同业比较 API 读取失败" })),
      Promise.allSettled(symbols.map((symbol) => api.equityResearch(symbol))),
    ]);
    const comparison = comparisonResult.value;
    if (!comparison) {
      setDraft((current) => ({ ...current, gaps: [...new Set([...current.gaps, comparisonResult.error])] }));
      setLoading(false);
      setMessage(comparisonResult.error);
      return;
    }
    const snapshots = new Map<string, EquityResearchSnapshot>();
    snapshotsResult.forEach((result, index) => {
      if (result.status === "fulfilled") snapshots.set(symbols[index]!, result.value);
    });
    const memberBySymbol = new Map(members.map((member) => [member.security.symbol.trim().toUpperCase(), member]));
    const rows = comparison.rows.map((row) => {
      const member = memberBySymbol.get(row.identity.symbol);
      const snapshot = snapshots.get(row.identity.symbol);
      return {
        security: {
          market: row.identity.market,
          symbol: row.identity.symbol,
          name: row.identity.name,
          currency: row.identity.currency,
        },
        isTarget: member?.role === "target",
        period: fiscalPeriod(snapshot),
        coverageRatio: row.coverage.ratio,
        values: { ...row.metrics },
        scores: { ...row.scores },
        sourceIds: [`research:${row.identity.symbol}`],
        warnings: [
          ...(row.coverage.ratio < 0.7 ? ["数据覆盖率低于 70%"] : []),
          ...(snapshot?.gaps || []).slice(0, 5),
        ],
      };
    });
    const periods = new Set(rows.map((row) => row.period).filter((value) => value !== "待确认"));
    const sources = rows.map((row) => ({
      id: `research:${row.security.symbol}`,
      label: `${row.security.name} Evidence Ledger`,
      symbol: row.security.symbol,
      asOf: snapshots.get(row.security.symbol)?.generatedAt || comparison.generatedAt,
      status: row.coverageRatio >= 0.7 ? "verified" as const : "available" as const,
    }));
    const gaps = [
      ...comparison.errors.map((item) => `${item.symbol}: ${item.message}`),
      ...symbols.filter((symbol) => !snapshots.has(symbol)).map((symbol) => `${symbol}: Evidence Ledger 读取失败`),
      ...(periods.size > 1 ? ["同业最新报告期不完全一致，解读增长和利润率时需要标记时间错位"] : []),
    ];
    const targetRow = rows.find((row) => row.isTarget);
    const next: PeerComparisonCase = {
      ...draft,
      target: targetRow?.security || draft.target,
      rows,
      statistics: calculatePeerStatistics(rows, draft.metrics),
      sourceMaterials: sources,
      period: {
        ...draft.period,
        asOf: comparison.generatedAt,
        fiscalAlignment: periods.size === 1 ? "aligned" : periods.size > 1 ? "mixed" : "unknown",
      },
      gaps: [...new Set([...draft.gaps, ...gaps])].slice(0, 30),
      updatedAt: new Date().toISOString(),
    };
    setDraft(next);
    setLoading(false);
    setMessage(`已更新 ${rows.length} 家公司的标准化指标、分位统计和 Evidence Ledger 来源`);
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
  const targetRow = draft.rows.find((row) => row.isTarget);

  return (
    <div>
      <PageHeader
        title="同业比较"
        subtitle="先审计可比性，再用统一报告期、指标口径、统计分布与 Evidence Ledger 解释经营质量和估值差异。"
        actions={(
          <>
            <button onClick={startNew} className="inline-flex items-center gap-1.5 rounded-lg border border-border bg-card/70 px-3 py-2 text-sm hover:border-primary/40"><Plus className="h-4 w-4" /> 新建</button>
            <button onClick={refresh} disabled={loading} className="inline-flex items-center gap-1.5 rounded-lg border border-border bg-card/70 px-3 py-2 text-sm hover:border-primary/40 disabled:opacity-50">{loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />} 刷新比较</button>
            <button onClick={save} className="inline-flex items-center gap-1.5 rounded-lg bg-primary px-3 py-2 text-sm font-semibold text-primary-foreground hover:opacity-90"><Save className="h-4 w-4" /> 保存</button>
          </>
        )}
      />

      {message && <div className="mb-4 flex items-center gap-2 rounded-lg border border-primary/20 bg-primary/8 px-3 py-2 text-sm"><CheckCircle2 className="h-4 w-4 text-primary" /> {message}</div>}

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
              <label><span className={labelClass}>数据截至</span><input className={inputClass} value={draft.period.asOf} onChange={(event) => setDraft({ ...draft, period: { ...draft.period, asOf: event.target.value } })} placeholder="YYYY-MM-DD" /></label>
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
                <input className={inputClass} value={member.security.market} onChange={(event) => updateMemberSecurity(index, "market", event.target.value)} placeholder="CN" />
                <input className={inputClass} value={member.security.symbol} onChange={(event) => updateMemberSecurity(index, "symbol", event.target.value)} placeholder="证券代码" />
                <input className={inputClass} value={member.security.name} onChange={(event) => updateMemberSecurity(index, "name", event.target.value)} placeholder="公司名称" />
                <input className={inputClass} value={member.security.currency} onChange={(event) => updateMemberSecurity(index, "currency", event.target.value)} placeholder="CNY" />
                <select className={inputClass} value={member.role} onChange={(event) => {
                  const role = event.target.value as PeerRole;
                  setDraft((current) => ({ ...current, members: current.members.map((item, itemIndex) => ({ ...item, role: itemIndex === index ? role : role === "target" && item.role === "target" ? "direct" : item.role })) }));
                }}>{Object.entries(ROLE_LABEL).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select>
                <div className="flex items-center gap-2"><label className="flex items-center gap-1 text-xs text-muted-foreground"><input type="checkbox" checked={member.included} onChange={(event) => updateMember(index, { included: event.target.checked })} /> 纳入</label><button disabled={draft.members.length <= 2} onClick={() => setDraft({ ...draft, members: draft.members.filter((_, itemIndex) => itemIndex !== index) })} className="text-muted-foreground hover:text-destructive disabled:opacity-30"><Trash2 className="h-4 w-4" /></button></div>
              </div>
              <div className="mt-2 grid gap-2 md:grid-cols-2"><input className={inputClass} value={member.rationale} onChange={(event) => updateMember(index, { rationale: event.target.value })} placeholder="为什么可比：业务模式、客户、产品、区域或规模" /><input className={inputClass} value={member.exceptions.join("；")} onChange={(event) => updateMember(index, { exceptions: event.target.value.split(/[；;]/).slice(0, 10) })} placeholder="口径例外：财年、币种、并购、业务结构等" /></div>
            </div>)}</div>
          </GlassCard>

          <GlassCard>
            <div className="mb-4 flex flex-wrap items-center justify-between gap-3"><div><div className="text-xs font-semibold uppercase tracking-[0.14em] text-primary">Operating & valuation</div><h2 className="mt-1 text-lg font-bold">经营质量与估值指标</h2></div><div className="text-xs text-muted-foreground">缺失值显示为 N/A，不用估算值静默填补</div></div>
            <div className="overflow-x-auto"><table className="w-full min-w-[980px] text-left text-xs"><thead className="text-muted-foreground"><tr className="border-b border-border"><th className="px-2 py-2">公司</th><th className="px-2 py-2">报告期</th><th className="px-2 py-2 text-right">覆盖率</th>{draft.metrics.map((metric) => <th key={metric.id} className="px-2 py-2 text-right">{metric.label}<div className="font-normal opacity-70">{metric.unit}</div></th>)}</tr></thead><tbody>{draft.rows.map((row) => <tr key={row.security.symbol} className={cn("border-b border-border/60", row.isTarget && "bg-primary/7")}><td className="px-2 py-2"><div className="font-semibold">{row.security.name}{row.isTarget ? " · 目标" : ""}</div><div className="text-[10px] text-muted-foreground">{row.security.market}:{row.security.symbol}</div></td><td className="px-2 py-2 text-muted-foreground">{row.period}</td><td className="px-2 py-2 text-right">{(row.coverageRatio * 100).toFixed(0)}%</td>{draft.metrics.map((metric) => <td key={metric.id} className="px-2 py-2 text-right font-medium">{formatMetric(row.values[metric.id], metric.unit)}</td>)}</tr>)}{draft.rows.length === 0 && <tr><td colSpan={draft.metrics.length + 3} className="px-3 py-10 text-center text-muted-foreground">完善可比公司集合后点击“刷新比较”。</td></tr>}</tbody></table></div>
          </GlassCard>

          {draft.rows.length > 0 && <GlassCard>
            <div className="mb-4 flex items-center gap-2"><Scale className="h-4 w-4 text-primary" /><div><h2 className="font-bold">统计分布与目标公司位置</h2><p className="mt-0.5 text-xs text-muted-foreground">规模绝对值不做简单优劣排序；增长、利润率和估值倍数使用分位数提供上下文。</p></div></div>
            <div className="overflow-x-auto"><table className="w-full min-w-[780px] text-xs"><thead className="text-muted-foreground"><tr className="border-b border-border"><th className="px-2 py-2 text-left">指标</th><th className="px-2 py-2 text-right">目标公司</th><th className="px-2 py-2 text-right">最大</th><th className="px-2 py-2 text-right">75 分位</th><th className="px-2 py-2 text-right">中位数</th><th className="px-2 py-2 text-right">25 分位</th><th className="px-2 py-2 text-right">最小</th></tr></thead><tbody>{draft.metrics.map((metric) => { const stats = draft.statistics[metric.id]; return <tr key={metric.id} className="border-b border-border/60"><td className="px-2 py-2 font-medium">{metric.label}</td><td className="px-2 py-2 text-right font-semibold text-primary">{formatMetric(targetRow?.values[metric.id], metric.unit)}</td><td className="px-2 py-2 text-right">{formatMetric(stats?.max, metric.unit)}</td><td className="px-2 py-2 text-right">{formatMetric(stats?.q75, metric.unit)}</td><td className="px-2 py-2 text-right">{formatMetric(stats?.median, metric.unit)}</td><td className="px-2 py-2 text-right">{formatMetric(stats?.q25, metric.unit)}</td><td className="px-2 py-2 text-right">{formatMetric(stats?.min, metric.unit)}</td></tr>; })}</tbody></table></div>
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
    </div>
  );
}
