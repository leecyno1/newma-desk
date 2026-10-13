import { waitForVibeDeskConfig, type VibeDeskConfig } from "@/lib/vibedesk";

export type EarningsMode = "preview" | "reported";
export const EARNINGS_BASIS = { ytd: '年初至今累计', quarter: '单季度', annual: '完整年度', ttm: '滚动十二个月（TTM）' } as const;
export type EarningsBasis = keyof typeof EARNINGS_BASIS;
function normalizeBasis(value: unknown): EarningsBasis | undefined {
  return typeof value === 'string' && Object.prototype.hasOwnProperty.call(EARNINGS_BASIS, value) ? value as EarningsBasis : undefined;
}
export type VerificationStatus = "verified" | "partial" | "unverified";
export type EarningsImpact = "strengthened" | "weakened" | "neutral" | "invalidated";
export type MetricCategory = "financial" | "operating" | "guidance" | "valuation";

export interface EarningsMetric {
  id: string;
  label: string;
  category: MetricCategory;
  unit: string;
  reported: number | null;
  internalEstimate: number | null;
  consensus: number | null;
  varianceVsConsensus: { amount: number | null; percent: number | null; bps: number | null };
  sourceIds: string[];
  asOf?: string;
  periodEnd?: string;
  reportedCurrency?: string;
  reportedOrigin?: 'provider' | 'manual';
  reportedBasis?: EarningsBasis;
  consensusBasis?: EarningsBasis;
  consensusPeriodEnd?: string;
  note?: string;
}

export interface GuidanceComparison {
  id: string;
  label: string;
  period: string;
  unit: string;
  priorLow: number | null;
  priorHigh: number | null;
  currentLow: number | null;
  currentHigh: number | null;
  sourceIds: string[];
  asOf?: string;
  note?: string;
}

export interface ConditionalScenario {
  id: string;
  type: "above" | "inline" | "below";
  condition: string;
  operatingPath: string;
  researchResponse: string;
  indicators: string[];
}

export interface EstimateRevision {
  id: string;
  label: string;
  period: string;
  unit: string;
  previous: number | null;
  current: number | null;
  reason: string;
  sourceIds: string[];
}

export interface EarningsThesisImpact {
  id: string;
  pillarId?: string;
  impact: EarningsImpact;
  summary: string;
  evidenceIds: string[];
}

export interface FilingAmountInput {
  value: string;
  unit: '元' | '万元' | '亿元';
  currency: 'CNY';
}

export interface EarningsSource {
  id: string;
  label: string;
  kind: "filing" | "company" | "consensus" | "research" | "news" | "derived" | "user";
  url?: string;
  asOf?: string;
  periodEnd?: string;
  retrievedAt?: string;
  basis?: EarningsBasis;
  status: "verified" | "available" | "stale" | "unavailable";
  discussion?: {
    reportId: string; text: string; topics: string[];
    pdfPage: number; pdfPageCount: number; readPages: number[];
    truncated: boolean; confirmedAt: string;
    contentOrigin: 'pdf-text';
  };
  capitalNote?: {
    reportId: string; title: string; text: string; topics: string[];
    pdfPage: number; pdfPageCount: number; readPages: number[];
    truncated: boolean; confirmedAt: string; contentOrigin: 'pdf-text';
  };
  importedReport?: {
    reportId: string; rawValue: string; rawUnit: string; columnHeader: string;
    confirmedAt: string;
  };
  correction?: {
    before: number | null;
    after: number;
    reason: string;
    adoptedAt: string;
    evidenceSourceId: string;
    previousSourceIds: string[];
    amountInput?: FilingAmountInput;
  };
  excerpt?: {
    text: string;
    segment?: number;
    pdfPage?: number;
    pdfPageCount?: number;
    pdfUrl?: string;
    metricId: string;
    reportedValue: number | null;
    unit: string;
    contentOrigin: 'provider-transcription' | 'pdf-text';
    association: 'user-linked';
  };
}

export interface EarningsWorkbook {
  id: string;
  security: {
    market: string;
    symbol: string;
    name: string;
    exchange?: string;
    currency: string;
  };
  mode: EarningsMode;
  fiscalPeriod: {
    label: string;
    basis?: EarningsBasis;
    periodEnd?: string;
    reportingDate?: string;
    reportingTime: "before-open" | "after-close" | "during-session" | "unknown";
  };
  verification: {
    status: VerificationStatus;
    latestPeriodChecked: boolean;
    checkedAt?: string;
    primarySourceIds: string[];
  };
  headline: string;
  metrics: EarningsMetric[];
  operatingMetrics: EarningsMetric[];
  guidance: GuidanceComparison[];
  scenarios: ConditionalScenario[];
  estimateRevisions: EstimateRevision[];
  thesisImpacts: EarningsThesisImpact[];
  sourceMaterials: EarningsSource[];
  gaps: string[];
  createdAt: string;
  updatedAt: string;
}

export interface EarningsWorkspace {
  schemaVersion: "newma-desk.earnings-research.v1";
  updatedAt: string;
  workbooks: EarningsWorkbook[];
}

interface StorageDocument {
  revision: number;
  value: unknown;
}

const LOCAL_KEY = "newma-desk.earnings-workbench.v1";
const NAMESPACE = "earnings-workbench";
const DOCUMENT_KEY = "workbooks";

function now() {
  return new Date().toISOString();
}

function makeId(prefix: string) {
  const suffix = globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(16).slice(2)}`;
  return `${prefix}:${suffix}`;
}

function baseMetric(id: string, label: string, unit: string): EarningsMetric {
  return {
    id,
    label,
    category: "financial",
    unit,
    reported: null,
    internalEstimate: null,
    consensus: null,
    varianceVsConsensus: { amount: null, percent: null, bps: null },
    sourceIds: [],
  };
}

export function defaultFinancialMetrics(): EarningsMetric[] {
  return [
    baseMetric("revenue", "营业收入", "亿元"),
    baseMetric("revenue-yoy", "营业收入同比", "%"),
    baseMetric("net-profit", "净利润", "亿元"),
    baseMetric("net-profit-yoy", "净利润同比", "%"),
    baseMetric("eps", "每股收益", "元"),
    baseMetric("gross-margin", "毛利率", "%"),
    baseMetric("net-margin", "净利率", "%"),
    baseMetric("roe", "ROE", "%"),
    baseMetric("op-cf-ps", "每股经营现金流", "元"),
  ];
}

function defaultScenarios(): ConditionalScenario[] {
  return [
    {
      id: makeId("scenario-above"),
      type: "above",
      condition: "核心财务和经营指标高于预期，且质量指标同步改善",
      operatingPath: "判断改善来自需求、价格、产品结构还是效率，并核验可持续性",
      researchResponse: "上调需要验证的经营假设，补充下一期领先指标与反方证据",
      indicators: ["收入", "利润率", "现金流"],
    },
    {
      id: makeId("scenario-inline"),
      type: "inline",
      condition: "核心指标大体符合预期，但结构、节奏或指引存在变化",
      operatingPath: "区分总量符合与内部结构变化，检查一次性因素和基数影响",
      researchResponse: "维持原研究框架，更新关键指标和下一期验证条件",
      indicators: ["产品结构", "费用率", "指引"],
    },
    {
      id: makeId("scenario-below"),
      type: "below",
      condition: "核心指标低于预期，或经营质量与管理层指引明显走弱",
      operatingPath: "识别短期扰动、执行问题与结构性恶化，检查证伪条件是否触发",
      researchResponse: "下调相关经营假设并明确恢复条件，不直接转换为交易建议",
      indicators: ["收入缺口", "利润率", "指引下修"],
    },
  ];
}

export function blankEarningsWorkbook(): EarningsWorkbook {
  const timestamp = now();
  return {
    id: makeId("earnings"),
    security: { market: "CN", symbol: "", name: "", exchange: "", currency: "CNY" },
    mode: "preview",
    fiscalPeriod: { label: "", reportingTime: "unknown" },
    verification: { status: "unverified", latestPeriodChecked: false, primarySourceIds: [] },
    headline: "",
    metrics: defaultFinancialMetrics(),
    operatingMetrics: [],
    guidance: [],
    scenarios: defaultScenarios(),
    estimateRevisions: [],
    thesisImpacts: [],
    sourceMaterials: [],
    gaps: [],
    createdAt: timestamp,
    updatedAt: timestamp,
  };
}

export function emptyEarningsWorkspace(): EarningsWorkspace {
  return { schemaVersion: "newma-desk.earnings-research.v1", updatedAt: now(), workbooks: [] };
}

export function earningsComparisonIssue(metric:EarningsMetric):string|null {
  if(metric.reported===null)return '实际值缺失';
  if(metric.consensus===null)return '一致预期缺失';
  if(!metric.reportedBasis||!metric.consensusBasis)return '实际或预期口径待确认';
  if(metric.reportedBasis!==metric.consensusBasis)return '实际与预期口径不同';
  if(!metric.periodEnd||!metric.consensusPeriodEnd)return '实际或预期期末待确认';
  if(metric.periodEnd!==metric.consensusPeriodEnd)return '实际与预期报告期不同';
  return null;
}

export function calculateVariance(metric: EarningsMetric): EarningsMetric {
  const { reported, consensus, unit } = metric;
  if (reported === null || consensus === null || earningsComparisonIssue(metric)) {
    return { ...metric, varianceVsConsensus: { amount: null, percent: null, bps: null } };
  }
  const amount = reported - consensus;
  const percent = consensus === 0 ? null : amount / Math.abs(consensus) * 100;
  const bps = unit === "%" ? amount * 100 : null;
  return { ...metric, varianceVsConsensus: { amount, percent, bps } };
}

export function earningsDataStatus(workbook:EarningsWorkbook) {
  const rows=workbook.metrics.map(metric=>{
    const sources=workbook.sourceMaterials.filter(source=>metric.sourceIds.includes(source.id));
    const adopted=sources.find(source=>source.correction&&source.correction.after===metric.reported&&source.excerpt?.metricId===metric.id&&source.excerpt.unit===metric.unit&&source.periodEnd===metric.periodEnd&&source.basis===metric.reportedBasis);
    const imported=sources.some(source=>source.importedReport&&source.excerpt?.reportedValue===metric.reported&&source.excerpt?.metricId===metric.id&&source.excerpt.unit===metric.unit&&source.periodEnd===metric.periodEnd&&source.basis===metric.reportedBasis);
    const origin=metric.reported===null?'missing':imported?'filing-import':adopted?(adopted.correction!.before===null?'filing-fill':'filing-revision'):metric.reportedOrigin==='provider'&&sources.length?'provider':metric.reportedOrigin==='manual'&&!metric.sourceIds.length?'manual':'unknown';
    const originLabel={missing:'实际值缺失','filing-import':'PDF 提取（用户确认）','filing-fill':'公告补录（人工采用）','filing-revision':'公告修订（人工采用）',provider:'财务摘要（未核验）',manual:'手工输入（无来源关联）',unknown:'来源待核对'}[origin];
    const comparisonIssue=earningsComparisonIssue(metric);
    return {metricId:metric.id,label:metric.label,origin,originLabel,comparisonIssue,
      comparisonNote:!comparisonIssue&&metric.consensus===0?'一致预期为零：可算差额，不计算相对增幅':null};
  });
  return {total:rows.length,present:rows.filter(row=>row.origin!=='missing').length,
    missing:rows.filter(row=>row.origin==='missing').length,
    comparable:rows.filter(row=>!row.comparisonIssue).length,
    filingAdopted:rows.filter(row=>row.origin==='filing-import'||row.origin==='filing-fill'||row.origin==='filing-revision').length,rows};
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function textValue(value: unknown, fallback = "", limit = 8_000) {
  return typeof value === "string" ? value.slice(0, limit) : fallback;
}

function numberValue(value: unknown) {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function stringList(value: unknown, limit: number) {
  return Array.isArray(value)
    ? value.filter((item): item is string => typeof item === "string" && Boolean(item.trim())).slice(0, limit)
    : [];
}

function normalizeMetric(value: unknown, fallback: EarningsMetric): EarningsMetric {
  const row = isRecord(value) ? value : {};
  const variance = isRecord(row.varianceVsConsensus) ? row.varianceVsConsensus : {};
  return calculateVariance({
    id: textValue(row.id, fallback.id, 160),
    label: textValue(row.label, fallback.label, 300),
    category: ["financial", "operating", "guidance", "valuation"].includes(String(row.category))
      ? row.category as MetricCategory
      : fallback.category,
    unit: textValue(row.unit, fallback.unit, 40),
    reported: numberValue(row.reported),
    internalEstimate: numberValue(row.internalEstimate),
    consensus: numberValue(row.consensus),
    varianceVsConsensus: {
      amount: numberValue(variance.amount),
      percent: numberValue(variance.percent),
      bps: numberValue(variance.bps),
    },
    sourceIds: stringList(row.sourceIds, 20),
    reportedBasis: normalizeBasis(row.reportedBasis),
    consensusBasis: normalizeBasis(row.consensusBasis),
    ...(textValue(row.consensusPeriodEnd) ? { consensusPeriodEnd: textValue(row.consensusPeriodEnd, '', 10) } : {}),
    ...(textValue(row.asOf) ? { asOf: textValue(row.asOf, "", 64) } : {}),
    ...(textValue(row.periodEnd) ? { periodEnd: textValue(row.periodEnd, '', 10) } : {}),
    ...(textValue(row.reportedCurrency) ? { reportedCurrency: textValue(row.reportedCurrency, '', 20) } : {}),
    ...(['provider','manual'].includes(String(row.reportedOrigin)) ? { reportedOrigin: row.reportedOrigin as 'provider'|'manual' } : {}),
    ...(textValue(row.note) ? { note: textValue(row.note, "", 2_000) } : {}),
  });
}

function normalizeWorkbook(value: unknown): EarningsWorkbook | null {
  if (!isRecord(value) || !isRecord(value.security)) return null;
  const symbol = textValue(value.security.symbol, "", 80);
  const name = textValue(value.security.name, "", 160);
  if (!symbol || !name) return null;
  const fallbackMetrics = defaultFinancialMetrics();
  const rawMetrics = Array.isArray(value.metrics) ? value.metrics : [];
  const byId = new Map(rawMetrics.filter(isRecord).map((item) => [textValue(item.id), item]));
  const metrics = fallbackMetrics.map((fallback) => normalizeMetric(byId.get(fallback.id), fallback));
  const fiscal = isRecord(value.fiscalPeriod) ? value.fiscalPeriod : {};
  const verification = isRecord(value.verification) ? value.verification : {};
  const timestamp = textValue(value.createdAt, now(), 64);
  return {
    ...blankEarningsWorkbook(),
    id: textValue(value.id, makeId("earnings"), 180),
    security: {
      market: textValue(value.security.market, "CN", 40),
      symbol,
      name,
      ...(textValue(value.security.exchange) ? { exchange: textValue(value.security.exchange, "", 40) } : {}),
      currency: textValue(value.security.currency, "CNY", 20),
    },
    mode: value.mode === "reported" ? "reported" : "preview",
    fiscalPeriod: {
      label: textValue(fiscal.label, "待确认报告期", 160),
      basis: normalizeBasis(fiscal.basis),
      ...(textValue(fiscal.periodEnd) ? { periodEnd: textValue(fiscal.periodEnd, "", 10) } : {}),
      ...(textValue(fiscal.reportingDate) ? { reportingDate: textValue(fiscal.reportingDate, "", 10) } : {}),
      reportingTime: ["before-open", "after-close", "during-session"].includes(String(fiscal.reportingTime))
        ? fiscal.reportingTime as EarningsWorkbook["fiscalPeriod"]["reportingTime"]
        : "unknown",
    },
    verification: {
      status: ["verified", "partial"].includes(String(verification.status))
        ? verification.status as VerificationStatus
        : "unverified",
      latestPeriodChecked: verification.latestPeriodChecked === true,
      ...(textValue(verification.checkedAt) ? { checkedAt: textValue(verification.checkedAt, "", 64) } : {}),
      primarySourceIds: stringList(verification.primarySourceIds, 20),
    },
    headline: textValue(value.headline, "", 4_000),
    metrics,
    operatingMetrics: (Array.isArray(value.operatingMetrics) ? value.operatingMetrics : [])
      .slice(0, 50)
      .map((item, index) => normalizeMetric(item, { ...baseMetric(`operating-${index + 1}`, "经营指标", "原始口径"), category: "operating" })),
    guidance: Array.isArray(value.guidance) ? value.guidance.slice(0, 30) as GuidanceComparison[] : [],
    scenarios: Array.isArray(value.scenarios) && value.scenarios.length === 3
      ? value.scenarios.slice(0, 3) as ConditionalScenario[]
      : defaultScenarios(),
    estimateRevisions: Array.isArray(value.estimateRevisions) ? value.estimateRevisions.slice(0, 30) as EstimateRevision[] : [],
    thesisImpacts: Array.isArray(value.thesisImpacts) ? value.thesisImpacts.slice(0, 30) as EarningsThesisImpact[] : [],
    sourceMaterials: Array.isArray(value.sourceMaterials) ? value.sourceMaterials.slice(0, 100) as EarningsSource[] : [],
    gaps: stringList(value.gaps, 30),
    createdAt: timestamp,
    updatedAt: textValue(value.updatedAt, timestamp, 64),
  };
}

function normalizeWorkspace(value: unknown): EarningsWorkspace {
  if (!isRecord(value)) return emptyEarningsWorkspace();
  return {
    schemaVersion: "newma-desk.earnings-research.v1",
    updatedAt: textValue(value.updatedAt, now(), 64),
    workbooks: (Array.isArray(value.workbooks) ? value.workbooks : [])
      .map(normalizeWorkbook)
      .filter((item): item is EarningsWorkbook => item !== null)
      .slice(0, 100),
  };
}

export function loadLocalEarningsWorkspace() {
  try {
    return normalizeWorkspace(JSON.parse(localStorage.getItem(LOCAL_KEY) || "null"));
  } catch {
    return emptyEarningsWorkspace();
  }
}

function canRead(config: VibeDeskConfig | null): config is VibeDeskConfig & {
  accessToken: string;
  instanceId: string;
  storageGateway: string;
} {
  return Boolean(config?.accessToken && config.instanceId && config.storageGateway && config.permissions?.includes("storage.read"));
}

function canWrite(config: VibeDeskConfig | null): config is VibeDeskConfig & {
  accessToken: string;
  instanceId: string;
  storageGateway: string;
} {
  return canRead(config) && Boolean(config.permissions?.includes("storage.write"));
}

function endpoint(config: VibeDeskConfig) {
  return `${config.storageGateway}/${NAMESPACE}/${DOCUMENT_KEY}`;
}

function headers(config: VibeDeskConfig, json = false) {
  return {
    Authorization: `Bearer ${config.accessToken}`,
    "X-Newma-Desk-Instance-Id": config.instanceId || "",
    ...(json ? { "Content-Type": "application/json" } : {}),
  };
}

async function readRemote(config: VibeDeskConfig) {
  const response = await fetch(endpoint(config), { headers: headers(config) });
  if (response.status === 404) return { found: false, revision: 0, state: emptyEarningsWorkspace() };
  if (!response.ok) throw new Error(`earnings workbench read failed: ${response.status}`);
  const document = await response.json() as StorageDocument;
  return { found: true, revision: Number(document.revision) || 0, state: normalizeWorkspace(document.value) };
}

export async function hydrateEarningsWorkspace() {
  const local = loadLocalEarningsWorkspace();
  const config = await waitForVibeDeskConfig();
  if (!canRead(config)) return local;
  try {
    const remote = await readRemote(config);
    return remote.found ? remote.state : local;
  } catch {
    return local;
  }
}

export async function persistEarningsWorkspace(workspace: EarningsWorkspace) {
  const normalized = normalizeWorkspace(workspace);
  let localSaved=false;
  try {
    localStorage.setItem(LOCAL_KEY, JSON.stringify(normalized));
    localSaved=true;
  } catch {
    // Keep the in-memory workbench usable when browser persistence is disabled.
  }
  const config = await waitForVibeDeskConfig();
  const fallback=()=>{if(localSaved)return 'local' as const;throw new Error('工作区及本地均未保存成功，请保留当前草稿并重试。')};
  if (!canWrite(config)) return fallback();
  for (let attempt = 0; attempt < 2; attempt += 1) {
    try {
      const current = await readRemote(config);
      const response = await fetch(endpoint(config), {
        method: "PUT",
        headers: headers(config, true),
        body: JSON.stringify({ expectedRevision: current.revision, value: normalized }),
      });
      if (response.status === 409 && attempt === 0) continue;
      if (!response.ok) throw new Error(`earnings workbench write failed: ${response.status}`);
      return 'desk' as const;
    } catch {
      return fallback();
    }
  }
  return fallback();
}
