import {
  wikiHandoffSchema,
  wikiLinkResolutionResponseSchema,
  wikiPageContextSchema,
  wikiSubjectMatchSchema,
  type WikiHandoff,
  type WikiLinkResolutionResponse,
  type WikiPageContext,
  type WikiSubjectMatch,
} from "@newma-desk/contracts";

function errorDetail(value: unknown, fallback: string): string {
  if (typeof value !== "object" || value === null) return fallback;
  const detail = (value as Record<string, unknown>).detail;
  return typeof detail === "string" ? detail : fallback;
}

async function requestJson(url: string, init?: RequestInit): Promise<unknown> {
  const headers = new Headers(init?.headers);
  headers.set("Accept", "application/json");
  if (init?.body !== undefined) headers.set("Content-Type", "application/json");
  const response = await fetch(url, {
    ...init,
    credentials: "omit",
    headers,
  });
  let body: unknown;
  try {
    body = await response.json();
  } catch {
    body = undefined;
  }
  if (!response.ok) {
    throw new Error(errorDetail(body, `Wiki 请求失败（${response.status}）`));
  }
  return body;
}

function identityHeaders(userId: string, workspaceId: string) {
  return {
    "X-User-Id": userId,
    "X-Workspace-Id": workspaceId,
  };
}

export async function searchWikiSubjects(input: {
  query: string;
  type?: "security" | "etf" | "fund" | "company" | "industry" | "concept" | "event" | "topic";
  market?: "CN" | "HK" | "US";
  limit?: number;
  signal?: AbortSignal;
}): Promise<WikiSubjectMatch[]> {
  const query = new URLSearchParams({
    query: input.query,
    limit: String(input.limit ?? 12),
  });
  if (input.type) query.set("type", input.type);
  if (input.market) query.set("market", input.market);
  const body = await requestJson(`/api/wiki/subjects?${query}`, {
    signal: input.signal,
  });
  return wikiSubjectMatchSchema.array().parse(body);
}

export async function resolveWikiLinks(input: {
  sourceModId: string;
  context: WikiPageContext;
  limit?: number;
  signal?: AbortSignal;
}): Promise<WikiLinkResolutionResponse> {
  const body = await requestJson("/api/wiki/link-resolutions", {
    method: "POST",
    signal: input.signal,
    body: JSON.stringify({
      sourceModId: input.sourceModId,
      context: wikiPageContextSchema.parse(input.context),
      limit: input.limit ?? 5,
    }),
  });
  return wikiLinkResolutionResponseSchema.parse(body);
}

export async function createWikiHandoff(input: {
  userId: string;
  workspaceId: string;
  sourceModId: string;
  targetModId: string;
  entrypointId: string;
  context: WikiPageContext;
  parameters?: Record<string, string | number | boolean>;
}): Promise<WikiHandoff> {
  const body = await requestJson("/api/wiki/handoffs", {
    method: "POST",
    headers: identityHeaders(input.userId, input.workspaceId),
    body: JSON.stringify({
      sourceModId: input.sourceModId,
      targetModId: input.targetModId,
      entrypointId: input.entrypointId,
      context: wikiPageContextSchema.parse(input.context),
      parameters: input.parameters ?? {},
    }),
  });
  return wikiHandoffSchema.parse(body);
}

export async function getWikiHandoff(input: {
  handoffId: string;
  userId: string;
  workspaceId: string;
  signal?: AbortSignal;
}): Promise<WikiHandoff> {
  const body = await requestJson(
    `/api/wiki/handoffs/${encodeURIComponent(input.handoffId)}`,
    {
      headers: identityHeaders(input.userId, input.workspaceId),
      signal: input.signal,
    },
  );
  return wikiHandoffSchema.parse(body);
}

export async function deleteWikiHandoff(input: {
  handoffId: string;
  userId: string;
  workspaceId: string;
}): Promise<void> {
  const response = await fetch(
    `/api/wiki/handoffs/${encodeURIComponent(input.handoffId)}`,
    {
      method: "DELETE",
      credentials: "omit",
      headers: identityHeaders(input.userId, input.workspaceId),
    },
  );
  if (!response.ok && response.status !== 404) {
    throw new Error(`Wiki 交接清理失败（${response.status}）`);
  }
}
