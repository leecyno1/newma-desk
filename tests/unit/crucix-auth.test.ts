// @vitest-environment jsdom
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { loadCrucixSnapshot } from "@/lib/crucix";

const bridge = vi.hoisted(() => ({ config: null as any }));
vi.mock("@/lib/vibedesk", () => ({
  waitForVibeDeskConfig: async () => bridge.config,
  getVibeDeskConfig: () => bridge.config,
}));
const snapshot = { contract: "newma-desk.crucix-intelligence.v1", news: [], macro: {}, freshness: { status: "stale" } };
beforeEach(() => {
  bridge.config = { apiOrigin: "https://desk.test", moduleId: "macro-monitor", userId: "alice", workspaceId: "one",
    instanceId: "instance-one", accessToken: "test-only", permissions: ["market.read"] };
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify(snapshot))));
});
afterEach(() => { vi.unstubAllGlobals(); });

it.each(["macro-monitor", "news-radar"])("%s uses its declared read Action with scoped credentials", async moduleId => {
  bridge.config.moduleId = moduleId;
  expect(await loadCrucixSnapshot()).toEqual(snapshot);
  const [url, init] = vi.mocked(fetch).mock.calls[0];
  expect(url).toBe(`https://desk.test/api/mods/${moduleId}/actions/crucix.snapshot`);
  expect(init).toMatchObject({ method: "POST", credentials: "omit", redirect: "error", cache: "no-store", body: "{}" });
  const headers = new Headers(init?.headers);
  expect(headers.get("Authorization")).toBe("Bearer test-only");
  expect(headers.get("X-Newma-Desk-Instance-Id")).toBe("instance-one");
  expect(headers.has("X-User-Id")).toBe(false);
});

it.each(["instanceId", "accessToken", "permissions"])("missing %s never falls back to the unscoped API", async field => {
  bridge.config[field] = field === "permissions" ? [] : undefined;
  await expect(loadCrucixSnapshot()).rejects.toThrow("授权不完整");
  expect(fetch).not.toHaveBeenCalled();
});

it("standalone without a Desk connection retains the unavailable supplement state", async () => {
  bridge.config = null;
  expect(await loadCrucixSnapshot()).toBeNull();
  expect(fetch).not.toHaveBeenCalled();
});

it.each(["workspaceId", "instanceId", "accessToken", "permissions"])("a late result is discarded after %s changes", async field => {
  let resolve!: (value: unknown) => void;
  vi.mocked(fetch).mockResolvedValue({ ok: true, json: () => new Promise(done => { resolve = done; }) } as Response);
  const pending = loadCrucixSnapshot();
  await vi.waitFor(() => expect(resolve).toBeTypeOf("function"));
  bridge.config[field] = field === "permissions" ? [] : "changed";
  resolve(snapshot);
  await expect(pending).rejects.toThrow("旧 Crucix 结果未采用");
});

it.each([401, 403, 503])("HTTP %s is not retried or exposed as raw upstream detail", async status => {
  vi.mocked(fetch).mockResolvedValue(new Response(JSON.stringify({ detail: "private upstream detail" }), { status }));
  await expect(loadCrucixSnapshot()).rejects.toThrow(status === 503 ? "HTTP 503" : "授权已失效或不足");
  expect(fetch).toHaveBeenCalledTimes(1);
});

it("rejects the wrong response contract", async () => {
  vi.mocked(fetch).mockResolvedValue(new Response(JSON.stringify({ contract: "wrong" })));
  await expect(loadCrucixSnapshot()).rejects.toThrow("数据格式不兼容");
});
