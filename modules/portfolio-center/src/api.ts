import type {
  ActivityType,
  Market,
  PortfolioAccount,
  PortfolioActivity,
  PortfolioDashboard,
} from "./types";

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
    dashboard: async (options: { includeQuotes?: boolean; signal?: AbortSignal } = {}) => {
      const query = options.includeQuotes === false ? "?includeQuotes=false" : "";
      return payload<PortfolioDashboard>(await fetch(`/api/portfolio-center${query}`, {
        headers: headers(identity),
        signal: options.signal,
      }));
    },
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
    importLegacy: async () => payload<{ imported: boolean; activitiesCreated: number; reason: string }>(
      await fetch("/api/portfolio-center/import/legacy", {
        method: "POST",
        headers: headers(identity),
      }),
    ),
  };
}
