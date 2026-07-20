import { describe, expect, it, vi } from "vitest";

import { createGatewayClient, GatewayError } from "./agent";

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("createGatewayClient", () => {
  it("creates an agent task and builds its events URL", async () => {
    const fetch = vi.fn(async () =>
      jsonResponse({
        id: "task-1",
        status: "queued",
        request: { prompt: "解释异动", context: {}, input: {} },
        result: null,
        error: null,
      }),
    );
    const client = createGatewayClient({
      baseUrl: "http://localhost:8901",
      fetch,
    });

    const task = await client.createTask({
      moduleId: "market-daily",
      capability: "market.explain",
      prompt: "解释异动",
    });

    expect(task.id).toBe("task-1");
    expect(client.eventsUrl(task.id)).toBe(
      "http://localhost:8901/api/agent/tasks/task-1/events",
    );
    expect(client.eventsUrl(task.id, 2)).toBe(
      "http://localhost:8901/api/agent/tasks/task-1/events?after=2",
    );
    expect(fetch).toHaveBeenCalledWith(
      "http://localhost:8901/api/agent/tasks",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          moduleId: "market-daily",
          capability: "market.explain",
          prompt: "解释异动",
        }),
      }),
    );
  });

  it("gets, cancels, and invokes a module action", async () => {
    const fetch = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse({ id: "task-1", status: "running" }))
      .mockResolvedValueOnce(jsonResponse({ id: "task-1", status: "cancelled" }))
      .mockResolvedValueOnce(jsonResponse({ breadth: 0.63 }));
    const client = createGatewayClient({
      baseUrl: "http://localhost:8901/",
      fetch,
    });

    await client.getTask("task-1");
    await client.cancelTask("task-1");
    const result = await client.invokeModuleAction(
      "market-daily",
      "market.overview",
      { date: "2026-07-20" },
    );

    expect(result).toEqual({ breadth: 0.63 });
    expect(fetch.mock.calls.map(([url]) => url)).toEqual([
      "http://localhost:8901/api/agent/tasks/task-1",
      "http://localhost:8901/api/agent/tasks/task-1/cancel",
      "http://localhost:8901/api/modules/market-daily/actions/market.overview",
    ]);
  });

  it("throws a safe GatewayError from an HTTP detail", async () => {
    const fetch = vi.fn(async () =>
      jsonResponse({ detail: "unknown agent adapter" }, 400),
    );
    const client = createGatewayClient({
      baseUrl: "http://localhost:8901",
      fetch,
    });

    await expect(client.createTask({ prompt: "hello" })).rejects.toEqual(
      expect.objectContaining<Partial<GatewayError>>({
        status: 400,
        detail: "unknown agent adapter",
      }),
    );
  });

  it("rejects non-origin base URLs and invalid event offsets", () => {
    expect(() =>
      createGatewayClient({ baseUrl: "javascript:alert(1)" }),
    ).toThrow();
    const client = createGatewayClient({ baseUrl: "http://localhost:8901" });
    expect(() => client.eventsUrl("task-1", -1)).toThrow();
  });
});
