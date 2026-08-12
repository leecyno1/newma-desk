import { describe, expect, it, vi } from "vitest";

import { createMarketDataSource } from "./data";

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
});
