import { beforeEach, describe, expect, it, vi } from "vitest";
import { createLayoutSaver, createReplayStorage } from "./workspaceStorage";
import type { StorageClientOptions, StorageSession } from "./storageAccess";

function options(modId = "trading-replay"): StorageClientOptions {
  return { baseUrl: "https://ignored.invalid", userId: "ignored", workspaceId: "ignored", session: {
    isCurrent: () => true,
    config: { type: "vibedesk:init", protocolVersion: "1.0", modId, instanceId: "instance-a", user: { id: "alice" }, workspace: { id: "workspace-a" },
      environment: { theme: "light", locale: "zh-CN", timezone: "Asia/Shanghai" },
      gateways: { storage: "https://desk.test/api/mods", data: "https://desk.test/api/data", actions: "https://desk.test/api/actions" },
      grants: { permissions: ["storage.read", "storage.write"], actions: [] },
      session: { id: "session-a", accessToken: "synthetic", expiresAt: new Date(Date.now() + 60000).toISOString() },
    } as StorageSession["config"],
  } };
}
const json = (value: unknown) => new Response(JSON.stringify(value));
const layout = { id: "layout-a", name: "私有布局", savedAt: "2026-10-23T00:00:00Z", state: { timeframe: "1d" } };
const replay = { id: "a".repeat(32), moduleId: "trading-replay", userId: "alice", workspaceId: "workspace-a", viewUrl: "https://untrusted.invalid" };

describe("workspace storage", () => {
  beforeEach(() => window.localStorage.clear());
  it("saves signed layouts through the declared namespace without reading or updating old local data", async () => {
    const key = "vibedesk.multi-timeframe.layouts.v1";
    window.localStorage.setItem(key, "private legacy layout");
    const fetcher = vi.fn(async () => json({ moduleId: "multi-timeframe", namespace: "layouts", key: layout.id, value: layout }));
    const save = createLayoutSaver({ ...options("multi-timeframe"), fetch: fetcher }, "multi-timeframe");
    expect(await save(layout)).toEqual(layout);
    expect(fetcher).toHaveBeenCalledWith("https://desk.test/api/mods/multi-timeframe/storage/layouts/layout-a", expect.objectContaining({
      method: "PUT", credentials: "omit", redirect: "error", cache: "no-store", body: JSON.stringify({ expectedRevision: 0, value: layout }),
    }));
    expect(window.localStorage.getItem(key)).toBe("private legacy layout");
  });
  it("does not save without a write grant or after an account switch", async () => {
    const input = options(); const fetcher = vi.fn(); input.fetch = fetcher;
    input.session!.config.grants.permissions = ["storage.read"];
    await expect(createLayoutSaver(input, "trading-replay")(layout)).rejects.toMatchObject({ status: 403 });
    input.session!.isCurrent = () => false;
    await expect(createLayoutSaver(input, "trading-replay")(layout)).rejects.toMatchObject({ status: 409 });
    expect(fetcher).not.toHaveBeenCalled();
  });
  it("keeps the explicit standalone layout store", async () => {
    await createLayoutSaver({ ...options(), session: undefined }, "trading-replay")(layout);
    expect(JSON.parse(window.localStorage.getItem("vibedesk.trading-replay.layouts.v1")!)[0]).toEqual(layout);
  });
  it("reads private replay records and HTML with a signature, not the record URL", async () => {
    const fetcher = vi.fn().mockResolvedValueOnce(json([replay])).mockResolvedValueOnce(new Response("<!doctype html><head></head>", { headers: { "Content-Type": "text/html" } }));
    const client = createReplayStorage({ ...options(), fetch: fetcher });
    const records = await client.listReplays("trading-replay");
    expect(client.viewUrl(records[0]!)).toBe("");
    expect(await client.readView!(records[0]!)).toContain("<!doctype html>");
    expect(fetcher.mock.calls[1]![0]).toBe(`https://desk.test/api/artifacts/replays/${replay.id}/view`);
    expect(fetcher.mock.calls[1]![1]).toMatchObject({ credentials: "omit", headers: { Authorization: "Bearer synthetic", "X-Newma-Desk-Instance-Id": "instance-a" } });
  });
  it("rejects a foreign archive and cannot use another page's session", async () => {
    const client = createReplayStorage({ ...options(), fetch: vi.fn(async () => json([{ ...replay, userId: "bob" }])) });
    await expect(client.listReplays("trading-replay")).rejects.toMatchObject({ status: 403 });
    expect(() => createReplayStorage(options("market-technical")).listReplays("trading-replay")).toThrow("当前页面不能访问回放归档");
  });
});
