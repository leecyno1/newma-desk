import { formatImportError } from './importErrors';
import type {
  ActivityType,
  Market,
  PortfolioAccount,
  PortfolioActivity,
  PortfolioDashboard,
  PortfolioOrder,
  PortfolioRiskAction,
  PortfolioRiskPolicy,
  PortfolioRiskReport,
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
  orderId?: string;
  executionId?: string;
  settlementDate?: string;
  decisionPrice?: number;
  arrivalPrice?: number;
  benchmarkPrice?: number;
}

export interface OrderInput {
  accountId: string;
  side: "buy" | "sell";
  market: Market;
  symbol: string;
  name?: string;
  currency: string;
  orderType: "market" | "limit" | "stop" | "stop-limit";
  quantity: number;
  limitPrice?: number;
  stopPrice?: number;
  timeInForce: "day" | "gtc" | "ioc" | "fok";
  status: "draft" | "submitted";
  brokerOrderId?: string;
  note?: string;
}

export type RiskPolicyInput = Omit<PortfolioRiskPolicy, "updatedAt">;

function headers(identity: PortfolioIdentity, json = false) {
  return {
    ...(json ? { "Content-Type": "application/json" } : {}),
    "X-User-Id": identity.userId,
    "X-Workspace-Id": identity.workspaceId,
  };
}

async function payload<T>(response: Response): Promise<T> {
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(Array.isArray(body?.detail) ? body.detail.map((item: { loc?: string[]; msg: string }) => `${item.loc?.slice(1).join('.') || '参数'}：${item.msg}`).join('；') : body?.detail || `HTTP ${response.status}`);
  return body as T;
}

export async function callPortfolioImport<T>(identity:PortfolioIdentity,path:string,body?:unknown):Promise<T> {
  const response=await fetch(`/api/portfolio-center/${path}`,{method:body===undefined?'GET':'POST',headers:headers(identity,body!==undefined),body:body===undefined?undefined:JSON.stringify(body)});
  const data=await response.json();
  if(!response.ok)throw new Error(formatImportError(data.detail,body));
  return data;
}

export function portfolioClient(identity: PortfolioIdentity) {
  return {
    riskReports: async () => payload<PortfolioRiskReport[]>(await fetch('/api/portfolio-center/risk-reports', { headers: headers(identity) })),
    saveRiskReport: async (analysisInput: PortfolioPerformanceInput, performanceReportId?: string | null) => payload<PortfolioRiskReport>(await fetch('/api/portfolio-center/risk-reports', {
      method: 'POST', headers: headers(identity, true), body: JSON.stringify({ performanceReportId, analysisInput }),
    })),
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
    createOrder: async (input: OrderInput) =>
      payload<PortfolioOrder>(await fetch("/api/portfolio-center/orders", {
        method: "POST",
        headers: headers(identity, true),
        body: JSON.stringify(input),
      })),
    updateOrder: async (orderId: string, input: { status?: PortfolioOrder["status"]; brokerOrderId?: string; note?: string }) =>
      payload<PortfolioOrder>(await fetch(`/api/portfolio-center/orders/${encodeURIComponent(orderId)}`, {
        method: "PATCH",
        headers: headers(identity, true),
        body: JSON.stringify(input),
      })),
    updateRiskPolicy: async (input: RiskPolicyInput) =>
      payload<PortfolioRiskPolicy>(await fetch("/api/portfolio-center/risk-policy", {
        method: "PUT",
        headers: headers(identity, true),
        body: JSON.stringify(input),
      })),
    createRiskAction: async (input: { ruleId: string; severity: PortfolioRiskAction["severity"]; title: string; detail: string; owner?: string; note?: string }) =>
      payload<PortfolioRiskAction>(await fetch("/api/portfolio-center/risk-actions", {
        method: "POST",
        headers: headers(identity, true),
        body: JSON.stringify(input),
      })),
    updateRiskAction: async (actionId: string, input: { reviewSnapshotId?: string | null; status?: PortfolioRiskAction["status"]; owner?: string; note?: string; dueAt?: string | null }) =>
      payload<PortfolioRiskAction>(await fetch(`/api/portfolio-center/risk-actions/${encodeURIComponent(actionId)}`, {
        method: "PATCH",
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
