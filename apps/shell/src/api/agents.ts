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

interface CapabilityResponse {
  adapters: AgentAdapterDescription[];
  moduleActions: Array<{ moduleId: string; capabilities: string[] }>;
}

interface AgentTask {
  id: string;
  status: "queued" | "running" | "completed" | "failed" | "cancelled";
  result?: { answer?: string } | null;
  error?: string | null;
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

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  headers.set("Accept", "application/json");
  if (init?.body !== undefined) headers.set("Content-Type", "application/json");
  return responseJson<T>(
    await fetch(path, { ...init, credentials: "omit", headers }),
  );
}

export async function loadAgentSettings(): Promise<{
  adapters: AgentAdapterDescription[];
  preferences: AgentPreferences;
}> {
  const [capabilities, preferences] = await Promise.all([
    request<CapabilityResponse>("/api/capabilities"),
    request<AgentPreferences>("/api/agent/preferences"),
  ]);
  return { adapters: capabilities.adapters, preferences };
}

export function saveAgentPreferences(
  preferences: Pick<AgentPreferences, "defaultAdapter" | "moduleOverrides">,
): Promise<AgentPreferences> {
  return request<AgentPreferences>("/api/agent/preferences", {
    method: "PUT",
    body: JSON.stringify(preferences),
  });
}

export async function probeAgent(adapter: string): Promise<string> {
  const created = await request<AgentTask>("/api/agent/tasks", {
    method: "POST",
    body: JSON.stringify({
      moduleId: "agent-settings",
      adapter,
      prompt: "只回复 VIBEDESK_AGENT_OK，不要调用工具，不要修改文件。",
    }),
  });
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
