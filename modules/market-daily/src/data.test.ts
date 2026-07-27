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
});
