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
export type OrderStatus = "draft" | "submitted" | "partial" | "filled" | "cancelled" | "rejected";

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
  orderId?: string | null;
  executionId?: string | null;
  settlementDate?: string | null;
  decisionPrice?: number | null;
  arrivalPrice?: number | null;
  benchmarkPrice?: number | null;
  createdAt: string;
}

export interface PortfolioOrder {
  id: string;
  accountId: string;
  side: "buy" | "sell";
  market: Market;
  symbol: string;
  name?: string | null;
  currency: string;
  orderType: "market" | "limit" | "stop" | "stop-limit";
  quantity: number;
  limitPrice?: number | null;
  stopPrice?: number | null;
  timeInForce: "day" | "gtc" | "ioc" | "fok";
  status: OrderStatus;
  filledQuantity: number;
  averageFillPrice?: number | null;
  submittedAt?: string | null;
  expiresAt?: string | null;
  brokerOrderId?: string | null;
  note?: string | null;
  source: "manual" | "import" | "broker";
  createdAt: string;
  updatedAt: string;
}

export interface PortfolioRiskPolicy {
  singlePositionLimitPct: number;
  topThreeLimitPct: number;
  minEffectivePositions: number;
  maxDrawdownLimitPct: number;
  var95LimitPct: number;
  maxUnpricedPositions: number;
  allowNegativeCash: boolean;
  updatedAt: string;
}

export interface PortfolioRiskAction {
  id: string;
  ruleId: string;
  severity: "low" | "medium" | "high" | "critical";
  status: "open" | "acknowledged" | "resolved" | "waived";
  title: string;
  detail: string;
  owner?: string | null;
  note?: string | null;
  createdAt: string;
  updatedAt: string;
  resolvedAt?: string | null;
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
  orders: PortfolioOrder[];
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
  riskPolicy: PortfolioRiskPolicy;
  riskActions: PortfolioRiskAction[];
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
  | "portfolio-scenarios"
  | "portfolio-performance"
  | "portfolio-settings";

export type StrategicAllocationModel =
  | "black-litterman"
  | "risk-parity"
  | "minimum-volatility";

export interface StrategicAllocationInput {
  model: StrategicAllocationModel;
  targetVolatilityPct: number;
  horizonMonths: 1 | 3 | 6;
  maxWeight: number;
  riskFreeRatePct: number;
}

export interface StrategicAllocationAsset {
  id: string;
  name: string;
  category: string;
  cycleAssetId?: string | null;
  benchmarkWeightPct: number;
  targetWeightPct: number;
  expectedReturnPct: number;
  volatilityPct: number;
  riskContributionPct: number;
  equilibriumReturnPct: number;
  cycleViewReturnPct?: number | null;
  upProbabilityPct?: number | null;
  confidencePct: number;
  publicationStatus: string;
  evidenceLevel: string;
  sourceAsOf?: string | null;
  forecastOrigin?: string | null;
}

export interface StrategicAllocationResult {
  status: "ready" | "partial" | "prior-only";
  model: StrategicAllocationModel;
  method: string;
  horizonMonths: 1 | 3 | 6;
  targetVolatilityPct: number;
  achievedVolatilityPct: number;
  expectedReturnPct: number;
  sharpe?: number | null;
  cashWeightPct: number;
  assets: StrategicAllocationAsset[];
  scenarios: Array<{
    id: string;
    name: string;
    description: string;
    portfolioImpactPct: number;
    assetImpactsPct: Record<string, number>;
  }>;
  insights: string[];
  warnings: string[];
  dataSources: string[];
  cycleAsOf?: string | null;
  generatedAt: string;
}
