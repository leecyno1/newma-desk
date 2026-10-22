// @vitest-environment jsdom
import { StrictMode } from "react";
import { render, waitFor, cleanup } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { KLineChartPanel } from "./KLineChartPanel";

const charts = vi.hoisted(() => [] as Array<Record<string, ReturnType<typeof vi.fn>>>);
vi.mock("klinecharts", () => ({
  init: () => {
    const chart = Object.fromEntries(["setDataLoader", "subscribeAction", "unsubscribeAction", "resize", "removeOverlay", "createOverlay", "setStyles", "setTimezone", "setSymbol", "setPeriod", "removeIndicator", "createIndicator"].map((key) => [key, vi.fn()]));
    charts.push(chart);
    return chart;
  },
  dispose: vi.fn(),
}));
afterEach(() => { cleanup(); charts.length = 0; vi.unstubAllGlobals(); });

it("initializes symbol and period on the surviving StrictMode chart and ignores a disposed chart response", async () => {
  vi.stubGlobal("ResizeObserver", class { observe() {} disconnect() {} });
  const loadBars = vi.fn(async () => [{ timestamp: 1, open: 10, high: 11, low: 9, close: 10 }]);
  const onLoadState = vi.fn();
  render(<StrictMode><KLineChartPanel security={{ symbol: "600519", name: "测试证券", market: "CN" }} timeframe="1d" adjustment="qfq" primaryIndicator="MA" secondaryIndicator="VOL" theme="light" refreshNonce={0} loadBars={loadBars} onLoadState={onLoadState} /></StrictMode>);
  expect(charts).toHaveLength(2);
  expect(charts[1]!.setSymbol).toHaveBeenCalledWith(expect.objectContaining({ ticker: "CN:600519" }));
  expect(charts[1]!.setPeriod).toHaveBeenCalled();
  const staleCallback = vi.fn();
  const currentCallback = vi.fn();
  await charts[0]!.setDataLoader!.mock.calls[0]![0].getBars({ callback: staleCallback });
  await charts[1]!.setDataLoader!.mock.calls[0]![0].getBars({ callback: currentCallback });
  await waitFor(() => expect(currentCallback).toHaveBeenCalled());
  expect(staleCallback).not.toHaveBeenCalled();
});
