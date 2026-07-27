import { describe, expect, it, vi } from "vitest";

import {
  createGatewayClient,
  createModAccessSession,
  GatewayError,
} from "./agent";

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
      modId: "market-daily",
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
      expect.objectContaining({ method: "POST" }),
    );
    const requestCall = fetch.mock.calls[0] as unknown as [
      RequestInfo | URL,
      RequestInit,
    ];
    const requestBody = requestCall[1].body;
    expect(JSON.parse(String(requestBody))).toEqual({
      moduleId: "market-daily",
      capability: "market.explain",
      prompt: "解释异动",
    });
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
    const result = await client.invokeModAction(
      "market-daily",
      "market.overview",
      { date: "2026-07-20" },
    );

    expect(result).toEqual({ breadth: 0.63 });
    expect(fetch.mock.calls.map(([url]) => url)).toEqual([
      "http://localhost:8901/api/agent/tasks/task-1",
      "http://localhost:8901/api/agent/tasks/task-1/cancel",
      "http://localhost:8901/api/mods/market-daily/actions/market.overview",
    ]);
  });

  it("binds scoped Mod actions to the session iframe instance", async () => {
    const fetch = vi.fn(async () => jsonResponse({ ok: true }));
    const client = createGatewayClient({
      baseUrl: "http://localhost:8901",
      fetch,
      accessToken: "scoped-token",
      instanceId: "instance-1",
    });

    await client.invokeModAction("market-daily", "market.explain", {
      prompt: "解释行情",
    });

    const actionCall = fetch.mock.calls[0] as unknown as [
      RequestInfo | URL,
      RequestInit,
    ];
    const headers = new Headers(actionCall[1].headers);
    expect(headers.get("Authorization")).toBe("Bearer scoped-token");
    expect(headers.get("X-Newma-Dock-Instance-Id")).toBe("instance-1");
  });

  it("creates a standalone Mod session with its stable instance identity", async () => {
    const fetch = vi.fn(async () =>
      jsonResponse(
        {
          sessionId: "session-1",
          instanceId: "standalone-1",
          accessToken: "scoped-token",
          tokenType: "Bearer",
          expiresAt: "2099-01-01T00:00:00Z",
          userId: "alice",
          workspaceId: "desk-1",
          moduleId: "market-daily",
          revision: 1,
          grants: { permissions: ["market.read"], actions: ["market.explain"] },
        },
        201,
      ),
    );

    const session = await createModAccessSession({
      baseUrl: "http://localhost:8901",
      modId: "market-daily",
      instanceId: "standalone-1",
      userId: "alice",
      workspaceId: "desk-1",
      fetch,
    });

    expect(session.instanceId).toBe("standalone-1");
    const sessionCall = fetch.mock.calls[0] as unknown as [
      RequestInfo | URL,
      RequestInit,
    ];
    const body = JSON.parse(String(sessionCall[1].body));
    expect(body).toEqual({ instanceId: "standalone-1", workspaceId: "desk-1" });
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
