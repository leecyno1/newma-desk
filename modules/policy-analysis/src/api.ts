import type { PolicyDashboard, PolicyEvent, PolicyInterpretation } from "./types";

async function errorMessage(response: Response, fallback: string) {
  try {
    const body = await response.json() as { detail?: unknown };
    if (typeof body.detail === "string" && body.detail.trim()) return body.detail;
  } catch { /* keep fallback */ }
  return `${fallback}（${response.status}）`;
}

export async function fetchPolicyDashboard(signal?: AbortSignal): Promise<PolicyDashboard> {
  const response = await fetch("/api/policy-analysis", { signal, headers: { Accept: "application/json" } });
  if (!response.ok) throw new Error(`政策数据读取失败（${response.status}）`);
  return response.json() as Promise<PolicyDashboard>;
}

export async function refreshPolicyDashboard(signal?: AbortSignal): Promise<PolicyDashboard> {
  const response = await fetch("/api/policy-analysis/refresh", {
    method: "POST", signal, headers: { Accept: "application/json" },
  });
  if (!response.ok) throw new Error(`政策数据刷新失败（${response.status}）`);
  return response.json() as Promise<PolicyDashboard>;
}

export async function reviewPolicyAssessment(
  eventId: string, level: 1 | 2 | 3, note: string, signal?: AbortSignal,
): Promise<PolicyEvent> {
  const response = await fetch(`/api/policy-analysis/events/${encodeURIComponent(eventId)}/assessment`, {
    method: "PATCH", signal, headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify({ level, note }),
  });
  if (!response.ok) throw new Error(`政策量级复核失败（${response.status}）`);
  return response.json() as Promise<PolicyEvent>;
}

export async function interpretPolicyEvent(
  eventId: string, signal?: AbortSignal,
): Promise<PolicyInterpretation> {
  const response = await fetch(`/api/policy-analysis/events/${encodeURIComponent(eventId)}/interpretation`, {
    method: "POST", signal, headers: { Accept: "application/json" },
  });
  if (!response.ok) throw new Error(await errorMessage(response, "政策解读失败"));
  return response.json() as Promise<PolicyInterpretation>;
}
