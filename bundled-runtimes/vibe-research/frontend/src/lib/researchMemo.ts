import { getVibeDeskConfig, isVibeDeskEmbedded, waitForVibeDeskConfig, type VibeDeskConfig } from "@/lib/vibedesk";
import type { ResearchArchiveEntry, ResearchArchiveIndex } from "@/lib/researchArchive";

export type ResearchMemoStatus = "draft" | "current" | "superseded" | "archived";
export type ResearchBias = "constructive" | "neutral" | "cautious" | "watch";
export type ResearchConviction = "high" | "medium" | "low";
export type ResearchScenarioId = "bear" | "base" | "bull";
export type ArtifactKind = "thesis" | "earnings" | "peer-comparison" | "valuation" | "catalyst" | "industry-chain" | "macro" | "news" | "other";

export interface ResearchSecurity {
  market: string;
  symbol: string;
  name: string;
  exchange?: string;
  currency: string;
}

export interface ResearchArtifactReference {
  id: string;
  kind: ArtifactKind;
  sourceModId: string;
  artifactId: string;
  title: string;
  asOf?: string;
  status: "linked" | "stale" | "missing" | "unverified";
  sourceRevision?: number;
  sourceUpdatedAt?: string;
  note?: string;
}

export interface ResearchKeyDriver {
  id: string;
  name: string;
  whyItMatters: string;
  currentView: string;
  monitorMetric: string;
  confirmationCondition: string;
  falsificationCondition: string;
  sourceIds: string[];
}

export interface ResearchScenario {
  id: ResearchScenarioId;
  label: string;
  probabilityPct: number;
  operatingPath: string;
  valuationReference: string;
  triggerConditions: string[];
  evidenceIds: string[];
}

export interface ResearchCatalyst {
  id: string;
  title: string;
  window: string;
  expectedPath: string;
  confirmationConditions: string[];
  invalidationConditions: string[];
  artifactReferenceId?: string;
}

export interface ResearchRisk {
  id: string;
  type: "fundamental" | "valuation" | "competition" | "cycle" | "regulation" | "technology" | "execution" | "accounting" | "macro" | "other";
  statement: string;
  severity: "high" | "medium" | "low";
  likelihood: "high" | "medium" | "low" | "unknown";
  earlyWarnings: string[];
  breakCondition: string;
  sourceIds: string[];
}

export interface MonitoringItem {
  id: string;
  metric: string;
  latest: string;
  trend: "improving" | "stable" | "deteriorating" | "unknown";
  threshold: string;
  frequency: string;
  nextReviewAt?: string;
  sourceIds: string[];
}

export interface ResearchMemoSource {
  id: string;
  label: string;
  kind: "filing" | "company" | "consensus" | "research" | "news" | "derived" | "user";
  claimType: "reported" | "guidance" | "consensus" | "inference";
  asOf: string;
  status: "verified" | "available" | "stale" | "unavailable";
  url?: string;
  note?: string;
}

export interface ResearchMemo {
  id: string;
  title: string;
  status: ResearchMemoStatus;
  security: ResearchSecurity;
  boundary: {
    asOf: string;
    horizon: string;
    fiscalYear: string;
    reportingCurrency: string;
    scope: string;
    disclosureLimits: string[];
  };
  executiveView: {
    bias: ResearchBias;
    conviction: ResearchConviction;
    conclusion: string;
    coreThesis: string;
    keyDebate: string;
    variantPerception: string;
    whatMayBeMissing: string;
    breakpoint: string;
  };
  linkedArtifacts: ResearchArtifactReference[];
  keyDrivers: ResearchKeyDriver[];
  scenarios: ResearchScenario[];
  catalysts: ResearchCatalyst[];
  risks: ResearchRisk[];
  monitoring: MonitoringItem[];
  sources: ResearchMemoSource[];
  gaps: string[];
  nextReviewAt: string;
  versions: Array<{ version: number; createdAt: string; summary: string; changedSections: string[] }>;
  createdAt: string;
  updatedAt: string;
}

export interface ResearchMemoWorkspace {
  schemaVersion: "newma-desk.research-memo.v1";
  updatedAt: string;
  memos: ResearchMemo[];
}

export interface ResearchMemoSession {
  workspace: ResearchMemoWorkspace;
  mode: "local" | "desk";
  scope: string;
  revision: number;
  localVersion?: string | null;
  writable: boolean;
}

export class ResearchMemoStorageError extends Error {}

const LOCAL_KEY = "newma-desk.research-memo.v1";
const NAMESPACE = "research-memo";
const DOCUMENT_KEY = "memos";

function now() { return new Date().toISOString(); }
function today() { return now().slice(0, 10); }

export function createResearchId(prefix: string) {
  const suffix = globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(16).slice(2)}`;
  return `${prefix}:${suffix}`;
}

function nextMonth() {
  const date = new Date();
  date.setMonth(date.getMonth() + 1);
  return date.toISOString().slice(0, 10);
}

function blankDriver(index: number): ResearchKeyDriver {
  return {
    id: createResearchId("driver"),
    name: `关键驱动 ${index}`,
    whyItMatters: "待补充：说明它如何影响增长、盈利质量或估值。",
    currentView: "待补充当前事实、预期与研究推断。",
    monitorMetric: "待补充可观察指标",
    confirmationCondition: "待补充确认条件",
    falsificationCondition: "待补充证伪条件",
    sourceIds: [],
  };
}

function blankRisk(index: number): ResearchRisk {
  return {
    id: createResearchId("risk"),
    type: "fundamental",
    statement: `关键风险 ${index}`,
    severity: "medium",
    likelihood: "unknown",
    earlyWarnings: ["待补充领先预警信号"],
    breakCondition: "待补充会迫使重新研究的可观察条件",
    sourceIds: [],
  };
}

function blankMonitor(index: number): MonitoringItem {
  return {
    id: createResearchId("monitor"),
    metric: `跟踪指标 ${index}`,
    latest: "待更新",
    trend: "unknown",
    threshold: "待补充触发复核的阈值",
    frequency: "月度",
    sourceIds: [],
  };
}

export function blankResearchMemo(): ResearchMemo {
  const timestamp = now();
  return {
    id: createResearchId("memo"),
    title: "",
    status: "draft",
    security: { market: "CN", symbol: "", name: "", currency: "CNY" },
    boundary: {
      asOf: today(),
      horizon: "未来 12 个月，重点跟踪未来 3–6 个月催化",
      fiscalYear: `FY${new Date().getFullYear()}`,
      reportingCurrency: "CNY",
      scope: "经营驱动、产业链、竞争、财报、估值、催化剂与反方证据",
      disclosureLimits: ["尚未核验的输入必须明确标记"],
    },
    executiveView: {
      bias: "watch",
      conviction: "low",
      conclusion: "",
      coreThesis: "",
      keyDebate: "",
      variantPerception: "",
      whatMayBeMissing: "",
      breakpoint: "",
    },
    linkedArtifacts: [],
    keyDrivers: [1, 2, 3].map(blankDriver),
    scenarios: [
      { id: "bear", label: "悲观", probabilityPct: 25, operatingPath: "待补充悲观经营路径", valuationReference: "待关联估值工作台悲观情景", triggerConditions: ["待补充触发条件"], evidenceIds: [] },
      { id: "base", label: "基准", probabilityPct: 50, operatingPath: "待补充基准经营路径", valuationReference: "待关联估值工作台基准情景", triggerConditions: ["待补充触发条件"], evidenceIds: [] },
      { id: "bull", label: "乐观", probabilityPct: 25, operatingPath: "待补充乐观经营路径", valuationReference: "待关联估值工作台乐观情景", triggerConditions: ["待补充触发条件"], evidenceIds: [] },
    ],
    catalysts: [],
    risks: [1, 2, 3].map(blankRisk),
    monitoring: [1, 2, 3].map(blankMonitor),
    sources: [],
    gaps: ["补齐原始来源、市场预期与反方证据"],
    nextReviewAt: nextMonth(),
    versions: [{ version: 1, createdAt: timestamp, summary: "创建研究备忘录草稿", changedSections: ["全部"] }],
    createdAt: timestamp,
    updatedAt: timestamp,
  };
}

export function emptyResearchMemoWorkspace(): ResearchMemoWorkspace {
  return { schemaVersion: "newma-desk.research-memo.v1", updatedAt: now(), memos: [] };
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function textValue(value: unknown, fallback = "", limit = 8_000) {
  return typeof value === "string" ? value.slice(0, limit) : fallback;
}

function list(value: unknown, limit: number) {
  return Array.isArray(value)
    ? value.filter((item): item is string => typeof item === "string" && Boolean(item.trim())).slice(0, limit)
    : [];
}

function enumValue<T extends string>(value: unknown, allowed: readonly T[], fallback: T): T {
  return allowed.includes(value as T) ? value as T : fallback;
}

function normalizeMemo(value: unknown): ResearchMemo | null {
  if (!isRecord(value)) return null;
  const fallback = blankResearchMemo();
  const security = isRecord(value.security) ? value.security : {};
  const title = textValue(value.title, "", 240);
  const symbol = textValue(security.symbol, "", 40);
  const name = textValue(security.name, "", 120);
  if (!title || !symbol || !name) return null;
  const boundary = isRecord(value.boundary) ? value.boundary : {};
  const view = isRecord(value.executiveView) ? value.executiveView : {};
  const scenariosById = new Map((Array.isArray(value.scenarios) ? value.scenarios : []).flatMap((item) => {
    if (!isRecord(item) || !["bear", "base", "bull"].includes(String(item.id))) return [];
    return [[item.id as ResearchScenarioId, item] as const];
  }));
  const scenarios = fallback.scenarios.map((base) => {
    const row = scenariosById.get(base.id);
    return row ? {
      ...base,
      label: textValue(row.label, base.label, 40),
      probabilityPct: typeof row.probabilityPct === "number" ? Math.max(0, Math.min(100, row.probabilityPct)) : base.probabilityPct,
      operatingPath: textValue(row.operatingPath, base.operatingPath),
      valuationReference: textValue(row.valuationReference, base.valuationReference),
      triggerConditions: list(row.triggerConditions, 20),
      evidenceIds: list(row.evidenceIds, 30),
    } : base;
  });
  const linkedArtifacts = (Array.isArray(value.linkedArtifacts) ? value.linkedArtifacts : []).flatMap((item) => {
    if (!isRecord(item)) return [];
    const artifactId = textValue(item.artifactId, "", 200);
    const itemTitle = textValue(item.title, "", 240);
    if (!artifactId || !itemTitle) return [];
    return [{
      id: textValue(item.id, createResearchId("artifact"), 200),
      kind: enumValue(item.kind, ["thesis", "earnings", "peer-comparison", "valuation", "catalyst", "industry-chain", "macro", "news", "other"] as const, "other"),
      sourceModId: textValue(item.sourceModId, "research-notes", 120),
      artifactId,
      title: itemTitle,
      ...(typeof item.asOf === "string" ? { asOf: item.asOf.slice(0, 80) } : {}),
      status: enumValue(item.status, ["linked", "stale", "missing", "unverified"] as const, "unverified"),
      ...(Number.isInteger(item.sourceRevision) && Number(item.sourceRevision) > 0 ? { sourceRevision: item.sourceRevision as number } : {}),
      ...(typeof item.sourceUpdatedAt === "string" ? { sourceUpdatedAt: item.sourceUpdatedAt.slice(0, 80) } : {}),
      ...(typeof item.note === "string" ? { note: item.note.slice(0, 2_000) } : {}),
    }];
  }).slice(0, 50);
  const normalizeRequiredRows = <T>(raw: unknown, defaults: T[], minimum: number) => {
    const rows = Array.isArray(raw) ? raw.filter(isRecord) : [];
    return rows.length >= minimum ? rows : defaults as unknown as Record<string, unknown>[];
  };
  const keyDrivers = normalizeRequiredRows(value.keyDrivers, fallback.keyDrivers, 3).slice(0, 7).map((row, index) => ({
    id: textValue(row.id, createResearchId("driver"), 160),
    name: textValue(row.name, `关键驱动 ${index + 1}`, 240),
    whyItMatters: textValue(row.whyItMatters, "待补充"),
    currentView: textValue(row.currentView, "待补充"),
    monitorMetric: textValue(row.monitorMetric, "待补充"),
    confirmationCondition: textValue(row.confirmationCondition, "待补充"),
    falsificationCondition: textValue(row.falsificationCondition, "待补充"),
    sourceIds: list(row.sourceIds, 30),
  }));
  const risks = normalizeRequiredRows(value.risks, fallback.risks, 3).slice(0, 12).map((row, index) => ({
    id: textValue(row.id, createResearchId("risk"), 160),
    type: enumValue(row.type, ["fundamental", "valuation", "competition", "cycle", "regulation", "technology", "execution", "accounting", "macro", "other"] as const, "other"),
    statement: textValue(row.statement, `关键风险 ${index + 1}`),
    severity: enumValue(row.severity, ["high", "medium", "low"] as const, "medium"),
    likelihood: enumValue(row.likelihood, ["high", "medium", "low", "unknown"] as const, "unknown"),
    earlyWarnings: list(row.earlyWarnings, 20),
    breakCondition: textValue(row.breakCondition, "待补充"),
    sourceIds: list(row.sourceIds, 30),
  }));
  const monitoring = normalizeRequiredRows(value.monitoring, fallback.monitoring, 3).slice(0, 20).map((row, index) => ({
    id: textValue(row.id, createResearchId("monitor"), 160),
    metric: textValue(row.metric, `跟踪指标 ${index + 1}`, 240),
    latest: textValue(row.latest, "待更新", 240),
    trend: enumValue(row.trend, ["improving", "stable", "deteriorating", "unknown"] as const, "unknown"),
    threshold: textValue(row.threshold, "待补充"),
    frequency: textValue(row.frequency, "月度", 80),
    ...(typeof row.nextReviewAt === "string" ? { nextReviewAt: row.nextReviewAt.slice(0, 10) } : {}),
    sourceIds: list(row.sourceIds, 30),
  }));
  const timestamp = textValue(value.updatedAt, now(), 64);
  return {
    ...fallback,
    id: textValue(value.id, createResearchId("memo"), 160),
    title,
    status: enumValue(value.status, ["draft", "current", "superseded", "archived"] as const, "draft"),
    security: {
      market: textValue(security.market, "CN", 20), symbol, name,
      ...(typeof security.exchange === "string" ? { exchange: security.exchange.slice(0, 40) } : {}),
      currency: textValue(security.currency, "CNY", 20),
    },
    boundary: {
      asOf: textValue(boundary.asOf, today(), 10),
      horizon: textValue(boundary.horizon, fallback.boundary.horizon, 240),
      fiscalYear: textValue(boundary.fiscalYear, fallback.boundary.fiscalYear, 80),
      reportingCurrency: textValue(boundary.reportingCurrency, "CNY", 20),
      scope: textValue(boundary.scope, fallback.boundary.scope, 2_000),
      disclosureLimits: list(boundary.disclosureLimits, 30),
    },
    executiveView: {
      bias: enumValue(view.bias, ["constructive", "neutral", "cautious", "watch"] as const, "watch"),
      conviction: enumValue(view.conviction, ["high", "medium", "low"] as const, "low"),
      conclusion: textValue(view.conclusion), coreThesis: textValue(view.coreThesis),
      keyDebate: textValue(view.keyDebate), variantPerception: textValue(view.variantPerception),
      whatMayBeMissing: textValue(view.whatMayBeMissing), breakpoint: textValue(view.breakpoint),
    },
    linkedArtifacts,
    keyDrivers,
    scenarios,
    catalysts: (Array.isArray(value.catalysts) ? value.catalysts : []).filter(isRecord).slice(0, 20).map((row) => ({
      id: textValue(row.id, createResearchId("catalyst"), 160), title: textValue(row.title, "待补充"),
      window: textValue(row.window, "待确认", 120), expectedPath: textValue(row.expectedPath, "待补充"),
      confirmationConditions: list(row.confirmationConditions, 20), invalidationConditions: list(row.invalidationConditions, 20),
      ...(typeof row.artifactReferenceId === "string" ? { artifactReferenceId: row.artifactReferenceId.slice(0, 160) } : {}),
    })),
    risks,
    monitoring,
    sources: (Array.isArray(value.sources) ? value.sources : []).filter(isRecord).slice(0, 150).map((row) => ({
      id: textValue(row.id, createResearchId("source"), 160), label: textValue(row.label, "用户来源", 240),
      kind: enumValue(row.kind, ["filing", "company", "consensus", "research", "news", "derived", "user"] as const, "user"),
      claimType: enumValue(row.claimType, ["reported", "guidance", "consensus", "inference"] as const, "inference"),
      asOf: textValue(row.asOf, "待核验", 80), status: enumValue(row.status, ["verified", "available", "stale", "unavailable"] as const, "available"),
      ...(typeof row.url === "string" ? { url: row.url.slice(0, 2_000) } : {}),
      ...(typeof row.note === "string" ? { note: row.note.slice(0, 2_000) } : {}),
    })),
    gaps: list(value.gaps, 40),
    nextReviewAt: textValue(value.nextReviewAt, nextMonth(), 10),
    versions: (Array.isArray(value.versions) ? value.versions : fallback.versions).filter(isRecord).slice(0, 100).map((row, index) => ({
      version: typeof row.version === "number" ? Math.max(1, Math.trunc(row.version)) : index + 1,
      createdAt: textValue(row.createdAt, timestamp, 64), summary: textValue(row.summary, "更新研究备忘录", 1_000),
      changedSections: list(row.changedSections, 30),
    })),
    createdAt: textValue(value.createdAt, timestamp, 64),
    updatedAt: timestamp,
  };
}

function normalizeWorkspace(value: unknown): ResearchMemoWorkspace {
  if (!isRecord(value)) return emptyResearchMemoWorkspace();
  return {
    schemaVersion: "newma-desk.research-memo.v1",
    updatedAt: textValue(value.updatedAt, now(), 64),
    memos: (Array.isArray(value.memos) ? value.memos : []).map(normalizeMemo).filter((item): item is ResearchMemo => item !== null).slice(0, 100),
  };
}

export function researchMemoScope(config = getVibeDeskConfig()) {
  return config ? JSON.stringify([config.apiOrigin, config.storageGateway, config.userId, config.workspaceId, config.moduleId, config.instanceId])
    : isVibeDeskEmbedded ? "unconnected" : "local";
}

function assertScope(scope: string, signal?: AbortSignal) {
  signal?.throwIfAborted();
  if (scope !== researchMemoScope()) throw new ResearchMemoStorageError("工作区已变化，请在当前工作区重新读取；未转存旧草稿。");
}

function checkedWorkspace(value: unknown): ResearchMemoWorkspace {
  if (!isRecord(value) || value.schemaVersion !== "newma-desk.research-memo.v1" || !Array.isArray(value.memos) || value.memos.length > 100) {
    throw new ResearchMemoStorageError("备忘录格式不完整或超过 100 份，未读取为空档案，也未覆盖原数据。");
  }
  const result = normalizeWorkspace(value);
  if (result.memos.length !== value.memos.length || new Set(result.memos.map((memo) => memo.id)).size !== result.memos.length) {
    throw new ResearchMemoStorageError("备忘录格式不完整或档案标识重复，未覆盖原数据。");
  }
  return result;
}

function canRead(config: VibeDeskConfig | null): config is VibeDeskConfig & { accessToken: string; instanceId: string; storageGateway: string } {
  return Boolean(config?.moduleId === "research-memo" && config.userId && config.workspaceId && config.accessToken && config.instanceId && config.storageGateway && config.permissions?.includes("storage.read"));
}
function canWrite(config: VibeDeskConfig | null): config is VibeDeskConfig & { accessToken: string; instanceId: string; storageGateway: string } {
  return canRead(config) && Boolean(config.permissions?.includes("storage.write"));
}
function endpoint(config: VibeDeskConfig) { return `${config.storageGateway}/${NAMESPACE}/${DOCUMENT_KEY}`; }
function headers(config: VibeDeskConfig, json = false) {
  return { Authorization: `Bearer ${config.accessToken}`, "X-Newma-Desk-Instance-Id": config.instanceId || "", ...(json ? { "Content-Type": "application/json" } : {}) };
}
function requestSignal(signal?: AbortSignal) {
  const timeout = AbortSignal.timeout(15_000);
  return signal ? AbortSignal.any([signal, timeout]) : timeout;
}
function checkedDocument(value: unknown, minimumRevision = 1) {
  if (!isRecord(value) || !Number.isInteger(value.revision) || Number(value.revision) < minimumRevision) {
    throw new ResearchMemoStorageError("存储回执格式或修订号异常，请保留草稿并重新读取核对。");
  }
  return { revision: value.revision as number, workspace: checkedWorkspace(value.value) };
}

export async function hydrateResearchMemoWorkspace(signal?: AbortSignal): Promise<ResearchMemoSession> {
  const config = await waitForVibeDeskConfig();
  const scope = researchMemoScope(config);
  assertScope(scope, signal);
  if (!config && !isVibeDeskEmbedded) {
    try {
      const raw = localStorage.getItem(LOCAL_KEY);
      return { workspace: raw === null ? emptyResearchMemoWorkspace() : checkedWorkspace(JSON.parse(raw)), mode: "local", scope, revision: 0, localVersion: raw, writable: true };
    } catch (error) {
      if (error instanceof ResearchMemoStorageError) throw error;
      throw new ResearchMemoStorageError("本机读取失败，原记录未改动；请检查浏览器存储后重试。");
    }
  }
  if (!canRead(config)) throw new ResearchMemoStorageError("尚未连接已授权的 Desk 存储；不会读取其他工作区或本机旧缓存。");
  try {
    const response = await fetch(endpoint(config), { headers: headers(config), signal: requestSignal(signal) });
    assertScope(scope, signal);
    const document = response.status === 404 ? { revision: 0, workspace: emptyResearchMemoWorkspace() }
      : response.ok ? checkedDocument(await response.json()) : null;
    if (!document) throw new ResearchMemoStorageError(`Desk 读取失败（HTTP ${response.status}），未载入其他工作区或本机旧缓存。`);
    assertScope(scope, signal);
    return { ...document, scope, mode: "desk", writable: canWrite(config) };
  } catch (error) {
    if (error instanceof ResearchMemoStorageError) throw error;
    throw new ResearchMemoStorageError("Desk 读取失败，请检查连接后重新读取；原记录未改动。");
  }
}

export async function persistResearchMemoWorkspace(workspace: ResearchMemoWorkspace, session: ResearchMemoSession, signal?: AbortSignal): Promise<ResearchMemoSession> {
  assertScope(session.scope, signal);
  const normalized = checkedWorkspace(workspace);
  if (session.mode === "local") {
    try {
      if (localStorage.getItem(LOCAL_KEY) !== session.localVersion) throw new ResearchMemoStorageError("保存冲突：其他窗口已更新本机档案。草稿保留，请先导出再重新读取核对。");
      const raw = JSON.stringify(normalized);
      localStorage.setItem(LOCAL_KEY, raw);
      if (localStorage.getItem(LOCAL_KEY) !== raw) throw new ResearchMemoStorageError("本机保存未确认，请保留草稿并重新读取核对。");
      return { ...session, workspace: normalized, localVersion: raw };
    } catch (error) {
      if (error instanceof ResearchMemoStorageError) throw error;
      throw new ResearchMemoStorageError("本机保存失败，草稿仍在；刷新或关闭前请导出草稿，检查浏览器存储空间。");
    }
  }
  const config = getVibeDeskConfig();
  if (!canWrite(config)) throw new ResearchMemoStorageError("当前工作区没有保存权限；草稿未写入，请先导出保留。");
  try {
    const response = await fetch(endpoint(config), {
      method: "PUT", headers: headers(config, true), signal: requestSignal(signal),
      body: JSON.stringify({ expectedRevision: session.revision, value: normalized }),
    });
    assertScope(session.scope, signal);
    if (response.status === 409) throw new ResearchMemoStorageError("保存冲突：其他窗口已更新。草稿保留，请先导出再重新读取核对；未覆盖对方版本。");
    if (!response.ok) throw new ResearchMemoStorageError(`Desk 保存未确认（HTTP ${response.status}）。草稿保留，请重新读取核对，勿重复提交。`);
    const result = checkedDocument(await response.json(), session.revision + 1);
    assertScope(session.scope, signal);
    return { ...session, ...result };
  } catch (error) {
    if (error instanceof ResearchMemoStorageError) throw error;
    throw new ResearchMemoStorageError("Desk 保存未确认，草稿仍在；请先导出，再重新读取核对，勿重复提交。");
  }
}

export function researchReferenceFromEntry(entry: ResearchArchiveEntry, previous?: ResearchArtifactReference): ResearchArtifactReference {
  const kind = ["thesis", "earnings", "peer-comparison", "valuation"].includes(entry.kind) ? entry.kind as ArtifactKind : "other";
  return {
    id: previous?.id || createResearchId("artifact"), kind,
    sourceModId: entry.sourceModId, artifactId: entry.artifactId, title: entry.title,
    asOf: entry.asOf,
    sourceRevision: entry.sourceRevision, sourceUpdatedAt: entry.updatedAt,
    status: entry.sourceRevision ? entry.status === "active" ? "linked" : "stale" : "unverified",
    note: previous?.note || (entry.sourceRevision ? "已登记档案索引版本；不代表底稿证据或投资结论已核验。" : "本机缓存引用，工作区归属与来源版本尚未核验。"),
  };
}

export function researchReferenceCheck(reference: ResearchArtifactReference, index: ResearchArchiveIndex | null) {
  if (!index) return { state: "unchecked", label: "尚未核对来源" };
  const source = index.entries.find((entry) => entry.sourceModId === reference.sourceModId && entry.artifactId === reference.artifactId);
  if (!source) {
    const covered = ["thesis-tracker", "earnings-workbench", "peer-comparison", "valuation-workbench", "research-memo", "research-notes"].includes(reference.sourceModId);
    return !covered || index.truncated !== false || !index.unavailableSources || index.unavailableSources.includes(reference.sourceModId)
      ? { state: "unavailable", label: "来源未完整读取，不能判断是否删除" }
      : { state: "missing", label: "当前工作区未找到该档案，请核对来源与 ID" };
  }
  if (["archived", "invalidated", "stale", "draft", "unknown"].includes(source.status)) return { state: "inactive", label: "来源为草稿、归档或待复核状态", source };
  if (reference.sourceUpdatedAt && (reference.sourceRevision !== source.sourceRevision || reference.sourceUpdatedAt !== source.updatedAt || reference.title !== source.title || reference.asOf !== source.asOf)) {
    return { state: "changed", label: source.sourceRevision ? "来源版本已变化，需复核后采纳" : "本机来源信息已变化，归属与版本仍待核验", source };
  }
  if (!source.sourceRevision || !reference.sourceRevision || !reference.sourceUpdatedAt) return { state: "unverified", label: "引用版本待确认", source };
  return { state: "current", label: "索引版本一致；证据内容仍需核验", source };
}
