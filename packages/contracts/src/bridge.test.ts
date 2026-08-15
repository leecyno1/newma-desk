import { describe, expect, it } from "vitest";

import {
  deskAppearanceSchema,
  deskActionResultSchema,
  deskContextRequestSchema,
  deskInitSchema,
  deskUiActionRequestSchema,
  deskHandoffSchema,
  modAckSchema,
  modActionRequestSchema,
  modContextSchema,
  modHelloSchema,
  modUiActionResultSchema,
  modHandoffResultSchema,
} from "./bridge";

const darkAppearance = {
  contractVersion: "1.0",
  mode: "dark",
  cssVars: {
    "--vibe-bg": "#0f1714",
    "--vibe-surface": "#16211c",
    "--vibe-accent": "#c89a5a",
  },
  semantic: {
    bg: "#0f1714",
    surface: "#16211c",
    surfaceMuted: "#121d18",
    surfaceRaised: "#1a2821",
    border: "#2a3931",
    borderStrong: "#405146",
    text: "#f3ecdd",
    textSoft: "#cfc7b7",
    textMuted: "#a8b4a5",
    textFaint: "#78847a",
    accent: "#c89a5a",
    accentHover: "#dab47d",
    accentSoft: "#5a452c",
    accentSurface: "#2c2a21",
    accentContrast: "#102019",
    positive: "#f87171",
    negative: "#4ade80",
    warning: "#fbbf24",
    error: "#f87171",
    successText: "#86efac",
    successBg: "#0d2818",
    successBorder: "#166534",
    errorText: "#fca5a5",
    errorBg: "#321417",
    errorBorder: "#7f1d1d",
  },
  charts: {
    gridColor: "#2a3931",
    textColor: "#a8b4a5",
    axisColor: "#405146",
    upColor: "#f87171",
    downColor: "#4ade80",
    tooltipBg: "#1a2821",
    tooltipBorder: "#405146",
    tooltipText: "#f3ecdd",
    series: ["#c89a5a", "#70a596", "#b67b64"],
  },
} as const;

describe("Newma-Desk bridge protocol", () => {
  it("validates the hello, init, and acknowledgement lifecycle", () => {
    const hello = modHelloSchema.parse({
      type: "vibedesk:hello",
      modId: "market-daily",
      protocolVersions: ["1.0"],
      sdkVersion: "0.2.0",
      capabilities: ["events", "actions", "theme"],
    });
    const init = deskInitSchema.parse({
      type: "vibedesk:init",
      protocolVersion: "1.0",
      instanceId: "instance-1",
      modId: hello.modId,
      user: { id: "local-user" },
      workspace: { id: "local-workspace" },
      environment: {
        theme: "light",
        locale: "zh-CN",
        timezone: "Asia/Shanghai",
      },
      appearance: { ...darkAppearance, mode: "light" },
      gateways: {
        actions: "http://127.0.0.1:8911/api/mods/market-daily/actions",
        agent: "http://127.0.0.1:8911/api/agent",
        model: "http://127.0.0.1:8911/api/model",
        data: "http://127.0.0.1:8911/api/data-services",
      },
      grants: {
        permissions: ["market.read"],
        actions: ["market.explain"],
      },
      session: {
        id: "session-1",
        accessToken: "scoped-session-token",
        expiresAt: "2099-07-23T10:00:00+08:00",
      },
    });

    expect(
      modAckSchema.parse({
        type: "vibedesk:ack",
        protocolVersion: init.protocolVersion,
        instanceId: init.instanceId,
        modId: init.modId,
      }),
    ).toBeTruthy();
    expect(init.appearance?.cssVars["--vibe-accent"]).toBe("#c89a5a");
  });

  it("keeps appearance optional and rejects unsafe CSS custom-property names", () => {
    expect(deskAppearanceSchema.parse(darkAppearance).mode).toBe("dark");
    expect(() =>
      deskAppearanceSchema.parse({
        ...darkAppearance,
        cssVars: { color: "red" },
      }),
    ).toThrow();
    expect(() =>
      deskInitSchema.parse({
        type: "vibedesk:init",
        protocolVersion: "1.0",
        instanceId: "instance-theme-mismatch",
        modId: "market-daily",
        user: { id: "local-user" },
        workspace: { id: "local-workspace" },
        environment: {
          theme: "light",
          locale: "zh-CN",
          timezone: "Asia/Shanghai",
        },
        appearance: darkAppearance,
        gateways: {
          actions: "http://127.0.0.1:8911/api/mods/market-daily/actions",
          agent: "http://127.0.0.1:8911/api/agent",
          model: "http://127.0.0.1:8911/api/model",
          data: "http://127.0.0.1:8911/api/data-services",
        },
        grants: { permissions: [], actions: [] },
      }),
    ).toThrow();
  });

  it("rejects unknown protocols and non-HTTP gateway URLs", () => {
    expect(() =>
      modHelloSchema.parse({
        type: "vibedesk:hello",
        modId: "market-daily",
        protocolVersions: ["2.0"],
      }),
    ).toThrow();
    expect(() =>
      deskInitSchema.parse({
        type: "vibedesk:init",
        protocolVersion: "1.0",
        instanceId: "instance-1",
        modId: "market-daily",
        user: { id: "local-user" },
        workspace: { id: "local-workspace" },
        environment: {
          theme: "light",
          locale: "zh-CN",
          timezone: "Asia/Shanghai",
        },
        gateways: {
          actions: "javascript:alert(1)",
          agent: "http://127.0.0.1:8911/api/agent",
          model: "http://127.0.0.1:8911/api/model",
          data: "http://127.0.0.1:8911/api/data-services",
        },
        grants: { permissions: [], actions: [] },
      }),
    ).toThrow();
  });

  it("validates context and action messages without exposing DOM access", () => {
    const common = {
      requestId: "request-1",
      instanceId: "instance-1",
      modId: "market-daily",
    };
    expect(
      deskContextRequestSchema.parse({
        type: "vibedesk:context-request",
        ...common,
        reason: "agent",
      }),
    ).toBeTruthy();
    expect(
      modContextSchema.parse({
        type: "vibedesk:context",
        ...common,
        context: {
          view: { id: "market-daily", title: "市场行情" },
          visibleBlocks: [{ id: "breadth", type: "metrics" }],
          selection: { symbol: "600519" },
          filters: {},
          data: { freshness: "fresh" },
          actions: [{ id: "market.explain", available: true }],
          tasks: [],
          wiki: {
            primarySubject: {
              type: "security",
              canonicalId: "security:CN:300308",
              displayName: "中际旭创",
              market: "CN",
              symbol: "300308",
              assetType: "stock",
            },
            relatedSubjects: [],
            conceptIds: ["concept:CN:CPO"],
            intent: "market.overview",
          },
        },
      }),
    ).toBeTruthy();
    expect(
      modActionRequestSchema.parse({
        type: "vibedesk:action-request",
        ...common,
        actionId: "market.explain",
        input: { prompt: "解释行情" },
      }),
    ).toBeTruthy();
    expect(
      deskActionResultSchema.parse({
        type: "vibedesk:action-result",
        ...common,
        actionId: "market.explain",
        status: 202,
        ok: true,
        result: { id: "task-1" },
      }),
    ).toBeTruthy();
    expect(
      deskUiActionRequestSchema.parse({
        type: "vibedesk:ui-action-request",
        ...common,
        actionId: "market.set-timeframe",
        input: { timeframe: "15m" },
      }),
    ).toBeTruthy();
    expect(
      modUiActionResultSchema.parse({
        type: "vibedesk:ui-action-result",
        ...common,
        actionId: "market.set-timeframe",
        ok: true,
        result: { accepted: true },
      }),
    ).toBeTruthy();
  });

  it("validates a Desk-to-Mod Wiki handoff lifecycle", () => {
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

    expect(
      deskHandoffSchema.parse({
        type: "vibedesk:handoff",
        requestId: "handoff-1",
        instanceId: "instance-1",
        modId: "instock-czsc",
        handoff,
      }),
    ).toBeTruthy();
    expect(
      modHandoffResultSchema.parse({
        type: "vibedesk:handoff-result",
        requestId: "handoff-1",
        instanceId: "instance-1",
        modId: "instock-czsc",
        handoffId: handoff.id,
        ok: true,
        result: { applied: true },
      }),
    ).toBeTruthy();
    expect(() =>
      deskHandoffSchema.parse({
        type: "vibedesk:handoff",
        requestId: "handoff-2",
        instanceId: "instance-1",
        modId: "news-radar",
        handoff,
      }),
    ).toThrow(/target/);
  });
});
