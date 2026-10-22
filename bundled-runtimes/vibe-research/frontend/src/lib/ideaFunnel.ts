import { createModStorageClient, GatewayError } from '@newma-desk/mod-sdk';
import { getVibeDeskConfig, isVibeDeskEmbedded, waitForVibeDeskConfig, type VibeDeskConfig } from "@/lib/vibedesk";

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

export interface IdeaFunnelSession {
  workspace: IdeaFunnelWorkspace; scope: string; mode: 'local' | 'desk'; revision: number;
  localVersion?: string | null; writable: boolean;
}
export class IdeaStorageError extends Error {}
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
    nextActions: [{ id: createIdeaId("action"), kind: "data-check", label: "待补充研究任务", status: "pending", completionStandard: "待补充完成标准" }],
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
  const normalizeRows = (raw: unknown) => Array.isArray(raw) ? raw.filter(isRecord) : [];
  const signals = normalizeRows(value.signals).slice(0, 30).map((row) => ({
    id: text(row.id, createIdeaId("signal"), 160),
    type: enumValue(row.type, ["quantitative", "thematic", "quality", "catalyst", "risk", "pattern"] as const, "pattern"),
    direction: enumValue(row.direction, ["supports", "challenges", "neutral"] as const, "neutral"),
    summary: text(row.summary, "待补充"), sourceIds: strings(row.sourceIds, 20),
  }));
  const risks = normalizeRows(value.risks).slice(0, 20).map((row) => ({
    id: text(row.id, createIdeaId("risk"), 160), statement: text(row.statement, "待补充"),
    earlyWarning: text(row.earlyWarning, "待补充"), falsificationCondition: text(row.falsificationCondition, "待补充"),
    sourceIds: strings(row.sourceIds, 20),
  }));
  const actions = normalizeRows(value.nextActions).slice(0, 30).map((row) => ({
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

export function ideaFunnelScope(config = getVibeDeskConfig()) {
  return config ? JSON.stringify([config.apiOrigin, config.moduleId, config.userId, config.workspaceId, config.instanceId,
    config.accessToken, config.permissions?.includes('storage.read'), config.permissions?.includes('storage.write')])
    : isVibeDeskEmbedded || import.meta.env.VITE_NEWMA_DESK_INTEGRATED === '1' ? 'unconnected' : 'local';
}
function assertScope(scope: string, signal?: AbortSignal) {
  signal?.throwIfAborted();
  if (scope !== ideaFunnelScope()) throw new IdeaStorageError('工作区或授权已变化，旧结果未采用，请重新读取。');
}
function checkedWorkspace(value: unknown) {
  if (!isRecord(value) || value.schemaVersion !== 'newma-desk.idea-funnel.v1' || !Array.isArray(value.ideas) || value.ideas.length > 300) {
    throw new IdeaStorageError('机会池档案格式异常，未按空库处理，也未覆盖原记录。');
  }
  const normalized = normalizeWorkspace(value);
  const collections = ['signals', 'risks', 'nextActions', 'metrics', 'catalysts', 'linkedArtifacts', 'sources', 'reviewLog'] as const;
  if (normalized.ideas.length !== value.ideas.length || new Set(normalized.ideas.map(idea => idea.id)).size !== normalized.ideas.length
    || value.ideas.some((idea, index) => !isRecord(idea) || typeof idea.id !== 'string' || !idea.id
      || collections.some(key => !Array.isArray(idea[key]) || idea[key].length !== normalized.ideas[index]?.[key].length)
      || !isRecord(idea.scorecard) || ['relevance', 'evidenceQuality', 'novelty', 'catalystClarity', 'falsifiability', 'researchEffort'].some(key => {
        const score = (idea.scorecard as Record<string, unknown>)[key];
        return typeof score !== 'number' || !Number.isFinite(score) || score < 0 || score > 100;
      }))) {
    throw new IdeaStorageError('机会池公司、评分或证据记录不完整，未丢弃条目，请核对原档案。');
  }
  return normalized;
}
function checkedDocument(value: unknown, minimum = 1) {
  if (!isRecord(value) || !Number.isInteger(value.revision) || Number(value.revision) < minimum) throw new IdeaStorageError('保存回执或修订号异常，请保留草稿并重新读取。');
  return { workspace: checkedWorkspace(value.value), revision: value.revision as number };
}
function canRead(config: VibeDeskConfig | null): config is VibeDeskConfig & { accessToken: string; instanceId: string } {
  return Boolean(config?.moduleId === 'idea-funnel' && config.userId && config.workspaceId && config.accessToken && config.instanceId && config.storageGateway && config.permissions?.includes('storage.read'));
}
function client(config: VibeDeskConfig & { accessToken: string; instanceId: string }, signal?: AbortSignal) {
  const cancel = signal ? AbortSignal.any([signal, AbortSignal.timeout(15_000)]) : AbortSignal.timeout(15_000);
  return createModStorageClient({ baseUrl: config.apiOrigin, modId: 'idea-funnel', accessToken: config.accessToken, instanceId: config.instanceId,
    fetch: (url, init) => { cancel.throwIfAborted(); return fetch(url, { ...init, signal: cancel, cache: 'no-store' }); },
  });
}
export async function hydrateIdeaFunnelWorkspace(signal?: AbortSignal): Promise<IdeaFunnelSession> {
  const scope = ideaFunnelScope(); const config = await waitForVibeDeskConfig(); assertScope(scope, signal);
  if (scope === 'local' && !config) {
    try { const raw = localStorage.getItem(LOCAL_KEY);
      return { workspace: raw === null ? emptyIdeaFunnelWorkspace() : checkedWorkspace(JSON.parse(raw)), scope, mode: 'local', revision: 0, localVersion: raw, writable: true };
    } catch (error) { if (error instanceof IdeaStorageError) throw error; throw new IdeaStorageError('本机机会池读取失败，未按空库处理。'); }
  }
  if (!canRead(config)) throw new IdeaStorageError('尚未获得机会池读取授权，不使用本机旧缓存替代。');
  try { const document = await client(config, signal).get(NAMESPACE, DOCUMENT_KEY); assertScope(scope, signal);
    return { ...checkedDocument(document), scope, mode: 'desk', writable: config.permissions?.includes('storage.write') === true };
  } catch (error) {
    assertScope(scope, signal);
    if (error instanceof GatewayError && error.status === 404) return { workspace: emptyIdeaFunnelWorkspace(), scope, mode: 'desk', revision: 0, writable: config.permissions?.includes('storage.write') === true };
    if (error instanceof IdeaStorageError) throw error;
    throw new IdeaStorageError('Desk 机会池读取失败，未使用本机旧缓存替代。');
  }
}
export async function persistIdeaFunnelWorkspace(workspace: IdeaFunnelWorkspace, session: IdeaFunnelSession, signal?: AbortSignal): Promise<IdeaFunnelSession> {
  assertScope(session.scope, signal); const normalized = checkedWorkspace(workspace);
  if (session.mode === 'local') {
    try {
      if (localStorage.getItem(LOCAL_KEY) !== session.localVersion) throw new IdeaStorageError('保存冲突：其他窗口已更新本机机会池，请导出草稿后重新读取。');
      const raw = JSON.stringify(normalized); localStorage.setItem(LOCAL_KEY, raw);
      if (localStorage.getItem(LOCAL_KEY) !== raw) throw new IdeaStorageError('本机保存未确认，请保留草稿并重新读取。');
      return { ...session, workspace: normalized, localVersion: raw };
    } catch (error) { if (error instanceof IdeaStorageError) throw error; throw new IdeaStorageError('本机保存失败，请在关闭前导出草稿。'); }
  }
  const config = getVibeDeskConfig();
  if (!session.writable || !canRead(config) || !config.permissions?.includes('storage.write')) throw new IdeaStorageError('当前没有机会池保存权限。');
  try { const document = await client(config, signal).put(NAMESPACE, DOCUMENT_KEY, normalized, session.revision); assertScope(session.scope, signal);
    return { ...session, ...checkedDocument(document, session.revision + 1) };
  } catch (error) {
    assertScope(session.scope, signal);
    if (error instanceof GatewayError && error.status === 409) throw new IdeaStorageError('保存冲突：其他窗口已更新。草稿保留，未覆盖新版；请导出后重新读取。');
    if (error instanceof IdeaStorageError) throw error;
    throw new IdeaStorageError('Desk 保存未确认，可能已写入；草稿保留，请重新读取核对，勿重复提交。');
  }
}

export function discoverWatchlistCandidates(): WatchlistCandidate[] {
  if (ideaFunnelScope() !== 'local') throw new Error('Desk 自选候选共享尚未接通，不读取本机旧账户缓存；请从自选股页面选择证券。');
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
