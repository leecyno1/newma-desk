import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { ArtifactClient, ModBridge } from "@newma-dock/mod-sdk";

import type { MarketDataSource, Quote, SecurityRef } from "../types";
import { buildWorkspacePageContext, MarketWorkspaceApp } from "./WorkspaceApp";
import { MARKET_WORKSPACES, marketWorkspaceFromSearch } from "./config";

vi.mock("@newma-dock/chart-kit", async () => {
  const actual = await vi.importActual<typeof import("@newma-dock/chart-kit")>("@newma-dock/chart-kit");
  return {
    ...actual,
    KLineChartPanel: (props: { ariaLabel?: string; loadBars: () => Promise<unknown> }) => {
      void props.loadBars();
      return <div data-testid="workspace-kline" aria-label={props.ariaLabel} />;
    },
    RelativeStrengthChart: () => <div data-testid="relative-strength-chart" />,
  };
});

const cnSecurity: SecurityRef = { symbol: "600519", name: "贵州茅台", market: "CN", exchange: "SH" };
const quotes: Quote[] = [
  { ...cnSecurity, price: 1500, changePct: 2.2, amount: 12_000_000_000, pe: 19, pb: 6, volumeRatio: 1.5 },
  { symbol: "688981", name: "中芯国际", market: "CN", price: 145, changePct: 3.8, amount: 8_000_000_000, pe: 40, pb: 4, volumeRatio: 1.8 },
  { symbol: "300308", name: "中际旭创", market: "CN", price: 220, changePct: -1.2, amount: 5_000_000_000, pe: 28, pb: 7 },
];

function dataSource(): MarketDataSource {
  const bars = Array.from({ length: 100 }, (_, index) => ({
    timestamp: 1_700_000_000_000 + index * 86_400_000,
    open: 100 + index,
    high: 102 + index,
    low: 99 + index,
    close: 101 + index,
    volume: index === 80 ? 10_000 : 1_000,
  }));
  return {
    search: vi.fn(async () => [{ symbol: "NVDA", name: "NVIDIA", market: "US" as const, exchange: "NASDAQ" }]),
    quotes: vi.fn(async (items: SecurityRef[]) => items.map((item) => quotes.find((quote) => quote.symbol === item.symbol) ?? { ...item, price: 100, changePct: 0.5 })),
    quote: vi.fn(async (item) => quotes.find((quote) => quote.symbol === item.symbol) ?? { ...item, price: 100, changePct: 0.5 }),
    ohlcv: vi.fn(async (item, timeframe, adjustment) => ({
      symbol: item.symbol,
      market: item.market,
      timeframe,
      adjust: adjustment,
      items: bars,
      source: "test-market",
      asOf: "2026-07-24T10:00:00+08:00",
      hasMore: false,
    })),
    overview: vi.fn(async () => ({})),
    indices: vi.fn(async () => []),
    globalIndices: vi.fn(async () => []),
    turnoverTop: vi.fn(async () => []),
    events: vi.fn(async () => ({ items: [], sources: [], asOf: "2026-07-24T10:00:00+08:00" })),
  };
}

function artifactClient(): ArtifactClient {
  return {
    createGraph: vi.fn(),
    listGraphs: vi.fn(),
    latestGraph: vi.fn(),
    publish: vi.fn(),
    createReplay: vi.fn(),
    listReplays: vi.fn(async () => []),
    latestReplay: vi.fn(async () => Promise.reject(new Error("missing"))),
    publishReplay: vi.fn(),
    viewUrl: vi.fn((artifact) => `http://desk.test${artifact.viewUrl}`),
  } as unknown as ArtifactClient;
}

function bridge(modId: string): ModBridge {
  return {
    emit: vi.fn((event, payload, target) => ({
      version: "1.0" as const,
      event,
      source: modId,
      ...(target ? { target } : {}),
      traceId: "trace-workspace",
      payload,
    })),
    subscribe: vi.fn(() => () => undefined),
    close: vi.fn(),
  };
}

describe("market chart workspaces", () => {
  beforeEach(() => window.localStorage.clear());

  it("resolves each store workspace from its query parameter", () => {
    expect(marketWorkspaceFromSearch("?workspace=scanner")?.modId).toBe("market-scanner");
    expect(marketWorkspaceFromSearch("?workspace=trading-replay")?.title).toBe("交易回放室");
    expect(marketWorkspaceFromSearch("?workspace=missing")).toBeUndefined();
  });

  it("renders a functional scanner and emits the shared security event", async () => {
    const moduleBridge = bridge("market-scanner");
    render(<MarketWorkspaceApp config={MARKET_WORKSPACES.scanner} bridge={moduleBridge} dataSource={dataSource()} />);

    expect(await screen.findByText("放量走强")).toBeVisible();
    const results = screen.getByRole("table");
    await userEvent.click(within(results).getByText("中芯国际"));
    expect(moduleBridge.emit).toHaveBeenCalledWith("security.selected", {
      symbol: "688981",
      name: "中芯国际",
      market: "CN",
      exchange: "",
    });
  });

  it("renders four linked charts for the multi-timeframe workspace", async () => {
    render(<MarketWorkspaceApp config={MARKET_WORKSPACES["multi-timeframe"]} bridge={bridge("multi-timeframe")} dataSource={dataSource()} />);

    expect(await screen.findAllByTestId("workspace-kline")).toHaveLength(4);
    await userEvent.click(screen.getByRole("button", { name: "MACD" }));
    expect(screen.getByRole("button", { name: "MACD" })).toHaveAttribute("aria-pressed", "true");
  });

  it("supports replay decisions while future bars remain hidden", async () => {
    render(<MarketWorkspaceApp config={MARKET_WORKSPACES["trading-replay"]} bridge={bridge("trading-replay")} dataSource={dataSource()} artifactClient={artifactClient()} />);

    expect(await screen.findByText(/未来数据已隐藏/)).toBeVisible();
    await userEvent.click(screen.getByRole("button", { name: "模拟买入" }));
    expect(screen.getByText("决策次数").parentElement).toHaveTextContent("1");
    expect(screen.getByRole("button", { name: "模拟卖出" })).toBeEnabled();
  });

  it("publishes workspace-specific structured Agent context", () => {
    const context = buildWorkspacePageContext({
      config: MARKET_WORKSPACES["relative-strength"],
      security: cnSecurity,
      quote: quotes[0],
      workspaceState: { timeframe: "1d", ranking: [{ label: "贵州茅台", returnPct: 8.2 }] },
    });

    expect(context.view).toEqual({ id: "relative-strength", title: "相对强弱地图" });
    expect(context.selection).toMatchObject({ symbol: "600519", market: "CN" });
    expect(context.filters).toMatchObject({ workspace: "relative-strength", timeframe: "1d" });
    expect(context.data.summary).toMatchObject({ workspace: { timeframe: "1d" } });
  });
});
