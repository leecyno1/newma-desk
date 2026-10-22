import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { ArtifactClient, ModBridge, ModHostConnection, ReplayArtifactRecord } from "@newma-desk/mod-sdk";

import type { MarketDataSource, Quote, SecurityRef } from "../types";
import { buildWorkspacePageContext, MarketWorkspaceApp } from "./WorkspaceApp";
import { MARKET_WORKSPACES, marketWorkspaceFromSearch } from "./config";

vi.mock("@newma-desk/chart-kit", async () => {
  const actual = await vi.importActual<typeof import("@newma-desk/chart-kit")>("@newma-desk/chart-kit");
  const { useEffect } = await import("react");
  return {
    ...actual,
    KLineChartPanel: (props: { ariaLabel?: string; variant?: string; loadBars: () => Promise<unknown> }) => {
      useEffect(() => { void props.loadBars().catch(() => undefined); }, [props.loadBars]);
      return <div data-testid="workspace-kline" data-variant={props.variant} aria-label={props.ariaLabel} />;
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
    scan: vi.fn(async (market, sort, order = "desc") => ({
      items: quotes.filter((item) => item.market === market),
      market,
      sort,
      order,
      source: "test-scan",
      asOf: "2026-07-24T10:00:00+08:00",
      coverage: { requested: 100, returned: quotes.filter((item) => item.market === market).length },
    })),
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
    sentimentHistory: vi.fn(() => new Promise<never>(() => {})),
    limitBoards: vi.fn(() => new Promise<never>(() => {})),
    sentiment: vi.fn(async () => ({
      sentiment: { up: 3200, down: 1600, flat: 100, zt: 72, dt: 12, breadth: "偏强" },
      sectors: [{ name: "通信", pct: 2.3, net: 1_200_000_000 }],
      updated: "2026-08-16 14:30",
    })),
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

function storageHost(modId: string, user = "alice", permissions = ["storage.read", "storage.write"]) {
  const handle = vi.fn();
  const host = {
    embedded: true, config: { modId, instanceId: `${user}-instance`, user: { id: user }, workspace: { id: `${user}-workspace` },
      gateways: { data: "https://desk.test/api/data", storage: "https://desk.test/api/mods" },
      grants: { permissions, actions: ["workspace.save-layout"] },
      session: { accessToken: `${user}-synthetic`, expiresAt: new Date(Date.now() + 60000).toISOString() },
    }, subscribe: vi.fn(() => () => {}), setContextProvider: vi.fn(() => () => {}), publishContext: vi.fn(),
    setUiActionHandler: handle, setHandoffHandler: vi.fn(() => () => {}),
  } as unknown as Extract<ModHostConnection, { embedded: true }>;
  return { host, handle };
}

describe("market chart workspaces", () => {
  beforeEach(() => window.localStorage.clear());

  it("resolves each store workspace from its query parameter", () => {
    expect(marketWorkspaceFromSearch("?workspace=scanner")?.modId).toBe("market-scanner");
    expect(marketWorkspaceFromSearch("?workspace=trading-replay")?.title).toBe("复盘回放");
    expect(marketWorkspaceFromSearch("?workspace=missing")).toBeUndefined();
  });

  it("renders a functional scanner and emits the shared security event", async () => {
    const moduleBridge = bridge("market-scanner");
    render(<MarketWorkspaceApp config={MARKET_WORKSPACES.scanner} bridge={moduleBridge} dataSource={dataSource()} alertClient={null} />);

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
    render(<MarketWorkspaceApp config={MARKET_WORKSPACES["multi-timeframe"]} bridge={bridge("multi-timeframe")} dataSource={dataSource()} alertClient={null} />);

    expect(await screen.findAllByTestId("workspace-kline")).toHaveLength(4);
    await userEvent.click(screen.getByRole("button", { name: "MACD" }));
    expect(screen.getByRole("button", { name: "MACD" })).toHaveAttribute("aria-pressed", "true");
  });

  it("renders market sentiment through its daily sample capability", async () => {
    const source = dataSource();
    render(<MarketWorkspaceApp config={MARKET_WORKSPACES.sentiment} bridge={bridge("market-sentiment")} dataSource={source} alertClient={null} />);

    expect(await screen.findByText("65.31%")).toBeVisible();
    expect(screen.getByText("A股市场参与度")).toBeVisible();
    expect(screen.getByText("65.31%")).toBeVisible();
    expect(screen.queryByRole("textbox", { name: "搜索证券" })).not.toBeInTheDocument();
    expect(source.quote).not.toHaveBeenCalled();
    expect(screen.getByText("涨停 / 跌停")).toBeVisible();
  });

  it("does not promote market freshness or selection using an unrelated stock quote", () => {
    const context = buildWorkspacePageContext({ config: MARKET_WORKSPACES.sentiment, security: cnSecurity,
      quote: { ...quotes[0]!, asOf: "2026-10-16T15:00:00+08:00" },
      workspaceState: { status: "error", freshness: "unknown", asOf: null } });
    expect(context.selection).toEqual({ market: "CN" });
    expect(context.data.freshness).toBe("unknown");
    expect(context.data.asOf).toBeUndefined();
    expect(context.data.summary).not.toHaveProperty("quote");
    expect(context.actions.map(action => action.id)).toEqual(["market.refresh"]);
  });

  it("computes technical structure from daily OHLCV", async () => {
    render(<MarketWorkspaceApp config={MARKET_WORKSPACES.technical} bridge={bridge("market-technical")} dataSource={dataSource()} alertClient={null} />);

    expect(await screen.findByText("技术结构")).toBeVisible();
    expect(screen.getByText("上行趋势")).toBeVisible();
    expect(screen.getByText("MA20")).toBeVisible();
    expect(screen.getByText(/完整分型、笔、中枢请通过 CZSC/)).toBeVisible();
  });

  it("switches the daily timeline to the ETF event composition", async () => {
    const source = dataSource();
    render(<MarketWorkspaceApp config={MARKET_WORKSPACES["event-timeline"]} bridge={bridge("event-timeline")} dataSource={source} alertClient={null} />);

    await userEvent.click(screen.getByRole("button", { name: "沪深300ETF" }));

    expect(await screen.findByText("ETF 日线事件")).toBeVisible();
    expect(screen.getByRole("button", { name: "基金公告" })).toBeVisible();
    expect(screen.getByRole("button", { name: "ETF资讯" })).toBeVisible();
    expect(screen.queryByRole("button", { name: "财报" })).not.toBeInTheDocument();
    expect(source.events).toHaveBeenCalledWith(expect.objectContaining({
      symbol: "510300",
      assetType: "etf",
    }));
  });

  it("renders open funds as a NAV line with fund profile metadata", async () => {
    const source = dataSource();
    const fund: SecurityRef = {
      symbol: "110022",
      name: "易方达消费行业股票",
      market: "CN",
      exchange: "OTC",
      assetType: "fund",
      securityType: "股票型",
    };
    source.search = vi.fn(async () => [fund]);
    source.quote = vi.fn(async () => ({
      ...fund,
      price: 2.928,
      changePct: -0.71,
      fundType: "股票型",
      fundCompany: "易方达基金",
      fundManager: "萧楠",
      navDate: "2026-08-14",
      subscribeStatus: "开放申购",
      redeemStatus: "开放赎回",
    }));

    render(<MarketWorkspaceApp config={MARKET_WORKSPACES["event-timeline"]} bridge={bridge("event-timeline")} dataSource={source} alertClient={null} />);
    await userEvent.type(screen.getByRole("textbox", { name: "搜索证券" }), "110022");
    await userEvent.click(await screen.findByRole("button", { name: /易方达消费行业股票/ }));

    expect(await screen.findByText("基金净值事件")).toBeVisible();
    expect(screen.getByLabelText("基金净值日线图")).toHaveAttribute("data-variant", "nav");
    expect(await screen.findByText("易方达基金")).toBeVisible();
    expect(screen.getByText(/开放申购 · 开放赎回/)).toBeVisible();
  });

  it("repairs a persisted stock that was previously stored as an OTC fund", async () => {
    const source = dataSource();
    const stock: SecurityRef = {
      symbol: "300308",
      name: "中际旭创",
      market: "CN",
      exchange: "SZ",
      assetType: "stock",
    };
    window.localStorage.setItem("vibedesk.event-timeline.security.v1", JSON.stringify({
      ...stock,
      exchange: "OTC",
      assetType: "fund",
    }));
    source.search = vi.fn(async () => [stock]);
    source.quote = vi.fn(async (item) => item.assetType === "fund"
      ? { ...item, name: "大成科技创新混合C", exchange: "OTC", price: 4.5843, assetType: "fund" }
      : { ...stock, price: 943, changePct: 1.2 });

    render(<MarketWorkspaceApp config={MARKET_WORKSPACES["event-timeline"]} bridge={bridge("event-timeline")} dataSource={source} alertClient={null} />);

    expect(await screen.findByText("300308 · SZ", { exact: true })).toBeVisible();
    expect(screen.getByText("CN", { selector: ".workspace-current-security > i" })).toBeVisible();
    expect(source.search).toHaveBeenCalledWith("中际旭创", "CN");
    await waitFor(() => expect(source.quote).toHaveBeenLastCalledWith(expect.objectContaining({
      symbol: "300308",
      assetType: "stock",
    })));
    expect(JSON.parse(window.localStorage.getItem("vibedesk.event-timeline.security.v1") || "{}")).toMatchObject({
      symbol: "300308",
      exchange: "SZ",
      assetType: "stock",
    });
  });

  it("marks the market workspace as embedded for host-controlled scrolling", async () => {
    const { container } = render(
      <MarketWorkspaceApp
        config={MARKET_WORKSPACES["multi-timeframe"]}
        bridge={bridge("multi-timeframe")}
        dataSource={dataSource()}
        alertClient={null}
        embedded
      />,
    );

    expect(await screen.findAllByTestId("workspace-kline")).toHaveLength(4);
    expect(container.querySelector(".market-workspace-root")).toHaveAttribute(
      "data-embedded",
      "true",
    );
  });

  it("supports replay decisions while future bars remain hidden", async () => {
    render(<MarketWorkspaceApp config={MARKET_WORKSPACES["trading-replay"]} bridge={bridge("trading-replay")} dataSource={dataSource()} artifactClient={artifactClient()} alertClient={null} />);

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

    expect(context.view).toEqual({ id: "relative-strength", title: "强弱对比" });
    expect(context.selection).toMatchObject({ symbol: "600519", market: "CN" });
    expect(context.filters).toMatchObject({ workspace: "relative-strength", timeframe: "1d" });
    expect(context.data.summary).toMatchObject({ workspace: { timeframe: "1d" } });
  });

  it("publishes saved layout metadata without putting credentials in Agent context", async () => {
    const { host, handle } = storageHost("multi-timeframe");
    const fetcher = vi.fn(async (_url, init) => {
      const { value } = JSON.parse(String(init?.body));
      return new Response(JSON.stringify({ moduleId: "multi-timeframe", namespace: "layouts", key: value.id, value }));
    });
    render(<MarketWorkspaceApp config={MARKET_WORKSPACES["multi-timeframe"]} bridge={bridge("multi-timeframe")} dataSource={dataSource()} alertClient={null} hostConnection={host} embedded fetch={fetcher} />);
    await screen.findAllByTestId("workspace-kline");
    await act(async () => { await handle.mock.calls.at(-1)![0]("workspace.save-layout", { name: "已保存布局" }); });
    expect(screen.getByText("最近布局：已保存布局")).toBeVisible();
    const context = vi.mocked(host.publishContext).mock.calls.at(-1)![0]!;
    expect(context.data?.summary?.workspace).toMatchObject({ lastSavedLayout: { name: "已保存布局" } });
    expect(JSON.stringify(context)).not.toContain("alice-synthetic");
    expect(JSON.stringify(context)).not.toContain("accessToken");
  });

  it("saves layouts with a signature and never reports an old account's late save", async () => {
    const first = storageHost("multi-timeframe");
    const second = storageHost("multi-timeframe", "bob");
    let finish!: (value: Response) => void;
    let body!: { value: { id: string; name: string } };
    const fetcher = vi.fn((_url, init) => { body = JSON.parse(String(init?.body)); return new Promise<Response>(resolve => { finish = resolve; }); });
    const props = { config: MARKET_WORKSPACES["multi-timeframe"], bridge: bridge("multi-timeframe"), dataSource: dataSource(), alertClient: null, embedded: true, fetch: fetcher };
    const view = render(<MarketWorkspaceApp {...props} hostConnection={first.host} />);
    await screen.findAllByTestId("workspace-kline");
    const handler = first.handle.mock.calls.at(-1)![0];
    const result = handler("workspace.save-layout", { name: "旧账户布局" }).catch((error: Error) => error);
    view.rerender(<MarketWorkspaceApp {...props} hostConnection={second.host} />);
    await act(async () => { finish(new Response(JSON.stringify({ moduleId: "multi-timeframe", namespace: "layouts", key: body.value.id, value: body.value }))); });
    expect(await result).toBeInstanceOf(Error);
    expect(screen.queryByText(/最近布局：旧账户布局/)).not.toBeInTheDocument();
    expect(window.localStorage.getItem("vibedesk.multi-timeframe.layouts.v1")).toBeNull();
    expect(fetcher.mock.calls[0]![1]).toMatchObject({ headers: { Authorization: "Bearer alice-synthetic" } });
  });

  it("disables layout writes for readonly sessions and archive saves before a host is connected", async () => {
    const first = storageHost("multi-timeframe", "alice", ["storage.read"]);
    const fetcher = vi.fn();
    const view = render(<MarketWorkspaceApp config={MARKET_WORKSPACES["multi-timeframe"]} bridge={bridge("multi-timeframe")} dataSource={dataSource()} hostConnection={first.host} fetch={fetcher} alertClient={null} embedded />);
    await expect(first.handle.mock.calls.at(-1)![0]("workspace.save-layout", {})).rejects.toThrow("未获布局存储授权");
    expect(fetcher).not.toHaveBeenCalled();
    view.unmount();
    render(<MarketWorkspaceApp config={MARKET_WORKSPACES["trading-replay"]} bridge={bridge("trading-replay")} dataSource={dataSource()} fetch={fetcher} alertClient={null} embedded />);
    await screen.findByText(/未来数据已隐藏/);
    expect(screen.getByRole("button", { name: "沉淀回放" })).toBeDisabled();
    expect(fetcher).not.toHaveBeenCalled();
  });

  it("does not replace a saved replay with a late initial archive list", async () => {
    let finish!: (records: ReplayArtifactRecord[]) => void;
    const client = artifactClient();
    client.listReplays = vi.fn(() => new Promise<ReplayArtifactRecord[]>(resolve => { finish = resolve; }));
    client.createReplay = vi.fn(async () => ({ id: "new", title: "新回放", viewUrl: "/new", moduleId: "trading-replay" }) as never);
    render(<MarketWorkspaceApp config={MARKET_WORKSPACES["trading-replay"]} bridge={bridge("trading-replay")} dataSource={dataSource()} artifactClient={client} alertClient={null} />);
    await screen.findByText(/未来数据已隐藏/);
    await userEvent.click(screen.getByRole("button", { name: "沉淀回放" }));
    expect(await screen.findByText("新回放")).toBeVisible();
    await act(async () => { finish([{ id: "old", title: "旧回放", viewUrl: "/old" } as ReplayArtifactRecord]); });
    expect(screen.queryByText("旧回放")).not.toBeInTheDocument();
    expect(screen.getByText("新回放")).toBeVisible();
  });
});
