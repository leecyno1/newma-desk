import { describe, expect, it, vi } from "vitest";

import { connectModHost, type ModHostRuntime } from "./host";

function embeddedRuntime() {
  let listener: ((event: MessageEvent) => void) | undefined;
  const postMessage = vi.fn();
  const parent = { postMessage } as unknown as Window;
  const child = {
    parent,
    addEventListener: vi.fn((_type: string, handler: EventListener) => {
      listener = handler as (event: MessageEvent) => void;
    }),
    removeEventListener: vi.fn(),
  } as unknown as Window;
  const runtime: ModHostRuntime = {
    window: child,
    setTimeout: globalThis.setTimeout.bind(globalThis),
    clearTimeout: globalThis.clearTimeout.bind(globalThis),
  };
  return {
    parent,
    child,
    runtime,
    postMessage,
    dispatch: (event: MessageEvent) => listener?.(event),
  };
}

describe("connectModHost", () => {
  it("returns immediately when the Mod runs standalone", async () => {
    const standalone = {} as Window;
    Object.assign(standalone, { parent: standalone });
    const runtime: ModHostRuntime = {
      window: standalone,
      setTimeout: globalThis.setTimeout.bind(globalThis),
      clearTimeout: globalThis.clearTimeout.bind(globalThis),
    };

    await expect(
      connectModHost(
        { modId: "market-daily", parentOrigin: "https://desk.example" },
        runtime,
      ),
    ).resolves.toEqual({ embedded: false, close: expect.any(Function) });
  });

  it("sends hello, accepts an exact-origin init, and acknowledges it", async () => {
    const { parent, runtime, postMessage, dispatch } = embeddedRuntime();
    const connection = connectModHost(
      {
        modId: "market-daily",
        parentOrigin: "https://desk.example",
        sdkVersion: "0.2.0",
        capabilities: ["events", "actions", "theme"],
      },
      runtime,
    );

    expect(parent.postMessage).toHaveBeenCalledWith(
      expect.objectContaining({
        type: "vibedesk:hello",
        modId: "market-daily",
        protocolVersions: ["1.0"],
      }),
      "https://desk.example",
    );
    const init = {
      type: "vibedesk:init",
      protocolVersion: "1.0",
      instanceId: "instance-1",
      modId: "market-daily",
      user: { id: "alice" },
      workspace: { id: "default" },
      environment: {
        theme: "dark",
        locale: "zh-CN",
        timezone: "Asia/Shanghai",
      },
      gateways: {
        actions: "https://desk.example/api/mods/market-daily/actions",
        agent: "https://desk.example/api/agent",
        model: "https://desk.example/api/model",
        data: "https://desk.example/api/data-services",
      },
      grants: { permissions: ["market.read"], actions: ["market.explain"] },
    } as const;
    dispatch({
      origin: "https://desk.example",
      source: parent,
      data: init,
    } as MessageEvent);

    const resolved = await connection;
    expect(resolved).toEqual(
      expect.objectContaining({
        embedded: true,
        config: expect.objectContaining({ instanceId: "instance-1" }),
      }),
    );
    expect(parent.postMessage).toHaveBeenLastCalledWith(
      {
        type: "vibedesk:ack",
        protocolVersion: "1.0",
        instanceId: "instance-1",
        modId: "market-daily",
      },
      "https://desk.example",
    );
    if (!resolved.embedded) throw new Error("expected embedded connection");
    const update = vi.fn();
    resolved.subscribe(update);
    dispatch({
      origin: "https://desk.example",
      source: parent,
      data: {
        ...init,
        environment: { ...init.environment, theme: "light" },
      },
    } as MessageEvent);
    expect(update).toHaveBeenCalledWith(
      expect.objectContaining({
        environment: expect.objectContaining({ theme: "light" }),
      }),
    );
    resolved.close();
  });

  it("publishes semantic context and proxies granted actions through the host", async () => {
    const { parent, runtime, postMessage, dispatch } = embeddedRuntime();
    const pending = connectModHost(
      {
        modId: "market-daily",
        parentOrigin: "https://desk.example",
        capabilities: ["context", "actions"],
      },
      runtime,
    );
    const init = {
      type: "vibedesk:init",
      protocolVersion: "1.0",
      instanceId: "instance-1",
      modId: "market-daily",
      user: { id: "alice" },
      workspace: { id: "desk-1" },
      environment: { theme: "light", locale: "zh-CN", timezone: "Asia/Shanghai" },
      gateways: {
        actions: "https://desk.example/api/mods/market-daily/actions",
        agent: "https://desk.example/api/agent",
        model: "https://desk.example/api/model",
        data: "https://desk.example/api/data-services",
      },
      grants: { permissions: ["market.read"], actions: ["market.explain"] },
      session: { id: "session-1", expiresAt: "2026-07-23T10:00:00+08:00" },
    } as const;
    dispatch({
      origin: "https://desk.example",
      source: parent,
      data: init,
    } as MessageEvent);
    const connection = await pending;
    if (!connection.embedded) throw new Error("expected embedded connection");
    connection.setContextProvider(() => ({
      view: { id: "market-daily", title: "市场行情" },
      visibleBlocks: [],
      selection: {},
      filters: {},
      data: { freshness: "fresh" },
      actions: [{ id: "market.explain", available: true }],
      tasks: [],
    }));
    dispatch({
      origin: "https://desk.example",
      source: parent,
      data: {
        type: "vibedesk:context-request",
        requestId: "context-1",
        instanceId: "instance-1",
        modId: "market-daily",
        reason: "agent",
      },
    } as MessageEvent);
    await Promise.resolve();
    expect(parent.postMessage).toHaveBeenCalledWith(
      expect.objectContaining({
        type: "vibedesk:context",
        requestId: "context-1",
        context: expect.objectContaining({ view: expect.any(Object) }),
      }),
      "https://desk.example",
    );

    const action = connection.invokeAction<{ id: string }>("market.explain", {
      prompt: "解释行情",
    });
    const request = postMessage.mock.calls.find(
      ([message]) =>
        typeof message === "object" &&
        message !== null &&
        "type" in message &&
        message.type === "vibedesk:action-request",
    )?.[0] as { requestId: string };
    dispatch({
      origin: "https://desk.example",
      source: parent,
      data: {
        type: "vibedesk:action-result",
        requestId: request.requestId,
        instanceId: "instance-1",
        modId: "market-daily",
        actionId: "market.explain",
        status: 202,
        ok: true,
        result: { id: "task-1" },
      },
    } as MessageEvent);

    await expect(action).resolves.toEqual({ id: "task-1" });
    connection.close();
  });

  it("accepts granted Desk-to-Mod UI actions through a scoped handler", async () => {
    const { parent, runtime, postMessage, dispatch } = embeddedRuntime();
    const pending = connectModHost(
      {
        modId: "multi-timeframe",
        parentOrigin: "https://desk.example",
        capabilities: ["actions", "context"],
      },
      runtime,
    );
    dispatch({
      origin: "https://desk.example",
      source: parent,
      data: {
        type: "vibedesk:init",
        protocolVersion: "1.0",
        instanceId: "instance-2",
        modId: "multi-timeframe",
        user: { id: "alice" },
        workspace: { id: "desk-1" },
        environment: { theme: "light", locale: "zh-CN", timezone: "Asia/Shanghai" },
        gateways: {
          actions: "https://desk.example/api/mods/multi-timeframe/actions",
          agent: "https://desk.example/api/agent",
          model: "https://desk.example/api/model",
          data: "https://desk.example/api/data-services",
        },
        grants: { permissions: ["market.read"], actions: ["market.set-timeframe"] },
      },
    } as MessageEvent);
    const connection = await pending;
    if (!connection.embedded) throw new Error("expected embedded connection");
    const handler = vi.fn(() => ({ timeframe: "15m" }));
    connection.setUiActionHandler(handler);

    dispatch({
      origin: "https://desk.example",
      source: parent,
      data: {
        type: "vibedesk:ui-action-request",
        requestId: "ui-1",
        instanceId: "instance-2",
        modId: "multi-timeframe",
        actionId: "market.set-timeframe",
        input: { timeframe: "15m" },
      },
    } as MessageEvent);
    await Promise.resolve();

    expect(handler).toHaveBeenCalledWith("market.set-timeframe", { timeframe: "15m" });
    expect(postMessage).toHaveBeenCalledWith(
      expect.objectContaining({
        type: "vibedesk:ui-action-result",
        requestId: "ui-1",
        ok: true,
      }),
      "https://desk.example",
    );
    connection.close();
  });
});
