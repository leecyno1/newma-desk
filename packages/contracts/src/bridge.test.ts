import { describe, expect, it } from "vitest";

import {
  deskActionResultSchema,
  deskContextRequestSchema,
  deskInitSchema,
  deskUiActionRequestSchema,
  modAckSchema,
  modActionRequestSchema,
  modContextSchema,
  modHelloSchema,
  modUiActionResultSchema,
} from "./bridge";

describe("Newma-Dock bridge protocol", () => {
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
    });

    expect(
      modAckSchema.parse({
        type: "vibedesk:ack",
        protocolVersion: init.protocolVersion,
        instanceId: init.instanceId,
        modId: init.modId,
      }),
    ).toBeTruthy();
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
});
