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

export type PortfolioOptimizationObjective =
  | "minimum-volatility"
  | "risk-balanced"
  | "return-seeking";

export interface PortfolioOptimizationInput {
  objective: PortfolioOptimizationObjective;
  currency: string;
  lookbackWeeks: number;
  maxWeight: number;
  allowCash: boolean;
  cashWeight: number;
  riskFreeRatePct: number;
}

export interface PortfolioOptimizationAllocation {
  market: Market | "CASH";
  symbol: string;
  name: string;
  currency: string;
  currentWeight: number;
  targetWeight: number;
  changeWeight: number;
  expectedReturnPct?: number | null;
  volatilityPct?: number | null;
  riskContributionPct?: number | null;
  historyPoints: number;
  frozen: boolean;
}

export interface PortfolioOptimizationResult {
  status: "ready" | "partial" | "insufficient-data";
  objective: PortfolioOptimizationObjective;
  method: string;
  currency: string;
  timeframe: "1w";
  lookbackWeeks: number;
  observations: number;
  dataSources: string[];
  asOf?: string | null;
  annualizedExpectedReturnPct?: number | null;
  annualizedVolatilityPct?: number | null;
  currentConcentration: number;
  targetConcentration: number;
  allocations: PortfolioOptimizationAllocation[];
  missingAssets: Array<{ market: Market; symbol: string; reason: string }>;
  warnings: string[];
  generatedAt: string;
}

export interface PortfolioPerformanceInput {
  currency: string;
  lookbackWeeks: number;
  riskFreeRatePct: number;
}

export interface PortfolioPerformanceResult {
  status: "ready" | "partial" | "insufficient-data";
  method: string;
  currency: string;
  timeframe: "1w";
  lookbackWeeks: number;
  observations: number;
  coverageWeightPct: number;
  metrics?: {
    totalReturnPct: number;
    annualizedReturnPct: number;
    annualizedVolatilityPct: number;
    sharpe?: number | null;
    sortino?: number | null;
    calmar?: number | null;
    maxDrawdownPct: number;
    maxDrawdownDurationWeeks: number;
    winRatePct: number;
    profitFactor?: number | null;
    bestWeekPct: number;
    worstWeekPct: number;
    valueAtRisk95Pct: number;
    conditionalValueAtRisk95Pct: number;
  } | null;
  series: Array<{ label: string; equity: number; drawdownPct: number }>;
  dataSources: string[];
  asOf?: string | null;
  missingAssets: Array<{ market: Market; symbol: string; reason: string }>;
  warnings: string[];
  generatedAt: string;
}

export type PortfolioWorkspace =
  | "portfolio-brief"
  | "portfolio-activities"
  | "portfolio-risk"
  | "portfolio-allocation"
  | "portfolio-performance"
  | "portfolio-settings";
