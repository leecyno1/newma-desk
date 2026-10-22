import { createModStorageClient, GatewayError } from '@newma-desk/mod-sdk';
import { reviewPeerComparison } from './peerReview';
export { calculatePeerStatistics } from './peerReview';
import { getVibeDeskConfig, isVibeDeskEmbedded, waitForVibeDeskConfig, type VibeDeskConfig } from "@/lib/vibedesk";

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
  metricEvidence?: Record<string, { id: string; source: string; asOf: string | null; unit: string | null; note?: string | null }>;
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

export interface PeerComparisonSession {
  workspace: PeerComparisonWorkspace;
  scope: string;
  mode: 'local' | 'desk';
  revision: number;
  localVersion?: string | null;
  writable: boolean;
}
export class PeerStorageError extends Error {}

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
    if (item.included !== false && (!security.symbol || !security.name)) return [];
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
      ...(isRecord(item.metricEvidence) ? { metricEvidence: item.metricEvidence as PeerRow['metricEvidence'] } : {}),
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
    statistics: {},
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

export function peerComparisonScope(config = getVibeDeskConfig()) {
  return config ? JSON.stringify([config.apiOrigin, config.storageGateway, config.moduleId, config.userId, config.workspaceId,
    config.instanceId, Boolean(config.accessToken), config.permissions?.includes('storage.read'), config.permissions?.includes('storage.write')])
    : isVibeDeskEmbedded || import.meta.env.VITE_NEWMA_DESK_INTEGRATED === '1' ? 'unconnected' : 'local';
}

function assertScope(scope: string, signal?: AbortSignal) {
  signal?.throwIfAborted();
  if (scope !== peerComparisonScope()) throw new PeerStorageError('工作区或权限已变化，旧结果未转存，请重新读取。');
}

function checkedWorkspace(value: unknown): PeerComparisonWorkspace {
  if (!isRecord(value) || value.schemaVersion !== 'newma-desk.peer-comparison.v1' || !Array.isArray(value.cases) || value.cases.length > 100) {
    throw new PeerStorageError('同业档案格式异常，未按空库处理，也未覆盖原记录。');
  }
  const workspace = normalizeWorkspace(value);
  if (workspace.cases.length !== value.cases.length || new Set(workspace.cases.map(item => item.id)).size !== workspace.cases.length
    || value.cases.some((item, index) => !isRecord(item) || !item.id
      || !Array.isArray(item.members) || item.members.length !== workspace.cases[index]?.members.length
      || !Array.isArray(item.metrics) || item.metrics.length !== workspace.cases[index]?.metrics.length
      || !Array.isArray(item.rows) || item.rows.length !== workspace.cases[index]?.rows.length
      || item.rows.some(row => !isRecord(row) || !isRecord(row.values)
        || Object.values(row.values).some(number => number !== null && (typeof number !== 'number' || !Number.isFinite(number)))
        || (row.metricEvidence !== undefined && (!isRecord(row.metricEvidence) || Object.values(row.metricEvidence).some(evidence =>
          !isRecord(evidence) || typeof evidence.id !== 'string' || typeof evidence.source !== 'string'
          || (evidence.asOf !== null && typeof evidence.asOf !== 'string') || (evidence.unit !== null && typeof evidence.unit !== 'string')))))
      || !Array.isArray(item.sourceMaterials) || item.sourceMaterials.length > 100
      || item.sourceMaterials.some(source => !isRecord(source) || typeof source.id !== 'string' || typeof source.label !== 'string' || typeof source.asOf !== 'string')
      || !Array.isArray(item.strategicDimensions) || item.strategicDimensions.length > 10
      || item.strategicDimensions.some(dimension => !isRecord(dimension) || typeof dimension.id !== 'string' || typeof dimension.label !== 'string'))) {
    throw new PeerStorageError('同业档案的公司、指标或来源不完整，未丢弃记录，请核对原数据。');
  }
  for (const draft of workspace.cases) draft.statistics = reviewPeerComparison(draft).statistics;
  return workspace;
}

function checkedDocument(value: unknown, minimumRevision = 1) {
  if (!isRecord(value) || !Number.isInteger(value.revision) || Number(value.revision) < minimumRevision) {
    throw new PeerStorageError('保存回执或修订号异常，请保留草稿并重新读取核对。');
  }
  return { revision: value.revision as number, workspace: checkedWorkspace(value.value) };
}

function canRead(config: VibeDeskConfig | null): config is VibeDeskConfig & { accessToken: string; instanceId: string; storageGateway: string } {
  return Boolean(config?.moduleId === 'peer-comparison' && config.userId && config.workspaceId && config.accessToken && config.instanceId && config.storageGateway && config.permissions?.includes("storage.read"));
}

function canWrite(config: VibeDeskConfig | null): config is VibeDeskConfig & { accessToken: string; instanceId: string; storageGateway: string } {
  return canRead(config) && Boolean(config.permissions?.includes("storage.write"));
}

function storageClient(config: VibeDeskConfig & { accessToken: string; instanceId: string }, signal?: AbortSignal) {
  const cancel = signal ? AbortSignal.any([signal, AbortSignal.timeout(15_000)]) : AbortSignal.timeout(15_000);
  return createModStorageClient({ baseUrl: config.apiOrigin, modId: 'peer-comparison', accessToken: config.accessToken, instanceId: config.instanceId,
    fetch: async (url, init) => { cancel.throwIfAborted(); return fetch(url, { ...init, signal: cancel, cache: 'no-store' }); },
  });
}

export async function hydratePeerComparisonWorkspace(signal?: AbortSignal): Promise<PeerComparisonSession> {
  const scope = peerComparisonScope();
  const config = await waitForVibeDeskConfig();
  assertScope(scope, signal);
  if (scope === 'local' && !config) {
    try {
      const raw = localStorage.getItem(LOCAL_KEY);
      return { workspace: raw === null ? emptyPeerComparisonWorkspace() : checkedWorkspace(JSON.parse(raw)),
        scope, mode: 'local', revision: 0, localVersion: raw, writable: true };
    } catch (error) {
      if (error instanceof PeerStorageError) throw error;
      throw new PeerStorageError('本机同业档案读取失败，未按空库处理，请检查浏览器存储。');
    }
  }
  if (!canRead(config)) throw new PeerStorageError('尚未获得同业档案读取授权，不会使用本机旧缓存替代。');
  try {
    const document = await storageClient(config, signal).get(NAMESPACE, DOCUMENT_KEY);
    assertScope(scope, signal);
    return { ...checkedDocument(document), scope, mode: 'desk', writable: canWrite(config) };
  } catch (error) {
    assertScope(scope, signal);
    if (error instanceof GatewayError && error.status === 404) return { workspace: emptyPeerComparisonWorkspace(), scope, mode: 'desk', revision: 0, writable: canWrite(config) };
    if (error instanceof PeerStorageError) throw error;
    throw new PeerStorageError('Desk 同业档案读取失败，未使用本机旧缓存替代；原记录未改动。');
  }
}

export async function persistPeerComparisonWorkspace(workspace: PeerComparisonWorkspace, session: PeerComparisonSession, signal?: AbortSignal): Promise<PeerComparisonSession> {
  assertScope(session.scope, signal);
  const normalized = checkedWorkspace(workspace);
  if (session.mode === 'local') {
    try {
      if (localStorage.getItem(LOCAL_KEY) !== session.localVersion) throw new PeerStorageError('保存冲突：其他窗口已更新本机同业档案，请先导出草稿再重新读取。');
      const raw = JSON.stringify(normalized);
      localStorage.setItem(LOCAL_KEY, raw);
      if (localStorage.getItem(LOCAL_KEY) !== raw) throw new PeerStorageError('本机保存未确认，请保留草稿并重新读取核对。');
      return { ...session, workspace: normalized, localVersion: raw };
    } catch (error) {
      if (error instanceof PeerStorageError) throw error;
      throw new PeerStorageError('本机保存失败，请在关闭或刷新前导出草稿。');
    }
  }
  const config = getVibeDeskConfig();
  if (!session.writable || !canWrite(config)) throw new PeerStorageError('当前工作区没有保存权限，请先导出草稿。');
  try {
    const result = await storageClient(config, signal).put(NAMESPACE, DOCUMENT_KEY, normalized, session.revision);
    assertScope(session.scope, signal);
    return { ...session, ...checkedDocument(result, session.revision + 1) };
  } catch (error) {
    assertScope(session.scope, signal);
    if (error instanceof GatewayError && error.status === 409) throw new PeerStorageError('保存冲突：其他窗口已更新。草稿保留，未覆盖对方版本；请先导出再重新读取核对。');
    if (error instanceof PeerStorageError) throw error;
    throw new PeerStorageError('Desk 保存未确认，可能已写入；请保留草稿并重新读取核对，勿重复提交。');
  }
}
