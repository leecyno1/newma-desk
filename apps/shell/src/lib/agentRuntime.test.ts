import { beforeEach, describe, expect, it } from "vitest";

import {
  adapterRuntimeLabel,
  adapterMatchesRuntimePreference,
  loadAgentRuntimePreference,
  preferredAdapterForRuntime,
  routeAgentAdapter,
  saveAgentRuntimePreference,
} from "./agentRuntime";

const adapters = [
  {
    id: "hermes-webui",
    kind: "agent-gateway",
    available: true,
    capabilities: ["module.explain", "module.analyze"],
  },
  {
    id: "codex-cli",
    kind: "local-cli",
    available: true,
    capabilities: ["module.explain", "module.analyze", "module.edit"],
  },
  {
    id: "claude-cli",
    kind: "local-cli",
    available: false,
    capabilities: ["module.explain", "module.edit"],
  },
];

describe("Agent Runtime selection", () => {
  beforeEach(() => window.localStorage.clear());

  it("persists auto, Newma, and local runtime preferences", () => {
    expect(loadAgentRuntimePreference()).toBe("auto");

    saveAgentRuntimePreference("newma");
    expect(loadAgentRuntimePreference()).toBe("newma");

    saveAgentRuntimePreference("local");
    expect(loadAgentRuntimePreference()).toBe("local");
  });

  it("migrates the legacy `numa` preference to Newma", () => {
    window.localStorage.setItem("newma-desk.agent-runtime.v1", "numa");
    expect(loadAgentRuntimePreference()).toBe("newma");
    expect(window.localStorage.getItem("newma-desk.agent-runtime.v1")).toBe(
      "newma",
    );
  });

  it("maps Newma to a compatible Agent Gateway and local to CLI adapters", () => {
    expect(adapterMatchesRuntimePreference(adapters[0]!, "newma")).toBe(true);
    expect(adapterMatchesRuntimePreference(adapters[1]!, "newma")).toBe(false);
    expect(adapterMatchesRuntimePreference(adapters[0]!, "local")).toBe(false);
    expect(adapterMatchesRuntimePreference(adapters[1]!, "local")).toBe(true);
    expect(adapterRuntimeLabel(adapters[0]!)).toBe("Newma / Hermes Runtime");
    expect(adapterRuntimeLabel(adapters[1]!)).toBe("本地 Agent CLI");
  });

  it("keeps the configured adapter in auto mode", () => {
    expect(preferredAdapterForRuntime(adapters, "auto", "codex-cli")?.id).toBe(
      "codex-cli",
    );
  });

  it("falls back to an available adapter when the configured one is unavailable", () => {
    expect(
      preferredAdapterForRuntime(adapters, "local", "claude-cli")?.id,
    ).toBe("codex-cli");
  });

  it("applies runtime ownership before a stale preferred adapter", () => {
    expect(
      routeAgentAdapter(adapters, {
        mode: "research",
        preference: "local",
        preferredId: "hermes-webui",
      })?.id,
    ).toBe("codex-cli");
    expect(
      routeAgentAdapter(adapters, {
        mode: "research",
        preference: "newma",
        preferredId: "codex-cli",
      })?.id,
    ).toBe("hermes-webui");
  });

  it("keeps capability filtering inside the routing interface", () => {
    expect(
      routeAgentAdapter(adapters, {
        mode: "edit",
        preference: "newma",
        preferredId: "hermes-webui",
      }),
    ).toBeUndefined();
    expect(
      routeAgentAdapter(adapters, {
        mode: "edit",
        preference: "auto",
      })?.id,
    ).toBe("codex-cli");
  });
});
