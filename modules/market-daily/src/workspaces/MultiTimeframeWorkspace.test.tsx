import { render, screen, waitFor } from "@testing-library/react";
import { StrictMode } from "react";
import { describe, expect, it, vi } from "vitest";
import { MultiTimeframeWorkspace } from "./MultiTimeframeWorkspace";
import type { MarketDataSource, SecurityRef } from "../types";

vi.mock("@newma-desk/chart-kit", async () => {
  const actual = await vi.importActual<typeof import("@newma-desk/chart-kit")>("@newma-desk/chart-kit");
  const { useEffect } = await import("react");
  return { ...actual, KLineChartPanel: ({ loadBars }: { loadBars: () => Promise<unknown> }) => {
    useEffect(() => { void loadBars().catch(() => undefined); }, [loadBars]);
    return <div />;
  } };
});

describe("multi-timeframe actual adjustment", () => {
  it("discloses downgraded daily prices and returns per-panel evidence to Agent", async () => {
    const ohlcv = vi.fn(async (security, timeframe) => ({ symbol: security.symbol, market: security.market, timeframe, adjust: "none", source: "fallback-unadjusted", asOf: "2026-10-22", items: [{ timestamp: 1, close: 10 }], hasMore: false }));
    const context = vi.fn();
    render(<MultiTimeframeWorkspace dataSource={{ ohlcv } as unknown as MarketDataSource} security={{ symbol: "600519", name: "A", market: "CN" }} theme="light" refreshNonce={0} onContextChange={context} />, { wrapper: StrictMode });
    await screen.findByText(/口径已降级/);
    expect(ohlcv.mock.calls.slice(0, 4).map((call) => call.slice(1))).toEqual([["1d", "qfq"], ["60m", "none"], ["15m", "none"], ["5m", "none"]]);
    expect(context.mock.lastCall?.[0]).toMatchObject({ adjustment: "none", requestedDailyAdjustment: "qfq", panels: [{ timeframe: "1d", adjustment: "none", source: "fallback-unadjusted", status: "ready" }, { timeframe: "60m", adjustment: "none" }, { timeframe: "15m", adjustment: "none" }, { timeframe: "5m", adjustment: "none" }] });
  });
  it("does not attribute a late old-security response to the current selection", async () => {
    let resolveOld!: (value: unknown) => void;
    const old = new Promise((resolve) => { resolveOld = resolve; });
    const ohlcv = vi.fn((security: SecurityRef, timeframe: string) => security.symbol === "old" ? old : Promise.resolve({ adjust: "none", source: "current", asOf: "2026-10-22", items: [], timeframe }));
    const props = { dataSource: { ohlcv } as unknown as MarketDataSource, theme: "light" as const, refreshNonce: 0, onContextChange: vi.fn() };
    const { rerender } = render(<MultiTimeframeWorkspace {...props} security={{ symbol: "old", name: "old", market: "CN" }} />);
    rerender(<MultiTimeframeWorkspace {...props} security={{ symbol: "AAPL", name: "new", market: "US" }} />);
    await waitFor(() => expect(props.onContextChange.mock.lastCall?.[0].panels[0].source).toBe("current"));
    resolveOld({ adjust: "hfq", source: "old", items: [{ close: 10 }], asOf: "old" });
    await waitFor(() => expect(screen.queryByText(/来源：old/)).toBeNull());
    expect(screen.getByLabelText("复权方式")).toHaveValue("none");
    expect(screen.getByLabelText("复权方式")).toBeDisabled();
  });
});
