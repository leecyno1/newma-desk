import type { MyReport } from "@/lib/api";
import { loadNotes } from "@/lib/notes";
import { getVibeDeskConfig, isVibeDeskEmbedded, waitForVibeDeskConfig, type VibeDeskConfig } from "@/lib/vibedesk";

export type ResearchArchiveKind =
  | "uploaded-report"
  | "research-record"
  | "thesis"
  | "earnings"
  | "peer-comparison"
  | "valuation"
  | "research-memo";

export type ResearchArchiveStatus =
  | "active"
  | "draft"
  | "archived"
  | "invalidated"
  | "stale"
  | "unknown";

export interface ResearchArchiveEntry {
  id: string;
  kind: ResearchArchiveKind;
  sourceModId: string;
  artifactId: string;
  title: string;
  status: ResearchArchiveStatus;
  security?: { market: string; symbol: string; name: string };
  asOf?: string;
  updatedAt: string;
  tags: string[];
  sourceRevision?: number;
}

export interface ResearchArchiveIndex {
  schemaVersion: "newma-desk.research-archive.v1";
  userId: string;
  workspaceId: string;
  generatedAt: string;
  entries: ResearchArchiveEntry[];
  unavailableSources?: string[];
  truncated?: boolean;
}

export const ARCHIVE_KIND_LABELS: Record<ResearchArchiveKind, string> = {
  "uploaded-report": "上传研报",
  "research-record": "研究记录",
  thesis: "投资逻辑",
  earnings: "财报研究",
  "peer-comparison": "同业比较",
  valuation: "预测与估值",
  "research-memo": "研究备忘录",
};

export const ARCHIVE_SOURCE_ROUTES: Record<ResearchArchiveKind, string> = {
  "uploaded-report": "research-library",
  "research-record": "research-notes",
  thesis: "thesis-tracker",
  earnings: "earnings-workbench",
  "peer-comparison": "peer-comparison",
  valuation: "valuation-workbench",
  "research-memo": "research-memo",
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function text(value: unknown, fallback = "", limit = 320) {
  return typeof value === "string" ? value.trim().slice(0, limit) : fallback;
}

function iso(value: unknown, fallback = new Date().toISOString()) {
  const candidate = text(value, "", 80);
  return candidate && !Number.isNaN(Date.parse(candidate)) ? candidate : fallback;
}

function cachedWorkspace(key: string) {
  try {
    const value = JSON.parse(localStorage.getItem(key) || "null");
    return isRecord(value) ? value : null;
  } catch {
    return null;
  }
}

function rows(workspace: Record<string, unknown> | null, key: string) {
  const value = workspace?.[key];
  return Array.isArray(value) ? value.filter(isRecord) : [];
}

function security(value: unknown) {
  const row = isRecord(value) ? value : {};
  const market = text(row.market, "", 24);
  const symbol = text(row.symbol, "", 32);
  const name = text(row.name, "", 160);
  return market && symbol && name ? { market, symbol, name } : undefined;
}

function entry(
  kind: ResearchArchiveKind,
  sourceModId: string,
  artifactId: unknown,
  title: unknown,
  updatedAt: unknown,
  options: {
    status?: ResearchArchiveStatus;
    security?: unknown;
    asOf?: unknown;
    tags?: unknown[];
  } = {},
): ResearchArchiveEntry | null {
  const normalizedId = text(artifactId, "", 240);
  const normalizedTitle = text(title);
  if (!normalizedId || !normalizedTitle) return null;
  const tags = (options.tags ?? [])
    .map((tag) => text(tag, "", 80))
    .filter((tag, index, values) => Boolean(tag) && values.indexOf(tag) === index)
    .slice(0, 16);
  const normalizedSecurity = security(options.security);
  const asOf = text(options.asOf, "", 80);
  return {
    id: `archive:${sourceModId}:${normalizedId}`.slice(0, 320),
    kind,
    sourceModId,
    artifactId: normalizedId,
    title: normalizedTitle,
    status: options.status ?? "active",
    ...(normalizedSecurity ? { security: normalizedSecurity } : {}),
    ...(asOf ? { asOf } : {}),
    updatedAt: iso(updatedAt),
    tags,
  };
}

function discoverLocalEntries() {
  const found: ResearchArchiveEntry[] = [];
  const add = (value: ResearchArchiveEntry | null) => {
    if (value) found.push(value);
  };

  for (const note of loadNotes()) {
    add(entry(
      "research-record",
      "research-notes",
      note.id,
      note.title,
      new Date(note.ts).toISOString(),
      { tags: [note.kind] },
    ));
  }
  for (const row of rows(cachedWorkspace("newma-desk.thesis-tracker.v1"), "theses")) {
    const status = text(row.status, "unknown", 32);
    add(entry("thesis", "thesis-tracker", row.id, row.title, row.updatedAt, {
      status: status === "draft" || status === "archived" || status === "invalidated"
        ? status
        : status === "active" || status === "watch" ? "active" : "unknown",
      security: row.security,
      tags: [status, row.conviction],
    }));
  }
  for (const row of rows(cachedWorkspace("newma-desk.earnings-workbench.v1"), "workbooks")) {
    const stock = isRecord(row.security) ? row.security : {};
    const period = isRecord(row.fiscalPeriod) ? row.fiscalPeriod : {};
    const verification = isRecord(row.verification) ? row.verification : {};
    add(entry(
      "earnings",
      "earnings-workbench",
      row.id,
      `${text(stock.name, "证券", 160)} · ${text(period.label, "财报研究", 120)}`,
      row.updatedAt,
      {
        security: stock,
        asOf: period.reportingDate || period.periodEnd,
        tags: [row.mode, verification.status],
      },
    ));
  }
  for (const row of rows(cachedWorkspace("newma-desk.peer-comparison.v1"), "cases")) {
    const period = isRecord(row.period) ? row.period : {};
    add(entry("peer-comparison", "peer-comparison", row.id, row.name, row.updatedAt, {
      security: row.target,
      asOf: period.asOf,
      tags: [row.researchQuestion],
    }));
  }
  for (const row of rows(cachedWorkspace("newma-desk.valuation-workbench.v1"), "models")) {
    add(entry("valuation", "valuation-workbench", row.id, row.name, row.updatedAt, {
      security: row.security,
      asOf: row.asOf,
      tags: [row.modelScope, row.selectedScenario],
    }));
  }
  for (const row of rows(cachedWorkspace("newma-desk.research-memo.v1"), "memos")) {
    const status = text(row.status, "unknown", 32);
    const boundary = isRecord(row.boundary) ? row.boundary : {};
    const view = isRecord(row.executiveView) ? row.executiveView : {};
    add(entry("research-memo", "research-memo", row.id, row.title, row.updatedAt, {
      status: status === "draft" || status === "archived"
        ? status
        : status === "superseded" ? "stale" : status === "current" ? "active" : "unknown",
      security: row.security,
      asOf: boundary.asOf,
      tags: [status, view.bias, view.conviction],
    }));
  }
  return found;
}

export function reportEntries(reports: MyReport[]) {
  return reports.map((report): ResearchArchiveEntry => ({
    id: `archive:research-library:${report.id}`,
    kind: "uploaded-report",
    sourceModId: "research-library",
    artifactId: report.id,
    title: report.name,
    status: "active",
    updatedAt: new Date(report.ts).toISOString(),
    tags: [report.industry, report.ext.replace(/^\./, "").toUpperCase()].filter(Boolean),
  }));
}

function mergeEntries(...groups: ResearchArchiveEntry[][]) {
  const merged = new Map<string, ResearchArchiveEntry>();
  for (const group of groups) {
    for (const item of group) merged.set(item.id, item);
  }
  return [...merged.values()]
    .sort((left, right) => Date.parse(right.updatedAt) - Date.parse(left.updatedAt))
    .slice(0, 1000);
}

export class ResearchArchiveError extends Error {}

function archiveScope(config: VibeDeskConfig | null) {
  return JSON.stringify([config?.apiOrigin, config?.userId, config?.workspaceId, config?.moduleId, config?.instanceId, config?.accessToken, config?.permissions]);
}

export async function loadResearchArchive(reports: MyReport[] = [], signal?: AbortSignal): Promise<ResearchArchiveIndex> {
  const config = await waitForVibeDeskConfig();
  signal?.throwIfAborted();
  if (config) {
    const scope = archiveScope(config);
    const permission = ['research-memo', 'idea-funnel'].includes(config.moduleId) ? "storage.read" : config.moduleId === "research-library" ? "investment.read" : "";
    if (!permission || !config.permissions?.includes(permission) || !config.accessToken || !config.instanceId) {
      throw new ResearchArchiveError("当前页面没有工作区档案读取权限，请从已授权的 Desk 重新打开。");
    }
    try {
      const response = await fetch(`${config.apiOrigin}/api/research-archive`, {
        cache: 'no-store',
        headers: {
          Authorization: `Bearer ${config.accessToken}`,
          "X-Newma-Desk-Instance-Id": config.instanceId,
        },
        signal: signal ? AbortSignal.any([signal, AbortSignal.timeout(15_000)]) : AbortSignal.timeout(15_000),
      });
      if (!response.ok) throw new ResearchArchiveError(`工作区档案读取失败（HTTP ${response.status}），未使用本机缓存替代。`);
      const payload = await response.json() as ResearchArchiveIndex;
      if (scope !== archiveScope(getVibeDeskConfig()) || payload.userId !== config.userId || payload.workspaceId !== config.workspaceId) {
        throw new ResearchArchiveError("工作区身份已变化，未采用旧工作区的档案结果。");
      }
      if (payload.schemaVersion !== "newma-desk.research-archive.v1" || !Array.isArray(payload.entries)
        || typeof payload.generatedAt !== "string" || !Number.isFinite(Date.parse(payload.generatedAt))
        || !Array.isArray(payload.unavailableSources) || !payload.unavailableSources.every((item) => typeof item === "string")
        || typeof payload.truncated !== "boolean" || payload.entries.some((item) => !item || !Object.prototype.hasOwnProperty.call(ARCHIVE_SOURCE_ROUTES, item.kind)
          || item.sourceModId !== ARCHIVE_SOURCE_ROUTES[item.kind] || typeof item.artifactId !== "string" || !item.artifactId
          || typeof item.id !== "string" || !item.id || !["active", "draft", "archived", "invalidated", "stale", "unknown"].includes(item.status)
          || typeof item.title !== "string" || !item.title || typeof item.updatedAt !== "string" || !Number.isFinite(Date.parse(item.updatedAt))
          || !Number.isInteger(item.sourceRevision) || Number(item.sourceRevision) < 1)) {
        throw new ResearchArchiveError("档案索引格式或完整性信息不完整，请更新服务后重试；不能据此判断引用已删除。");
      }
      signal?.throwIfAborted();
      return { ...payload, entries: mergeEntries(payload.entries, reportEntries(reports)) };
    } catch (error) {
      if (error instanceof ResearchArchiveError) throw error;
      throw new ResearchArchiveError("工作区档案读取未确认，请检查连接后重试；已有引用未改动。");
    }
  }
  if (isVibeDeskEmbedded || import.meta.env.VITE_NEWMA_DESK_INTEGRATED === '1') throw new ResearchArchiveError("尚未连接 Desk 工作区，不读取本机旧缓存。");
  return {
    schemaVersion: "newma-desk.research-archive.v1",
    userId: "local-user",
    workspaceId: "local-workspace",
    generatedAt: new Date().toISOString(),
    entries: mergeEntries(discoverLocalEntries(), reportEntries(reports)),
    // Local caches cannot establish complete coverage or workspace ownership.
    truncated: true,
  };
}

export function researchArchiveSourceUrl(item: ResearchArchiveEntry) {
  const modId = ARCHIVE_SOURCE_ROUTES[item.kind];
  const config = getVibeDeskConfig();
  if (!config) {
    const route = item.kind === "uploaded-report" ? "my-reports" : item.kind === "research-record" ? "notes" : modId;
    return `${import.meta.env.BASE_URL || "/"}${route}${item.kind === "thesis" ? `#artifact=${encodeURIComponent(item.artifactId)}` : ""}`;
  }
  const url = new URL(config.gatewayOrigin);
  url.searchParams.set("mod", modId);
  url.hash = `artifact=${encodeURIComponent(item.artifactId)}`;
  return url.toString();
}
