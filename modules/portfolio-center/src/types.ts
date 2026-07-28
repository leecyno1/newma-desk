export type Market = "CN" | "HK" | "US";
export type ActivityType =
  | "buy"
  | "sell"
  | "dividend"
  | "interest"
  | "fee"
  | "deposit"
  | "withdrawal"
  | "split";

export interface PortfolioAccount {
  id: string;
  name: string;
  currency: string;
  platform?: string | null;
  accountType: "securities" | "cash" | "paper";
  archived: boolean;
  createdAt: string;
  updatedAt: string;
}

export interface PortfolioActivity {
  id: string;
  accountId: string;
  type: ActivityType;
  market?: Market | null;
  symbol?: string | null;
  name?: string | null;
  currency: string;
  quantity?: number | null;
  unitPrice?: number | null;
  amount?: number | null;
  fee: number;
  occurredAt: string;
  note?: string | null;
  source: "manual" | "import" | "broker";
  createdAt: string;
}

export interface PortfolioPosition {
  accountId: string;
  market: Market;
  symbol: string;
  name: string;
  currency: string;
  quantity: number;
  averageCost: number;
  costValue: number;
  price?: number | null;
  marketValue?: number | null;
  unrealizedPnl?: number | null;
  unrealizedPnlPct?: number | null;
  realizedPnl: number;
  quoteSource?: string | null;
  quoteAsOf?: string | null;
}

export interface CurrencySummary {
  currency: string;
  cash: number;
  costValue: number;
  marketValue?: number | null;
  unrealizedPnl?: number | null;
  realizedPnl: number;
  income: number;
  fees: number;
}

export interface AllocationSlice {
  key: string;
  label: string;
  currency: string;
  value: number;
  weight: number;
}

export interface PortfolioDashboard {
  userId: string;
  workspaceId: string;
  accounts: PortfolioAccount[];
  activities: PortfolioActivity[];
  positions: PortfolioPosition[];
  currencies: CurrencySummary[];
  analytics: {
    basis: "market-value" | "cost-value";
    byMarket: AllocationSlice[];
    byCurrency: AllocationSlice[];
    byAccount: AllocationSlice[];
    concentration: {
      positionCount: number;
      topPositionWeight: number;
      topThreeWeight: number;
      herfindahlIndex: number;
      effectivePositionCount: number;
    };
  };
  valuationStatus: "live" | "partial" | "cost-based";
  updatedAt: string;
}

export type PortfolioWorkspace =
  | "portfolio-brief"
  | "portfolio-activities"
  | "portfolio-risk"
  | "portfolio-performance"
  | "portfolio-settings";
