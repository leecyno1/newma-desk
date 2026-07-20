import { describe, expect, it, vi } from "vitest";

import { createDataServiceClient } from "./data";

describe("createDataServiceClient", () => {
  it("invokes a registered service capability without accepting a URL", async () => {
    const fetch = vi.fn(async () =>
      new Response(JSON.stringify({ breadth: 0.63 }), {
        headers: { "Content-Type": "application/json" },
      }),
    );
    const client = createDataServiceClient({
      baseUrl: "http://localhost:8901",
      fetch,
    });

    const result = await client.invoke(
      "market-data",
      "market.overview",
      { date: "2026-07-20" },
    );

    expect(result).toEqual({ breadth: 0.63 });
    expect(fetch).toHaveBeenCalledWith(
      "http://localhost:8901/api/data-services/market-data/invoke/market.overview",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ date: "2026-07-20" }),
      }),
    );
  });
});
