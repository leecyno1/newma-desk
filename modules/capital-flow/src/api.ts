import type { AppetiteResearchData, CapitalFlowDashboard, CapitalResearch, CapitalSupplyData, SupplyKind, SupplyVerificationData, SectorCategory, SectorLevel, SectorResearchData, SecuritySearchItem, SecurityResearchData, SecurityEvidenceData, LiquidityResearchData } from "./types";

export async function fetchAppetiteResearch(refresh = false, signal?: AbortSignal): Promise<AppetiteResearchData> {
  const response = await fetch("/api/capital-flow/appetite-research" + (refresh ? "?refresh=true" : ""), { signal });
  if (!response.ok) throw new Error(`风险偏好读取失败（${response.status}）`);
  return response.json() as Promise<AppetiteResearchData>;
}

export async function fetchLiquidityResearch(refresh = false, signal?: AbortSignal): Promise<LiquidityResearchData> {
  const response = await fetch("/api/capital-flow/liquidity-research" + (refresh ? "?refresh=true" : ""), { signal });
  if (!response.ok) throw new Error(`流动性研究读取失败（${response.status}）`);
  return response.json() as Promise<LiquidityResearchData>;
}

export async function fetchSecurityEvidence(code: string, boardDate: string, auditDate: string, refresh = false, signal?: AbortSignal): Promise<SecurityEvidenceData> {
  const params = new URLSearchParams({ code });
  if (boardDate) params.set("board_date", boardDate);
  if (auditDate) params.set("audit_date", auditDate);
  if (refresh) params.set("refresh", "true");
  const response = await fetch(`/api/capital-flow/security-evidence?${params}`, { signal });
  if (!response.ok) throw new Error(`席位与融资追溯读取失败（${response.status}）`);
  return response.json() as Promise<SecurityEvidenceData>;
}

export async function fetchSecurityResearch(code: string, refresh = false, signal?: AbortSignal): Promise<SecurityResearchData> {
  const params = new URLSearchParams({ code });
  if (refresh) params.set("refresh", "true");
  const response = await fetch(`/api/capital-flow/security-research?${params}`, { signal });
  if (!response.ok) throw new Error(`个股历史读取失败（${response.status}）`);
  return response.json() as Promise<SecurityResearchData>;
}

export async function fetchSupplyVerification(code: string, kind: SupplyKind, annDate: string, refresh = false, signal?: AbortSignal): Promise<SupplyVerificationData> {
  const params = new URLSearchParams({ code, kind, ann_date: annDate });
  if (refresh) params.set("refresh", "true");
  const response = await fetch(`/api/capital-flow/supply-verification?${params}`, { signal });
  if (!response.ok) throw new Error(`公告核验失败（${response.status}）`);
  return response.json() as Promise<SupplyVerificationData>;
}

export async function fetchCapitalSupply(code: string, refresh = false, signal?: AbortSignal): Promise<CapitalSupplyData> {
  const params = new URLSearchParams({ code });
  if (refresh) params.set("refresh", "true");
  const response = await fetch(`/api/capital-flow/supply-research?${params}`, { signal });
  if (!response.ok) throw new Error(`供需证据读取失败（${response.status}）`);
  return response.json() as Promise<CapitalSupplyData>;
}

export async function fetchSectorResearch(category: SectorCategory, code: string, refresh = false, signal?: AbortSignal, level: SectorLevel = "all"): Promise<SectorResearchData> {
  const params = new URLSearchParams({ category, level: category === "industry" ? level : "all" });
  if (code) params.set("code", code);
  if (refresh) params.set("refresh", "true");
  const response = await fetch(`/api/capital-flow/sector-research?${params}`, { signal });
  if (!response.ok) throw new Error(`板块历史读取失败（${response.status}）`);
  return response.json() as Promise<SectorResearchData>;
}

export async function fetchCapitalResearch(refresh = false, signal?: AbortSignal): Promise<CapitalResearch> {
  const response = await fetch("/api/capital-flow/research" + (refresh ? "?refresh=true" : ""), { signal });
  if (!response.ok) throw new Error(`配置与融资数据读取失败（${response.status}）`);
  return response.json() as Promise<CapitalResearch>;
}

export async function fetchCapitalFlow(
  code: string | null,
  signal?: AbortSignal,
  refresh = false,
): Promise<CapitalFlowDashboard> {
  const query = new URLSearchParams();
  if (code) query.set("code", code);
  if (refresh) query.set("refresh", "true");
  const response = await fetch("/api/capital-flow" + (query.size ? `?${query}` : ""), { signal });
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
