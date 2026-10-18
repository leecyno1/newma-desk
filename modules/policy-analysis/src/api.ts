import type { PolicyDashboard, PolicyDocument, PolicyEvent, PolicyInterpretation } from "./types";

export async function policyDocument(eventId: string, refresh = false, signal?: AbortSignal): Promise<PolicyDocument> {
  const response = await fetch(`/api/policy-analysis/events/${encodeURIComponent(eventId)}/document`, {
    method: refresh ? "POST" : "GET", signal, headers: { Accept: "application/json" },
  });
  if (!response.ok) throw new Error(await errorMessage(response, "官方正文读取失败"));
  return response.json() as Promise<PolicyDocument>;
}

export async function importOfficialPolicy(url: string): Promise<{ event: PolicyEvent; document: PolicyDocument }> {
  const response = await fetch("/api/policy-analysis/import", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ url }),
  });
  if (!response.ok) throw new Error(await errorMessage(response, "官方政策导入失败"));
  return response.json();
}

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
