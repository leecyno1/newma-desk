import { describe, expect, it, vi } from "vitest";

import { createArtifactClient } from "./artifact";


describe("ArtifactClient", () => {
  it("creates, lists and publishes graph artifacts through the stable API", async () => {
    const response = {
      id: "a".repeat(32),
      moduleId: "industry-map",
      kind: "graph",
      renderer: "archify",
      title: "AI 算力产业链",
      status: "draft",
      createdAt: "2026-07-23T00:00:00Z",
      updatedAt: "2026-07-23T00:00:00Z",
      viewUrl: `/api/artifacts/${"a".repeat(32)}/view`,
      spec: { moduleId: "industry-map", title: "AI 算力产业链", nodes: [], edges: [] },
      archifyIr: {},
    };
    const fetcher = vi.fn(async () => new Response(JSON.stringify(response), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    }));
    const client = createArtifactClient({ baseUrl: "http://127.0.0.1:8911", fetch: fetcher });

    await client.createGraph({
      moduleId: "industry-map",
      title: "AI 算力产业链",
      nodes: [
        { id: "upstream", label: "上游" },
        { id: "downstream", label: "下游" },
      ],
      edges: [{ source: "upstream", target: "downstream" }],
    });
    await client.listGraphs("industry-map", "published");
    await client.publish("a".repeat(32));

    expect(fetcher).toHaveBeenNthCalledWith(
      1,
      "http://127.0.0.1:8911/api/artifacts",
      expect.objectContaining({ method: "POST" }),
    );
    expect(fetcher).toHaveBeenNthCalledWith(
      2,
      "http://127.0.0.1:8911/api/artifacts?module_id=industry-map&status=published",
      expect.any(Object),
    );
    expect(fetcher).toHaveBeenNthCalledWith(
      3,
      `http://127.0.0.1:8911/api/artifacts/${"a".repeat(32)}/publish`,
      expect.objectContaining({ method: "POST" }),
    );
    expect(client.viewUrl(response as never)).toBe(
      `http://127.0.0.1:8911/api/artifacts/${"a".repeat(32)}/view`,
    );
  });

  it("persists replay sessions through the Artifact client", async () => {
    const response = {
      id: "b".repeat(32),
      moduleId: "trading-replay",
      kind: "replay",
      renderer: "replay-html",
      title: "贵州茅台回放",
      status: "draft",
      createdAt: "2026-07-24T00:00:00Z",
      updatedAt: "2026-07-24T00:00:00Z",
      viewUrl: `/api/artifacts/replays/${"b".repeat(32)}/view`,
      spec: {},
    };
    const fetcher = vi.fn(async () => new Response(JSON.stringify(response), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    }));
    const client = createArtifactClient({ baseUrl: "http://127.0.0.1:8911", fetch: fetcher });

    await client.createReplay({
      moduleId: "trading-replay",
      title: "贵州茅台回放",
      security: { symbol: "600519", name: "贵州茅台", market: "CN" },
      timeframe: "1d",
      cursor: 80,
      totalBars: 240,
      orders: [],
    });

    expect(fetcher).toHaveBeenCalledWith(
      "http://127.0.0.1:8911/api/artifacts/replays",
      expect.objectContaining({ method: "POST" }),
    );
  });
});
