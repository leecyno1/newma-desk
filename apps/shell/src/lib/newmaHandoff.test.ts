import { afterEach, describe, expect, it, vi } from "vitest";

import {
  buildDeskReturnUrl,
  buildNewmaHandoffUrl,
  loadModCopilotSessionMetadata,
  modCopilotSessionStorageKey,
  readDeskReturnHandoff,
  readNewmaHandoffPayload,
  resolveNewmaAgentUrl,
  saveModCopilotSessionMetadata,
  stripDeskReturnHandoffFragment,
  type ModCopilotSessionMetadata,
} from "./newmaHandoff";

afterEach(() => {
  delete (globalThis as typeof globalThis & {
    __NEWMA_DESK_CONFIG__?: unknown;
  }).__NEWMA_DESK_CONFIG__;
  document
    .querySelectorAll(
      'meta[name="newma-desk:newma-agent-url"], meta[name="newma-desk:newma-allowed-origins"]',
    )
    .forEach((element) => element.remove());
  vi.unstubAllEnvs();
});

describe("Newma handoff protocol", () => {
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

  it("builds a fragment-only Newma handoff with a safe Desk return link", () => {
    const handoff = buildNewmaHandoffUrl({
      newmaAgentUrl: "https://newma.example/chat?theme=dark#/conversation",
      newmaAllowedOrigins: ["https://newma.example"],
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
    expect(readNewmaHandoffPayload(handoff!)).toMatchObject({
      protocol: "newma-desk.v1",
      source: "newma-desk",
      moduleId: "industry-map",
      projectId: "vibe-research",
      workspaceId: "workspace-1",
      upstreamSessionId: "hermes-session-1",
    });

    const returnTo = readNewmaHandoffPayload(handoff!)?.returnTo;
    expect(returnTo).toBeDefined();
    expect(new URL(returnTo!).searchParams.has("session")).toBe(false);
  });

  it("enforces same-origin or an explicit Newma origin allowlist", () => {
    expect(
      resolveNewmaAgentUrl(
        "https://desk.example/newma",
        "https://desk.example/?mod=industry-map",
      ),
    ).toBe("https://desk.example/newma");
    expect(
      resolveNewmaAgentUrl(
        "https://newma.example/chat",
        "https://desk.example/?mod=industry-map",
      ),
    ).toBeUndefined();
    expect(
      resolveNewmaAgentUrl(
        "https://newma.example/chat",
        "https://desk.example/?mod=industry-map",
        ["https://newma.example"],
      ),
    ).toBe("https://newma.example/chat");
  });

  it("allows different loopback Newma origins only when Desk is loopback", () => {
    expect(
      resolveNewmaAgentUrl(
        "http://localhost:8787/chat",
        "http://127.0.0.1:5888/?mod=industry-map",
      ),
    ).toBe("http://localhost:8787/chat");
    expect(
      resolveNewmaAgentUrl(
        "http://127.0.0.1:8787/chat",
        "https://desk.example/?mod=industry-map",
      ),
    ).toBeUndefined();
  });

  it("reads Newma URL and allowed origins from runtime, meta, or env config", () => {
    (globalThis as typeof globalThis & {
      __NEWMA_DESK_CONFIG__?: {
        newmaAgentUrl: string;
        newmaAllowedOrigins: string[];
      };
    }).__NEWMA_DESK_CONFIG__ = {
      newmaAgentUrl: "https://runtime.newma.example/chat",
      newmaAllowedOrigins: ["https://runtime.newma.example"],
    };
    expect(resolveNewmaAgentUrl(undefined, "https://desk.example/")).toBe(
      "https://runtime.newma.example/chat",
    );
    delete (globalThis as typeof globalThis & {
      __NEWMA_DESK_CONFIG__?: unknown;
    }).__NEWMA_DESK_CONFIG__;

    const urlMeta = document.createElement("meta");
    urlMeta.name = "newma-desk:newma-agent-url";
    urlMeta.content = "https://meta.newma.example/chat";
    const originsMeta = document.createElement("meta");
    originsMeta.name = "newma-desk:newma-allowed-origins";
    originsMeta.content = "https://meta.newma.example";
    document.head.append(urlMeta, originsMeta);
    expect(resolveNewmaAgentUrl(undefined, "https://desk.example/")).toBe(
      "https://meta.newma.example/chat",
    );
    urlMeta.remove();
    originsMeta.remove();

    vi.stubEnv("VITE_NEWMA_AGENT_URL", "https://env.newma.example/chat");
    vi.stubEnv("VITE_NEWMA_ALLOWED_ORIGINS", "https://env.newma.example");
    expect(resolveNewmaAgentUrl(undefined, "https://desk.example/")).toBe(
      "https://env.newma.example/chat",
    );
  });

  it("falls back to the current Desk origin when a stored return URL is polluted", () => {
    const handoff = buildNewmaHandoffUrl({
      newmaAgentUrl: "https://newma.example/chat",
      newmaAllowedOrigins: ["https://newma.example"],
      deskUrl: "https://desk.example/current?mod=industry-map",
      deskReturnUrl: "https://attacker.example/collect?session=leak",
      moduleId: "industry-map",
      projectId: "vibe-research",
      workspaceId: "workspace-1",
      upstreamSessionId: "session-1",
    });
    const payload = readNewmaHandoffPayload(handoff!);
    expect(new URL(payload!.returnTo).origin).toBe("https://desk.example");
    expect(new URL(payload!.returnTo).pathname).toBe("/current");
    expect([...new URL(payload!.returnTo).searchParams.keys()]).toEqual([
      "mod",
      "copilot",
    ]);
  });

  it("rejects absent or unsafe Newma base URLs", () => {
    expect(
      buildNewmaHandoffUrl({
        deskUrl: "https://desk.example/?mod=industry-map",
        moduleId: "industry-map",
        workspaceId: "workspace-1",
        upstreamSessionId: "session-1",
      }),
    ).toBeUndefined();
    expect(
      buildNewmaHandoffUrl({
        newmaAgentUrl: "javascript:alert(1)",
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
