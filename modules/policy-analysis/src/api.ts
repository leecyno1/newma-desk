import type { PolicyDashboard } from "./types";

export async function fetchPolicyDashboard(signal?: AbortSignal): Promise<PolicyDashboard> {
  const response = await fetch("/api/policy-analysis", { signal, headers: { Accept: "application/json" } });
  if (!response.ok) throw new Error(`政策数据读取失败（${response.status}）`);
  return response.json() as Promise<PolicyDashboard>;
}
