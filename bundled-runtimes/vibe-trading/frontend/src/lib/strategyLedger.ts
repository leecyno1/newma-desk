import type { RunListItem, StrategyLedgerRecord } from "@/lib/api";

export interface StrategyLedgerFilters {
  query: string;
  status: string;
  startDate: string;
  endDate: string;
  sort: string;
}

export type StrategyComparisonLevel = "ready" | "caution" | "not_comparable" | "legacy";
export type StrategyComparisonMode =
  | "repeatability"
  | "parameter_sensitivity"
  | "strategy_revision"
  | "cross_strategy"
  | "unclassified";

export interface StrategyComparisonAssessment {
  schemaVersion: "newma-desk.strategy-comparison.v1";
  level: StrategyComparisonLevel;
  mode: StrategyComparisonMode;
  directlyComparable: boolean;
  reasonCodes: string[];
  matchedFields: string[];
  differingFields: string[];
}

export function strategyLedgerForRun(run: RunListItem): StrategyLedgerRecord | undefined {
  const ledger = run.strategy_ledger;
  return ledger?.schema_version === "newma-desk.strategy-ledger.v1" ? ledger : undefined;
}

function compactExperiment(run: RunListItem) {
  const ledger = strategyLedgerForRun(run);
  return {
    runId: run.run_id,
    status: ledger?.status ?? run.status,
    strategy: ledger
      ? {
          id: ledger.strategy.id,
          name: ledger.strategy.name,
          version: ledger.strategy.version,
          templateId: ledger.strategy.template_id,
          parameters: ledger.strategy.parameters,
        }
      : undefined,
    dataset: ledger
      ? {
          symbols: ledger.dataset.symbols,
          market: ledger.dataset.market,
          startDate: ledger.dataset.start_date,
          endDate: ledger.dataset.end_date,
          timeframe: ledger.dataset.timeframe,
          dataSources: ledger.dataset.data_sources,
        }
      : {
          symbols: run.codes ?? [],
          startDate: run.start_date,
          endDate: run.end_date,
        },
    metrics: ledger?.metrics ?? {
      total_return: run.total_return,
      sharpe: run.sharpe,
    },
    attribution: ledger?.attribution,
    costModel: ledger?.cost_model,
    quality: ledger?.quality,
    policy: ledger
      ? {
          mode: ledger.mode,
          executionMode: ledger.execution_mode,
          dataPolicy: ledger.provenance.data_policy,
        }
      : undefined,
  };
}

function normalizedStrings(values: string[] | undefined): string[] {
  return [...new Set((values ?? []).map((value) => value.trim().toUpperCase()).filter(Boolean))]
    .sort();
}

function sameStrings(left: string[] | undefined, right: string[] | undefined): boolean {
  return JSON.stringify(normalizedStrings(left)) === JSON.stringify(normalizedStrings(right));
}

function sameValue(left: unknown, right: unknown): boolean {
  return (left ?? null) === (right ?? null);
}

function stableParameters(parameters: StrategyLedgerRecord["strategy"]["parameters"]): string {
  return JSON.stringify(Object.entries(parameters).sort(([left], [right]) => left.localeCompare(right)));
}

function addComparisonField(
  matchedFields: string[],
  differingFields: string[],
  field: string,
  matches: boolean,
) {
  (matches ? matchedFields : differingFields).push(field);
}

export function assessStrategyLedgerComparison(
  leftRun: RunListItem | undefined,
  rightRun: RunListItem | undefined,
): StrategyComparisonAssessment | undefined {
  if (!leftRun || !rightRun) return undefined;

  const left = strategyLedgerForRun(leftRun);
  const right = strategyLedgerForRun(rightRun);
  if (!left || !right) {
    return {
      schemaVersion: "newma-desk.strategy-comparison.v1",
      level: "legacy",
      mode: "unclassified",
      directlyComparable: false,
      reasonCodes: ["missingLedger"],
      matchedFields: [],
      differingFields: ["nativeLedger"],
    };
  }

  const matchedFields: string[] = [];
  const differingFields: string[] = [];
  const reasonCodes: string[] = [];
  const symbolsAvailable = normalizedStrings(left.dataset.symbols).length > 0
    && normalizedStrings(right.dataset.symbols).length > 0;
  const marketAvailable = Boolean(left.dataset.market && right.dataset.market);
  const windowAvailable = Boolean(
    left.dataset.start_date
    && left.dataset.end_date
    && right.dataset.start_date
    && right.dataset.end_date,
  );
  const timeframeAvailable = Boolean(left.dataset.timeframe && right.dataset.timeframe);
  const dataSourcesAvailable = normalizedStrings(left.dataset.data_sources).length > 0
    && normalizedStrings(right.dataset.data_sources).length > 0;
  const symbolsMatch = symbolsAvailable && sameStrings(left.dataset.symbols, right.dataset.symbols);
  const marketMatches = marketAvailable && sameValue(left.dataset.market, right.dataset.market);
  const windowMatches = windowAvailable
    && sameValue(left.dataset.start_date, right.dataset.start_date)
    && sameValue(left.dataset.end_date, right.dataset.end_date);
  const timeframeMatches = timeframeAvailable && sameValue(left.dataset.timeframe, right.dataset.timeframe);
  const dataSourcesMatch = dataSourcesAvailable
    && sameStrings(left.dataset.data_sources, right.dataset.data_sources);
  const leftCommission = left.cost_model.commission_rate;
  const rightCommission = right.cost_model.commission_rate;
  const commissionAvailable = leftCommission != null && rightCommission != null;
  const commissionMatches = commissionAvailable
    && Math.abs(Number(leftCommission) - Number(rightCommission)) < 1e-12;

  addComparisonField(matchedFields, differingFields, "symbols", symbolsMatch);
  addComparisonField(matchedFields, differingFields, "market", marketMatches);
  addComparisonField(matchedFields, differingFields, "datasetWindow", windowMatches);
  addComparisonField(matchedFields, differingFields, "timeframe", timeframeMatches);
  addComparisonField(matchedFields, differingFields, "dataSources", dataSourcesMatch);
  addComparisonField(matchedFields, differingFields, "commission", commissionMatches);

  if (!symbolsAvailable || !marketAvailable || !windowAvailable || !timeframeAvailable) {
    reasonCodes.push("missingDatasetIdentity");
  }
  if (symbolsAvailable && !symbolsMatch) reasonCodes.push("differentSymbols");
  if (marketAvailable && !marketMatches) reasonCodes.push("differentMarket");
  if (windowAvailable && !windowMatches) reasonCodes.push("differentWindow");
  if (timeframeAvailable && !timeframeMatches) reasonCodes.push("differentTimeframe");
  if (!dataSourcesAvailable) reasonCodes.push("missingDataSources");
  else if (!dataSourcesMatch) reasonCodes.push("differentDataSources");
  if (!commissionAvailable) reasonCodes.push("missingCommission");
  else if (!commissionMatches) reasonCodes.push("differentCommission");
  if (left.status !== "completed" || right.status !== "completed") {
    reasonCodes.push("unfinishedExperiment");
  }

  const flags = new Set([...left.quality.flags, ...right.quality.flags]);
  const tradeCounts = [left.metrics.trade_count, right.metrics.trade_count]
    .filter((value): value is number => typeof value === "number" && Number.isFinite(value));
  if (flags.has("low_trade_sample") || tradeCounts.some((value) => value < 30)) {
    reasonCodes.push("lowTradeSample");
  }
  if (flags.has("zero_cost_assumption")) reasonCodes.push("zeroCostAssumption");
  if (flags.has("missing_risk_metrics")) reasonCodes.push("missingRiskMetrics");
  if ([left.quality.level, right.quality.level].some((level) => level === "limited" || level === "pending")) {
    reasonCodes.push("limitedQuality");
  }

  const blockingDatasetMismatch = !symbolsMatch || !marketMatches || !windowMatches || !timeframeMatches;
  const mode: StrategyComparisonMode = left.strategy.id !== right.strategy.id
    ? "cross_strategy"
    : left.strategy.version !== right.strategy.version
      ? "strategy_revision"
      : stableParameters(left.strategy.parameters) === stableParameters(right.strategy.parameters)
        ? "repeatability"
        : "parameter_sensitivity";
  const uniqueReasons = [...new Set(reasonCodes)];
  const level: StrategyComparisonLevel = blockingDatasetMismatch
    ? "not_comparable"
    : uniqueReasons.length > 0
      ? "caution"
      : "ready";

  return {
    schemaVersion: "newma-desk.strategy-comparison.v1",
    level,
    mode,
    directlyComparable: level === "ready",
    reasonCodes: uniqueReasons,
    matchedFields,
    differingFields,
  };
}

export function buildStrategyComparisonContext(
  leftRun: RunListItem | undefined,
  rightRun: RunListItem | undefined,
): Record<string, unknown> {
  const assessment = assessStrategyLedgerComparison(leftRun, rightRun);
  return {
    strategyComparison: {
      schemaVersion: "newma-desk.strategy-comparison.v1",
      executionPolicy: "paper-only",
      assessment,
      experiments: [leftRun, rightRun].filter((run): run is RunListItem => run != null).map(compactExperiment),
      guidance: [
        "Do not rank experiments when symbols, market, dataset window, or timeframe differ.",
        "Treat different data sources, commission assumptions, and samples below 30 trades as evidence limitations.",
        "Prefer stable parameter plateaus over the single experiment with the highest return.",
      ],
    },
  };
}

export function buildStrategyLedgerContext(
  runs: RunListItem[],
  filters: StrategyLedgerFilters,
): Record<string, unknown> {
  const experiments = runs.slice(0, 20).map(compactExperiment);

  return {
    strategyLedger: {
      schemaVersion: "newma-desk.strategy-ledger.v1",
      runtime: "vibe-trading-native",
      executionPolicy: "paper-only",
      experimentCount: runs.length,
      filters,
      experiments,
      guidance: [
        "Compare experiments using the same dataset window before ranking strategies.",
        "Treat low-trade samples and zero-cost assumptions as evidence limitations.",
        "Use return, drawdown, risk-adjusted metrics, and cost assumptions together.",
      ],
    },
  };
}
