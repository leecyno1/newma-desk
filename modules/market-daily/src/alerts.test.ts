import { describe, expect, it, vi } from "vitest";

import { createMarketAlertClient } from "./alerts";


describe("market alert client", () => {
  it("uses the shared Desk API and propagates workspace identity", async () => {
    const fetcher = vi.fn(async (url: string | URL | Request, init?: RequestInit) => {
      const path = String(url);
      if (init?.method === "POST") {
        return new Response(JSON.stringify({
          id: "alert-1",
          userId: "alice",
          workspaceId: "desk-a",
          security: { symbol: "AAPL", name: "Apple", market: "US" },
          direction: "above",
          price: 250,
          label: "突破观察位",
          enabled: true,
          createdAt: "2026-08-02T10:00:00Z",
          updatedAt: "2026-08-02T10:00:00Z",
        }), { status: 201, headers: { "Content-Type": "application/json" } });
      }
      expect(path).toContain("/api/market-alerts");
      return new Response(JSON.stringify({ items: [] }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    });
    const client = createMarketAlertClient({
      baseUrl: "https://desk.example",
      userId: "alice",
      workspaceId: "desk-a",
      fetch: fetcher,
    });

    await expect(client.load()).resolves.toEqual([]);
    await expect(client.create({
      security: { symbol: "AAPL", name: "Apple", market: "US" },
      direction: "above",
      price: 250,
      label: "突破观察位",
    })).resolves.toMatchObject({ id: "alert-1", price: 250 });

    expect(fetcher).toHaveBeenCalledWith(
      "https://desk.example/api/market-alerts",
      expect.objectContaining({
        headers: expect.objectContaining({
          "X-User-Id": "alice",
          "X-Workspace-Id": "desk-a",
        }),
      }),
    );
  });
});
