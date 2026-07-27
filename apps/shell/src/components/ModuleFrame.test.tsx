import { createRef } from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ModEvent, ModManifest } from "@newma-dock/contracts";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ShellEventBus } from "../events/ShellEventBus";
import { ModFrame, type ModFrameHandle } from "./ModuleFrame";

const manifest: ModManifest = {
  schemaVersion: "1.0",
  id: "market-daily",
  name: "市场行情",
  version: "0.1.0",
  category: "market",
  entry: { type: "structured", url: "/modules/market-daily/" },
  permissions: [],
  dataServices: [],
  agentCapabilities: [],
  events: {
    emits: ["security.selected"],
    accepts: ["security.selected"],
  },
};

const connectedManifest: ModManifest = {
  schemaVersion: "1.1",
  id: "market-daily",
  name: "市场行情",
  version: "1.0.0",
  category: "market",
  entry: { type: "structured", url: "/modules/market-daily/" },
  compatibility: { level: 3, bridgeProtocol: "1.0", viewSpecVersion: "1.0" },
  permissions: ["market.read"],
  dataServices: [],
  actions: {
    "market.explain": {
      binding: { type: "agent", memoryScope: "user-agent-mod" },
      execution: "task",
      permission: "market.read",
      confirmation: "none",
    },
    "market.set-timeframe": {
      binding: { type: "local" },
      execution: "request",
      permission: "market.read",
      confirmation: "none",
    },
  },
  events: { emits: [], accepts: [] },
};

function event(overrides: Partial<ModEvent> = {}): ModEvent {
  return {
    version: "1.0",
    event: "security.selected",
    source: "market-daily",
    traceId: "trace-1",
    payload: { symbol: "AAPL" },
    ...overrides,
  };
}

function dispatchFromFrame(
  frame: HTMLIFrameElement,
  data: unknown,
  origin = "http://127.0.0.1:5891",
  source: MessageEventSource | null = frame.contentWindow,
) {
  window.dispatchEvent(new MessageEvent("message", { data, origin, source }));
}

afterEach(() => vi.restoreAllMocks());

describe("ModFrame event boundary", () => {
  it("exposes a page-context request to the Desk-level copilot", async () => {
    const eventBus = new ShellEventBus();
    const frameHandle = createRef<ModFrameHandle>();
    const contextSaver = vi.fn(async () => undefined);
    render(
      <ModFrame
        ref={frameHandle}
        manifest={connectedManifest}
        eventBus={eventBus}
        theme="light"
        contextSaver={contextSaver}
        sessionIssuer={async (input) => ({
          sessionId: "session-context",
          instanceId: input.instanceId,
          accessToken: "token",
          tokenType: "Bearer",
          expiresAt: "2099-07-23T10:00:00+08:00",
          userId: input.userId,
          workspaceId: input.workspaceId,
          moduleId: input.modId,
          revision: 1,
          grants: { permissions: [], actions: [] },
        })}
      />,
    );
    const frame = screen.getByTitle("市场行情") as HTMLIFrameElement;
    const frameBoundary = frame.closest("section");
    expect(frameBoundary).toHaveAttribute("data-vibedesk-mod-id", "market-daily");
    expect(frameBoundary).toHaveAttribute("data-vibedesk-bridge-state", "pending");
    const frameWindow = frame.contentWindow;
    if (!frameWindow) throw new Error("expected iframe window");
    const postMessage = vi
      .spyOn(frameWindow, "postMessage")
      .mockImplementation(() => undefined);

    dispatchFromFrame(frame, {
      type: "vibedesk:hello",
      modId: "market-daily",
      protocolVersions: ["1.0"],
      capabilities: ["context"],
    });
    await waitFor(() =>
      expect(postMessage).toHaveBeenCalledWith(
        expect.objectContaining({ type: "vibedesk:init" }),
        "http://127.0.0.1:5891",
      ),
    );
    const init = postMessage.mock.calls.find(
      ([message]) =>
        typeof message === "object" &&
        message !== null &&
        "type" in message &&
        message.type === "vibedesk:init",
    )?.[0] as { instanceId: string };
    dispatchFromFrame(frame, {
      type: "vibedesk:ack",
      protocolVersion: "1.0",
      instanceId: init.instanceId,
      modId: "market-daily",
    });
    postMessage.mockClear();

    if (!frameHandle.current) throw new Error("expected Mod frame handle");
    const pending = frameHandle.current.requestContext("agent");
    const request = postMessage.mock.calls.find(
      ([message]) =>
        typeof message === "object" &&
        message !== null &&
        "type" in message &&
        message.type === "vibedesk:context-request" &&
        "reason" in message &&
        message.reason === "agent",
    )?.[0] as { requestId: string };
    dispatchFromFrame(frame, {
      type: "vibedesk:context",
      requestId: request.requestId,
      instanceId: init.instanceId,
      modId: "market-daily",
      context: {
        view: { id: "market-daily", title: "市场行情" },
        visibleBlocks: [],
        selection: { symbol: "600519" },
        filters: {},
        data: { freshness: "fresh" },
        actions: [],
        tasks: [],
      },
    });

    await expect(pending).resolves.toMatchObject({
      selection: { symbol: "600519" },
    });
    eventBus.close();
  });

  it("clears the loading status when the iframe finishes loading", () => {
    const eventBus = new ShellEventBus();
    render(<ModFrame manifest={manifest} eventBus={eventBus} theme="light" />);
    const frame = screen.getByTitle("市场行情") as HTMLIFrameElement;

    expect(screen.getByRole("status")).toHaveTextContent("正在加载 Mod");
    fireEvent.load(frame);
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
    eventBus.close();
  });

  it("forwards a declared event from the exact iframe window and origin", () => {
    const eventBus = new ShellEventBus();
    const route = vi.spyOn(eventBus, "route");
    render(<ModFrame manifest={manifest} eventBus={eventBus} theme="light" />);
    const frame = screen.getByTitle("市场行情") as HTMLIFrameElement;
    const valid = event();

    fireEvent.load(frame);
    dispatchFromFrame(frame, valid);

    expect(route).toHaveBeenCalledWith(valid, frame.contentWindow);
    eventBus.close();
  });

  it("resends config when a Mod reports ready before the iframe load event", () => {
    const eventBus = new ShellEventBus();
    const register = vi.spyOn(eventBus, "register");
    render(<ModFrame manifest={manifest} eventBus={eventBus} theme="light" />);
    const frame = screen.getByTitle("市场行情") as HTMLIFrameElement;
    const frameWindow = frame.contentWindow;
    if (!frameWindow) throw new Error("expected iframe window");
    const postMessage = vi
      .spyOn(frameWindow, "postMessage")
      .mockImplementation(() => undefined);

    dispatchFromFrame(frame, { type: "vibedesk:ready" });

    expect(register).toHaveBeenCalledWith({
      moduleId: "market-daily",
      manifest,
      target: frameWindow,
      origin: "http://127.0.0.1:5891",
    });
    expect(postMessage).toHaveBeenCalledWith(
      expect.objectContaining({
        type: "vibedesk:config",
        moduleId: "market-daily",
        userId: "local-user",
        workspaceId: "local-workspace",
      }),
      "http://127.0.0.1:5891",
    );
    eventBus.close();
  });

  it("opens the shared Desk copilot when the current Mod requests it", () => {
    const eventBus = new ShellEventBus();
    const onRequestCopilotOpen = vi.fn();
    render(
      <ModFrame
        manifest={manifest}
        eventBus={eventBus}
        theme="light"
        onRequestCopilotOpen={onRequestCopilotOpen}
      />,
    );
    const frame = screen.getByTitle("市场行情") as HTMLIFrameElement;

    dispatchFromFrame(frame, { type: "vibedesk:copilot-open" });

    expect(onRequestCopilotOpen).toHaveBeenCalledTimes(1);
    eventBus.close();
  });

  it("negotiates the hello, init, and acknowledgement protocol", () => {
    const eventBus = new ShellEventBus();
    const view = render(
      <ModFrame manifest={manifest} eventBus={eventBus} theme="light" />,
    );
    const frame = screen.getByTitle("市场行情") as HTMLIFrameElement;
    const frameBoundary = frame.closest("section");
    expect(frameBoundary).toHaveAttribute("data-vibedesk-mod-id", "market-daily");
    expect(frameBoundary).toHaveAttribute("data-vibedesk-bridge-state", "pending");
    const frameWindow = frame.contentWindow;
    if (!frameWindow) throw new Error("expected iframe window");
    const postMessage = vi
      .spyOn(frameWindow, "postMessage")
      .mockImplementation(() => undefined);

    fireEvent.load(frame);
    postMessage.mockClear();

    dispatchFromFrame(frame, {
      type: "vibedesk:hello",
      modId: "market-daily",
      protocolVersions: ["1.0"],
      sdkVersion: "0.2.0",
      capabilities: ["events", "actions", "theme"],
    });

    const initCall = postMessage.mock.calls.find(
      ([message]) =>
        typeof message === "object" &&
        message !== null &&
        "type" in message &&
        message.type === "vibedesk:init",
    );
    expect(initCall).toBeTruthy();
    const init = initCall?.[0] as {
      instanceId: string;
      modId: string;
      environment: { theme: string };
      grants: { permissions: string[]; actions: string[] };
    };
    expect(init).toEqual(
      expect.objectContaining({
        protocolVersion: "1.0",
        modId: "market-daily",
        user: { id: "local-user" },
        workspace: { id: "local-workspace" },
        environment: expect.objectContaining({ theme: "light" }),
        grants: { permissions: [], actions: [] },
      }),
    );

    dispatchFromFrame(frame, {
      type: "vibedesk:ack",
      protocolVersion: "1.0",
      instanceId: init.instanceId,
      modId: init.modId,
    });
    postMessage.mockClear();
    view.rerender(
      <ModFrame manifest={manifest} eventBus={eventBus} theme="dark" />,
    );

    expect(postMessage).toHaveBeenCalledWith(
      expect.objectContaining({
        type: "vibedesk:init",
        instanceId: init.instanceId,
        environment: expect.objectContaining({ theme: "dark" }),
      }),
      "http://127.0.0.1:5891",
    );
    eventBus.close();
  });

  it("reloads the iframe through the Desk-level frame handle", () => {
    const eventBus = new ShellEventBus();
    const frameHandle = createRef<ModFrameHandle>();
    render(
      <ModFrame
        ref={frameHandle}
        manifest={manifest}
        eventBus={eventBus}
        theme="light"
      />,
    );
    const frame = screen.getByTitle("市场行情") as HTMLIFrameElement;
    fireEvent.load(frame);
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
    frame.src = "about:blank";

    frameHandle.current?.reload();

    expect(frame.src).toBe(
      "http://127.0.0.1:5891/modules/market-daily/",
    );
    eventBus.close();
  });

  it("sends a scoped Desk-to-Mod UI action and resolves its result", async () => {
    const eventBus = new ShellEventBus();
    const frameHandle = createRef<ModFrameHandle>();
    render(
      <ModFrame
        ref={frameHandle}
        manifest={connectedManifest}
        eventBus={eventBus}
        theme="light"
        sessionIssuer={async (input) => ({
          sessionId: "session-ui",
          instanceId: input.instanceId,
          accessToken: "token",
          tokenType: "Bearer",
          expiresAt: "2099-07-23T10:00:00+08:00",
          userId: input.userId,
          workspaceId: input.workspaceId,
          moduleId: input.modId,
          revision: 1,
          grants: { permissions: ["market.read"], actions: ["market.set-timeframe"] },
        })}
      />,
    );
    const frame = screen.getByTitle("市场行情") as HTMLIFrameElement;
    const frameWindow = frame.contentWindow;
    if (!frameWindow) throw new Error("expected iframe window");
    const postMessage = vi.spyOn(frameWindow, "postMessage").mockImplementation(() => undefined);
    dispatchFromFrame(frame, {
      type: "vibedesk:hello",
      modId: "market-daily",
      protocolVersions: ["1.0"],
      capabilities: ["actions"],
    });
    await waitFor(() => expect(postMessage).toHaveBeenCalledWith(expect.objectContaining({ type: "vibedesk:init" }), "http://127.0.0.1:5891"));
    const init = postMessage.mock.calls.find(([message]) => typeof message === "object" && message !== null && "type" in message && message.type === "vibedesk:init")?.[0] as { instanceId: string };
    dispatchFromFrame(frame, {
      type: "vibedesk:ack",
      protocolVersion: "1.0",
      instanceId: init.instanceId,
      modId: "market-daily",
    });
    postMessage.mockClear();

    const pending = frameHandle.current?.invokeUiAction("market.set-timeframe", { timeframe: "15m" });
    const request = postMessage.mock.calls.find(([message]) => typeof message === "object" && message !== null && "type" in message && message.type === "vibedesk:ui-action-request")?.[0] as { requestId: string };
    dispatchFromFrame(frame, {
      type: "vibedesk:ui-action-result",
      requestId: request.requestId,
      instanceId: init.instanceId,
      modId: "market-daily",
      actionId: "market.set-timeframe",
      ok: true,
      result: { timeframe: "15m" },
    });

    await expect(pending).resolves.toEqual({ timeframe: "15m" });
    eventBus.close();
  });

  it("issues a scoped session, persists Mod context, and proxies actions", async () => {
    const eventBus = new ShellEventBus();
    const sessionIssuer = vi.fn(async (input: { instanceId: string }) => ({
      sessionId: "session-1",
      instanceId: input.instanceId,
      accessToken: "scoped-token",
      tokenType: "Bearer" as const,
      expiresAt: "2099-07-23T10:00:00+08:00",
      userId: "alice",
      workspaceId: "desk-1",
      moduleId: "market-daily",
      revision: 1,
      grants: {
        permissions: ["market.read"],
        actions: ["market.explain"],
      },
    }));
    const actionInvoker = vi.fn(async () => ({
      status: 202,
      body: { id: "task-1", status: "queued" },
    }));
    const contextSaver = vi.fn(async () => undefined);
    render(
      <ModFrame
        manifest={connectedManifest}
        eventBus={eventBus}
        theme="light"
        userId="alice"
        workspaceId="desk-1"
        sessionIssuer={sessionIssuer}
        actionInvoker={actionInvoker}
        contextSaver={contextSaver}
      />,
    );
    const frame = screen.getByTitle("市场行情") as HTMLIFrameElement;
    const frameBoundary = frame.closest("section");
    expect(frameBoundary).toHaveAttribute("data-vibedesk-mod-id", "market-daily");
    expect(frameBoundary).toHaveAttribute("data-vibedesk-bridge-state", "pending");
    const frameWindow = frame.contentWindow;
    if (!frameWindow) throw new Error("expected iframe window");
    const postMessage = vi
      .spyOn(frameWindow, "postMessage")
      .mockImplementation(() => undefined);

    dispatchFromFrame(frame, {
      type: "vibedesk:hello",
      modId: "market-daily",
      protocolVersions: ["1.0"],
      capabilities: ["actions", "context"],
    });
    await waitFor(() => expect(sessionIssuer).toHaveBeenCalledTimes(1));
    expect(frameBoundary).toHaveAttribute("data-vibedesk-bridge-state", "hello");
    const init = postMessage.mock.calls.find(
      ([message]) =>
        typeof message === "object" &&
        message !== null &&
        "type" in message &&
        message.type === "vibedesk:init",
    )?.[0] as { instanceId: string };
    expect(init).toEqual(
      expect.objectContaining({
        session: { id: "session-1", expiresAt: "2099-07-23T10:00:00+08:00" },
      }),
    );

    dispatchFromFrame(frame, {
      type: "vibedesk:ack",
      protocolVersion: "1.0",
      instanceId: init.instanceId,
      modId: "market-daily",
    });
    await waitFor(() =>
      expect(frameBoundary).toHaveAttribute(
        "data-vibedesk-bridge-state",
        "acknowledged",
      ),
    );
    expect(postMessage).toHaveBeenCalledWith(
      expect.objectContaining({ type: "vibedesk:context-request" }),
      "http://127.0.0.1:5891",
    );

    dispatchFromFrame(frame, {
      type: "vibedesk:context",
      requestId: "context-1",
      instanceId: init.instanceId,
      modId: "market-daily",
      context: {
        view: { id: "market-daily", title: "市场行情" },
        visibleBlocks: [],
        selection: {},
        filters: {},
        data: { freshness: "fresh" },
        actions: [{ id: "market.explain", available: true }],
        tasks: [],
      },
    });
    await waitFor(() => expect(contextSaver).toHaveBeenCalledTimes(1));
    await waitFor(() =>
      expect(frameBoundary).toHaveAttribute(
        "data-vibedesk-context-state",
        "received",
      ),
    );

    dispatchFromFrame(frame, {
      type: "vibedesk:action-request",
      requestId: "action-1",
      instanceId: init.instanceId,
      modId: "market-daily",
      actionId: "market.explain",
      input: { prompt: "解释行情" },
    });
    await waitFor(() =>
      expect(postMessage).toHaveBeenCalledWith(
        expect.objectContaining({
          type: "vibedesk:context-request",
          reason: "agent",
        }),
        "http://127.0.0.1:5891",
      ),
    );
    const agentContextRequest = postMessage.mock.calls.find(
      ([message]) =>
        typeof message === "object" &&
        message !== null &&
        "type" in message &&
        message.type === "vibedesk:context-request" &&
        "reason" in message &&
        message.reason === "agent",
    )?.[0] as { requestId: string };
    dispatchFromFrame(frame, {
      type: "vibedesk:context",
      requestId: agentContextRequest.requestId,
      instanceId: init.instanceId,
      modId: "market-daily",
      context: {
        view: { id: "market-daily", title: "市场行情" },
        visibleBlocks: [],
        selection: { symbol: "600519" },
        filters: {},
        data: { freshness: "fresh" },
        actions: [{ id: "market.explain", available: true }],
        tasks: [],
      },
    });
    await waitFor(() => expect(actionInvoker).toHaveBeenCalledTimes(1));
    expect(postMessage).toHaveBeenCalledWith(
      expect.objectContaining({
        type: "vibedesk:action-result",
        requestId: "action-1",
        ok: true,
      }),
      "http://127.0.0.1:5891",
    );
    eventBus.close();
  });

  it("forwards a changed shell theme without reloading the Mod", () => {
    const eventBus = new ShellEventBus();
    const view = render(
      <ModFrame manifest={manifest} eventBus={eventBus} theme="light" />,
    );
    const frame = screen.getByTitle("市场行情") as HTMLIFrameElement;
    const frameWindow = frame.contentWindow;
    if (!frameWindow) throw new Error("expected iframe window");
    const postMessage = vi
      .spyOn(frameWindow, "postMessage")
      .mockImplementation(() => undefined);

    fireEvent.load(frame);
    postMessage.mockClear();
    view.rerender(
      <ModFrame manifest={manifest} eventBus={eventBus} theme="dark" />,
    );

    expect(postMessage).toHaveBeenCalledWith(
      expect.objectContaining({
        type: "vibedesk:config",
        moduleId: "market-daily",
        theme: "dark",
      }),
      "http://127.0.0.1:5891",
    );
    eventBus.close();
  });

  it.each([
    ["wrong source", event(), "http://127.0.0.1:5891", window],
    ["wrong origin", event(), "https://attacker.example", null],
    [
      "wrong module id",
      event({ source: "other-module" }),
      "http://127.0.0.1:5891",
      null,
    ],
    [
      "undeclared event",
      event({ event: "date.changed" }),
      "http://127.0.0.1:5891",
      null,
    ],
  ])("ignores %s messages", (_label, data, origin, explicitSource) => {
    const eventBus = new ShellEventBus();
    const route = vi.spyOn(eventBus, "route");
    render(<ModFrame manifest={manifest} eventBus={eventBus} theme="light" />);
    const frame = screen.getByTitle("市场行情") as HTMLIFrameElement;

    fireEvent.load(frame);
    dispatchFromFrame(
      frame,
      data,
      origin,
      explicitSource === null ? frame.contentWindow : explicitSource,
    );

    expect(route).not.toHaveBeenCalled();
    eventBus.close();
  });

  it("registers only after load, replaces the registration on reload, and unregisters on cleanup", () => {
    const eventBus = new ShellEventBus();
    const register = vi.spyOn(eventBus, "register");
    const unregister = vi.spyOn(eventBus, "unregister");
    const view = render(
      <ModFrame manifest={manifest} eventBus={eventBus} theme="light" />,
    );
    const frame = screen.getByTitle("市场行情") as HTMLIFrameElement;
    const frameWindow = frame.contentWindow;
    if (!frameWindow) throw new Error("expected iframe window");
    const postMessage = vi
      .spyOn(frameWindow, "postMessage")
      .mockImplementation(() => undefined);

    eventBus.route(
      event({ target: "market-daily", traceId: "before-load" }),
    );

    expect(register).not.toHaveBeenCalled();
    expect(postMessage).not.toHaveBeenCalled();

    fireEvent.load(frame);

    expect(register).toHaveBeenCalledWith({
      moduleId: "market-daily",
      manifest,
      target: frameWindow,
      origin: "http://127.0.0.1:5891",
    });
    expect(register).toHaveBeenCalledTimes(1);
    expect(unregister).not.toHaveBeenCalled();

    eventBus.route(
      event({ target: "market-daily", traceId: "after-load" }),
    );
    expect(postMessage).toHaveBeenCalledWith(
      expect.objectContaining({ traceId: "after-load" }),
      "http://127.0.0.1:5891",
    );

    fireEvent.load(frame);
    expect(unregister).toHaveBeenCalledWith(frameWindow);
    expect(register).toHaveBeenCalledTimes(2);

    view.unmount();

    expect(unregister).toHaveBeenLastCalledWith(frameWindow);
    eventBus.close();
  });

  it("routes only declared post-load events without echoing to the source frame", () => {
    const targetManifest: ModManifest = {
      ...manifest,
      id: "research-news",
      name: "研究资讯",
      category: "research",
      entry: { type: "structured", url: "/modules/research-news/" },
      events: {
        emits: [],
        accepts: ["security.selected", "date.changed"],
      },
    };
    const eventBus = new ShellEventBus();
    render(
      <>
        <ModFrame manifest={manifest} eventBus={eventBus} theme="light" />
        <ModFrame manifest={targetManifest} eventBus={eventBus} theme="light" />
      </>,
    );
    const sourceFrame = screen.getByTitle(
      "市场行情",
    ) as HTMLIFrameElement;
    const targetFrame = screen.getByTitle("研究资讯") as HTMLIFrameElement;
    if (!sourceFrame.contentWindow || !targetFrame.contentWindow) {
      throw new Error("expected iframe windows");
    }
    const sourcePost = vi
      .spyOn(sourceFrame.contentWindow, "postMessage")
      .mockImplementation(() => undefined);
    const targetPost = vi
      .spyOn(targetFrame.contentWindow, "postMessage")
      .mockImplementation(() => undefined);

    fireEvent.load(targetFrame);
    expect(targetPost).toHaveBeenCalledWith(
      expect.objectContaining({
        type: "vibedesk:config",
        moduleId: "research-news",
      }),
      "http://127.0.0.1:5891",
    );
    targetPost.mockClear();
    dispatchFromFrame(
      sourceFrame,
      event({ target: "research-news", traceId: "before-source-load" }),
    );
    expect(targetPost).not.toHaveBeenCalled();

    fireEvent.load(sourceFrame);
    expect(sourcePost).toHaveBeenCalledWith(
      expect.objectContaining({
        type: "vibedesk:config",
        moduleId: "market-daily",
      }),
      "http://127.0.0.1:5891",
    );
    sourcePost.mockClear();
    dispatchFromFrame(
      sourceFrame,
      event({
        event: "date.changed",
        target: "research-news",
        traceId: "undeclared-event",
      }),
    );
    expect(targetPost).not.toHaveBeenCalled();

    const targeted = event({
      target: "research-news",
      traceId: "valid-targeted",
    });
    dispatchFromFrame(sourceFrame, targeted);
    expect(targetPost).toHaveBeenCalledWith(
      targeted,
      "http://127.0.0.1:5891",
    );

    targetPost.mockClear();
    dispatchFromFrame(
      sourceFrame,
      event({ target: "market-daily", traceId: "self-targeted" }),
    );
    expect(sourcePost).not.toHaveBeenCalled();
    expect(targetPost).not.toHaveBeenCalled();

    const broadcast = event({ traceId: "valid-broadcast" });
    dispatchFromFrame(sourceFrame, broadcast);
    expect(sourcePost).not.toHaveBeenCalled();
    expect(targetPost).toHaveBeenCalledWith(
      broadcast,
      "http://127.0.0.1:5891",
    );
    eventBus.close();
  });
});
