import type { CapitalFlowDashboard, SecuritySearchItem } from "./types";

export async function fetchCapitalFlow(
  code: string | null,
  signal?: AbortSignal,
): Promise<CapitalFlowDashboard> {
  const query = code ? "?code=" + encodeURIComponent(code) : "";
  const response = await fetch("/api/capital-flow" + query, { signal });
  if (!response.ok) throw new Error("资金数据读取失败（" + response.status + "）");
  return response.json() as Promise<CapitalFlowDashboard>;
}

export async function searchCapitalFlowSecurities(
  query: string,
  signal?: AbortSignal,
): Promise<SecuritySearchItem[]> {
  const response = await fetch(
    "/api/capital-flow/search?query=" + encodeURIComponent(query) + "&limit=8",
    { signal },
  );
  if (!response.ok) throw new Error("标的搜索失败（" + response.status + "）");
  const payload = await response.json() as { items?: SecuritySearchItem[] };
  return payload.items ?? [];
}
