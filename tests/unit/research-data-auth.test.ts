// @vitest-environment jsdom
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { api } from "@/lib/api";

const bridge = vi.hoisted(() => ({ config: null as any, embedded: true }));
vi.mock("@/lib/vibedesk", () => ({
  getVibeDeskConfig: () => bridge.config,
  waitForVibeDeskConfig: async () => bridge.config,
  get isVibeDeskEmbedded() { return bridge.embedded; },
}));
beforeEach(() => {
  bridge.embedded = true;
  bridge.config = { apiOrigin: "https://desk.test", moduleId: "macro-monitor", userId: "alice", workspaceId: "one",
    accessToken: "test-only", instanceId: "one", permissions: ["market.read"] };
  vi.stubGlobal("localStorage", { getItem: () => "standalone-key" });
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({ data: { synthetic: true } }))));
});
afterEach(() => { vi.unstubAllGlobals(); vi.unstubAllEnvs(); });

it("macro data uses its declared Action, not the native key or account cookie", async () => {
  expect(await api.macroMonitor(14)).toEqual({ synthetic: true });
  const [url, init] = vi.mocked(fetch).mock.calls[0];
  expect(url).toBe("https://desk.test/api/mods/macro-monitor/actions/research.macro-monitor");
  expect(init).toMatchObject({ method: "POST", credentials: "omit", redirect: "error", cache: "no-store", body: '{"days":14}' });
  const headers = new Headers(init?.headers);
  expect(headers.get("Authorization")).toBe("Bearer test-only");
  expect(headers.get("X-Newma-Desk-Instance-Id")).toBe("one");
  expect(headers.has("X-User-Id")).toBe(false);
});

it("catalysts preserve all filters and boolean types", async () => {
  bridge.config.moduleId = "catalyst-calendar";
  await api.catalysts(["600519"], 90, false, ["半导体"], false);
  const [url, init] = vi.mocked(fetch).mock.calls[0];
  expect(url).toBe("https://desk.test/api/mods/catalyst-calendar/actions/research.catalysts");
  expect(JSON.parse(init!.body as string)).toEqual({ symbols: "600519", days: 90, concepts: "半导体", include_cycles: false, include_macro: false });
});

it("news reads collected data and rejects full collection in Desk", async () => {
  bridge.config.moduleId = "news-radar";
  await api.radar();
  expect(vi.mocked(fetch).mock.calls[0][0]).toBe("https://desk.test/api/mods/news-radar/actions/research.news-snapshot");
  await expect(api.radarRefresh()).rejects.toMatchObject({ status: 403 });
  expect(fetch).toHaveBeenCalledTimes(1);
});

it("news topics use typed pagination and preserve filters", async () => {
  bridge.config.moduleId = "news-radar";
  await api.radarTopics({ query: "增长", industry: "technology", signal: "risk", sort: "latest", offset: 80, limit: 40 });
  const [url, init] = vi.mocked(fetch).mock.calls[0];
  expect(String(url)).toContain("/actions/research.news-topics");
  expect(JSON.parse(init!.body as string)).toEqual({ q: "增长", industry: "technology", signal: "risk", sort: "latest", offset: 80, limit: 40 });
});

it.each([["radarAnnouncements", "market.announcements"], ["radarNews", "market.news"]] as const)("%s uses the declared news-page action", async (method, action) => {
  bridge.config.moduleId = "news-radar";
  vi.mocked(fetch).mockResolvedValue(new Response(JSON.stringify({ data: [] })));
  expect(await api[method]("600519")).toEqual([]);
  const [url, init] = vi.mocked(fetch).mock.calls[0];
  expect(String(url)).toBe(`https://desk.test/api/mods/news-radar/actions/${action}`);
  expect(JSON.parse(init!.body as string)).toEqual({ code: "600519" });
});

it("native news retains its explicit collection endpoint", async () => {
  bridge.config = null; bridge.embedded = false;
  vi.stubEnv("VITE_NEWMA_DESK_INTEGRATED", "0");
  await api.radarRefresh();
  expect(fetch).toHaveBeenCalledWith("/api/radar/refresh", expect.objectContaining({ method: "POST" }));
});

it("standalone keeps the native URL and configured access key", async () => {
  bridge.config = null; bridge.embedded = false;
  vi.stubEnv("VITE_NEWMA_DESK_INTEGRATED", "0");
  await api.macroMonitor(7);
  expect(fetch).toHaveBeenCalledWith("/api/macro-monitor?days=7", expect.objectContaining({ headers: { Authorization: "Bearer standalone-key" } }));
});

it.each(["embedded", "integrated"])("%s without handshake does not fall back to native authentication", async mode => {
  bridge.config = null; bridge.embedded = mode === "embedded";
  vi.stubEnv("VITE_NEWMA_DESK_INTEGRATED", mode === "integrated" ? "1" : "0");
  await expect(api.macroMonitor()).rejects.toMatchObject({ status: 401 });
  expect(fetch).not.toHaveBeenCalled();
});

it.each(["accessToken", "instanceId", "permissions"])("missing %s prevents a request", async key => {
  bridge.config[key] = key === "permissions" ? [] : undefined;
  await expect(api.macroMonitor()).rejects.toMatchObject({ status: 403 });
  expect(fetch).not.toHaveBeenCalled();
});

it.each(["workspaceId", "moduleId", "instanceId", "accessToken", "permissions"])("discards a late result after %s changes", async key => {
  let finish!: (body: unknown) => void;
  vi.mocked(fetch).mockResolvedValue({ ok: true, json: () => new Promise(resolve => { finish = resolve; }) } as Response);
  const pending = api.macroMonitor();
  const rejected = expect(pending).rejects.toMatchObject({ status: 409 });
  await vi.waitFor(() => expect(finish).toBeTypeOf("function"));
  bridge.config[key] = key === "permissions" ? [] : "changed";
  finish({ data: { synthetic: true } });
  await rejected;
});

it.each([401, 403, 404, 502])("HTTP %s never retries or leaks upstream details", async status => {
  vi.mocked(fetch).mockResolvedValue(new Response(JSON.stringify({ detail: "private-path-and-key" }), { status }));
  const error = await api.macroMonitor().catch(error => error);
  expect(error.status).toBe(status);
  expect(error.message).not.toContain("private-path-and-key");
  expect(fetch).toHaveBeenCalledTimes(1);
});

it("rejects an incompatible response instead of treating it as empty data", async () => {
  vi.mocked(fetch).mockResolvedValue(new Response(JSON.stringify({ unrelated: [] })));
  await expect(api.macroMonitor()).rejects.toMatchObject({ status: 502 });
});
