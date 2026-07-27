export type GatewayFetch = (
  input: RequestInfo | URL,
  init?: RequestInit,
) => Promise<Response>;

export interface GatewayClientConfig {
  baseUrl: string;
  fetch?: GatewayFetch;
  accessToken?: string;
  instanceId?: string;
}

export interface ModAccessSession {
  sessionId: string;
  instanceId: string;
  accessToken: string;
  expiresAt: string;
  userId: string;
  workspaceId: string;
  moduleId: string;
  revision: number;
  grants: { permissions: string[]; actions: string[] };
}

export interface ModAccessSessionInput {
  baseUrl: string;
  modId: string;
  instanceId: string;
  userId: string;
  workspaceId: string;
  fetch?: GatewayFetch;
}

export interface AgentTaskCreateInput {
  modId?: string;
  /** @deprecated Use modId in new Newma-Dock code. */
  moduleId?: string;
  capability?: string;
  memoryScope?: "user-agent-mod" | "task";
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
        : typeof body === "object" &&
            body !== null &&
            "error" in body &&
            typeof body.error === "object" &&
            body.error !== null &&
            "message" in body.error &&
            typeof body.error.message === "string"
          ? body.error.message
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
  invokeModAction<T = unknown>(
    modId: string,
    actionId: string,
    input: Record<string, unknown>,
  ): Promise<T>;
  /** @deprecated Use invokeModAction in new Newma-Dock code. */
  invokeModuleAction<T = unknown>(
    moduleId: string,
    actionId: string,
    input: Record<string, unknown>,
  ): Promise<T>;
}

export type AgentGatewayClient = Pick<
  GatewayClient,
  "createTask" | "getTask" | "cancelTask" | "eventsUrl"
>;

export function createAgentClient(
  config: GatewayClientConfig,
): AgentGatewayClient {
  const client = createGatewayClient(config);
  return {
    createTask: client.createTask,
    getTask: client.getTask,
    cancelTask: client.cancelTask,
    eventsUrl: client.eventsUrl,
  };
}

export function createGatewayClient(config: GatewayClientConfig): GatewayClient {
  const baseUrl = normalizeGatewayBaseUrl(config.baseUrl);
  const fetcher = config.fetch ?? globalThis.fetch.bind(globalThis);

  return {
    createTask(input) {
      const { modId, ...legacyInput } = input;
      return requestGatewayJson<AgentTask>(
        fetcher,
        `${baseUrl}/api/agent/tasks`,
        {
          method: "POST",
          body: JSON.stringify({
            ...legacyInput,
            ...(legacyInput.moduleId === undefined && modId !== undefined
              ? { moduleId: modId }
              : {}),
          }),
        },
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
    invokeModAction<T = unknown>(
      modId: string,
      actionId: string,
      input: Record<string, unknown>,
    ) {
      return requestGatewayJson<T>(
        fetcher,
        `${baseUrl}/api/mods/${pathSegment(modId)}/actions/${pathSegment(actionId)}`,
        {
          method: "POST",
          headers: config.accessToken
            ? {
                Authorization: `Bearer ${config.accessToken}`,
                ...(config.instanceId
                  ? { "X-Newma-Dock-Instance-Id": config.instanceId }
                  : {}),
              }
            : undefined,
          body: JSON.stringify(input),
        },
      );
    },
    invokeModuleAction<T = unknown>(
      moduleId: string,
      actionId: string,
      input: Record<string, unknown>,
    ) {
      return requestGatewayJson<T>(
        fetcher,
        `${baseUrl}/api/mods/${pathSegment(moduleId)}/actions/${pathSegment(actionId)}`,
        {
          method: "POST",
          headers: config.accessToken
            ? {
                Authorization: `Bearer ${config.accessToken}`,
                ...(config.instanceId
                  ? { "X-Newma-Dock-Instance-Id": config.instanceId }
                  : {}),
              }
            : undefined,
          body: JSON.stringify(input),
        },
      );
    },
  };
}

export async function createModAccessSession(
  input: ModAccessSessionInput,
): Promise<ModAccessSession> {
  const baseUrl = normalizeGatewayBaseUrl(input.baseUrl);
  const fetcher = input.fetch ?? globalThis.fetch.bind(globalThis);
  const value = await requestGatewayJson<unknown>(
    fetcher,
    `${baseUrl}/api/mods/${pathSegment(input.modId)}/sessions`,
    {
      method: "POST",
      headers: { "X-User-Id": input.userId },
      body: JSON.stringify({
        instanceId: input.instanceId,
        workspaceId: input.workspaceId,
      }),
    },
  );
  if (typeof value !== "object" || value === null) {
    throw new Error("Mod session response is malformed");
  }
  const row = value as Record<string, unknown>;
  const grants = row.grants as Record<string, unknown> | undefined;
  if (
    typeof row.sessionId !== "string" ||
    typeof row.instanceId !== "string" ||
    typeof row.accessToken !== "string" ||
    typeof row.expiresAt !== "string" ||
    typeof row.userId !== "string" ||
    typeof row.workspaceId !== "string" ||
    typeof row.moduleId !== "string" ||
    !Number.isInteger(row.revision) ||
    !grants ||
    !Array.isArray(grants.permissions) ||
    !grants.permissions.every((item) => typeof item === "string") ||
    !Array.isArray(grants.actions) ||
    !grants.actions.every((item) => typeof item === "string")
  ) {
    throw new Error("Mod session response is malformed");
  }
  return row as unknown as ModAccessSession;
}
