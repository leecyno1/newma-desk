import { render, screen } from "@testing-library/react";
import { Compare } from "../Compare";
import type { RunListItem, StrategyLedgerRecord } from "@/lib/api";

const apiMock = vi.hoisted(() => ({
  listRuns: vi.fn(),
  getRun: vi.fn(),
}));

vi.mock("@/lib/api", () => ({
  api: apiMock,
}));

function ledger(runId: string, fastWindow: number, startDate = "2025-01-01"): StrategyLedgerRecord {
  return {
    schema_version: "newma-desk.strategy-ledger.v1",
    ledger_id: `ledger-${runId}`,
    experiment: { id: runId, revision: `revision-${runId}` },
    mode: "paper-only",
    execution_mode: "paper",
    status: "completed",
    strategy: {
      id: "vibe-trading.sma-crossover",
      name: "SMA Crossover",
      version: "1.0.0+stable",
      template_id: "sma_crossover",
      parameters: { fast_window: fastWindow, slow_window: 40 },
    },
    dataset: {
      symbols: ["AAPL"],
      market: "US",
      start_date: startDate,
      end_date: "2025-12-31",
      timeframe: "1D",
      source: "newma-desk",
      data_sources: ["sina"],
    },
    metrics: {
      total_return: 0.12,
      max_drawdown: -0.08,
      sharpe: 1.4,
      trade_count: 40,
    },
    attribution: [],
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

function run(runId: string, fastWindow: number, startDate?: string): RunListItem {
  return {
    run_id: runId,
    status: "success",
    created_at: `2026-08-0${fastWindow === 10 ? "1" : "2"}T00:00:00Z`,
    prompt: `SMA ${fastWindow}`,
    total_return: 0.12,
    sharpe: 1.4,
    strategy_ledger: ledger(runId, fastWindow, startDate),
  };
}

describe("Strategy comparison readiness", () => {
  beforeEach(() => {
    localStorage.clear();
    apiMock.listRuns.mockReset();
    apiMock.getRun.mockReset();
    apiMock.getRun.mockResolvedValue({
      metrics: { total_return: 0.12, sharpe: 1.4 },
      equity_curve: [],
    });
  });

  it("shows a direct parameter-sensitivity comparison only for aligned evidence", async () => {
    apiMock.listRuns.mockResolvedValue([run("run-2", 15), run("run-1", 10)]);

    render(<Compare />);

    expect(await screen.findByText("Comparison readiness")).toBeInTheDocument();
    expect(screen.getByText("Ready for direct comparison")).toBeInTheDocument();
    expect(screen.getByText("Parameter sensitivity")).toBeInTheDocument();
    expect(screen.getByText("Dataset window")).toBeInTheDocument();
    expect(screen.getByText("Commission")).toBeInTheDocument();
  });

  it("prevents direct ranking when the selected dataset windows differ", async () => {
    apiMock.listRuns.mockResolvedValue([
      run("run-2", 15, "2024-01-01"),
      run("run-1", 10, "2025-01-01"),
    ]);

    render(<Compare />);

    expect(await screen.findByText("Not directly comparable; do not rank these results")).toBeInTheDocument();
    expect(screen.getByText("The selected runs use different dataset windows.")).toBeInTheDocument();
  });
});
