export type GatewayFetch = (
  input: RequestInfo | URL,
  init?: RequestInit,
) => Promise<Response>;

export interface GatewayClientConfig {
  baseUrl: string;
  fetch?: GatewayFetch;
}

export interface AgentTaskCreateInput {
  moduleId?: string;
  capability?: string;
  prompt?: string;
  context?: Record<string, unknown>;
  input?: Record<string, unknown>;
  adapter?: string;
}

export interface AgentTask {
  id: string;
  status: "queued" | "running" | "completed" | "failed" | "cancelled";
  request?: AgentTaskCreateInput;
  result?: Record<string, unknown> | null;
  error?: string | null;
}

export class GatewayError extends Error {
  readonly status: number;
  readonly detail: string;

  constructor(status: number, detail: string) {
    super(detail);
    this.name = "GatewayError";
    this.status = status;
    this.detail = detail;
  }
}

export function normalizeGatewayBaseUrl(baseUrl: string): string {
  let parsed: URL;
  try {
    parsed = new URL(baseUrl);
  } catch {
    throw new Error("Gateway baseUrl must be an HTTP(S) origin");
  }
  if (
    (parsed.protocol !== "http:" && parsed.protocol !== "https:") ||
    parsed.username ||
    parsed.password ||
    parsed.search ||
    parsed.hash ||
    (parsed.pathname !== "/" && parsed.pathname !== "")
  ) {
    throw new Error("Gateway baseUrl must be an HTTP(S) origin");
  }
  return parsed.origin;
}

async function responseBody(response: Response): Promise<unknown> {
  if (response.status === 204) return undefined;
  try {
    return await response.json();
  } catch {
    if (response.ok) {
      throw new GatewayError(
        response.status,
        "Gateway returned an invalid response",
      );
    }
    return undefined;
  }
}

export async function requestGatewayJson<T>(
  fetcher: GatewayFetch,
  url: string,
  init?: RequestInit,
): Promise<T> {
  const headers = new Headers(init?.headers);
  headers.set("Accept", "application/json");
  if (init?.body !== undefined) headers.set("Content-Type", "application/json");
  const response = await fetcher(url, {
    ...init,
    credentials: "omit",
    redirect: "error",
    headers,
  });
  const body = await responseBody(response);
  if (!response.ok) {
    const detail =
      typeof body === "object" &&
      body !== null &&
      "detail" in body &&
      typeof body.detail === "string"
        ? body.detail
        : "Gateway request failed";
    throw new GatewayError(response.status, detail);
  }
  return body as T;
}

function pathSegment(value: string): string {
  if (!value) throw new Error("Gateway resource ID cannot be empty");
  return encodeURIComponent(value);
}

export interface GatewayClient {
  createTask(input: AgentTaskCreateInput): Promise<AgentTask>;
  getTask(taskId: string): Promise<AgentTask>;
  cancelTask(taskId: string): Promise<AgentTask>;
  eventsUrl(taskId: string, after?: number): string;
  invokeModuleAction<T = unknown>(
    moduleId: string,
    actionId: string,
    input: Record<string, unknown>,
  ): Promise<T>;
}

export function createGatewayClient(config: GatewayClientConfig): GatewayClient {
  const baseUrl = normalizeGatewayBaseUrl(config.baseUrl);
  const fetcher = config.fetch ?? globalThis.fetch.bind(globalThis);

  return {
    createTask(input) {
      return requestGatewayJson<AgentTask>(
        fetcher,
        `${baseUrl}/api/agent/tasks`,
        { method: "POST", body: JSON.stringify(input) },
      );
    },
    getTask(taskId) {
      return requestGatewayJson<AgentTask>(
        fetcher,
        `${baseUrl}/api/agent/tasks/${pathSegment(taskId)}`,
      );
    },
    cancelTask(taskId) {
      return requestGatewayJson<AgentTask>(
        fetcher,
        `${baseUrl}/api/agent/tasks/${pathSegment(taskId)}/cancel`,
        { method: "POST" },
      );
    },
    eventsUrl(taskId, after) {
      const url = new URL(
        `${baseUrl}/api/agent/tasks/${pathSegment(taskId)}/events`,
      );
      if (after !== undefined) {
        if (!Number.isInteger(after) || after < 0) {
          throw new Error("after must be a non-negative integer");
        }
        url.searchParams.set("after", String(after));
      }
      return url.toString();
    },
    invokeModuleAction<T = unknown>(
      moduleId: string,
      actionId: string,
      input: Record<string, unknown>,
    ) {
      return requestGatewayJson<T>(
        fetcher,
        `${baseUrl}/api/modules/${pathSegment(moduleId)}/actions/${pathSegment(actionId)}`,
        { method: "POST", body: JSON.stringify(input) },
      );
    },
  };
}
