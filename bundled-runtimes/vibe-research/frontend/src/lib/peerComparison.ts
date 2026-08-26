import { waitForVibeDeskConfig, type VibeDeskConfig } from "@/lib/vibedesk";

export type PeerQuestion = "valuation" | "growth" | "quality" | "efficiency" | "competitive-positioning";
export type PeerRole = "target" | "direct" | "adjacent" | "emerging";

export interface PeerSecurity {
  market: string;
  symbol: string;
  name: string;
  currency: string;
}

export interface PeerMember {
  security: PeerSecurity;
  role: PeerRole;
  included: boolean;
  rationale: string;
  exceptions: string[];
}

export interface PeerMetric {
  id: string;
  label: string;
  category: "operating" | "valuation" | "quality" | "industry";
  unit: string;
  higherIsBetter: boolean | null;
}

export interface PeerRow {
  security: PeerSecurity;
  isTarget: boolean;
  period: string;
  coverageRatio: number;
  values: Record<string, number | null>;
  scores: Record<string, number | null>;
  sourceIds: string[];
  warnings: string[];
}

export interface MetricStatistics {
  max: number | null;
  q75: number | null;
  median: number | null;
  q25: number | null;
  min: number | null;
}

export interface StrategicDimension {
  id: string;
  label: string;
  moat: "network-effects" | "switching-costs" | "scale-economies" | "intangible-assets" | "other";
  targetAssessment: string;
  peerObservation: string;
  trajectory: "improving" | "stable" | "deteriorating" | "unknown";
  sourceIds: string[];
}

export interface PeerSource {
  id: string;
  label: string;
  symbol?: string;
  asOf: string;
  url?: string;
  status: "verified" | "available" | "stale" | "unavailable";
}

export interface PeerComparisonCase {
  id: string;
  name: string;
  researchQuestion: PeerQuestion;
  target: PeerSecurity;
  members: PeerMember[];
  period: { label: string; asOf: string; fiscalAlignment: "aligned" | "mixed" | "unknown"; unitScale: string };
  metrics: PeerMetric[];
  rows: PeerRow[];
  statistics: Record<string, MetricStatistics>;
  strategicDimensions: StrategicDimension[];
  sourceMaterials: PeerSource[];
  synthesis: { durableAdvantages: string[]; structuralVulnerabilities: string[]; currentVsTrajectory: string };
  gaps: string[];
  createdAt: string;
  updatedAt: string;
}

export interface PeerComparisonWorkspace {
  schemaVersion: "newma-desk.peer-comparison.v1";
  updatedAt: string;
  cases: PeerComparisonCase[];
}

interface StorageDocument {
  revision: number;
  value: unknown;
}

const LOCAL_KEY = "newma-desk.peer-comparison.v1";
const NAMESPACE = "peer-comparison";
const DOCUMENT_KEY = "cases";

function now() {
  return new Date().toISOString();
}

function makeId(prefix: string) {
  const suffix = globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(16).slice(2)}`;
  return `${prefix}:${suffix}`;
}

function blankSecurity(): PeerSecurity {
  return { market: "CN", symbol: "", name: "", currency: "CNY" };
}

export function defaultPeerMetrics(): PeerMetric[] {
  return [
    { id: "revenueGrowthPct", label: "营收增长", category: "operating", unit: "%", higherIsBetter: true },
    { id: "netProfitGrowthPct", label: "净利润增长", category: "operating", unit: "%", higherIsBetter: true },
    { id: "grossMarginPct", label: "毛利率", category: "quality", unit: "%", higherIsBetter: true },
    { id: "netMarginPct", label: "净利率", category: "quality", unit: "%", higherIsBetter: true },
    { id: "roePct", label: "ROE", category: "quality", unit: "%", higherIsBetter: true },
    { id: "cashConversionPct", label: "现金转化", category: "quality", unit: "%", higherIsBetter: true },
    { id: "debtRatioPct", label: "资产负债率", category: "quality", unit: "%", higherIsBetter: false },
    { id: "pe", label: "PE", category: "valuation", unit: "x", higherIsBetter: null },
    { id: "pb", label: "PB", category: "valuation", unit: "x", higherIsBetter: null },
    { id: "valuationPercentile", label: "估值历史分位", category: "valuation", unit: "%", higherIsBetter: null },
  ];
}

function blankMember(role: PeerRole): PeerMember {
  return {
    security: blankSecurity(),
    role,
    included: true,
    rationale: role === "target" ? "核心研究对象" : "待说明业务模式、区域、客户或产品的可比性",
    exceptions: [],
  };
}

export function blankPeerComparisonCase(): PeerComparisonCase {
  const timestamp = now();
  return {
    id: makeId("peer-case"),
    name: "",
    researchQuestion: "quality",
    target: blankSecurity(),
    members: [blankMember("target"), blankMember("direct"), blankMember("direct")],
    period: { label: "最新报告期", asOf: timestamp.slice(0, 10), fiscalAlignment: "unknown", unitScale: "原始披露口径" },
    metrics: defaultPeerMetrics(),
    rows: [],
    statistics: {},
    strategicDimensions: [],
    sourceMaterials: [],
    synthesis: { durableAdvantages: [], structuralVulnerabilities: [], currentVsTrajectory: "" },
    gaps: [],
    createdAt: timestamp,
    updatedAt: timestamp,
  };
}

export function emptyPeerComparisonWorkspace(): PeerComparisonWorkspace {
  return { schemaVersion: "newma-desk.peer-comparison.v1", updatedAt: now(), cases: [] };
}

function quantile(sorted: number[], p: number) {
  if (!sorted.length) return null;
  const position = (sorted.length - 1) * p;
  const lower = Math.floor(position);
  const upper = Math.ceil(position);
  if (lower === upper) return sorted[lower] ?? null;
  const fraction = position - lower;
  return (sorted[lower] ?? 0) * (1 - fraction) + (sorted[upper] ?? 0) * fraction;
}

export function calculatePeerStatistics(rows: PeerRow[], metrics: PeerMetric[]) {
  return Object.fromEntries(metrics.map((metric) => {
    const values = rows
      .map((row) => row.values[metric.id])
      .filter((value): value is number => typeof value === "number" && Number.isFinite(value))
      .sort((left, right) => left - right);
    return [metric.id, {
      max: values.length ? values[values.length - 1] ?? null : null,
      q75: quantile(values, 0.75),
      median: quantile(values, 0.5),
      q25: quantile(values, 0.25),
      min: values[0] ?? null,
    } satisfies MetricStatistics];
  }));
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function textValue(value: unknown, fallback = "", limit = 8_000) {
  return typeof value === "string" ? value.slice(0, limit) : fallback;
}

function stringList(value: unknown, limit: number) {
  return Array.isArray(value)
    ? value.filter((item): item is string => typeof item === "string" && Boolean(item.trim())).slice(0, limit)
    : [];
}

function numberRecord(value: unknown) {
  if (!isRecord(value)) return {};
  return Object.fromEntries(Object.entries(value).flatMap(([key, item]) =>
    item === null || (typeof item === "number" && Number.isFinite(item)) ? [[key, item]] : []));
}

function normalizeSecurity(value: unknown, fallback = blankSecurity()): PeerSecurity {
  const row = isRecord(value) ? value : {};
  return {
    market: textValue(row.market, fallback.market, 20),
    symbol: textValue(row.symbol, fallback.symbol, 40),
    name: textValue(row.name, fallback.name, 120),
    currency: textValue(row.currency, fallback.currency, 20),
  };
}

function normalizeCase(value: unknown): PeerComparisonCase | null {
  if (!isRecord(value)) return null;
  const target = normalizeSecurity(value.target);
  if (!target.symbol || !target.name) return null;
  const fallback = blankPeerComparisonCase();
  const period = isRecord(value.period) ? value.period : {};
  const synthesis = isRecord(value.synthesis) ? value.synthesis : {};
  const members = (Array.isArray(value.members) ? value.members : []).flatMap((item) => {
    if (!isRecord(item)) return [];
    const security = normalizeSecurity(item.security);
    if (!security.symbol || !security.name) return [];
    return [{
      security,
      role: ["target", "direct", "adjacent", "emerging"].includes(String(item.role)) ? item.role as PeerRole : "direct",
      included: item.included !== false,
      rationale: textValue(item.rationale, "待补充可比性理由", 2_000),
      exceptions: stringList(item.exceptions, 10),
    }];
  }).slice(0, 8);
  const metrics = (Array.isArray(value.metrics) ? value.metrics : fallback.metrics).flatMap((item) => {
    if (!isRecord(item)) return [];
    const id = textValue(item.id, "", 100);
    if (!id) return [];
    return [{
      id,
      label: textValue(item.label, id, 160),
      category: ["operating", "valuation", "quality", "industry"].includes(String(item.category))
        ? item.category as PeerMetric["category"]
        : "industry",
      unit: textValue(item.unit, "原始口径", 30),
      higherIsBetter: typeof item.higherIsBetter === "boolean" ? item.higherIsBetter : null,
    }];
  }).slice(0, 15);
  const rows = (Array.isArray(value.rows) ? value.rows : []).flatMap((item) => {
    if (!isRecord(item)) return [];
    const security = normalizeSecurity(item.security);
    if (!security.symbol || !security.name) return [];
    return [{
      security,
      isTarget: item.isTarget === true,
      period: textValue(item.period, "待确认", 100),
      coverageRatio: typeof item.coverageRatio === "number" ? Math.max(0, Math.min(1, item.coverageRatio)) : 0,
      values: numberRecord(item.values),
      scores: numberRecord(item.scores),
      sourceIds: stringList(item.sourceIds, 30),
      warnings: stringList(item.warnings, 20),
    }];
  }).slice(0, 8);
  const createdAt = textValue(value.createdAt, now(), 64);
  return {
    id: textValue(value.id, makeId("peer-case"), 160),
    name: textValue(value.name, `${target.name} 同业比较`, 240),
    researchQuestion: ["valuation", "growth", "quality", "efficiency", "competitive-positioning"].includes(String(value.researchQuestion))
      ? value.researchQuestion as PeerQuestion
      : "quality",
    target,
    members: members.length >= 2 ? members : fallback.members.map((item, index) => index === 0 ? { ...item, security: target } : item),
    period: {
      label: textValue(period.label, "最新报告期", 120),
      asOf: textValue(period.asOf, now().slice(0, 10), 64),
      fiscalAlignment: ["aligned", "mixed"].includes(String(period.fiscalAlignment))
        ? period.fiscalAlignment as PeerComparisonCase["period"]["fiscalAlignment"]
        : "unknown",
      unitScale: textValue(period.unitScale, "原始披露口径", 80),
    },
    metrics: metrics.length >= 3 ? metrics : defaultPeerMetrics(),
    rows,
    statistics: calculatePeerStatistics(rows, metrics.length >= 3 ? metrics : defaultPeerMetrics()),
    strategicDimensions: Array.isArray(value.strategicDimensions) ? value.strategicDimensions.slice(0, 10) as StrategicDimension[] : [],
    sourceMaterials: Array.isArray(value.sourceMaterials) ? value.sourceMaterials.slice(0, 100) as PeerSource[] : [],
    synthesis: {
      durableAdvantages: stringList(synthesis.durableAdvantages, 10),
      structuralVulnerabilities: stringList(synthesis.structuralVulnerabilities, 10),
      currentVsTrajectory: textValue(synthesis.currentVsTrajectory, "", 4_000),
    },
    gaps: stringList(value.gaps, 30),
    createdAt,
    updatedAt: textValue(value.updatedAt, createdAt, 64),
  };
}

function normalizeWorkspace(value: unknown): PeerComparisonWorkspace {
  if (!isRecord(value)) return emptyPeerComparisonWorkspace();
  return {
    schemaVersion: "newma-desk.peer-comparison.v1",
    updatedAt: textValue(value.updatedAt, now(), 64),
    cases: (Array.isArray(value.cases) ? value.cases : [])
      .map(normalizeCase)
      .filter((item): item is PeerComparisonCase => item !== null)
      .slice(0, 100),
  };
}

export function loadLocalPeerComparisonWorkspace() {
  try {
    return normalizeWorkspace(JSON.parse(localStorage.getItem(LOCAL_KEY) || "null"));
  } catch {
    return emptyPeerComparisonWorkspace();
  }
}

function canRead(config: VibeDeskConfig | null): config is VibeDeskConfig & { accessToken: string; instanceId: string; storageGateway: string } {
  return Boolean(config?.accessToken && config.instanceId && config.storageGateway && config.permissions?.includes("storage.read"));
}

function canWrite(config: VibeDeskConfig | null): config is VibeDeskConfig & { accessToken: string; instanceId: string; storageGateway: string } {
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
  if (response.status === 404) return { found: false, revision: 0, state: emptyPeerComparisonWorkspace() };
  if (!response.ok) throw new Error(`peer comparison read failed: ${response.status}`);
  const document = await response.json() as StorageDocument;
  return { found: true, revision: Number(document.revision) || 0, state: normalizeWorkspace(document.value) };
}

export async function hydratePeerComparisonWorkspace() {
  const local = loadLocalPeerComparisonWorkspace();
  const config = await waitForVibeDeskConfig();
  if (!canRead(config)) return local;
  try {
    const remote = await readRemote(config);
    return remote.found ? remote.state : local;
  } catch {
    return local;
  }
}

export async function persistPeerComparisonWorkspace(workspace: PeerComparisonWorkspace) {
  const normalized = normalizeWorkspace(workspace);
  try {
    localStorage.setItem(LOCAL_KEY, JSON.stringify(normalized));
  } catch {
    // Keep the in-memory comparison usable when browser persistence is disabled.
  }
  const config = await waitForVibeDeskConfig();
  if (!canWrite(config)) return;
  for (let attempt = 0; attempt < 2; attempt += 1) {
    try {
      const current = await readRemote(config);
      const response = await fetch(endpoint(config), {
        method: "PUT",
        headers: headers(config, true),
        body: JSON.stringify({ expectedRevision: current.revision, value: normalized }),
      });
      if (response.status === 409 && attempt === 0) continue;
      if (!response.ok) throw new Error(`peer comparison write failed: ${response.status}`);
      return;
    } catch {
      return;
    }
  }
}
