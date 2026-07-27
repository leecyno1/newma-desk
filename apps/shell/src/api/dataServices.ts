export interface DataServiceProvider {
  id: string;
  name: string;
  description: string;
  priority: number;
  transport: "rest" | "mcp" | "sse" | "websocket";
}

export interface DataCapabilityCatalogItem {
  id: string;
  permissions: string[];
  providers: DataServiceProvider[];
}

export interface DataServiceCatalog {
  version: "1.0";
  capabilities: DataCapabilityCatalogItem[];
}

export interface DataServicePreferences {
  userId: string;
  workspaceId: string;
  suiteId: string;
  capabilityServices: Record<string, string>;
  updatedAt: string | null;
}

function errorMessage(value: unknown, fallback: string): string {
  if (typeof value !== "object" || value === null) return fallback;
  const detail = (value as Record<string, unknown>).detail;
  if (typeof detail === "string") return detail;
  const error = (value as Record<string, unknown>).error;
  if (typeof error === "object" && error !== null) {
    const message = (error as Record<string, unknown>).message;
    if (typeof message === "string") return message;
  }
  return fallback;
}

async function requestJson<T>(url: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  headers.set("Accept", "application/json");
  if (init?.body !== undefined) headers.set("Content-Type", "application/json");
  const response = await fetch(url, { ...init, headers });
  let body: unknown;
  try {
    body = await response.json();
  } catch {
    body = undefined;
  }
  if (!response.ok) {
    throw new Error(errorMessage(body, `数据服务请求失败（${response.status}）`));
  }
  return body as T;
}

function identityHeaders(userId: string, workspaceId: string) {
  return {
    "X-User-Id": userId,
    "X-Workspace-Id": workspaceId,
  };
}

export function loadDataServiceCatalog(): Promise<DataServiceCatalog> {
  return requestJson<DataServiceCatalog>("/api/data-services/catalog");
}

export function loadDataServicePreferences(
  suiteId: string,
  userId: string,
  workspaceId: string,
): Promise<DataServicePreferences> {
  return requestJson<DataServicePreferences>(
    `/api/data-services/preferences/${encodeURIComponent(suiteId)}`,
    { headers: identityHeaders(userId, workspaceId) },
  );
}

export function saveDataServicePreferences(
  suiteId: string,
  userId: string,
  workspaceId: string,
  capabilityServices: Record<string, string>,
): Promise<DataServicePreferences> {
  return requestJson<DataServicePreferences>(
    `/api/data-services/preferences/${encodeURIComponent(suiteId)}`,
    {
      method: "PUT",
      headers: identityHeaders(userId, workspaceId),
      body: JSON.stringify({ capabilityServices }),
    },
  );
}
