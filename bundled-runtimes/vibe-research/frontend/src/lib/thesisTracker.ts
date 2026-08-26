import { waitForVibeDeskConfig, type VibeDeskConfig } from "@/lib/vibedesk";

export type ThesisStatus = "draft" | "active" | "watch" | "invalidated" | "archived";
export type ThesisConviction = "high" | "medium" | "low";
export type ThesisImpact = "strengthened" | "weakened" | "neutral" | "invalidated";
export type ThesisTrend = "improving" | "stable" | "deteriorating" | "pending";
export type ThesisFreshness = "live" | "fresh" | "stale" | "unknown";

export interface ThesisPillar {
  id: string;
  title: string;
  expectation: string;
  currentStatus: string;
  trend: ThesisTrend;
  evidenceIds: string[];
}

export interface ThesisInvalidationRisk {
  id: string;
  statement: string;
  invalidationCondition: string;
  status: "monitoring" | "triggered" | "cleared";
  evidenceIds: string[];
}

export interface ThesisEvidence {
  id: string;
  source: { id: string; label: string; url?: string };
  summary: string;
  asOf: string;
  freshness: { status: ThesisFreshness; ageDays?: number };
  confidence: { level: ThesisConviction; score?: number; rationale: string };
  impact: ThesisImpact;
  pillarId?: string;
  createdAt: string;
}

export interface ThesisUpdate {
  id: string;
  date: string;
  dataPoint: string;
  impact: ThesisImpact;
  pillarId?: string;
  evidenceIds: string[];
  conviction: ThesisConviction;
  note?: string;
}

export interface InvestmentThesis {
  id: string;
  security: { market: string; symbol: string; name: string; exchange?: string };
  title: string;
  statement: string;
  status: ThesisStatus;
  conviction: ThesisConviction;
  pillars: ThesisPillar[];
  invalidationRisks: ThesisInvalidationRisk[];
  linkedCatalysts: Array<{ id: string; title: string; date?: string; status?: string }>;
  evidence: ThesisEvidence[];
  updates: ThesisUpdate[];
  valuation?: {
    method: string;
    referenceValue: number | null;
    currency: string;
    asOf?: string;
    assumptions: string[];
  };
  nextReviewAt: string;
  gaps: string[];
  createdAt: string;
  updatedAt: string;
}

export interface InvestmentThesisPortfolio {
  schemaVersion: "newma-desk.investment-thesis.v1";
  updatedAt: string;
  theses: InvestmentThesis[];
}

interface StorageDocument {
  revision: number;
  value: unknown;
}

const LOCAL_KEY = "newma-desk.thesis-tracker.v1";
const NAMESPACE = "thesis-tracker";
const DOCUMENT_KEY = "portfolio";

function now() {
  return new Date().toISOString();
}

export function emptyThesisPortfolio(): InvestmentThesisPortfolio {
  return {
    schemaVersion: "newma-desk.investment-thesis.v1",
    updatedAt: now(),
    theses: [],
  };
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function stringValue(value: unknown, fallback = "", limit = 8_000) {
  return typeof value === "string" ? value.slice(0, limit) : fallback;
}

function stringList(value: unknown, limit: number) {
  return Array.isArray(value)
    ? value.filter((item): item is string => typeof item === "string" && Boolean(item.trim())).slice(0, limit)
    : [];
}

function enumValue<T extends string>(value: unknown, choices: readonly T[], fallback: T): T {
  return typeof value === "string" && choices.includes(value as T) ? value as T : fallback;
}

function dateValue(value: unknown, fallback = new Date().toISOString().slice(0, 10)) {
  const candidate = stringValue(value, fallback, 10);
  return /^\d{4}-\d{2}-\d{2}$/.test(candidate) ? candidate : fallback;
}

function isoValue(value: unknown) {
  const candidate = stringValue(value, "", 64);
  return Number.isNaN(Date.parse(candidate)) ? now() : candidate;
}

function normalizePillar(value: unknown, index: number, thesisId: string): ThesisPillar {
  const row = isRecord(value) ? value : {};
  return {
    id: stringValue(row.id, `${thesisId}:pillar:${index + 1}`, 160),
    title: stringValue(row.title, "待补充支柱", 300),
    expectation: stringValue(row.expectation, "待补充原始预期", 2_000),
    currentStatus: stringValue(row.currentStatus, "等待证据更新", 2_000),
    trend: enumValue(row.trend, ["improving", "stable", "deteriorating", "pending"], "pending"),
    evidenceIds: stringList(row.evidenceIds, 100),
  };
}

function normalizeRisk(value: unknown, index: number, thesisId: string): ThesisInvalidationRisk {
  const row = isRecord(value) ? value : {};
  return {
    id: stringValue(row.id, `${thesisId}:risk:${index + 1}`, 160),
    statement: stringValue(row.statement, "待补充风险", 2_000),
    invalidationCondition: stringValue(row.invalidationCondition, "待补充可观察的证伪条件", 2_000),
    status: enumValue(row.status, ["monitoring", "triggered", "cleared"], "monitoring"),
    evidenceIds: stringList(row.evidenceIds, 100),
  };
}

function normalizeEvidence(value: unknown): ThesisEvidence | null {
  if (!isRecord(value) || !isRecord(value.source)) return null;
  const id = stringValue(value.id, "", 180);
  const summary = stringValue(value.summary, "", 4_000);
  const sourceLabel = stringValue(value.source.label, "", 300);
  if (!id || !summary || !sourceLabel) return null;
  const freshness = isRecord(value.freshness) ? value.freshness : {};
  const confidence = isRecord(value.confidence) ? value.confidence : {};
  const sourceUrl = stringValue(value.source.url, "", 2_000);
  const ageDays = typeof freshness.ageDays === "number" && freshness.ageDays >= 0
    ? Math.floor(freshness.ageDays)
    : undefined;
  const score = typeof confidence.score === "number" && confidence.score >= 0 && confidence.score <= 1
    ? confidence.score
    : undefined;
  const pillarId = stringValue(value.pillarId, "", 180);
  return {
    id,
    source: {
      id: stringValue(value.source.id, sourceLabel.toLowerCase().replace(/[^a-z0-9]+/g, "-") || "user", 180),
      label: sourceLabel,
      ...(sourceUrl ? { url: sourceUrl } : {}),
    },
    summary,
    asOf: stringValue(value.asOf, dateValue(undefined), 64),
    freshness: {
      status: enumValue(freshness.status, ["live", "fresh", "stale", "unknown"], "unknown"),
      ...(ageDays === undefined ? {} : { ageDays }),
    },
    confidence: {
      level: enumValue(confidence.level, ["high", "medium", "low"], "low"),
      ...(score === undefined ? {} : { score }),
      rationale: stringValue(confidence.rationale, "用户录入，需进一步交叉核验", 1_000),
    },
    impact: enumValue(value.impact, ["strengthened", "weakened", "neutral", "invalidated"], "neutral"),
    ...(pillarId ? { pillarId } : {}),
    createdAt: isoValue(value.createdAt),
  };
}

function normalizeUpdate(value: unknown): ThesisUpdate | null {
  if (!isRecord(value)) return null;
  const id = stringValue(value.id, "", 180);
  const dataPoint = stringValue(value.dataPoint, "", 4_000);
  if (!id || !dataPoint) return null;
  const pillarId = stringValue(value.pillarId, "", 180);
  const note = stringValue(value.note, "", 2_000);
  return {
    id,
    date: dateValue(value.date),
    dataPoint,
    impact: enumValue(value.impact, ["strengthened", "weakened", "neutral", "invalidated"], "neutral"),
    ...(pillarId ? { pillarId } : {}),
    evidenceIds: stringList(value.evidenceIds, 20),
    conviction: enumValue(value.conviction, ["high", "medium", "low"], "low"),
    ...(note ? { note } : {}),
  };
}

function normalizeThesis(value: unknown): InvestmentThesis | null {
  if (!isRecord(value) || !isRecord(value.security)) return null;
  const id = stringValue(value.id, "", 180);
  const symbol = stringValue(value.security.symbol, "", 80);
  const name = stringValue(value.security.name, "", 160);
  if (!id || !symbol || !name) return null;
  const rawPillars = Array.isArray(value.pillars) ? value.pillars.slice(0, 5) : [];
  const rawRisks = Array.isArray(value.invalidationRisks) ? value.invalidationRisks.slice(0, 5) : [];
  while (rawPillars.length < 3) rawPillars.push({});
  while (rawRisks.length < 3) rawRisks.push({});
  const valuation = isRecord(value.valuation) && stringValue(value.valuation.method)
    ? {
        method: stringValue(value.valuation.method, "", 300),
        referenceValue: typeof value.valuation.referenceValue === "number" ? value.valuation.referenceValue : null,
        currency: stringValue(value.valuation.currency, "CNY", 20),
        ...(stringValue(value.valuation.asOf) ? { asOf: dateValue(value.valuation.asOf) } : {}),
        assumptions: stringList(value.valuation.assumptions, 20),
      }
    : undefined;
  const exchange = stringValue(value.security.exchange, "", 40);
  const createdAt = isoValue(value.createdAt);
  return {
    id,
    security: {
      market: stringValue(value.security.market, "CN", 40),
      symbol,
      name,
      ...(exchange ? { exchange } : {}),
    },
    title: stringValue(value.title, `${name} 投资逻辑`, 300),
    statement: stringValue(value.statement, "待补充可证伪的核心论点", 4_000),
    status: enumValue(value.status, ["draft", "active", "watch", "invalidated", "archived"], "draft"),
    conviction: enumValue(value.conviction, ["high", "medium", "low"], "low"),
    pillars: rawPillars.map((item, index) => normalizePillar(item, index, id)),
    invalidationRisks: rawRisks.map((item, index) => normalizeRisk(item, index, id)),
    linkedCatalysts: (Array.isArray(value.linkedCatalysts) ? value.linkedCatalysts : [])
      .flatMap((item) => {
        if (!isRecord(item)) return [];
        const catalystId = stringValue(item.id, "", 180);
        if (!catalystId) return [];
        const catalystDate = stringValue(item.date, "", 10);
        const catalystStatus = stringValue(item.status, "", 80);
        return [{
          id: catalystId,
          title: stringValue(item.title, catalystId, 300),
          ...(catalystDate ? { date: dateValue(catalystDate) } : {}),
          ...(catalystStatus ? { status: catalystStatus } : {}),
        }];
      })
      .slice(0, 20),
    evidence: (Array.isArray(value.evidence) ? value.evidence : [])
      .map(normalizeEvidence)
      .filter((item): item is ThesisEvidence => item !== null)
      .slice(0, 100),
    updates: (Array.isArray(value.updates) ? value.updates : [])
      .map(normalizeUpdate)
      .filter((item): item is ThesisUpdate => item !== null)
      .slice(0, 100),
    ...(valuation ? { valuation } : {}),
    nextReviewAt: dateValue(value.nextReviewAt),
    gaps: stringList(value.gaps, 20),
    createdAt,
    updatedAt: isoValue(value.updatedAt || createdAt),
  };
}

function normalizePortfolio(value: unknown): InvestmentThesisPortfolio {
  if (!isRecord(value)) return emptyThesisPortfolio();
  return {
    schemaVersion: "newma-desk.investment-thesis.v1",
    updatedAt: isoValue(value.updatedAt),
    theses: (Array.isArray(value.theses) ? value.theses : [])
      .map(normalizeThesis)
      .filter((item): item is InvestmentThesis => item !== null)
      .slice(0, 100),
  };
}

export function loadLocalThesisPortfolio() {
  try {
    return normalizePortfolio(JSON.parse(localStorage.getItem(LOCAL_KEY) || "null"));
  } catch {
    return emptyThesisPortfolio();
  }
}

function canRead(config: VibeDeskConfig | null): config is VibeDeskConfig & {
  accessToken: string;
  instanceId: string;
  storageGateway: string;
} {
  return Boolean(
    config?.accessToken &&
    config.instanceId &&
    config.storageGateway &&
    config.permissions?.includes("storage.read"),
  );
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
  if (response.status === 404) {
    return { found: false, revision: 0, state: emptyThesisPortfolio() };
  }
  if (!response.ok) throw new Error(`thesis tracker read failed: ${response.status}`);
  const document = await response.json() as StorageDocument;
  return {
    found: true,
    revision: Number(document.revision) || 0,
    state: normalizePortfolio(document.value),
  };
}

export async function hydrateThesisPortfolio() {
  const local = loadLocalThesisPortfolio();
  const config = await waitForVibeDeskConfig();
  if (!canRead(config)) return local;
  try {
    const remote = await readRemote(config);
    return remote.found ? remote.state : local;
  } catch {
    return local;
  }
}

export async function persistThesisPortfolio(portfolio: InvestmentThesisPortfolio) {
  const normalized = normalizePortfolio(portfolio);
  try {
    localStorage.setItem(LOCAL_KEY, JSON.stringify(normalized));
  } catch {
    // The in-memory page remains usable when browser persistence is disabled.
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
      if (!response.ok) throw new Error(`thesis tracker write failed: ${response.status}`);
      return;
    } catch {
      return;
    }
  }
}
