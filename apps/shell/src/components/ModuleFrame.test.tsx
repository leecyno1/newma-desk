import { createRef, useEffect, useState } from "react";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ModEvent, ModManifest } from "@newma-desk/contracts";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ModSessionRequestError } from "../api/modSessions";
import { ShellEventBus } from "../events/ShellEventBus";
import { ModFrame, type ModFrameHandle } from "./ModuleFrame";

const embeddedPage = vi.hoisted(() => ({ symbol: "600519" }));

vi.mock("./EmbeddedMarketFrame", () => ({
  default: ({
    hostConnection,
    search,
  }: {
    hostConnection?: {
      setContextProvider?: (
        provider: () => {
          actions: never[];
          data: Record<string, never>;
          filters: Record<string, never>;
          selection: { symbol: string };
          tasks: never[];
          view: { id: string; title: string };
          visibleBlocks: never[];
        },
      ) => () => void;
    };
    search: string;
  }) => {
    hostConnection?.setContextProvider?.(() => ({
      view: { id: "market-scanner", title: "市场扫描器" },
      visibleBlocks: [],
      selection: { symbol: embeddedPage.symbol },
      filters: {},
      data: {},
      actions: [],
      tasks: [],
    }));
    return <div data-testid="embedded-market-frame">{search || "terminal"}</div>;
  },
}));

vi.mock("./EmbeddedIntelligenceFrame", () => ({
  default: ({
    hostConnection,
  }: {
    hostConnection: {
      config: { environment: { theme: string } };
      subscribe(handler: (config: { environment: { theme: string } }) => void): () => void;
    };
  }) => {
    const [theme, setTheme] = useState(hostConnection.config.environment.theme);
    useEffect(() => hostConnection.subscribe((config) => setTheme(config.environment.theme)), [hostConnection]);
    return <div data-testid="embedded-intelligence-frame">{theme}</div>;
  },
}));

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

afterEach(() => {
  vi.restoreAllMocks();
  vi.useRealTimers();
  embeddedPage.symbol = "600519";
});

describe("ModFrame event boundary", () => {
  it("renders first-party market workspaces inside the Desk instead of an iframe", async () => {
    const eventBus = new ShellEventBus();
    const embeddedManifest: ModManifest = {
      ...connectedManifest,
      id: "market-scanner",
      name: "市场扫描器",
      entry: {
        type: "structured",
        url: "/mods/market-daily/?workspace=scanner",
      },
    };

    render(
      <ModFrame
        manifest={embeddedManifest}
        eventBus={eventBus}
        theme="light"
      />,
    );

    expect(await screen.findByTestId("embedded-market-frame")).toHaveTextContent(
      "?workspace=scanner",
    );
    expect(screen.queryByTitle("市场扫描器")).not.toBeInTheDocument();
    const boundary = screen.getByTestId("embedded-market-frame").closest("section");
    expect(boundary).toHaveAttribute("data-vibedesk-mod-id", "market-scanner");
    expect(boundary).toHaveAttribute("data-vibedesk-frame-state", "ready");
    eventBus.close();
  });

  it("renders the host-owned Chinese, English, and explanatory title", async () => {
    const eventBus = new ShellEventBus();
    render(
      <ModFrame
        manifest={{
          ...connectedManifest,
          presentation: {
            englishName: "Market Daily",
            description: "统一查看行情、盘口与技术指标。",
            titleOwner: "host",
          },
        }}
        eventBus={eventBus}
        theme="light"
      />,
    );

    expect(screen.getByRole("heading", { level: 1, name: "市场行情" })).toBeVisible();
    expect(screen.getByText("Market Daily")).toBeVisible();
    expect(screen.getByText("统一查看行情、盘口与技术指标。")).toBeVisible();
    eventBus.close();
  });

  it("opens a Desk-hosted standalone Mod surface without a local Agent", () => {
    const eventBus = new ShellEventBus();
    render(
      <ModFrame
        manifest={connectedManifest}
        eventBus={eventBus}
        theme="light"
      />,
    );

    const link = screen.getByRole("link", { name: "独立打开" });
    const url = new URL(link.getAttribute("href") ?? "", window.location.href);
    expect(url.origin).toBe(window.location.origin);
    expect(url.searchParams.get("mod")).toBe("market-daily");
    expect(url.searchParams.get("copilot")).toBeNull();
    expect(url.searchParams.get("standalone")).toBe("1");
    expect(url.pathname).not.toBe("/modules/market-daily/");
    eventBus.close();
  });

  it("gives canvas presentations the full frame without the host toolbar", () => {
    const eventBus = new ShellEventBus();
    render(
      <ModFrame
        manifest={{
          ...connectedManifest,
          presentation: {
            englishName: "Market Daily",
            description: "统一查看行情、盘口与技术指标。",
            titleOwner: "host",
            chrome: "canvas",
          },
        }}
        eventBus={eventBus}
        theme="light"
      />,
    );

    expect(
      screen.queryByRole("heading", { level: 1, name: "市场行情" }),
    ).not.toBeInTheDocument();
    const frame = screen.getByTitle("市场行情");
    expect(frame.closest("section")).toHaveAttribute(
      "data-vibedesk-chrome",
      "canvas",
    );
    eventBus.close();
  });

  it("accepts an initial context request for an embedded first-party workspace", async () => {
    const eventBus = new ShellEventBus();
    const frameHandle = createRef<ModFrameHandle>();
    render(
      <ModFrame
        ref={frameHandle}
        manifest={{
          ...connectedManifest,
          id: "market-scanner",
          name: "市场扫描器",
          entry: {
            type: "structured",
            url: "/mods/market-daily/?workspace=scanner",
          },
        }}
        eventBus={eventBus}
        theme="light"
      />,
    );
    expect(await screen.findByTestId("embedded-market-frame")).toBeVisible();
    await expect(
      frameHandle.current?.requestContext("initial"),
    ).resolves.toMatchObject({ selection: { symbol: "600519" } });
    embeddedPage.symbol = "000001";
    await expect(
      frameHandle.current?.requestContext("agent"),
    ).resolves.toMatchObject({ selection: { symbol: "000001" } });
    eventBus.close();
  });

  it("updates the embedded intelligence theme with the Desk", async () => {
    const eventBus = new ShellEventBus();
    const intelligenceManifest: ModManifest = {
      ...connectedManifest,
      id: "global-situation",
      name: "全球情报",
      entry: {
        type: "structured",
        url: "/mods/global-intelligence/",
      },
    };
    const view = render(
      <ModFrame
        manifest={intelligenceManifest}
        eventBus={eventBus}
        theme="light"
      />,
    );

    expect(await screen.findByTestId("embedded-intelligence-frame")).toHaveTextContent("light");
    view.rerender(
      <ModFrame
        manifest={intelligenceManifest}
        eventBus={eventBus}
        theme="dark"
      />,
    );
    expect(screen.getByTestId("embedded-intelligence-frame")).toHaveTextContent("dark");
    eventBus.close();
  });

  it("exposes a page-context request to the Desk-level copilot", async () => {
    const eventBus = new ShellEventBus();
    const frameHandle = createRef<ModFrameHandle>();
    const contextSaver = vi.fn(async (_session: { accessToken: string }) => undefined);
    const mounted = render(
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
    vi.spyOn(frame, "contentDocument", "get").mockReturnValue(null);
    vi.useFakeTimers();
    const timedOut = frameHandle.current.requestContext("agent");
    await act(async () => { await vi.advanceTimersByTimeAsync(5000); });
    await expect(timedOut).resolves.toBeUndefined();
    const detached = frameHandle.current.requestContext("agent");
    mounted.unmount();
    await expect(detached).resolves.toBeUndefined();
    eventBus.close();
  });

  it("uploads a Mod-provided current visual capture for the Desk copilot", async () => {
    const eventBus = new ShellEventBus();
    const frameHandle = createRef<ModFrameHandle>();
    const visualContextSaver = vi.fn(async () => ({
      status: "ready" as const,
      source: "browser-mod-bridge" as const,
      capturedAt: "2026-08-28T00:00:00+00:00",
      moduleId: "market-daily",
      image: {
        artifactId: "0123456789abcdef0123456789abcdef",
        mimeType: "image/png" as const,
        width: 1280,
        height: 720,
        bytes: 4,
      },
    }));
    render(
      <ModFrame
        ref={frameHandle}
        manifest={connectedManifest}
        eventBus={eventBus}
        theme="light"
        visualContextSaver={visualContextSaver}
        sessionIssuer={async (input) => ({
          sessionId: "session-visual",
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
    const frameWindow = frame.contentWindow;
    if (!frameWindow || !frameHandle.current) throw new Error("expected Mod frame");
    const postMessage = vi
      .spyOn(frameWindow, "postMessage")
      .mockImplementation(() => undefined);

    dispatchFromFrame(frame, {
      type: "vibedesk:hello",
      modId: "market-daily",
      protocolVersions: ["1.0"],
      capabilities: ["context", "visual-context"],
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

    const rawPending = frameHandle.current.requestVisualCapture("agent");
    const rawRequest = postMessage.mock.calls.find(
      ([message]) =>
        typeof message === "object" &&
        message !== null &&
        "type" in message &&
        message.type === "vibedesk:visual-context-request",
    )?.[0] as { requestId: string };
    dispatchFromFrame(frame, {
      type: "vibedesk:visual-context",
      requestId: rawRequest.requestId,
      instanceId: init.instanceId,
      modId: "market-daily",
      ok: true,
      capture: {
        dataUrl: "data:image/png;base64,iVBORw==",
        width: 1280,
        height: 720,
        capturedAt: "2026-08-28T00:00:00+08:00",
        title: "当前市场曲面",
      },
    });
    await expect(rawPending).resolves.toMatchObject({
      width: 1280,
      height: 720,
      title: "当前市场曲面",
    });
    expect(visualContextSaver).not.toHaveBeenCalled();

    postMessage.mockClear();
    const pending = frameHandle.current.requestVisualContext("agent");
    const request = postMessage.mock.calls.find(
      ([message]) =>
        typeof message === "object" &&
        message !== null &&
        "type" in message &&
        message.type === "vibedesk:visual-context-request",
    )?.[0] as { requestId: string };
    dispatchFromFrame(frame, {
      type: "vibedesk:visual-context",
      requestId: request.requestId,
      instanceId: init.instanceId,
      modId: "market-daily",
      ok: true,
      capture: {
        dataUrl: "data:image/png;base64,iVBORw==",
        width: 1280,
        height: 720,
        capturedAt: "2026-08-28T00:00:00+08:00",
        title: "当前市场曲面",
      },
    });

    await expect(pending).resolves.toMatchObject({
      source: "browser-mod-bridge",
      image: { artifactId: "0123456789abcdef0123456789abcdef" },
    });
    expect(visualContextSaver).toHaveBeenCalledWith(
      expect.objectContaining({ moduleId: "market-daily" }),
      expect.objectContaining({ title: "当前市场曲面" }),
    );

    postMessage.mockClear();
    const evidencePending = frameHandle.current.requestAgentEvidence("agent");
    const contextRequest = postMessage.mock.calls.find(
      ([message]) =>
        typeof message === "object" &&
        message !== null &&
        "type" in message &&
        message.type === "vibedesk:context-request",
    )?.[0] as { requestId: string };
    dispatchFromFrame(frame, {
      type: "vibedesk:context",
      requestId: contextRequest.requestId,
      instanceId: init.instanceId,
      modId: "market-daily",
      context: {
        view: { id: "market-daily", title: "当前市场曲面" },
        visibleBlocks: [],
        selection: {},
        filters: {},
        data: {
          freshness: "fresh",
          summary: {
            contextSource: "dom-html-fallback",
            visibleText: "当前市场曲面",
            visualElementCount: 1,
          },
        },
        actions: [],
        tasks: [],
      },
    });
    await waitFor(() =>
      expect(postMessage).toHaveBeenCalledWith(
        expect.objectContaining({ type: "vibedesk:visual-context-request" }),
        "http://127.0.0.1:5891",
      ),
    );
    const evidenceVisualRequest = postMessage.mock.calls.find(
      ([message]) =>
        typeof message === "object" &&
        message !== null &&
        "type" in message &&
        message.type === "vibedesk:visual-context-request",
    )?.[0] as { requestId: string };
    dispatchFromFrame(frame, {
      type: "vibedesk:visual-context",
      requestId: evidenceVisualRequest.requestId,
      instanceId: init.instanceId,
      modId: "market-daily",
      ok: true,
      capture: {
        dataUrl: "data:image/png;base64,iVBORw==",
        width: 1280,
        height: 720,
        capturedAt: "2026-08-28T00:00:00+08:00",
        title: "当前市场曲面",
      },
    });

    await expect(evidencePending).resolves.toMatchObject({
      source: "dom-html",
      freshness: "fresh",
      visual: {
        source: "browser-mod-bridge",
        image: { artifactId: "0123456789abcdef0123456789abcdef" },
      },
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

  it("allows a user-clicked embedded link to open a Desk-level settings page", () => {
    const eventBus = new ShellEventBus();
    render(<ModFrame manifest={manifest} eventBus={eventBus} theme="light" />);
    expect(screen.getByTitle("市场行情")).toHaveAttribute(
      "sandbox",
      expect.stringContaining("allow-top-navigation-by-user-activation"),
    );
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

  it("forwards a scoped Mod Agent request after the bridge handshake", async () => {
    const eventBus = new ShellEventBus();
    const onRequestCopilotOpen = vi.fn();
    render(
      <ModFrame
        manifest={manifest}
        eventBus={eventBus}
        theme="light"
        agentRuntime={{ mode: "local", request: onRequestCopilotOpen }}
      />,
    );
    const frame = screen.getByTitle("市场行情") as HTMLIFrameElement;
    const frameWindow = frame.contentWindow;
    if (!frameWindow) throw new Error("expected iframe window");
    const postMessage = vi
      .spyOn(frameWindow, "postMessage")
      .mockImplementation(() => undefined);

    dispatchFromFrame(frame, {
      type: "vibedesk:hello",
      modId: "market-daily",
      protocolVersions: ["1.0"],
      capabilities: ["agent", "context"],
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
    )?.[0] as {
      instanceId: string;
      runtime?: { owner: string; aiExecution: string; requestMessage: string };
    };
    expect(init.runtime).toEqual({
      owner: "desk",
      aiExecution: "gateway",
      requestMessage: "vibedesk:copilot-open",
    });
    dispatchFromFrame(frame, {
      type: "vibedesk:ack",
      protocolVersion: "1.0",
      instanceId: init.instanceId,
      modId: "market-daily",
    });

    dispatchFromFrame(frame, {
      type: "vibedesk:copilot-open",
      instanceId: init.instanceId,
      modId: "market-daily",
      mode: "edit",
      prompt: "按分镜完成粗剪",
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
    const contextRequest = postMessage.mock.calls.find(
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
      requestId: contextRequest.requestId,
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
    await waitFor(() => {
      expect(onRequestCopilotOpen).toHaveBeenCalledTimes(1);
      expect(onRequestCopilotOpen).toHaveBeenCalledWith({
        mode: "edit",
        prompt: "按分镜完成粗剪",
      });
    });
    eventBus.close();
  });

  it("uses the explicit Runtime Binding instead of presentation embedding", async () => {
    const eventBus = new ShellEventBus();
    render(
      <ModFrame
        manifest={manifest}
        eventBus={eventBus}
        theme="light"
        agentRuntime={{ mode: "newma", request: vi.fn() }}
      />,
    );
    const frame = screen.getByTitle("市场行情") as HTMLIFrameElement;
    const frameWindow = frame.contentWindow;
    if (!frameWindow) throw new Error("expected iframe window");
    const postMessage = vi
      .spyOn(frameWindow, "postMessage")
      .mockImplementation(() => undefined);

    dispatchFromFrame(frame, {
      type: "vibedesk:hello",
      modId: "market-daily",
      protocolVersions: ["1.0"],
      capabilities: ["agent"],
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
    )?.[0] as {
      runtime?: { owner: string; aiExecution: string; requestMessage: string };
      gateways: { agent?: string; model?: string };
    };
    expect(init.runtime).toEqual({
      owner: "newma",
      aiExecution: "host",
      requestMessage: "vibedesk:copilot-open",
    });
    expect(init.gateways.agent).toBeUndefined();
    expect(init.gateways.model).toBeUndefined();
    eventBus.close();
  });

  it("rejects unscoped or undeclared Mod Agent requests", async () => {
    const eventBus = new ShellEventBus();
    const onRequestCopilotOpen = vi.fn();
    render(
      <ModFrame
        manifest={manifest}
        eventBus={eventBus}
        theme="light"
        agentRuntime={{ mode: "local", request: onRequestCopilotOpen }}
      />,
    );
    const frame = screen.getByTitle("市场行情") as HTMLIFrameElement;
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

    dispatchFromFrame(frame, {
      type: "vibedesk:copilot-open",
      mode: "ask",
      prompt: "缺少作用域",
    });
    dispatchFromFrame(frame, {
      type: "vibedesk:copilot-open",
      instanceId: init.instanceId,
      modId: "market-daily",
      mode: "ask",
      prompt: "未声明 Agent 能力",
    });

    await Promise.resolve();
    expect(onRequestCopilotOpen).not.toHaveBeenCalled();
    expect(postMessage).not.toHaveBeenCalledWith(
      expect.objectContaining({
        type: "vibedesk:context-request",
        reason: "agent",
      }),
      "http://127.0.0.1:5891",
    );
    eventBus.close();
  });

  it("negotiates the hello, init, and acknowledgement protocol", () => {
    const eventBus = new ShellEventBus();
    const onNavigate = vi.fn();
    const view = render(
      <ModFrame manifest={manifest} eventBus={eventBus} theme="light" onNavigate={onNavigate} />,
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
      appearance: {
        mode: string;
        cssVars: Record<string, string>;
      };
      grants: { permissions: string[]; actions: string[] };
    };
    expect(init).toEqual(
      expect.objectContaining({
        protocolVersion: "1.0",
        modId: "market-daily",
        user: { id: "local-user" },
        workspace: { id: "local-workspace" },
        environment: expect.objectContaining({ theme: "light" }),
        appearance: expect.objectContaining({
          mode: "light",
          cssVars: expect.objectContaining({
            "--vibe-bg": "#f4efe3",
            "--vibe-accent": "#a87432",
          }),
        }),
        gateways: expect.not.objectContaining({
          agent: expect.anything(),
          model: expect.anything(),
        }),
        grants: { permissions: [], actions: [] },
      }),
    );
    expect(init).not.toHaveProperty("runtime");

    const navigation = { type: 'vibedesk:navigate', modId: init.modId,
      instanceId: init.instanceId, targetModId: 'fund-discover', search: 'symbol=000171.OF' };
    dispatchFromFrame(frame, navigation);
    expect(onNavigate).not.toHaveBeenCalled();

    dispatchFromFrame(frame, {
      type: "vibedesk:ack",
      protocolVersion: "1.0",
      instanceId: init.instanceId,
      modId: init.modId,
    });
    postMessage.mockClear();
    dispatchFromFrame(frame, navigation, 'https://untrusted.example');
    dispatchFromFrame(frame, { ...navigation, instanceId: 'old-instance' });
    dispatchFromFrame(frame, navigation, 'http://127.0.0.1:5891', window);
    expect(onNavigate).not.toHaveBeenCalled();
    dispatchFromFrame(frame, navigation);
    expect(onNavigate).toHaveBeenCalledExactlyOnceWith('fund-discover', 'symbol=000171.OF');
    view.rerender(
      <ModFrame manifest={manifest} eventBus={eventBus} theme="dark" />,
    );

    expect(postMessage).toHaveBeenCalledWith(
      expect.objectContaining({
        type: "vibedesk:init",
        instanceId: init.instanceId,
        environment: expect.objectContaining({ theme: "dark" }),
        appearance: expect.objectContaining({
          mode: "dark",
          cssVars: expect.objectContaining({
            "--vibe-bg": "#0f1714",
            "--vibe-accent": "#c89a5a",
          }),
        }),
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
      "http://127.0.0.1:5891/modules/market-daily/?__newma_mod_version=0.1.0",
    );
    eventBus.close();
  });

  it("revalidates a local external Mod when its version changes", () => {
    const eventBus = new ShellEventBus();
    render(
      <ModFrame
        manifest={{ ...manifest, id: "seven-cycle-research", name: "周期叠加", version: "0.1.1", entry: { type: "external", url: "http://127.0.0.1:4174/" } }}
        eventBus={eventBus}
        theme="light"
      />,
    );
    expect((screen.getByTitle("周期叠加") as HTMLIFrameElement).src).toBe(
      "http://127.0.0.1:4174/?__newma_mod_version=0.1.1",
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

  it("queues a Wiki handoff until the target Mod finishes its handshake", async () => {
    const eventBus = new ShellEventBus();
    const frameHandle = createRef<ModFrameHandle>();
    render(
      <ModFrame
        ref={frameHandle}
        manifest={connectedManifest}
        eventBus={eventBus}
        theme="light"
        sessionIssuer={async (input) => ({
          sessionId: "session-handoff",
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
    const frameWindow = frame.contentWindow;
    if (!frameWindow || !frameHandle.current) throw new Error("expected Mod frame");
    const postMessage = vi.spyOn(frameWindow, "postMessage").mockImplementation(() => undefined);
    const handoff = {
      version: 1 as const,
      id: "hf_test1234",
      sourceModId: "event-timeline",
      targetModId: "market-daily",
      entrypointId: "overview",
      subject: {
        type: "security" as const,
        canonicalId: "security:CN:300308",
        displayName: "中际旭创",
        market: "CN" as const,
        symbol: "300308",
        assetType: "stock" as const,
      },
      relatedSubjects: [],
      conceptIds: [],
      intent: "market.overview",
      timeframe: "daily",
      parameters: {},
      createdAt: "2026-08-15T10:00:00+08:00",
      expiresAt: "2026-08-15T10:05:00+08:00",
    };

    const pending = frameHandle.current.deliverHandoff(handoff);
    expect(postMessage).not.toHaveBeenCalledWith(
      expect.objectContaining({ type: "vibedesk:handoff" }),
      expect.anything(),
    );
    dispatchFromFrame(frame, {
      type: "vibedesk:hello",
      modId: "market-daily",
      protocolVersions: ["1.0"],
      capabilities: ["handoff"],
    });
    await waitFor(() => expect(postMessage).toHaveBeenCalledWith(
      expect.objectContaining({ type: "vibedesk:init" }),
      "http://127.0.0.1:5891",
    ));
    const init = postMessage.mock.calls.find(
      ([message]) => typeof message === "object" && message !== null && "type" in message && message.type === "vibedesk:init",
    )?.[0] as { instanceId: string };
    dispatchFromFrame(frame, {
      type: "vibedesk:ack",
      protocolVersion: "1.0",
      instanceId: init.instanceId,
      modId: "market-daily",
    });
    const request = postMessage.mock.calls.find(
      ([message]) => typeof message === "object" && message !== null && "type" in message && message.type === "vibedesk:handoff",
    )?.[0] as { requestId: string };
    expect(request).toBeDefined();
    dispatchFromFrame(frame, {
      type: "vibedesk:handoff-result",
      requestId: request.requestId,
      instanceId: init.instanceId,
      modId: "market-daily",
      handoffId: handoff.id,
      ok: true,
      result: { selected: "300308" },
    });

    await expect(pending).resolves.toEqual({ selected: "300308" });
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
    const contextSaver = vi.fn(async (_session: { accessToken: string }) => undefined);
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
        session: {
          id: "session-1",
          accessToken: "scoped-token",
          expiresAt: "2099-07-23T10:00:00+08:00",
        },
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

  it("renews an invalid Mod session and retries context persistence once", async () => {
    const eventBus = new ShellEventBus();
    const sessionIssuer = vi.fn(async (input: { instanceId: string }) => {
      const generation = sessionIssuer.mock.calls.length;
      return {
        sessionId: `session-${generation}`,
        instanceId: input.instanceId,
        accessToken: `token-${generation}`,
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
      };
    });
    const contextSaver = vi
      .fn()
      .mockRejectedValueOnce(new ModSessionRequestError(401, "expired"))
      .mockResolvedValueOnce(undefined);
    render(
      <ModFrame
        manifest={connectedManifest}
        eventBus={eventBus}
        theme="light"
        userId="alice"
        workspaceId="desk-1"
        sessionIssuer={sessionIssuer}
        contextSaver={contextSaver}
      />,
    );
    const frame = screen.getByTitle("市场行情") as HTMLIFrameElement;
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
    await waitFor(() => expect(sessionIssuer).toHaveBeenCalledTimes(1));
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
    dispatchFromFrame(frame, {
      type: "vibedesk:context",
      requestId: "context-retry",
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

    await waitFor(() => expect(contextSaver).toHaveBeenCalledTimes(2));
    expect(sessionIssuer).toHaveBeenCalledTimes(2);
    expect(contextSaver.mock.calls[0]?.[0].accessToken).toBe("token-1");
    expect(contextSaver.mock.calls[1]?.[0].accessToken).toBe("token-2");
    expect(postMessage).toHaveBeenCalledWith(
      expect.objectContaining({
        type: "vibedesk:init",
        session: expect.objectContaining({ accessToken: "token-2" }),
      }),
      "http://127.0.0.1:5891",
    );
    eventBus.close();
  });

  it("pushes a proactively renewed session to the Mod before persisting context", async () => {
    const eventBus = new ShellEventBus();
    const sessionIssuer = vi.fn(async (input: { instanceId: string }) => {
      const generation = sessionIssuer.mock.calls.length;
      return {
        sessionId: `session-${generation}`,
        instanceId: input.instanceId,
        accessToken: `token-${generation}`,
        tokenType: "Bearer" as const,
        expiresAt:
          generation === 1
            ? new Date(Date.now() + 10_000).toISOString()
            : "2099-07-23T10:00:00+08:00",
        userId: "alice",
        workspaceId: "desk-1",
        moduleId: "market-daily",
        revision: generation,
        grants: {
          permissions: ["market.read", "storage.read", "storage.write"],
          actions: ["market.explain"],
        },
      };
    });
    const contextSaver = vi.fn(async (_session: { accessToken: string }) => undefined);
    render(
      <ModFrame
        manifest={connectedManifest}
        eventBus={eventBus}
        theme="light"
        userId="alice"
        workspaceId="desk-1"
        sessionIssuer={sessionIssuer}
        contextSaver={contextSaver}
      />,
    );
    const frame = screen.getByTitle("市场行情") as HTMLIFrameElement;
    const frameWindow = frame.contentWindow;
    if (!frameWindow) throw new Error("expected iframe window");
    const postMessage = vi
      .spyOn(frameWindow, "postMessage")
      .mockImplementation(() => undefined);

    dispatchFromFrame(frame, {
      type: "vibedesk:hello",
      modId: "market-daily",
      protocolVersions: ["1.0"],
      capabilities: ["context", "storage"],
    });
    await waitFor(() => expect(sessionIssuer).toHaveBeenCalledTimes(1));
    const firstInit = postMessage.mock.calls.find(
      ([message]) =>
        typeof message === "object" &&
        message !== null &&
        "type" in message &&
        message.type === "vibedesk:init",
    )?.[0] as { instanceId: string };
    dispatchFromFrame(frame, {
      type: "vibedesk:ack",
      protocolVersion: "1.0",
      instanceId: firstInit.instanceId,
      modId: "market-daily",
    });
    postMessage.mockClear();

    dispatchFromFrame(frame, {
      type: "vibedesk:context",
      requestId: "context-proactive-renewal",
      instanceId: firstInit.instanceId,
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

    await waitFor(() => expect(contextSaver).toHaveBeenCalledTimes(1));
    expect(sessionIssuer).toHaveBeenCalledTimes(2);
    expect(contextSaver.mock.calls[0]?.[0].accessToken).toBe("token-2");
    expect(postMessage.mock.invocationCallOrder[0]).toBeLessThan(
      contextSaver.mock.invocationCallOrder[0]!,
    );
    expect(postMessage).toHaveBeenCalledWith(
      expect.objectContaining({
        type: "vibedesk:init",
        session: expect.objectContaining({ accessToken: "token-2" }),
      }),
      "http://127.0.0.1:5891",
    );
    eventBus.close();
  });

  it("does not renew a valid session for an authorization failure", async () => {
    const eventBus = new ShellEventBus();
    const sessionIssuer = vi.fn(async (input: { instanceId: string }) => ({
      sessionId: "session-1",
      instanceId: input.instanceId,
      accessToken: "token-1",
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
    const contextSaver = vi.fn(async () => {
      throw new ModSessionRequestError(403, "forbidden");
    });
    render(
      <ModFrame
        manifest={connectedManifest}
        eventBus={eventBus}
        theme="light"
        userId="alice"
        workspaceId="desk-1"
        sessionIssuer={sessionIssuer}
        contextSaver={contextSaver}
      />,
    );
    const frame = screen.getByTitle("市场行情") as HTMLIFrameElement;
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
    await waitFor(() => expect(sessionIssuer).toHaveBeenCalledTimes(1));
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
    dispatchFromFrame(frame, {
      type: "vibedesk:context",
      requestId: "context-forbidden",
      instanceId: init.instanceId,
      modId: "market-daily",
      context: {
        view: { id: "market-daily", title: "市场行情" },
        visibleBlocks: [],
        selection: { symbol: "600519" },
        filters: {},
        data: {},
        actions: [],
        tasks: [],
      },
    });

    await waitFor(() => expect(contextSaver).toHaveBeenCalledTimes(1));
    expect(sessionIssuer).toHaveBeenCalledTimes(1);
    expect(
      postMessage.mock.calls.filter(
        ([message]) =>
          typeof message === "object" &&
          message !== null &&
          "type" in message &&
          message.type === "vibedesk:init",
      ),
    ).toHaveLength(1);
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
        appearance: expect.objectContaining({
          mode: "dark",
          cssVars: expect.objectContaining({
            "--vibe-accent": "#c89a5a",
          }),
        }),
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
