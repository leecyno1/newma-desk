import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { ModBridge } from "@newma-desk/mod-sdk";

import { buildMarketPageContext, MarketTerminalApp } from "./App";
import type { MarketDataSource, Quote, SecurityRef } from "./types";
import type { MarketAlertClient } from "./alerts";

vi.mock("./KLineChartPanel", async () => {
  const React = await import("react");
  return {
    KLineChartPanel: React.forwardRef(function MockChart(
      props: { loadBars: () => Promise<unknown> },
      ref: React.ForwardedRef<unknown>,
    ) {
      React.useImperativeHandle(ref, () => ({
        draw: vi.fn(),
        clearDrawings: vi.fn(),
        visibleRange: vi.fn(),
      }));
      React.useEffect(() => { void props.loadBars(); }, [props.loadBars]);
      return <div data-testid="kline-chart" />;
    }),
  };
});

const cnSecurity: SecurityRef = {
  symbol: "600519", name: "贵州茅台", market: "CN", exchange: "SH",
};
const usSecurity: SecurityRef = {
  symbol: "NVDA", name: "NVIDIA", market: "US", exchange: "NASDAQ",
};
const securities: SecurityRef[] = [cnSecurity, usSecurity];

const quotes: Quote[] = [
  {
    ...cnSecurity,
    price: 1500,
    change: 12,
    changePct: 0.81,
    open: 1490,
    high: 1510,
    low: 1485,
    amount: 12_000_000_000,
    source: "tencent",
    asOf: "2026-07-24T10:00:00+08:00",
    orderBook: { bids: [{ price: 1499, volume: 1000 }], asks: [{ price: 1501, volume: 800 }] },
  },
  {
    ...usSecurity,
    price: 186.5,
    change: -2,
    changePct: -1.06,
    source: "sina",
  },
];

function dataSource(): MarketDataSource {
  return {
    search: vi.fn(async () => [
      { ...usSecurity, source: "eastmoney-search" },
    ]),
    quotes: vi.fn(async () => quotes),
    quote: vi.fn(async (security) => quotes.find((item) => item.symbol === security.symbol) ?? { ...security }),
    scan: vi.fn(async (market, sort, order = "desc") => ({
      items: quotes.filter((item) => item.market === market),
      market,
      sort,
      order,
      source: "test-scan",
      asOf: "2026-07-24T10:00:00+08:00",
      coverage: { requested: 100, returned: quotes.filter((item) => item.market === market).length },
    })),
    ohlcv: vi.fn(async (security, timeframe, adjustment) => ({
      symbol: security.symbol,
      market: security.market,
      timeframe,
      adjust: adjustment,
      source: "tencent",
      asOf: "2026-07-24T10:00:00+08:00",
      hasMore: false,
      items: [{ timestamp: 1, open: 1, high: 2, low: 1, close: 2, volume: 10 }],
    })),
    overview: vi.fn(async () => ({
      sentiment: { up: 3000, down: 1800, flat: 120, breadth: "偏强" },
      sectors: [{ name: "半导体", pct: 2.1, net: 200000000 }],
      updated: "2026-07-24 10:00",
    })),
    indices: vi.fn(async () => [{ name: "上证指数", price: 3500, change_pct: 0.6 }]),
    globalIndices: vi.fn(async () => [{ name: "纳斯达克", price: 22000, change_pct: -0.2 }]),
    turnoverTop: vi.fn(async () => [{ code: "600519", name: "贵州茅台", price: 1500, pct: 0.81, amount: 12_000_000_000 }]),
    events: vi.fn(async () => ({ items: [], sources: [], asOf: "2026-07-24T10:00:00+08:00" })),
  };
}

function bridge(): ModBridge {
  return {
    emit: vi.fn((event, payload, target) => ({
      version: "1.0" as const,
      event,
      source: "market-daily",
      ...(target ? { target } : {}),
      traceId: "trace-1",
      payload,
    })),
    subscribe: vi.fn(() => () => undefined),
    close: vi.fn(),
  };
}

function alertClient(): MarketAlertClient {
  return {
    load: vi.fn(async () => []),
    create: vi.fn(async (input) => ({
      id: "alert-1",
      userId: "local-user",
      workspaceId: "local-workspace",
      ...input,
      label: input.label || "价格预警",
      enabled: input.enabled ?? true,
      createdAt: "2026-08-02T10:00:00Z",
      updatedAt: "2026-08-02T10:00:00Z",
    })),
    update: vi.fn(async () => { throw new Error("not used"); }),
    delete: vi.fn(async () => undefined),
  };
}

describe("MarketTerminalApp", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  it("renders a KLineChart terminal with quote, order book and market overview", async () => {
    render(<MarketTerminalApp bridge={bridge()} dataSource={dataSource()} watchlistClient={null} alertClient={null} />);

    expect((await screen.findAllByText("1,500.00"))[0]).toBeVisible();
    expect(screen.getByTestId("kline-chart")).toBeVisible();
    expect(screen.getByText("卖1")).toBeVisible();
    expect(await screen.findByText("3000")).toBeVisible();
    expect(screen.queryByText("AI 调用方式")).not.toBeInTheDocument();
  });

  it("searches global securities and emits the shared security event", async () => {
    const moduleBridge = bridge();
    render(<MarketTerminalApp bridge={moduleBridge} dataSource={dataSource()} watchlistClient={null} alertClient={null} />);

    await userEvent.type(screen.getByRole("textbox", { name: "搜索证券" }), "NVDA");
    const results = await screen.findByRole("listbox");
    await userEvent.click(within(results).getByRole("button", { name: /US NVIDIA/ }));

    expect(moduleBridge.emit).toHaveBeenCalledWith("security.selected", {
      symbol: "NVDA",
      name: "NVIDIA",
      market: "US",
      exchange: "NASDAQ",
    });
    expect((await screen.findAllByText("186.50"))[0]).toBeVisible();
  });

  it("creates manual price alerts through the shared Desk client", async () => {
    const alerts = alertClient();
    render(<MarketTerminalApp bridge={bridge()} dataSource={dataSource()} watchlistClient={null} alertClient={alerts} />);

    await userEvent.click(screen.getByLabelText("价格预警中心"));
    const priceInput = screen.getByRole("spinbutton", { name: "预警价格" });
    await userEvent.clear(priceInput);
    await userEvent.type(priceInput, "1600");
    await userEvent.click(screen.getByRole("button", { name: "添加" }));

    expect(alerts.create).toHaveBeenCalledWith(expect.objectContaining({
      security: expect.objectContaining(cnSecurity),
      direction: "above",
      price: 1600,
    }));
  });

  it("lets users create their own watchlist groups", async () => {
    render(<MarketTerminalApp bridge={bridge()} dataSource={dataSource()} watchlistClient={null} alertClient={null} />);

    await userEvent.click(screen.getByRole("button", { name: "新建自选分组" }));
    await userEvent.type(screen.getByRole("textbox", { name: "自选分组名称" }), "我的海外组合");
    await userEvent.click(screen.getByRole("button", { name: "保存" }));
    expect((screen.getByRole("combobox", { name: "自选分组" }) as HTMLSelectElement).value).toMatch(/^group-/);
    expect(screen.getByText("当前分组为空")).toBeVisible();
  });

  it("publishes chart state as Desk-level Agent context without duplicate Agent actions", () => {
    const context = buildMarketPageContext({
      security: cnSecurity,
      quote: quotes[0],
      timeframe: "1d",
      adjustment: "qfq",
      primaryIndicator: "MA",
      secondaryIndicator: "MACD",
      bottomTab: "overview",
      railTab: "orderbook",
      source: "tencent",
      asOf: "2026-07-24T10:00:00+08:00",
      visibleRange: { from: 10, to: 90 },
    });

    expect(context.selection).toMatchObject({ symbol: "600519", market: "CN" });
    expect(context.filters).toMatchObject({ timeframe: "1d", secondaryIndicator: "MACD" });
    expect(context.actions.map((item) => item.id)).toEqual([
      "market.refresh",
      "market.set-timeframe",
      "chart.set-indicator",
      "market.set-alert",
      "workspace.save-layout",
    ]);
    expect(context.actions.some((item) => item.id === "market.explain")).toBe(false);
  });
});
