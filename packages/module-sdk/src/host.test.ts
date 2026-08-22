import { describe, expect, it, vi } from "vitest";

import {
  applyDeskAppearance,
  connectModHost,
  type ModHostRuntime,
} from "./host";

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

function createAppearance(
  mode: "light" | "dark",
  cssVars: Record<string, string>,
  bg = mode === "dark" ? "#0f1714" : "#f4efe3",
) {
  return {
    contractVersion: "1.0" as const,
    mode,
    cssVars,
    semantic: {
      bg,
      surface: mode === "dark" ? "#16211c" : "#fbf7ef",
      surfaceMuted: mode === "dark" ? "#121d18" : "#f6f0e2",
      surfaceRaised: mode === "dark" ? "#1a2821" : "#fffaf1",
      border: mode === "dark" ? "#2a3931" : "#d6cab5",
      borderStrong: mode === "dark" ? "#405146" : "#baa17d",
      text: mode === "dark" ? "#f3ecdd" : "#173128",
      textSoft: mode === "dark" ? "#cfc7b7" : "#345347",
      textMuted: mode === "dark" ? "#a8b4a5" : "#60756a",
      textFaint: mode === "dark" ? "#78847a" : "#7f8f85",
      accent: mode === "dark" ? "#c89a5a" : "#a87432",
      accentHover: mode === "dark" ? "#dab47d" : "#bb8a47",
      accentSoft: mode === "dark" ? "#5a452c" : "#ead8ba",
      accentSurface: mode === "dark" ? "#2c2a21" : "#f2e8d5",
      accentContrast: mode === "dark" ? "#102019" : "#173128",
      positive: mode === "dark" ? "#f87171" : "#dc2626",
      negative: mode === "dark" ? "#4ade80" : "#16a34a",
      warning: "#fbbf24",
      error: mode === "dark" ? "#f87171" : "#dc2626",
      successText: mode === "dark" ? "#86efac" : "#166534",
      successBg: mode === "dark" ? "#0d2818" : "#dcfce7",
      successBorder: "#166534",
      errorText: mode === "dark" ? "#fca5a5" : "#991b1b",
      errorBg: mode === "dark" ? "#321417" : "#fee2e2",
      errorBorder: "#7f1d1d",
    },
    charts: {
      gridColor: mode === "dark" ? "#2a3931" : "#d6cab5",
      textColor: mode === "dark" ? "#a8b4a5" : "#60756a",
      axisColor: mode === "dark" ? "#405146" : "#baa17d",
      upColor: mode === "dark" ? "#f87171" : "#dc2626",
      downColor: mode === "dark" ? "#4ade80" : "#16a34a",
      tooltipBg: mode === "dark" ? "#1a2821" : "#fffaf1",
      tooltipBorder: mode === "dark" ? "#405146" : "#baa17d",
      tooltipText: mode === "dark" ? "#f3ecdd" : "#173128",
      series: [mode === "dark" ? "#c89a5a" : "#a87432", mode === "dark" ? "#70a596" : "#3f7667"],
    },
  };
}

function createThemeRoot() {
  const properties = new Map<string, string>();
  const classes = new Set<string>();
  const dispatchEvent = vi.fn();
  const setThemeColor = vi.fn();
  class ThemeEvent {
    constructor(
      readonly type: string,
      readonly init: { detail: unknown },
    ) {}
  }
  const ownerDocument = {
    querySelector: vi.fn(() => ({ setAttribute: setThemeColor })),
    defaultView: {
      CustomEvent: ThemeEvent,
      dispatchEvent,
    },
  };
  const root = {
    dataset: {} as Record<string, string>,
    classList: {
      toggle(name: string, enabled: boolean) {
        if (enabled) classes.add(name);
        else classes.delete(name);
      },
      contains(name: string) {
        return classes.has(name);
      },
    },
    style: {
      colorScheme: "",
      setProperty(name: string, value: string) {
        properties.set(name, value);
      },
      removeProperty(name: string) {
        properties.delete(name);
      },
      getPropertyValue(name: string) {
        return properties.get(name) ?? "";
      },
    },
    ownerDocument,
  } as unknown as HTMLElement;
  return { root, properties, classes, dispatchEvent, setThemeColor, ownerDocument };
}

describe("connectModHost", () => {
  it("applies the Newma palette, mode classes, and theme event", () => {
    const { root, classes, dispatchEvent, setThemeColor } = createThemeRoot();

    applyDeskAppearance(
      {
        environment: { theme: "dark" },
        appearance: createAppearance("dark", {
          "--vibe-bg": "#0f1714",
          "--vibe-accent": "#c89a5a",
        }),
      },
      root,
    );

    expect(root.dataset.theme).toBe("dark");
    expect(root.dataset.vibedeskTheme).toBe("dark");
    expect(root.dataset.bsTheme).toBe("dark");
    expect(root.classList.contains("dark")).toBe(true);
    expect(root.classList.contains("light")).toBe(false);
    expect(root.style.colorScheme).toBe("dark");
    expect(root.style.getPropertyValue("--vibe-accent")).toBe("#c89a5a");
    expect(setThemeColor).toHaveBeenCalledWith("content", "#0f1714");
    expect(dispatchEvent).toHaveBeenCalledWith(
      expect.objectContaining({ type: "newma:themechange" }),
    );

    applyDeskAppearance({ environment: { theme: "light" } }, root);

    expect(root.dataset.theme).toBe("light");
    expect(root.dataset.bsTheme).toBe("light");
    expect(root.classList.contains("dark")).toBe(false);
    expect(root.classList.contains("light")).toBe(true);
    expect(root.style.getPropertyValue("--vibe-accent")).toBe("");
    expect(setThemeColor).toHaveBeenLastCalledWith("content", "#f4efe3");
  });

  it("clears stale CSS variables when appearance shrinks, disappears, or mismatches the active mode", () => {
    const { root, dispatchEvent, setThemeColor } = createThemeRoot();

    applyDeskAppearance(
      {
        environment: { theme: "dark" },
        appearance: createAppearance("dark", {
          "--vibe-bg": "#0f1714",
          "--vibe-accent": "#c89a5a",
          "--chart-series-1": "#70a596",
        }),
      },
      root,
    );
    expect(root.style.getPropertyValue("--vibe-accent")).toBe("#c89a5a");
    expect(root.style.getPropertyValue("--chart-series-1")).toBe("#70a596");

    applyDeskAppearance(
      {
        environment: { theme: "dark" },
        appearance: createAppearance("dark", {
          "--vibe-bg": "#16211c",
        }, "#16211c"),
      },
      root,
    );
    expect(root.style.getPropertyValue("--vibe-bg")).toBe("#16211c");
    expect(root.style.getPropertyValue("--vibe-accent")).toBe("");
    expect(root.style.getPropertyValue("--chart-series-1")).toBe("");
    expect(setThemeColor).toHaveBeenLastCalledWith("content", "#16211c");

    applyDeskAppearance({ environment: { theme: "dark" } }, root);
    expect(root.style.getPropertyValue("--vibe-bg")).toBe("");
    expect(setThemeColor).toHaveBeenLastCalledWith("content", "#0f1714");

    applyDeskAppearance(
      {
        environment: { theme: "dark" },
        appearance: createAppearance("light", {
          "--vibe-accent": "#a87432",
        }),
      },
      root,
    );
    expect(root.style.getPropertyValue("--vibe-accent")).toBe("");
    expect(dispatchEvent).toHaveBeenLastCalledWith(
      expect.objectContaining({
        type: "newma:themechange",
        init: { detail: { mode: "dark" } },
      }),
    );
  });

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

  it("uses Newma light as the standalone default and preserves an explicit dark mode", async () => {
    const lightTheme = createThemeRoot();
    const lightWindow = {
      document: { documentElement: lightTheme.root },
    } as unknown as Window;
    Object.assign(lightWindow, { parent: lightWindow });

    await connectModHost(
      { modId: "market-daily", parentOrigin: "https://desk.example" },
      {
        window: lightWindow,
        setTimeout: globalThis.setTimeout.bind(globalThis),
        clearTimeout: globalThis.clearTimeout.bind(globalThis),
      },
    );

    expect(lightTheme.root.dataset.theme).toBe("light");
    expect(lightTheme.root.dataset.vibedeskTheme).toBe("light");
    expect(lightTheme.root.dataset.vibedeskEmbedded).toBe("false");
    expect(lightTheme.root.style.colorScheme).toBe("light");

    const darkTheme = createThemeRoot();
    darkTheme.root.dataset.theme = "dark";
    const darkWindow = {
      document: { documentElement: darkTheme.root },
    } as unknown as Window;
    Object.assign(darkWindow, { parent: darkWindow });

    await connectModHost(
      { modId: "market-daily", parentOrigin: "https://desk.example" },
      {
        window: darkWindow,
        setTimeout: globalThis.setTimeout.bind(globalThis),
        clearTimeout: globalThis.clearTimeout.bind(globalThis),
      },
    );

    expect(darkTheme.root.dataset.theme).toBe("dark");
    expect(darkTheme.root.dataset.vibedeskTheme).toBe("dark");
    expect(darkTheme.root.style.colorScheme).toBe("dark");
  });

  it("recognizes standalone dark markers from data-vibedesk-theme, data-bs-theme, and .dark", async () => {
    const embeddedDarkTheme = createThemeRoot();
    embeddedDarkTheme.root.dataset.vibedeskTheme = "dark";
    const embeddedDarkWindow = {
      document: { documentElement: embeddedDarkTheme.root },
    } as unknown as Window;
    Object.assign(embeddedDarkWindow, { parent: embeddedDarkWindow });

    await connectModHost(
      { modId: "market-daily", parentOrigin: "https://desk.example" },
      {
        window: embeddedDarkWindow,
        setTimeout: globalThis.setTimeout.bind(globalThis),
        clearTimeout: globalThis.clearTimeout.bind(globalThis),
      },
    );

    expect(embeddedDarkTheme.root.dataset.theme).toBe("dark");
    expect(embeddedDarkTheme.root.dataset.bsTheme).toBe("dark");

    const bootstrapDarkTheme = createThemeRoot();
    bootstrapDarkTheme.root.dataset.bsTheme = "dark";
    const bootstrapDarkWindow = {
      document: { documentElement: bootstrapDarkTheme.root },
    } as unknown as Window;
    Object.assign(bootstrapDarkWindow, { parent: bootstrapDarkWindow });

    await connectModHost(
      { modId: "market-daily", parentOrigin: "https://desk.example" },
      {
        window: bootstrapDarkWindow,
        setTimeout: globalThis.setTimeout.bind(globalThis),
        clearTimeout: globalThis.clearTimeout.bind(globalThis),
      },
    );

    expect(bootstrapDarkTheme.root.dataset.theme).toBe("dark");
    expect(bootstrapDarkTheme.root.dataset.vibedeskTheme).toBe("dark");

    const classDarkTheme = createThemeRoot();
    classDarkTheme.root.classList.toggle("dark", true);
    const classDarkWindow = {
      document: { documentElement: classDarkTheme.root },
    } as unknown as Window;
    Object.assign(classDarkWindow, { parent: classDarkWindow });

    await connectModHost(
      { modId: "market-daily", parentOrigin: "https://desk.example" },
      {
        window: classDarkWindow,
        setTimeout: globalThis.setTimeout.bind(globalThis),
        clearTimeout: globalThis.clearTimeout.bind(globalThis),
      },
    );

    expect(classDarkTheme.root.dataset.theme).toBe("dark");
    expect(classDarkTheme.root.dataset.vibedeskTheme).toBe("dark");
  });

  it("prefers explicit data-theme over legacy standalone dark markers", async () => {
    const conflictedTheme = createThemeRoot();
    conflictedTheme.root.dataset.theme = "light";
    conflictedTheme.root.dataset.vibedeskTheme = "dark";
    conflictedTheme.root.dataset.bsTheme = "dark";
    conflictedTheme.root.classList.toggle("dark", true);
    const conflictedWindow = {
      document: { documentElement: conflictedTheme.root },
    } as unknown as Window;
    Object.assign(conflictedWindow, { parent: conflictedWindow });

    await connectModHost(
      { modId: "market-daily", parentOrigin: "https://desk.example" },
      {
        window: conflictedWindow,
        setTimeout: globalThis.setTimeout.bind(globalThis),
        clearTimeout: globalThis.clearTimeout.bind(globalThis),
      },
    );

    expect(conflictedTheme.root.dataset.theme).toBe("light");
    expect(conflictedTheme.root.dataset.vibedeskTheme).toBe("light");
    expect(conflictedTheme.root.dataset.bsTheme).toBe("light");
    expect(conflictedTheme.root.classList.contains("dark")).toBe(false);
    expect(conflictedTheme.root.classList.contains("light")).toBe(true);
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

  it("applies follow-up init messages without leaving stale appearance variables behind", async () => {
    const { parent, runtime, dispatch } = embeddedRuntime();
    const { root, setThemeColor, ownerDocument } = createThemeRoot();
    Object.defineProperty(runtime.window, "document", {
      configurable: true,
      value: { documentElement: root } as unknown as Document,
    });
    Object.defineProperty(root, "ownerDocument", {
      configurable: true,
      value: ownerDocument as unknown as Document,
    });

    const connection = connectModHost(
      {
        modId: "market-daily",
        parentOrigin: "https://desk.example",
        capabilities: ["theme"],
      },
      runtime,
    );

    const darkInit = {
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
      appearance: createAppearance("dark", {
        "--vibe-bg": "#0f1714",
        "--vibe-accent": "#c89a5a",
        "--chart-series-1": "#70a596",
      }),
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
      data: darkInit,
    } as MessageEvent);

    const resolved = await connection;
    if (!resolved.embedded) throw new Error("expected embedded connection");
    expect(root.dataset.vibedeskEmbedded).toBe("true");
    expect(root.style.getPropertyValue("--vibe-accent")).toBe("#c89a5a");
    expect(root.style.getPropertyValue("--chart-series-1")).toBe("#70a596");

    dispatch({
      origin: "https://desk.example",
      source: parent,
      data: {
        ...darkInit,
        appearance: createAppearance("dark", {
          "--vibe-bg": "#16211c",
        }, "#16211c"),
      },
    } as MessageEvent);
    expect(root.style.getPropertyValue("--vibe-bg")).toBe("#16211c");
    expect(root.style.getPropertyValue("--vibe-accent")).toBe("");
    expect(root.style.getPropertyValue("--chart-series-1")).toBe("");
    expect(setThemeColor).toHaveBeenLastCalledWith("content", "#16211c");

    dispatch({
      origin: "https://desk.example",
      source: parent,
      data: {
        ...darkInit,
        environment: { ...darkInit.environment, theme: "light" as const },
        appearance: undefined,
      },
    } as MessageEvent);
    expect(root.dataset.theme).toBe("light");
    expect(root.style.getPropertyValue("--vibe-bg")).toBe("");
    expect(setThemeColor).toHaveBeenLastCalledWith("content", "#f4efe3");

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
      session: {
        id: "session-1",
        accessToken: "scoped-session-token",
        expiresAt: "2026-07-23T10:00:00+08:00",
      },
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

  it("queues a Wiki handoff until the Mod registers its handler", async () => {
    const { parent, runtime, postMessage, dispatch } = embeddedRuntime();
    const pending = connectModHost(
      {
        modId: "instock-czsc",
        parentOrigin: "https://desk.example",
        capabilities: ["handoff"],
      },
      runtime,
    );
    dispatch({
      origin: "https://desk.example",
      source: parent,
      data: {
        type: "vibedesk:init",
        protocolVersion: "1.0",
        instanceId: "instance-czsc",
        modId: "instock-czsc",
        user: { id: "alice" },
        workspace: { id: "desk-1" },
        environment: { theme: "light", locale: "zh-CN", timezone: "Asia/Shanghai" },
        gateways: {
          actions: "https://desk.example/api/mods/instock-czsc/actions",
          agent: "https://desk.example/api/agent",
          model: "https://desk.example/api/model",
          data: "https://desk.example/api/data-services",
        },
        grants: { permissions: [], actions: [] },
      },
    } as MessageEvent);
    const connection = await pending;
    if (!connection.embedded) throw new Error("expected embedded connection");

    const handoff = {
      version: 1,
      id: "hf_abc12345",
      sourceModId: "market-daily",
      targetModId: "instock-czsc",
      entrypointId: "structure",
      subject: {
        type: "etf",
        canonicalId: "etf:CN:512010",
        displayName: "医药 ETF",
        market: "CN",
        symbol: "512010",
        assetType: "etf",
      },
      relatedSubjects: [],
      conceptIds: ["concept:CN:医药"],
      intent: "technical.structure",
      timeframe: "daily",
      parameters: { bars: 480 },
      createdAt: "2026-08-15T10:00:00+08:00",
      expiresAt: "2026-08-15T10:05:00+08:00",
    } as const;
    dispatch({
      origin: "https://desk.example",
      source: parent,
      data: {
        type: "vibedesk:handoff",
        requestId: "handoff-1",
        instanceId: "instance-czsc",
        modId: "instock-czsc",
        handoff,
      },
    } as MessageEvent);

    const handler = vi.fn(() => ({ applied: true }));
    connection.setHandoffHandler(handler);
    await Promise.resolve();
    await Promise.resolve();

    expect(handler).toHaveBeenCalledWith(handoff);
    expect(postMessage).toHaveBeenCalledWith(
      expect.objectContaining({
        type: "vibedesk:handoff-result",
        requestId: "handoff-1",
        handoffId: handoff.id,
        ok: true,
      }),
      "https://desk.example",
    );
    connection.close();
  });
});
