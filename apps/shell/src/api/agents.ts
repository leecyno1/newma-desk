import type { StoredMod } from "./modules";

export interface AgentAdapterDescription {
  id: string;
  name?: string;
  description?: string;
  kind?: string;
  available?: boolean;
  supportsMemory?: boolean;
  capabilities: string[];
  default: boolean;
}

export interface AgentPreferences {
  userId: string;
  defaultAdapter: string;
  moduleOverrides: Record<string, string>;
  updatedAt: string | null;
}

export interface AgentArtifact {
  id: string;
  kind: "report" | "graph" | "replay";
  title: string;
  summary?: string;
  content?: string;
  viewUrl?: string;
}

interface CapabilityResponse {
  adapters: AgentAdapterDescription[];
  moduleActions: Array<{ moduleId: string; capabilities: string[] }>;
}

export interface AgentTask {
  id: string;
  status: "queued" | "running" | "completed" | "failed" | "cancelled";
  request?: {
    adapter?: string | null;
    moduleId?: string | null;
    memoryScope?: "user-agent-mod" | "task";
    [key: string]: unknown;
  };
  result?: {
    answer?: string;
    message?: string;
    actions?: Array<{ actionId: string; input?: Record<string, unknown> }>;
    artifacts?: unknown;
    agentId?: string;
    upstreamSessionId?: string;
    [key: string]: unknown;
  } | null;
  error?: string | null;
}

export interface AgentTaskCreateInput {
  moduleId: string;
  capability?: string;
  memoryScope?: "user-agent-mod" | "task";
  prompt: string;
  context?: Record<string, unknown>;
  input?: Record<string, unknown>;
  adapter?: string;
}

export interface AgentRequestIdentity {
  userId: string;
  workspaceId?: string;
}

async function responseJson<T>(response: Response): Promise<T> {
  let body: unknown;
  try {
    body = await response.json();
  } catch {
    body = undefined;
  }
  if (!response.ok) {
    const detail =
      typeof body === "object" &&
      body !== null &&
      "detail" in body &&
      typeof body.detail === "string"
        ? body.detail
        : `Agent Gateway 返回 ${response.status}`;
    throw new Error(detail);
  }
  return body as T;
}

async function request<T>(
  path: string,
  init?: RequestInit,
  identity?: AgentRequestIdentity,
): Promise<T> {
  const headers = new Headers(init?.headers);
  headers.set("Accept", "application/json");
  if (init?.body !== undefined) headers.set("Content-Type", "application/json");
  if (identity?.userId) headers.set("X-User-Id", identity.userId);
  if (identity?.workspaceId) {
    headers.set("X-Workspace-Id", identity.workspaceId);
  }
  return responseJson<T>(
    await fetch(path, { ...init, credentials: "omit", headers }),
  );
}

export async function loadAgentSettings(userId: string): Promise<{
  adapters: AgentAdapterDescription[];
  preferences: AgentPreferences;
}> {
  const [capabilities, preferences] = await Promise.all([
    request<CapabilityResponse>("/api/capabilities"),
    request<AgentPreferences>("/api/agent/preferences", undefined, { userId }),
  ]);
  return { adapters: capabilities.adapters, preferences };
}

export function saveAgentPreferences(
  userId: string,
  preferences: Pick<AgentPreferences, "defaultAdapter" | "moduleOverrides">,
): Promise<AgentPreferences> {
  return request<AgentPreferences>("/api/agent/preferences", {
    method: "PUT",
    body: JSON.stringify(preferences),
  }, { userId });
}

export function createAgentTask(
  identity: AgentRequestIdentity,
  input: AgentTaskCreateInput,
): Promise<AgentTask> {
  return request<AgentTask>(
    "/api/agent/tasks",
    { method: "POST", body: JSON.stringify(input) },
    identity,
  );
}

export function getAgentTask(taskId: string): Promise<AgentTask> {
  return request<AgentTask>(`/api/agent/tasks/${encodeURIComponent(taskId)}`);
}

export function cancelAgentTask(taskId: string): Promise<AgentTask> {
  return request<AgentTask>(
    `/api/agent/tasks/${encodeURIComponent(taskId)}/cancel`,
    { method: "POST" },
  );
}

export async function probeAgent(
  userId: string,
  adapter: string,
  moduleId: string,
): Promise<string> {
  const created = await request<AgentTask>("/api/agent/tasks", {
    method: "POST",
    body: JSON.stringify({
      moduleId,
      adapter,
      prompt: "只回复 NEWMA_DESK_AGENT_OK，不要调用工具，不要修改文件。",
    }),
  }, { userId });
  const deadline = Date.now() + 90_000;
  while (Date.now() < deadline) {
    const task = await request<AgentTask>(`/api/agent/tasks/${created.id}`);
    if (task.status === "completed") {
      return task.result?.answer || "Agent 已完成测试";
    }
    if (["failed", "cancelled"].includes(task.status)) {
      throw new Error(task.error || "Agent 测试失败");
    }
    await new Promise((resolve) => window.setTimeout(resolve, 500));
  }
  throw new Error("Agent 测试超时");
}

export function displayModuleName(module: StoredMod): string {
  return module.manifest.name || module.moduleId;
}
