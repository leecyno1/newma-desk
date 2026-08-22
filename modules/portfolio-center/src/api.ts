import type {
  ActivityType,
  Market,
  PortfolioAccount,
  PortfolioActivity,
  PortfolioDashboard,
  PortfolioOptimizationInput,
  PortfolioOptimizationResult,
  PortfolioPerformanceInput,
  PortfolioPerformanceResult,
  StrategicAllocationInput,
  StrategicAllocationResult,
} from "./types";
import type { PortfolioResearchCoverage } from "@newma-desk/contracts";

export interface PortfolioIdentity {
  userId: string;
  workspaceId: string;
}

export interface ActivityInput {
  accountId: string;
  type: ActivityType;
  market?: Market;
  symbol?: string;
  name?: string;
  currency: string;
  quantity?: number;
  unitPrice?: number;
  amount?: number;
  fee?: number;
  occurredAt: string;
  note?: string;
}

function headers(identity: PortfolioIdentity, json = false) {
  return {
    ...(json ? { "Content-Type": "application/json" } : {}),
    "X-User-Id": identity.userId,
    "X-Workspace-Id": identity.workspaceId,
  };
}

async function payload<T>(response: Response): Promise<T> {
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body?.detail || `HTTP ${response.status}`);
  return body as T;
}

export function portfolioClient(identity: PortfolioIdentity) {
  return {
    strategicAllocation: async (input: StrategicAllocationInput, options: { signal?: AbortSignal } = {}) =>
      payload<StrategicAllocationResult>(await fetch(
        "/api/portfolio-center/asset-allocation/optimize",
        {
          method: "POST",
          headers: headers(identity, true),
          body: JSON.stringify(input),
          signal: options.signal,
        },
      )),
    dashboard: async (options: { includeQuotes?: boolean; signal?: AbortSignal } = {}) => {
      const query = options.includeQuotes === false ? "?includeQuotes=false" : "";
      return payload<PortfolioDashboard>(await fetch(`/api/portfolio-center${query}`, {
        headers: headers(identity),
        signal: options.signal,
      }));
    },
    researchCoverage: async (options: { signal?: AbortSignal } = {}) =>
      payload<PortfolioResearchCoverage>(await fetch(
        "/api/portfolio-center/research-coverage",
        {
          headers: headers(identity),
          signal: options.signal,
        },
      )),
    createAccount: async (input: { id: string; name: string; currency: string; platform?: string }) =>
      payload<PortfolioAccount>(await fetch("/api/portfolio-center/accounts", {
        method: "POST",
        headers: headers(identity, true),
        body: JSON.stringify(input),
      })),
    createActivity: async (input: ActivityInput) =>
      payload<PortfolioActivity>(await fetch("/api/portfolio-center/activities", {
        method: "POST",
        headers: headers(identity, true),
        body: JSON.stringify(input),
      })),
    deleteActivity: async (activityId: string) => {
      const response = await fetch(`/api/portfolio-center/activities/${encodeURIComponent(activityId)}`, {
        method: "DELETE",
        headers: headers(identity),
      });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
    },
    optimizeAllocation: async (input: PortfolioOptimizationInput) =>
      payload<PortfolioOptimizationResult>(await fetch(
        "/api/portfolio-center/allocations/optimize",
        {
          method: "POST",
          headers: headers(identity, true),
          body: JSON.stringify(input),
        },
      )),
    analyzePerformance: async (input: PortfolioPerformanceInput) =>
      payload<PortfolioPerformanceResult>(await fetch(
        "/api/portfolio-center/performance/analyze",
        {
          method: "POST",
          headers: headers(identity, true),
          body: JSON.stringify(input),
        },
      )),
    importLegacy: async () => payload<{ imported: boolean; activitiesCreated: number; reason: string }>(
      await fetch("/api/portfolio-center/import/legacy", {
        method: "POST",
        headers: headers(identity),
      }),
    ),
  };
}
