import { waitForVibeDeskConfig, type VibeDeskConfig } from "@/lib/vibedesk";

export type IdeaStage = "inbox" | "triage" | "shortlist" | "deep-dive" | "handoff" | "deferred" | "closed";
export type IdeaPriority = "high" | "medium" | "low";
export type IdeaResearchStyle = "value" | "growth" | "quality" | "event" | "special-situation" | "risk" | "other";

export interface IdeaArtifactReference {
  id: string;
  sourceModId: string;
  artifactId: string;
  title: string;
  asOf?: string;
  status: "linked" | "stale" | "missing";
}

export interface IdeaSource {
  id: string;
  label: string;
  kind: "market" | "filing" | "company" | "consensus" | "research" | "news" | "derived" | "user";
  asOf: string;
  status: "verified" | "available" | "stale" | "unavailable";
  url?: string;
}

export interface ResearchIdea {
  id: string;
  title: string;
  security: { market: string; symbol: string; name: string; currency: string };
  stage: IdeaStage;
  priority: IdeaPriority;
  researchStyle: IdeaResearchStyle;
  origin: {
    type: "screener" | "theme" | "news" | "catalyst" | "industry" | "watchlist" | "agent" | "manual";
    label: string;
    sourceModId?: string;
    artifactId?: string;
    asOf: string;
    discoveredAt: string;
  };
  searchCriteria: {
    markets: string[];
    sectors: string[];
    styles: IdeaResearchStyle[];
    themes: string[];
    marketCapRange: string;
    rules: Array<{ id: string; metric: string; operator: "gt" | "gte" | "lt" | "lte" | "eq" | "between" | "trend"; value: string; rationale: string }>;
  };
  researchQuestion: string;
  initialHypothesis: string;
  opposingHypothesis: string;
  whyNow: string;
  marketMayMiss: string;
  metrics: Array<{ id: string; label: string; value: string; peerReference: string; asOf: string; sourceIds: string[] }>;
  signals: Array<{ id: string; type: "quantitative" | "thematic" | "quality" | "catalyst" | "risk" | "pattern"; direction: "supports" | "challenges" | "neutral"; summary: string; sourceIds: string[] }>;
  scorecard: { relevance: number; evidenceQuality: number; novelty: number; catalystClarity: number; falsifiability: number; researchEffort: number; total: number };
  catalysts: Array<{ id: string; title: string; window: string; confirmationCondition: string; invalidationCondition: string; sourceIds: string[] }>;
  risks: Array<{ id: string; statement: string; earlyWarning: string; falsificationCondition: string; sourceIds: string[] }>;
  linkedArtifacts: IdeaArtifactReference[];
  sources: IdeaSource[];
  gaps: string[];
  nextActions: Array<{ id: string; kind: "data-check" | "filing" | "model" | "peer" | "industry" | "catalyst" | "expert" | "other"; label: string; status: "pending" | "done" | "skipped"; dueAt?: string; completionStandard: string }>;
  handoff: { targetModId: "thesis-tracker" | "earnings-workbench" | "peer-comparison" | "valuation-workbench" | "research-memo" | "other"; status: "none" | "ready" | "created"; artifactId?: string; note: string };
  reviewLog: Array<{ id: string; createdAt: string; stage: IdeaStage; summary: string }>;
  createdAt: string;
  updatedAt: string;
}

export interface IdeaFunnelWorkspace {
  schemaVersion: "newma-desk.idea-funnel.v1";
  updatedAt: string;
  ideas: ResearchIdea[];
}

export interface WatchlistCandidate {
  market: string;
  symbol: string;
  name: string;
  currency: string;
  groupName: string;
}

interface StorageDocument { revision: number; value: unknown }
const LOCAL_KEY = "newma-desk.idea-funnel.v1";
const NAMESPACE = "idea-funnel";
const DOCUMENT_KEY = "pipeline";

function now() { return new Date().toISOString(); }
function today() { return now().slice(0, 10); }
export function createIdeaId(prefix: string) {
  return `${prefix}:${globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(16).slice(2)}`}`;
}
function textList(value: string) { return value.split(/[，,\n]/).map((item) => item.trim()).filter(Boolean); }
export { textList as splitIdeaList };

export function calculateIdeaScore(scorecard: ResearchIdea["scorecard"]) {
  const total = (
    scorecard.relevance + scorecard.evidenceQuality + scorecard.novelty +
    scorecard.catalystClarity + scorecard.falsifiability + (100 - scorecard.researchEffort)
  ) / 6;
  return Math.round(Math.max(0, Math.min(100, total)));
}

export function blankResearchIdea(): ResearchIdea {
  const timestamp = now();
  const scorecard = { relevance: 50, evidenceQuality: 40, novelty: 50, catalystClarity: 40, falsifiability: 50, researchEffort: 50, total: 47 };
  return {
    id: createIdeaId("idea"),
    title: "",
    security: { market: "CN", symbol: "", name: "", currency: "CNY" },
    stage: "inbox",
    priority: "medium",
    researchStyle: "other",
    origin: { type: "manual", label: "手工录入", asOf: today(), discoveredAt: timestamp },
    searchCriteria: {
      markets: ["CN"], sectors: [], styles: [], themes: [], marketCapRange: "不限",
      rules: [{ id: createIdeaId("rule"), metric: "关键筛选指标", operator: "trend", value: "待定义", rationale: "记录候选进入机会池的可复核条件" }],
    },
    researchQuestion: "",
    initialHypothesis: "",
    opposingHypothesis: "",
    whyNow: "",
    marketMayMiss: "",
    metrics: [],
    signals: [
      { id: createIdeaId("signal"), type: "thematic", direction: "supports", summary: "待补充支持候选的证据", sourceIds: [] },
      { id: createIdeaId("signal"), type: "risk", direction: "challenges", summary: "待补充挑战候选的反方证据", sourceIds: [] },
    ],
    scorecard,
    catalysts: [],
    risks: [{ id: createIdeaId("risk"), statement: "待补充关键风险", earlyWarning: "待补充领先预警", falsificationCondition: "待补充证伪条件", sourceIds: [] }],
    linkedArtifacts: [],
    sources: [],
    gaps: ["补齐原始来源、量化筛选结果和反方证据"],
    nextActions: [{ id: createIdeaId("action"), kind: "data-check", label: "核验候选的基础事实与来源", status: "pending", completionStandard: "关键数据具备来源、截至日期和口径" }],
    handoff: { targetModId: "thesis-tracker", status: "none", note: "通过初筛后交接到投资逻辑或其他深度研究 Mod" },
    reviewLog: [{ id: createIdeaId("review"), createdAt: timestamp, stage: "inbox", summary: "进入研究机会池" }],
    createdAt: timestamp,
    updatedAt: timestamp,
  };
}

export function emptyIdeaFunnelWorkspace(): IdeaFunnelWorkspace {
  return { schemaVersion: "newma-desk.idea-funnel.v1", updatedAt: now(), ideas: [] };
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}
function text(value: unknown, fallback = "", limit = 8_000) { return typeof value === "string" ? value.slice(0, limit) : fallback; }
function strings(value: unknown, limit = 30) { return Array.isArray(value) ? value.filter((item): item is string => typeof item === "string" && Boolean(item.trim())).slice(0, limit) : []; }
function enumValue<T extends string>(value: unknown, allowed: readonly T[], fallback: T) { return allowed.includes(value as T) ? value as T : fallback; }
function numberValue(value: unknown, fallback: number) { return typeof value === "number" && Number.isFinite(value) ? Math.max(0, Math.min(100, value)) : fallback; }

function normalizeIdea(value: unknown): ResearchIdea | null {
  if (!isRecord(value)) return null;
  const fallback = blankResearchIdea();
  const security = isRecord(value.security) ? value.security : {};
  const title = text(value.title, "", 240);
  const symbol = text(security.symbol, "", 40);
  const name = text(security.name, "", 120);
  if (!title || !symbol || !name) return null;
  const origin = isRecord(value.origin) ? value.origin : {};
  const criteria = isRecord(value.searchCriteria) ? value.searchCriteria : {};
  const rawScore = isRecord(value.scorecard) ? value.scorecard : {};
  const scorecard = {
    relevance: numberValue(rawScore.relevance, 50), evidenceQuality: numberValue(rawScore.evidenceQuality, 40),
    novelty: numberValue(rawScore.novelty, 50), catalystClarity: numberValue(rawScore.catalystClarity, 40),
    falsifiability: numberValue(rawScore.falsifiability, 50), researchEffort: numberValue(rawScore.researchEffort, 50), total: 0,
  };
  scorecard.total = calculateIdeaScore(scorecard);
  const normalizeRows = (raw: unknown, minimum: number, defaults: Record<string, unknown>[]) => {
    const rows = Array.isArray(raw) ? raw.filter(isRecord) : [];
    return rows.length >= minimum ? rows : defaults;
  };
  const signals = normalizeRows(value.signals, 2, fallback.signals).slice(0, 30).map((row) => ({
    id: text(row.id, createIdeaId("signal"), 160),
    type: enumValue(row.type, ["quantitative", "thematic", "quality", "catalyst", "risk", "pattern"] as const, "pattern"),
    direction: enumValue(row.direction, ["supports", "challenges", "neutral"] as const, "neutral"),
    summary: text(row.summary, "待补充"), sourceIds: strings(row.sourceIds, 20),
  }));
  const risks = normalizeRows(value.risks, 1, fallback.risks).slice(0, 20).map((row) => ({
    id: text(row.id, createIdeaId("risk"), 160), statement: text(row.statement, "待补充"),
    earlyWarning: text(row.earlyWarning, "待补充"), falsificationCondition: text(row.falsificationCondition, "待补充"),
    sourceIds: strings(row.sourceIds, 20),
  }));
  const actions = normalizeRows(value.nextActions, 1, fallback.nextActions).slice(0, 30).map((row) => ({
    id: text(row.id, createIdeaId("action"), 160),
    kind: enumValue(row.kind, ["data-check", "filing", "model", "peer", "industry", "catalyst", "expert", "other"] as const, "other"),
    label: text(row.label, "待补充"), status: enumValue(row.status, ["pending", "done", "skipped"] as const, "pending"),
    ...(typeof row.dueAt === "string" ? { dueAt: row.dueAt.slice(0, 10) } : {}),
    completionStandard: text(row.completionStandard, "待补充"),
  }));
  const handoff = isRecord(value.handoff) ? value.handoff : {};
  const createdAt = text(value.createdAt, now(), 64);
  return {
    ...fallback,
    id: text(value.id, createIdeaId("idea"), 160), title,
    security: { market: text(security.market, "CN", 20), symbol, name, currency: text(security.currency, "CNY", 20) },
    stage: enumValue(value.stage, ["inbox", "triage", "shortlist", "deep-dive", "handoff", "deferred", "closed"] as const, "inbox"),
    priority: enumValue(value.priority, ["high", "medium", "low"] as const, "medium"),
    researchStyle: enumValue(value.researchStyle, ["value", "growth", "quality", "event", "special-situation", "risk", "other"] as const, "other"),
    origin: {
      type: enumValue(origin.type, ["screener", "theme", "news", "catalyst", "industry", "watchlist", "agent", "manual"] as const, "manual"),
      label: text(origin.label, "手工录入", 240),
      ...(typeof origin.sourceModId === "string" ? { sourceModId: origin.sourceModId.slice(0, 120) } : {}),
      ...(typeof origin.artifactId === "string" ? { artifactId: origin.artifactId.slice(0, 200) } : {}),
      asOf: text(origin.asOf, today(), 80), discoveredAt: text(origin.discoveredAt, createdAt, 64),
    },
    searchCriteria: {
      markets: strings(criteria.markets, 20), sectors: strings(criteria.sectors, 30),
      styles: (Array.isArray(criteria.styles) ? criteria.styles : []).filter((item): item is IdeaResearchStyle => ["value", "growth", "quality", "event", "special-situation", "risk", "other"].includes(String(item))).slice(0, 10),
      themes: strings(criteria.themes, 30), marketCapRange: text(criteria.marketCapRange, "不限", 120),
      rules: (Array.isArray(criteria.rules) ? criteria.rules : fallback.searchCriteria.rules).filter(isRecord).slice(0, 30).map((row) => ({
        id: text(row.id, createIdeaId("rule"), 160), metric: text(row.metric, "待补充", 240),
        operator: enumValue(row.operator, ["gt", "gte", "lt", "lte", "eq", "between", "trend"] as const, "trend"),
        value: text(row.value, "待补充", 120), rationale: text(row.rationale, "待补充"),
      })),
    },
    researchQuestion: text(value.researchQuestion), initialHypothesis: text(value.initialHypothesis),
    opposingHypothesis: text(value.opposingHypothesis), whyNow: text(value.whyNow), marketMayMiss: text(value.marketMayMiss),
    metrics: (Array.isArray(value.metrics) ? value.metrics : []).filter(isRecord).slice(0, 30).map((row) => ({
      id: text(row.id, createIdeaId("metric"), 160), label: text(row.label, "待补充", 240), value: text(row.value, "待核验", 240),
      peerReference: text(row.peerReference, "", 240), asOf: text(row.asOf, "待核验", 80), sourceIds: strings(row.sourceIds, 20),
    })),
    signals, scorecard,
    catalysts: (Array.isArray(value.catalysts) ? value.catalysts : []).filter(isRecord).slice(0, 20).map((row) => ({
      id: text(row.id, createIdeaId("catalyst"), 160), title: text(row.title, "待补充", 240), window: text(row.window, "待确认", 120),
      confirmationCondition: text(row.confirmationCondition, "待补充"), invalidationCondition: text(row.invalidationCondition, "待补充"), sourceIds: strings(row.sourceIds, 20),
    })),
    risks,
    linkedArtifacts: (Array.isArray(value.linkedArtifacts) ? value.linkedArtifacts : []).filter(isRecord).slice(0, 40).map((row) => ({
      id: text(row.id, createIdeaId("artifact"), 160), sourceModId: text(row.sourceModId, "research-notes", 120),
      artifactId: text(row.artifactId, createIdeaId("manual"), 200), title: text(row.title, "待命名档案", 240),
      ...(typeof row.asOf === "string" ? { asOf: row.asOf.slice(0, 80) } : {}),
      status: enumValue(row.status, ["linked", "stale", "missing"] as const, "linked"),
    })),
    sources: (Array.isArray(value.sources) ? value.sources : []).filter(isRecord).slice(0, 100).map((row) => ({
      id: text(row.id, createIdeaId("source"), 160), label: text(row.label, "待命名来源", 240),
      kind: enumValue(row.kind, ["market", "filing", "company", "consensus", "research", "news", "derived", "user"] as const, "user"),
      asOf: text(row.asOf, "待核验", 80), status: enumValue(row.status, ["verified", "available", "stale", "unavailable"] as const, "available"),
      ...(typeof row.url === "string" ? { url: row.url.slice(0, 2_000) } : {}),
    })),
    gaps: strings(value.gaps, 30), nextActions: actions,
    handoff: {
      targetModId: enumValue(handoff.targetModId, ["thesis-tracker", "earnings-workbench", "peer-comparison", "valuation-workbench", "research-memo", "other"] as const, "thesis-tracker"),
      status: enumValue(handoff.status, ["none", "ready", "created"] as const, "none"),
      ...(typeof handoff.artifactId === "string" ? { artifactId: handoff.artifactId.slice(0, 200) } : {}),
      note: text(handoff.note, "", 2_000),
    },
    reviewLog: (Array.isArray(value.reviewLog) ? value.reviewLog : fallback.reviewLog).filter(isRecord).slice(0, 100).map((row) => ({
      id: text(row.id, createIdeaId("review"), 160), createdAt: text(row.createdAt, createdAt, 64),
      stage: enumValue(row.stage, ["inbox", "triage", "shortlist", "deep-dive", "handoff", "deferred", "closed"] as const, "inbox"),
      summary: text(row.summary, "更新研究候选", 1_000),
    })),
    createdAt, updatedAt: text(value.updatedAt, createdAt, 64),
  };
}

function normalizeWorkspace(value: unknown): IdeaFunnelWorkspace {
  if (!isRecord(value)) return emptyIdeaFunnelWorkspace();
  return {
    schemaVersion: "newma-desk.idea-funnel.v1",
    updatedAt: text(value.updatedAt, now(), 64),
    ideas: (Array.isArray(value.ideas) ? value.ideas : []).map(normalizeIdea).filter((item): item is ResearchIdea => item !== null).slice(0, 300),
  };
}

export function loadLocalIdeaFunnelWorkspace() {
  try { return normalizeWorkspace(JSON.parse(localStorage.getItem(LOCAL_KEY) || "null")); }
  catch { return emptyIdeaFunnelWorkspace(); }
}

function canRead(config: VibeDeskConfig | null): config is VibeDeskConfig & { accessToken: string; instanceId: string; storageGateway: string } {
  return Boolean(config?.accessToken && config.instanceId && config.storageGateway && config.permissions?.includes("storage.read"));
}
function canWrite(config: VibeDeskConfig | null): config is VibeDeskConfig & { accessToken: string; instanceId: string; storageGateway: string } {
  return canRead(config) && Boolean(config.permissions?.includes("storage.write"));
}
function endpoint(config: VibeDeskConfig) { return `${config.storageGateway}/${NAMESPACE}/${DOCUMENT_KEY}`; }
function headers(config: VibeDeskConfig, json = false) { return { Authorization: `Bearer ${config.accessToken}`, "X-Newma-Desk-Instance-Id": config.instanceId || "", ...(json ? { "Content-Type": "application/json" } : {}) }; }
async function readRemote(config: VibeDeskConfig) {
  const response = await fetch(endpoint(config), { headers: headers(config) });
  if (response.status === 404) return { found: false, revision: 0, state: emptyIdeaFunnelWorkspace() };
  if (!response.ok) throw new Error(`idea funnel read failed: ${response.status}`);
  const document = await response.json() as StorageDocument;
  return { found: true, revision: Number(document.revision) || 0, state: normalizeWorkspace(document.value) };
}
export async function hydrateIdeaFunnelWorkspace() {
  const local = loadLocalIdeaFunnelWorkspace();
  const config = await waitForVibeDeskConfig();
  if (!canRead(config)) return local;
  try { const remote = await readRemote(config); return remote.found ? remote.state : local; } catch { return local; }
}
export async function persistIdeaFunnelWorkspace(workspace: IdeaFunnelWorkspace) {
  const normalized = normalizeWorkspace(workspace);
  try { localStorage.setItem(LOCAL_KEY, JSON.stringify(normalized)); } catch { /* persistence is optional outside Desk */ }
  const config = await waitForVibeDeskConfig();
  if (!canWrite(config)) return;
  for (let attempt = 0; attempt < 2; attempt += 1) {
    try {
      const current = await readRemote(config);
      const response = await fetch(endpoint(config), { method: "PUT", headers: headers(config, true), body: JSON.stringify({ expectedRevision: current.revision, value: normalized }) });
      if (response.status === 409 && attempt === 0) continue;
      if (!response.ok) throw new Error(`idea funnel write failed: ${response.status}`);
      return;
    } catch { return; }
  }
}

export function discoverWatchlistCandidates(): WatchlistCandidate[] {
  try {
    const groups = JSON.parse(localStorage.getItem("vibedesk.research.watch-groups.v1") || "[]");
    if (!Array.isArray(groups)) return [];
    const seen = new Set<string>();
    return groups.flatMap((group) => {
      if (!isRecord(group) || !Array.isArray(group.symbols)) return [];
      const groupName = text(group.name, "自选股", 120);
      return group.symbols.flatMap((security) => {
        if (!isRecord(security)) return [];
        const market = text(security.market, "CN", 20).toUpperCase();
        const symbol = text(security.symbol, "", 40).toUpperCase();
        if (!symbol || seen.has(`${market}:${symbol}`)) return [];
        seen.add(`${market}:${symbol}`);
        return [{ market, symbol, name: text(security.name, symbol, 120), currency: text(security.currency, market === "US" ? "USD" : market === "HK" ? "HKD" : "CNY", 20), groupName }];
      });
    }).slice(0, 100);
  } catch { return []; }
}
