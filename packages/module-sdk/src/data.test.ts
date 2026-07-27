import { describe, expect, it, vi } from "vitest";

import { createUnifiedDataClient } from "./data";

describe("createUnifiedDataClient", () => {
  it("routes a capability through the scoped Mod action channel", async () => {
    const invokeAction = vi.fn().mockResolvedValue({ data: { price: 12.3 } });
    const client = createUnifiedDataClient({ invokeAction });

    await expect(
      client.query("market.quote", { symbol: "600519", market: "CN" }),
    ).resolves.toEqual({ data: { price: 12.3 } });
    expect(invokeAction).toHaveBeenCalledWith("market.quote", {
      symbol: "600519",
      market: "CN",
    });
  });

  it("supports a capability-to-action alias without exposing a provider", async () => {
    const invokeAction = vi.fn().mockResolvedValue({ data: [] });
    const client = createUnifiedDataClient({
      invokeAction,
      actionByCapability: { "market.quotes": "portfolio.refresh-quotes" },
    });

    await client.query("market.quotes", { symbols: "CN:600519" });
    expect(invokeAction).toHaveBeenCalledWith("portfolio.refresh-quotes", {
      symbols: "CN:600519",
    });
  });
});
