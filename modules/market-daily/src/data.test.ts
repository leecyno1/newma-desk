import { describe, expect, it, vi } from "vitest";

import { createMarketDataSource, isOpenFundSecurity } from "./data";

describe("createMarketDataSource", () => {
  it("uses the provider-agnostic Mod action channel when embedded", async () => {
    const invokeAction = vi.fn().mockResolvedValue({
      data: {
        symbol: "600519",
        name: "贵州茅台",
        market: "CN",
        price: 1500,
      },
    });
    const source = createMarketDataSource({
      baseUrl: "https://desk.example",
      invokeAction,
    });

    await expect(source.quote({
      symbol: "600519",
      name: "贵州茅台",
      market: "CN",
    })).resolves.toEqual(expect.objectContaining({ price: 1500 }));
    expect(invokeAction).toHaveBeenCalledWith("market.quote", {
      symbol: "600519",
      market: "CN",
    });
  });

  it("loads a broad market scan through the same capability channel", async () => {
    const invokeAction = vi.fn().mockResolvedValue({
      data: {
        items: [],
        market: "US",
        sort: "amount",
        order: "desc",
        source: "eastmoney-delay",
        asOf: "2026-08-02T10:00:00Z",
        coverage: { requested: 100, returned: 0 },
      },
    });
    const source = createMarketDataSource({
      baseUrl: "https://desk.example",
      invokeAction,
    });

    await source.scan("US", "amount");

    expect(invokeAction).toHaveBeenCalledWith("market.scan", {
      market: "US",
      sort: "amount",
      order: "desc",
      limit: 100,
    });
  });

  it("builds an ETF event feed from fund announcements and ETF news", async () => {
    const invokeAction = vi.fn();
    invokeAction.mockImplementation(async (capabilityId: string) => {
      if (capabilityId === "market.announcements") {
        return {
          data: [{
            date: "2026-08-13",
            title: "沪深300ETF更新的招募说明书",
            type: "基金公告",
            fundCode: "510300",
            url: "https://pdf.dfcfw.com/pdf/H2_AN_TEST_1.pdf",
          }],
        };
      }
      if (capabilityId === "market.news") {
        return {
          data: [
            {
              新闻标题: "沪深300ETF成交活跃",
              发布时间: "2026-08-13 10:00:00",
              文章来源: "东方财富",
            },
            {
              新闻标题: "恒生科技ETF获得资金流入",
              发布时间: "2026-08-13 11:00:00",
              文章来源: "东方财富",
            },
          ],
        };
      }
      throw new Error(`unexpected capability ${capabilityId}`);
    });
    const source = createMarketDataSource({
      baseUrl: "https://desk.example",
      invokeAction,
    });

    const feed = await source.events({
      symbol: "510300",
      name: "沪深300ETF",
      market: "CN",
      assetType: "etf",
    });

    expect(invokeAction).toHaveBeenCalledWith("market.announcements", {
      code: "510300",
      assetType: "etf",
    });
    expect(invokeAction).not.toHaveBeenCalledWith("market.reports", expect.anything());
    expect(feed.sources.map((item) => item.label)).toEqual(["基金公告", "ETF资讯"]);
    expect(feed.items).toEqual(expect.arrayContaining([
      expect.objectContaining({ type: "announcement", source: "东方财富基金公告" }),
      expect.objectContaining({ type: "news", title: "沪深300ETF成交活跃" }),
    ]));
    expect(feed.items.some((item) => item.title.includes("恒生科技ETF"))).toBe(false);
  });

  it("routes open funds through NAV data and fund announcements", async () => {
    const invokeAction = vi.fn();
    invokeAction.mockImplementation(async (capabilityId: string) => {
      if (capabilityId === "market.quote") {
        return { data: { symbol: "110022", name: "110022", market: "CN", price: 2.928 } };
      }
      if (capabilityId === "market.ohlcv") {
        return { data: { symbol: "110022", market: "CN", timeframe: "1d", adjust: "none", items: [], source: "eastmoney-fund-nav", asOf: "2026-08-14", hasMore: false } };
      }
      if (capabilityId === "market.announcements") {
        return { data: [{ date: "2026-08-11", title: "基金产品资料概要更新", type: "基金公告", fundCode: "110022" }] };
      }
      throw new Error(`unexpected capability ${capabilityId}`);
    });
    const source = createMarketDataSource({ baseUrl: "https://desk.example", invokeAction });
    const fund = {
      symbol: "110022",
      name: "易方达消费行业股票",
      market: "CN" as const,
      exchange: "OTC",
      assetType: "fund",
      securityType: "股票型",
    };

    expect(isOpenFundSecurity(fund)).toBe(true);
    await expect(source.quote(fund)).resolves.toEqual(expect.objectContaining({ name: fund.name, price: 2.928 }));
    await source.ohlcv(fund, "1d", "qfq");
    const feed = await source.events(fund);

    expect(invokeAction).toHaveBeenCalledWith("market.quote", expect.objectContaining({ assetType: "fund" }));
    expect(invokeAction).toHaveBeenCalledWith("market.ohlcv", expect.objectContaining({ assetType: "fund", adjust: "none" }));
    expect(invokeAction).toHaveBeenCalledWith("market.announcements", { code: "110022", assetType: "fund" });
    expect(feed.sources.map((item) => item.label)).toEqual(["基金公告"]);
  });
});
