import {
  assessStrategyLedgerComparison,
  buildStrategyComparisonContext,
  buildStrategyLedgerContext,
  strategyLedgerForRun,
} from "../strategyLedger";
import type { RunListItem, StrategyLedgerRecord } from "../api";

function ledger(): StrategyLedgerRecord {
  return {
    schema_version: "newma-desk.strategy-ledger.v1",
    ledger_id: "vibe-trading-ledger",
    experiment: { id: "run-1", revision: "abc123" },
    mode: "paper-only",
    execution_mode: "paper",
    status: "completed",
    strategy: {
      id: "vibe-trading.sma-crossover",
      name: "SMA Crossover",
      version: "1.0.0+def456",
      template_id: "sma_crossover",
      parameters: { fast_window: 10, slow_window: 40 },
    },
    dataset: {
      symbols: ["AAPL"],
      market: "US",
      start_date: "2025-01-01",
      end_date: "2025-12-31",
      timeframe: "1D",
      source: "newma-desk",
      data_sources: ["sina"],
    },
    metrics: { total_return: 0.12, max_drawdown: -0.08, sharpe: 1.4, trade_count: 40 },
    attribution: [
      { kind: "risk", factor: "max_drawdown", value: -0.08, unit: "ratio" },
    ],
    cost_model: { commission_rate: 0.001, realized_fees_available: false },
    quality: { level: "complete", flags: [] },
    provenance: {
      runtime: "vibe-trading-native",
      data_policy: "desk-unified",
      execution_policy: "paper-only",
      artifact_policy: "run-directory",
      methodology: "quantdinger-inspired-native-extraction",
    },
  };
}

describe("Strategy Ledger context", () => {
  it("keeps only the native schema", () => {
    const run = { run_id: "run-1", status: "success", created_at: "2026-08-01", strategy_ledger: ledger() };
    expect(strategyLedgerForRun(run)).toEqual(run.strategy_ledger);
  });

  it("builds a compact Agent-readable experiment comparison context", () => {
    const run: RunListItem = {
      run_id: "run-1",
      status: "success",
      created_at: "2026-08-01",
      strategy_ledger: ledger(),
    };
    const context = buildStrategyLedgerContext([run], {
      query: "AAPL",
      status: "all",
      startDate: "",
      endDate: "",
      sort: "created_desc",
    });

    expect(context).toMatchObject({
      strategyLedger: {
        schemaVersion: "newma-desk.strategy-ledger.v1",
        executionPolicy: "paper-only",
        experimentCount: 1,
        experiments: [
          {
            runId: "run-1",
            strategy: { id: "vibe-trading.sma-crossover" },
            metrics: { total_return: 0.12, max_drawdown: -0.08 },
          },
        ],
      },
    });
  });

  it("recognizes parameter sensitivity experiments only when evidence is directly comparable", () => {
    const leftLedger = ledger();
    const rightLedger = ledger();
    rightLedger.experiment.id = "run-2";
    rightLedger.strategy.parameters = { fast_window: 15, slow_window: 40 };
    const assessment = assessStrategyLedgerComparison(
      { run_id: "run-1", status: "success", created_at: "2026-08-01", strategy_ledger: leftLedger },
      { run_id: "run-2", status: "success", created_at: "2026-08-02", strategy_ledger: rightLedger },
    );

    expect(assessment).toMatchObject({
      level: "ready",
      mode: "parameter_sensitivity",
      directlyComparable: true,
      reasonCodes: [],
    });
    expect(assessment?.matchedFields).toEqual([
      "symbols",
      "market",
      "datasetWindow",
      "timeframe",
      "dataSources",
      "commission",
    ]);
  });

  it("blocks ranking experiments from different dataset windows", () => {
    const leftLedger = ledger();
    const rightLedger = ledger();
    rightLedger.dataset.start_date = "2024-01-01";
    const assessment = assessStrategyLedgerComparison(
      { run_id: "run-1", status: "success", created_at: "2026-08-01", strategy_ledger: leftLedger },
      { run_id: "run-2", status: "success", created_at: "2026-08-02", strategy_ledger: rightLedger },
    );

    expect(assessment).toMatchObject({
      level: "not_comparable",
      directlyComparable: false,
      reasonCodes: ["differentWindow"],
    });
    expect(assessment?.differingFields).toContain("datasetWindow");
  });

  it("does not mislabel a changed strategy version as parameter sensitivity", () => {
    const leftLedger = ledger();
    const rightLedger = ledger();
    rightLedger.strategy.version = "1.1.0+newcode";
    rightLedger.strategy.parameters = { fast_window: 15, slow_window: 40 };
    const assessment = assessStrategyLedgerComparison(
      { run_id: "run-1", status: "success", created_at: "2026-08-01", strategy_ledger: leftLedger },
      { run_id: "run-2", status: "success", created_at: "2026-08-02", strategy_ledger: rightLedger },
    );

    expect(assessment).toMatchObject({
      level: "ready",
      mode: "strategy_revision",
      directlyComparable: true,
    });
  });

  it("downgrades different costs and samples below 30 trades to caution", () => {
    const leftLedger = ledger();
    const rightLedger = ledger();
    rightLedger.cost_model.commission_rate = 0.002;
    rightLedger.metrics.trade_count = 12;
    const assessment = assessStrategyLedgerComparison(
      { run_id: "run-1", status: "success", created_at: "2026-08-01", strategy_ledger: leftLedger },
      { run_id: "run-2", status: "success", created_at: "2026-08-02", strategy_ledger: rightLedger },
    );

    expect(assessment).toMatchObject({ level: "caution", directlyComparable: false });
    expect(assessment?.reasonCodes).toEqual(["differentCommission", "lowTradeSample"]);
  });

  it("marks legacy runs without a native ledger and exposes the diagnosis to Desk Agent", () => {
    const nativeRun: RunListItem = {
      run_id: "run-1",
      status: "success",
      created_at: "2026-08-01",
      strategy_ledger: ledger(),
    };
    const legacyRun: RunListItem = {
      run_id: "legacy-run",
      status: "success",
      created_at: "2026-08-02",
      total_return: 0.2,
    };

    expect(assessStrategyLedgerComparison(nativeRun, legacyRun)).toMatchObject({
      level: "legacy",
      mode: "unclassified",
      directlyComparable: false,
      reasonCodes: ["missingLedger"],
    });
    expect(buildStrategyComparisonContext(nativeRun, legacyRun)).toMatchObject({
      strategyComparison: {
        schemaVersion: "newma-desk.strategy-comparison.v1",
        executionPolicy: "paper-only",
        assessment: { level: "legacy" },
        experiments: [{ runId: "run-1" }, { runId: "legacy-run" }],
      },
    });
  });
});
