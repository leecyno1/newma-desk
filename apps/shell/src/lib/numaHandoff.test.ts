import { afterEach, describe, expect, it, vi } from "vitest";

import {
  buildDeskReturnUrl,
  buildNumaHandoffUrl,
  loadModCopilotSessionMetadata,
  modCopilotSessionStorageKey,
  readDeskReturnHandoff,
  readNumaHandoffPayload,
  resolveNumaAgentUrl,
  saveModCopilotSessionMetadata,
  stripDeskReturnHandoffFragment,
  type ModCopilotSessionMetadata,
} from "./numaHandoff";

afterEach(() => {
  delete (globalThis as typeof globalThis & {
    __NEWMA_DESK_CONFIG__?: unknown;
  }).__NEWMA_DESK_CONFIG__;
  document
    .querySelectorAll(
      'meta[name="newma-desk:numa-agent-url"], meta[name="newma-desk:numa-allowed-origins"]',
    )
    .forEach((element) => element.remove());
  vi.unstubAllEnvs();
});

describe("Numa handoff protocol", () => {
  it("keeps continuity identifiers out of query strings", () => {
    const returnTo = buildDeskReturnUrl({
      deskUrl: "https://desk.example/?view=store&session=stale",
      moduleId: "industry-map",
      projectId: "vibe-research",
      workspaceId: "workspace-1",
      upstreamSessionId: "hermes-session-1",
    });
    expect(returnTo).toBeDefined();

    const parsed = new URL(returnTo!);
    expect(parsed.searchParams.get("mod")).toBe("industry-map");
    expect(parsed.searchParams.get("copilot")).toBe("1");
    expect([...parsed.searchParams.keys()]).toEqual(["mod", "copilot"]);
    expect(parsed.hash).toContain("newma-handoff=");
    expect(
      readDeskReturnHandoff(
        returnTo!,
        "industry-map",
        "workspace-1",
        "vibe-research",
      ),
    ).toEqual({
      moduleId: "industry-map",
      projectId: "vibe-research",
      workspaceId: "workspace-1",
      upstreamSessionId: "hermes-session-1",
    });

    const rebuilt = buildDeskReturnUrl({
      deskUrl: returnTo!,
      moduleId: "industry-map",
      projectId: "vibe-research",
      workspaceId: "workspace-1",
      upstreamSessionId: "hermes-session-2",
    });
    expect(rebuilt?.match(/newma-handoff=/g)).toHaveLength(1);
    expect(
      readDeskReturnHandoff(
        rebuilt!,
        "industry-map",
        "workspace-1",
        "vibe-research",
      )
        ?.upstreamSessionId,
    ).toBe("hermes-session-2");
    expect(
      readDeskReturnHandoff(
        rebuilt!,
        "industry-map",
        "workspace-1",
        "other-project",
      ),
    ).toBeUndefined();
  });

  it("strips a consumed handoff while preserving the existing hash route", () => {
    const returnTo = buildDeskReturnUrl({
      deskUrl:
        "https://desk.example/app?old=1#/research?tab=industry&panel=open",
      moduleId: "industry-map",
      projectId: "vibe-research",
      workspaceId: "workspace-1",
      upstreamSessionId: "session-1",
    });
    const stripped = stripDeskReturnHandoffFragment(returnTo!);
    const parsed = new URL(stripped!);

    expect(parsed.search).toBe("?mod=industry-map&copilot=1");
    expect(parsed.hash).toBe("#/research?tab=industry&panel=open");
    expect(stripped).not.toContain("newma-handoff=");
  });

  it("falls back to moduleId when a manifest has no project id", () => {
    const returnTo = buildDeskReturnUrl({
      deskUrl: "https://desk.example/",
      moduleId: "standalone-mod",
      workspaceId: "workspace-1",
      upstreamSessionId: "session-1",
    });
    expect(
      readDeskReturnHandoff(
        returnTo!,
        "standalone-mod",
        "workspace-1",
      )?.projectId,
    ).toBe("standalone-mod");
  });

  it("builds a fragment-only Numa handoff with a safe Desk return link", () => {
    const handoff = buildNumaHandoffUrl({
      numaAgentUrl: "https://numa.example/chat?theme=dark#/conversation",
      numaAllowedOrigins: ["https://numa.example"],
      deskUrl: "https://desk.example/?mod=industry-map",
      moduleId: "industry-map",
      projectId: "vibe-research",
      workspaceId: "workspace-1",
      upstreamSessionId: "hermes-session-1",
    });
    expect(handoff).toBeDefined();

    const parsed = new URL(handoff!);
    expect(parsed.searchParams.get("theme")).toBe("dark");
    expect(parsed.searchParams.has("session")).toBe(false);
    expect(parsed.searchParams.has("workspace")).toBe(false);
    expect(parsed.hash).toContain("#/conversation?newma-handoff=");
    expect(readNumaHandoffPayload(handoff!)).toMatchObject({
      protocol: "newma-desk.v1",
      source: "newma-desk",
      moduleId: "industry-map",
      projectId: "vibe-research",
      workspaceId: "workspace-1",
      upstreamSessionId: "hermes-session-1",
    });

    const returnTo = readNumaHandoffPayload(handoff!)?.returnTo;
    expect(returnTo).toBeDefined();
    expect(new URL(returnTo!).searchParams.has("session")).toBe(false);
  });

  it("enforces same-origin or an explicit Numa origin allowlist", () => {
    expect(
      resolveNumaAgentUrl(
        "https://desk.example/numa",
        "https://desk.example/?mod=industry-map",
      ),
    ).toBe("https://desk.example/numa");
    expect(
      resolveNumaAgentUrl(
        "https://numa.example/chat",
        "https://desk.example/?mod=industry-map",
      ),
    ).toBeUndefined();
    expect(
      resolveNumaAgentUrl(
        "https://numa.example/chat",
        "https://desk.example/?mod=industry-map",
        ["https://numa.example"],
      ),
    ).toBe("https://numa.example/chat");
  });

  it("allows different loopback Numa origins only when Desk is loopback", () => {
    expect(
      resolveNumaAgentUrl(
        "http://localhost:8787/chat",
        "http://127.0.0.1:5888/?mod=industry-map",
      ),
    ).toBe("http://localhost:8787/chat");
    expect(
      resolveNumaAgentUrl(
        "http://127.0.0.1:8787/chat",
        "https://desk.example/?mod=industry-map",
      ),
    ).toBeUndefined();
  });

  it("reads Numa URL and allowed origins from runtime, meta, or env config", () => {
    (globalThis as typeof globalThis & {
      __NEWMA_DESK_CONFIG__?: {
        numaAgentUrl: string;
        numaAllowedOrigins: string[];
      };
    }).__NEWMA_DESK_CONFIG__ = {
      numaAgentUrl: "https://runtime.numa.example/chat",
      numaAllowedOrigins: ["https://runtime.numa.example"],
    };
    expect(resolveNumaAgentUrl(undefined, "https://desk.example/")).toBe(
      "https://runtime.numa.example/chat",
    );
    delete (globalThis as typeof globalThis & {
      __NEWMA_DESK_CONFIG__?: unknown;
    }).__NEWMA_DESK_CONFIG__;

    const urlMeta = document.createElement("meta");
    urlMeta.name = "newma-desk:numa-agent-url";
    urlMeta.content = "https://meta.numa.example/chat";
    const originsMeta = document.createElement("meta");
    originsMeta.name = "newma-desk:numa-allowed-origins";
    originsMeta.content = "https://meta.numa.example";
    document.head.append(urlMeta, originsMeta);
    expect(resolveNumaAgentUrl(undefined, "https://desk.example/")).toBe(
      "https://meta.numa.example/chat",
    );
    urlMeta.remove();
    originsMeta.remove();

    vi.stubEnv("VITE_NUMA_AGENT_URL", "https://env.numa.example/chat");
    vi.stubEnv("VITE_NUMA_ALLOWED_ORIGINS", "https://env.numa.example");
    expect(resolveNumaAgentUrl(undefined, "https://desk.example/")).toBe(
      "https://env.numa.example/chat",
    );
  });

  it("falls back to the current Desk origin when a stored return URL is polluted", () => {
    const handoff = buildNumaHandoffUrl({
      numaAgentUrl: "https://numa.example/chat",
      numaAllowedOrigins: ["https://numa.example"],
      deskUrl: "https://desk.example/current?mod=industry-map",
      deskReturnUrl: "https://attacker.example/collect?session=leak",
      moduleId: "industry-map",
      projectId: "vibe-research",
      workspaceId: "workspace-1",
      upstreamSessionId: "session-1",
    });
    const payload = readNumaHandoffPayload(handoff!);
    expect(new URL(payload!.returnTo).origin).toBe("https://desk.example");
    expect(new URL(payload!.returnTo).pathname).toBe("/current");
    expect([...new URL(payload!.returnTo).searchParams.keys()]).toEqual([
      "mod",
      "copilot",
    ]);
  });

  it("rejects absent or unsafe Numa base URLs", () => {
    expect(
      buildNumaHandoffUrl({
        deskUrl: "https://desk.example/?mod=industry-map",
        moduleId: "industry-map",
        workspaceId: "workspace-1",
        upstreamSessionId: "session-1",
      }),
    ).toBeUndefined();
    expect(
      buildNumaHandoffUrl({
        numaAgentUrl: "javascript:alert(1)",
        deskUrl: "https://desk.example/?mod=industry-map",
        moduleId: "industry-map",
        workspaceId: "workspace-1",
        upstreamSessionId: "session-1",
      }),
    ).toBeUndefined();
  });
});

describe("Mod copilot session metadata", () => {
  const metadata: ModCopilotSessionMetadata = {
    schemaVersion: 1,
    moduleId: "industry-map",
    moduleName: "产业链研究",
    workspaceId: "workspace-1",
    projectId: "vibe-research",
    mode: "ask",
    status: "completed",
    taskId: "task-1",
    adapterId: "hermes-webui",
    upstreamSessionId: "hermes-session-1",
    deskReturnUrl: "https://desk.example/?mod=industry-map&copilot=1",
    lastPrompt: "梳理产业链",
    updatedAt: "2026-07-29T00:00:00.000Z",
  };

  it("persists metadata separately for every workspace and Mod", () => {
    expect(saveModCopilotSessionMetadata(metadata)).toBe(true);
    expect(
      loadModCopilotSessionMetadata("industry-map", "workspace-1"),
    ).toEqual(metadata);
    expect(
      loadModCopilotSessionMetadata("industry-map", "workspace-2"),
    ).toBeUndefined();
  });

  it("ignores corrupt or mismatched persisted metadata", () => {
    window.localStorage.setItem(
      modCopilotSessionStorageKey("industry-map", "workspace-1"),
      JSON.stringify({ ...metadata, moduleId: "other-mod" }),
    );
    expect(
      loadModCopilotSessionMetadata("industry-map", "workspace-1"),
    ).toBeUndefined();
  });
});
