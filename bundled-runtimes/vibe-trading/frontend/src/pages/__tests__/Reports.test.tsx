import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { Reports } from "../Reports";

const apiMock = vi.hoisted(() => ({
  listRuns: vi.fn(),
  createQuickRun: vi.fn(),
  getRunStatus: vi.fn(),
  cancelRun: vi.fn(),
}));

vi.mock("@/lib/api", () => ({
  api: apiMock,
}));

describe("Reports page", () => {
  beforeEach(() => {
    apiMock.listRuns.mockReset();
    apiMock.createQuickRun.mockReset();
    apiMock.getRunStatus.mockReset();
    apiMock.cancelRun.mockReset();
  });

  it("lists backtest reports newest first with Full Report links and skips non-report runs", async () => {
    apiMock.listRuns.mockResolvedValue([
      {
        run_id: "old-report",
        status: "success",
        created_at: "2026-06-01T00:00:00Z",
        prompt: "Old report",
        codes: ["MSFT"],
        total_return: 0.05,
        sharpe: 1.1,
      },
      {
        run_id: "chat-only",
        status: "success",
        created_at: "2026-06-03T00:00:00Z",
        prompt: "No metrics",
        codes: [],
      },
      {
        run_id: "new-report",
        status: "success",
        created_at: "2026-06-04T00:00:00Z",
        prompt: "New report",
        codes: ["AAPL"],
        total_return: 0.12,
        sharpe: 1.8,
        strategy_ledger: {
          schema_version: "newma-desk.strategy-ledger.v1",
          ledger_id: "ledger-new-report",
          experiment: { id: "new-report", revision: "abc123" },
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
          metrics: {
            total_return: 0.12,
            max_drawdown: -0.08,
            sharpe: 1.8,
            trade_count: 24,
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
        },
      },
    ]);

    render(<Reports />, { wrapper: MemoryRouter });

    expect(await screen.findByText("Backtest Report Library")).toBeInTheDocument();
    expect(apiMock.listRuns).toHaveBeenCalledWith(100);
    expect(screen.queryByText("chat-only")).not.toBeInTheDocument();
    const reportRunLinks = screen.getAllByRole("link", { name: /-report$/ });
    expect(reportRunLinks[0]).toHaveAttribute("href", "/runs/new-report");
    expect(reportRunLinks[1]).toHaveAttribute("href", "/runs/old-report");
    const fullReportLinks = screen.getAllByRole("link", { name: "Full Report" });
    expect(fullReportLinks[0]).toHaveAttribute("href", "/runs/new-report");
    expect(fullReportLinks[1]).toHaveAttribute("href", "/runs/old-report");
    expect(screen.getByText("Strategy Experiment Ledger")).toBeInTheDocument();
    expect(screen.getAllByText("SMA Crossover").length).toBeGreaterThan(1);
    expect(screen.getByText("v1.0.0+def456")).toBeInTheDocument();
    expect(screen.getAllByText("Paper only").length).toBeGreaterThan(0);
    expect(screen.getByText("Commission 0.10%")).toBeInTheDocument();
    expect(screen.getByText("-8.00%")).toBeInTheDocument();
  });

  it("filters reports by search text", async () => {
    apiMock.listRuns.mockResolvedValue([
      {
        run_id: "aapl-report",
        status: "success",
        created_at: "2026-06-04T00:00:00Z",
        prompt: "Apple strategy",
        codes: ["AAPL"],
        total_return: 0.12,
      },
      {
        run_id: "msft-report",
        status: "success",
        created_at: "2026-06-03T00:00:00Z",
        prompt: "Microsoft strategy",
        codes: ["MSFT"],
        total_return: 0.08,
      },
    ]);

    render(<Reports />, { wrapper: MemoryRouter });
    await screen.findByText("aapl-report");

    fireEvent.change(screen.getByPlaceholderText("Search run id, prompt, symbol, status..."), {
      target: { value: "MSFT" },
    });

    expect(screen.queryByText("aapl-report")).not.toBeInTheDocument();
    expect(screen.getByText("msft-report")).toBeInTheDocument();
  });

  it("submits a quick SMA backtest with the expected payload", async () => {
    apiMock.listRuns.mockResolvedValue([]);
    apiMock.getRunStatus.mockResolvedValue({
      run_id: "run-quick-1",
      status: "queued",
    });
    apiMock.createQuickRun.mockResolvedValue({
      status: "queued",
      run_id: "run-quick-1",
    });

    render(<Reports />, { wrapper: MemoryRouter });
    await screen.findByText("Quick Backtest");

    fireEvent.change(screen.getByDisplayValue("Buy and Hold"), {
      target: { value: "sma_crossover" },
    });
    fireEvent.change(screen.getByPlaceholderText("e.g. AAPL or 600519.SH"), {
      target: { value: "msft" },
    });
    const dateInputs = screen.getAllByDisplayValue(/\d{4}-\d{2}-\d{2}/);
    fireEvent.change(dateInputs[0], { target: { value: "2025-01-01" } });
    fireEvent.change(dateInputs[1], { target: { value: "2025-12-31" } });
    fireEvent.change(screen.getByDisplayValue("100000"), { target: { value: "250000" } });
    fireEvent.change(screen.getByDisplayValue("0"), { target: { value: "0.0015" } });
    fireEvent.change(screen.getByDisplayValue("20"), { target: { value: "10" } });
    fireEvent.change(screen.getByDisplayValue("50"), { target: { value: "40" } });
    fireEvent.click(screen.getByRole("button", { name: "Start backtest" }));

    await screen.findByText("Backtest queued: run-quick-1");
    expect(apiMock.createQuickRun).toHaveBeenCalledWith({
      template_id: "sma_crossover",
      symbol: "MSFT",
      start_date: "2025-01-01",
      end_date: "2025-12-31",
      params: {
        initial_cash: 250000,
        commission: 0.0015,
        fast_window: 10,
        slow_window: 40,
      },
    });
  });

  it("shows active quick runs and lets the user cancel them", async () => {
    apiMock.listRuns
      .mockResolvedValueOnce([
        {
          run_id: "run-live-1",
          status: "queued",
          created_at: "2026-07-29T10:00:00Z",
          prompt: "Quick SMA run",
          codes: ["AAPL"],
          start_date: "2025-01-01",
          end_date: "2025-12-31",
        },
      ])
      .mockResolvedValueOnce([
        {
          run_id: "run-live-1",
          status: "cancelled",
          created_at: "2026-07-29T10:00:00Z",
          prompt: "Quick SMA run",
          codes: ["AAPL"],
          start_date: "2025-01-01",
          end_date: "2025-12-31",
        },
      ])
      .mockResolvedValue([
        {
          run_id: "run-live-1",
          status: "cancelled",
          created_at: "2026-07-29T10:00:00Z",
          prompt: "Quick SMA run",
          codes: ["AAPL"],
          start_date: "2025-01-01",
          end_date: "2025-12-31",
        },
      ]);
    apiMock.getRunStatus
      .mockResolvedValueOnce({
        run_id: "run-live-1",
        status: "running",
      })
      .mockResolvedValueOnce({
        run_id: "run-live-1",
        status: "cancelled",
      });
    apiMock.cancelRun.mockResolvedValue({ status: "cancelled" });

    render(<Reports />, { wrapper: MemoryRouter });
    expect(await screen.findByText("run-live-1")).toBeInTheDocument();
    expect(screen.getByText("This run is still active. The page refreshes status automatically while it is queued or running.")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Cancel run" }));

    await screen.findByText("Cancel requested for run-live-1");
    expect(apiMock.cancelRun).toHaveBeenCalledWith("run-live-1");
  });
});
