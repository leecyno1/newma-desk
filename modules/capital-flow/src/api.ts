import type { CapitalFlowDashboard } from "./types";

export async function fetchCapitalFlow(
  code: string | null,
  signal?: AbortSignal,
): Promise<CapitalFlowDashboard> {
  const query = code ? "?code=" + encodeURIComponent(code) : "";
  const response = await fetch("/api/capital-flow" + query, { signal });
  if (!response.ok) throw new Error("资金数据读取失败（" + response.status + "）");
  return response.json() as Promise<CapitalFlowDashboard>;
}
