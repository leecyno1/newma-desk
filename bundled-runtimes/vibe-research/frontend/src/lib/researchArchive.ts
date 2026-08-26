import type { MyReport } from "@/lib/api";
import { loadNotes } from "@/lib/notes";
import { getVibeDeskConfig, waitForVibeDeskConfig } from "@/lib/vibedesk";

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
      asOf: row.nextReviewAt,
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

function reportEntries(reports: MyReport[]) {
  return reports.map((report): ResearchArchiveEntry => ({
    id: `archive:research-library:${report.id}`,
    kind: "uploaded-report",
    sourceModId: "research-library",
    artifactId: report.id,
    title: report.name,
    status: "active",
    asOf: new Date(report.ts).toISOString().slice(0, 10),
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

export async function loadResearchArchive(reports: MyReport[]): Promise<ResearchArchiveIndex> {
  const localEntries = discoverLocalEntries();
  const config = await waitForVibeDeskConfig();
  let remoteEntries: ResearchArchiveEntry[] = [];
  let remoteLoaded = false;
  if (config) {
    try {
      const response = await fetch(`${config.apiOrigin}/api/research-archive`, {
        headers: {
          "X-User-Id": config.userId,
          "X-Workspace-Id": config.workspaceId,
        },
      });
      if (response.ok) {
        const payload = await response.json() as ResearchArchiveIndex;
        if (payload.schemaVersion === "newma-desk.research-archive.v1" && Array.isArray(payload.entries)) {
          remoteEntries = payload.entries;
          remoteLoaded = true;
        }
      }
    } catch {
      // The local cache remains useful when the Desk archive Interface is offline.
    }
  }
  return {
    schemaVersion: "newma-desk.research-archive.v1",
    userId: config?.userId ?? "local-user",
    workspaceId: config?.workspaceId ?? "local-workspace",
    generatedAt: new Date().toISOString(),
    entries: mergeEntries(remoteLoaded ? [] : localEntries, remoteEntries, reportEntries(reports)),
  };
}

export function researchArchiveSourceUrl(item: ResearchArchiveEntry) {
  const modId = ARCHIVE_SOURCE_ROUTES[item.kind];
  const config = getVibeDeskConfig();
  if (!config) return `/${modId}`;
  const url = new URL(config.gatewayOrigin);
  url.searchParams.set("mod", modId);
  url.hash = `artifact=${encodeURIComponent(item.artifactId)}`;
  return url.toString();
}
