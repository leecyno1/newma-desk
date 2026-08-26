import type { IdeaFunnelWorkspace, IdeaStage, ResearchIdea } from "@/lib/ideaFunnel";

export type CoverageModId = "idea-funnel" | "thesis-tracker" | "earnings-workbench" | "peer-comparison" | "valuation-workbench" | "research-memo";
export type CoverageStatus = "ready" | "due" | "stale" | "missing";

export interface CoverageModuleState {
  modId: CoverageModId;
  label: string;
  status: CoverageStatus;
  artifactCount: number;
  sourceCount: number;
  staleSourceCount: number;
  gapCount: number;
  latestAt?: string;
  nextReviewAt?: string;
}

export interface ResearchCoverageItem {
  id: string;
  security: { market: string; symbol: string; name: string };
  ideaId?: string;
  stage: IdeaStage | "untracked";
  latestAt?: string;
  nextReviewAt?: string;
  sourceCount: number;
  staleSourceCount: number;
  gapCount: number;
  pendingTaskCount: number;
  overdueTaskCount: number;
  modules: CoverageModuleState[];
  nextModId: CoverageModId;
  nextModLabel: string;
  attention: string[];
}

export interface ResearchCoverageSnapshot {
  asOf: string;
  items: ResearchCoverageItem[];
  totals: { securities: number; dueReviews: number; pendingTasks: number; overdueTasks: number; staleSources: number; coverageGaps: number };
}

type Row = Record<string, unknown>;
type StorageReader = (key: string) => string | null;
type Mutable = {
  security: ResearchCoverageItem["security"];
  idea?: ResearchIdea;
  latestAt?: string;
  nextReviewAt?: string;
  pendingTaskCount: number;
  overdueTaskCount: number;
  modules: Map<CoverageModId, CoverageModuleState>;
};

const MODS: Array<{ id: CoverageModId; label: string; key?: string; collection?: string }> = [
  { id: "idea-funnel", label: "机会池" },
  { id: "thesis-tracker", label: "投资逻辑", key: "newma-desk.thesis-tracker.v1", collection: "theses" },
  { id: "earnings-workbench", label: "财报", key: "newma-desk.earnings-workbench.v1", collection: "workbooks" },
  { id: "peer-comparison", label: "同业", key: "newma-desk.peer-comparison.v1", collection: "cases" },
  { id: "valuation-workbench", label: "估值", key: "newma-desk.valuation-workbench.v1", collection: "models" },
  { id: "research-memo", label: "备忘录", key: "newma-desk.research-memo.v1", collection: "memos" },
];

const isRow = (value: unknown): value is Row => Boolean(value) && typeof value === "object" && !Array.isArray(value);
const rows = (value: unknown) => Array.isArray(value) ? value.filter(isRow) : [];
const count = (value: unknown) => Array.isArray(value) ? value.length : 0;
const text = (value: unknown, fallback = "") => typeof value === "string" ? value.trim().slice(0, 240) : fallback;
const time = (value: unknown) => {
  const candidate = text(value);
  return candidate && !Number.isNaN(Date.parse(candidate)) ? candidate : undefined;
};
const pickTime = (left: string | undefined, right: string | undefined, latest: boolean) => {
  if (!left) return right;
  if (!right) return left;
  return (Date.parse(left) >= Date.parse(right)) === latest ? left : right;
};

function cachedRows(read: StorageReader, key: string, collection: string) {
  try {
    const value = JSON.parse(read(key) || "null");
    return isRow(value) ? rows(value[collection]) : [];
  } catch {
    return [];
  }
}

function securityOf(row: Row) {
  const raw = isRow(row.security) ? row.security : isRow(row.target) ? row.target : {};
  const symbol = text(raw.symbol).toUpperCase();
  return symbol ? { market: text(raw.market, "CN").toUpperCase(), symbol, name: text(raw.name, symbol) } : null;
}

function ensure(map: Map<string, Mutable>, security: Mutable["security"]) {
  const id = `${security.market}:${security.symbol}`;
  let item = map.get(id);
  if (!item) {
    item = { security, pendingTaskCount: 0, overdueTaskCount: 0, modules: new Map() };
    map.set(id, item);
  } else if (item.security.name === item.security.symbol) item.security.name = security.name;
  return item;
}

function sourceRows(row: Row, modId: CoverageModId) {
  return rows(modId === "thesis-tracker" ? row.evidence : modId === "research-memo" ? row.sources : row.sourceMaterials);
}

function sourceStatus(source: Row) {
  return text(isRow(source.freshness) ? source.freshness.status : source.status);
}

function gapCount(row: Row, modId: CoverageModId) {
  let gaps = count(row.gaps);
  if (modId === "valuation-workbench") gaps += rows(row.auditChecks).filter((check) => text(check.status) !== "pass").length;
  if (modId === "earnings-workbench" && text(isRow(row.verification) ? row.verification.status : "") !== "verified") gaps += 1;
  if (modId === "research-memo" && text(row.status, "draft") === "draft") gaps += 1;
  return gaps;
}

function addIdea(map: Map<string, Mutable>, idea: ResearchIdea, today: string) {
  if (!idea.security.symbol) return;
  const item = ensure(map, { market: idea.security.market.toUpperCase(), symbol: idea.security.symbol.toUpperCase(), name: idea.security.name || idea.security.symbol });
  const pending = idea.nextActions.filter((action) => action.status === "pending");
  const stale = idea.sources.filter((source) => source.status === "stale" || source.status === "unavailable").length;
  item.idea = idea;
  item.latestAt = pickTime(item.latestAt, time(idea.updatedAt), true);
  item.pendingTaskCount += pending.length;
  item.overdueTaskCount += pending.filter((action) => action.dueAt && action.dueAt <= today).length;
  item.modules.set("idea-funnel", { modId: "idea-funnel", label: "机会池", status: stale ? "stale" : "ready", artifactCount: 1, sourceCount: idea.sources.length, staleSourceCount: stale, gapCount: idea.gaps.length, latestAt: idea.updatedAt });
}

function addArtifact(map: Map<string, Mutable>, row: Row, mod: typeof MODS[number]) {
  const security = securityOf(row);
  if (!security) return;
  const item = ensure(map, security);
  const sources = sourceRows(row, mod.id);
  const stale = sources.filter((source) => ["stale", "unavailable"].includes(sourceStatus(source))).length;
  const updatedAt = time(row.updatedAt);
  const nextReviewAt = text(row.nextReviewAt) || undefined;
  const current = item.modules.get(mod.id);
  item.latestAt = pickTime(item.latestAt, updatedAt, true);
  item.nextReviewAt = pickTime(item.nextReviewAt, nextReviewAt, false);
  item.modules.set(mod.id, {
    modId: mod.id, label: mod.label, status: "ready",
    artifactCount: (current?.artifactCount || 0) + 1,
    sourceCount: (current?.sourceCount || 0) + sources.length,
    staleSourceCount: (current?.staleSourceCount || 0) + stale,
    gapCount: (current?.gapCount || 0) + gapCount(row, mod.id),
    latestAt: pickTime(current?.latestAt, updatedAt, true),
    nextReviewAt: pickTime(current?.nextReviewAt, nextReviewAt, false),
  });
}

function emptyModule(mod: typeof MODS[number]): CoverageModuleState {
  return { modId: mod.id, label: mod.label, status: "missing", artifactCount: 0, sourceCount: 0, staleSourceCount: 0, gapCount: 0 };
}

export function buildResearchCoverageSnapshot(workspace: IdeaFunnelWorkspace, read: StorageReader = (key) => globalThis.localStorage?.getItem(key) ?? null, now = new Date()): ResearchCoverageSnapshot {
  const today = now.toISOString().slice(0, 10);
  const map = new Map<string, Mutable>();
  workspace.ideas.forEach((idea) => addIdea(map, idea, today));
  MODS.filter((mod) => mod.key && mod.collection).forEach((mod) => cachedRows(read, mod.key!, mod.collection!).forEach((row) => addArtifact(map, row, mod)));

  const items = [...map.entries()].map(([id, item]): ResearchCoverageItem => {
    const modules = MODS.map((mod) => {
      const value = item.modules.get(mod.id) || emptyModule(mod);
      return value.status === "missing" ? value : { ...value, status: value.nextReviewAt && value.nextReviewAt <= today ? "due" as const : value.staleSourceCount ? "stale" as const : "ready" as const };
    });
    const missing = modules.filter((module) => module.status === "missing");
    const due = modules.filter((module) => module.status === "due");
    const handoff = item.idea?.handoff;
    const target = handoff?.status === "ready" && handoff.targetModId !== "other" ? handoff.targetModId : undefined;
    const next = due[0] || (target ? modules.find((module) => module.modId === target) : undefined) || missing[0] || modules.find((module) => module.status === "stale" || module.gapCount) || modules[modules.length - 1]!;
    const attention = [
      !item.idea ? "尚未回链研究机会池" : "",
      item.overdueTaskCount ? `${item.overdueTaskCount} 项研究任务逾期` : "",
      due.length ? `${due.length} 个档案已到复核日` : "",
      missing.length ? `${missing.length} 个研究环节尚未覆盖` : "",
    ].filter(Boolean).slice(0, 4);
    return {
      id, security: item.security, ...(item.idea ? { ideaId: item.idea.id } : {}), stage: item.idea?.stage || "untracked",
      latestAt: item.latestAt, nextReviewAt: item.nextReviewAt,
      sourceCount: modules.reduce((sum, module) => sum + module.sourceCount, 0),
      staleSourceCount: modules.reduce((sum, module) => sum + module.staleSourceCount, 0),
      gapCount: modules.reduce((sum, module) => sum + module.gapCount, 0),
      pendingTaskCount: item.pendingTaskCount, overdueTaskCount: item.overdueTaskCount,
      modules, nextModId: next.modId, nextModLabel: next.label, attention,
    };
  }).sort((left, right) => (right.overdueTaskCount - left.overdueTaskCount) || (right.modules.filter((module) => module.status === "due").length - left.modules.filter((module) => module.status === "due").length) || (right.gapCount - left.gapCount));

  return { asOf: now.toISOString(), items, totals: {
    securities: items.length,
    dueReviews: items.reduce((sum, item) => sum + item.modules.filter((module) => module.status === "due").length, 0),
    pendingTasks: items.reduce((sum, item) => sum + item.pendingTaskCount, 0),
    overdueTasks: items.reduce((sum, item) => sum + item.overdueTaskCount, 0),
    staleSources: items.reduce((sum, item) => sum + item.staleSourceCount, 0),
    coverageGaps: items.reduce((sum, item) => sum + item.modules.filter((module) => module.status === "missing").length, 0),
  } };
}
