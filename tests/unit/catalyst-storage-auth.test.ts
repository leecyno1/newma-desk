// @vitest-environment jsdom
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { hydrateCatalystTracker, loadLocalCatalystTracker, persistCatalystTracker } from "@/lib/catalystTracker";
import { loadLocalCatalystResearchGroups, saveLocalCatalystResearchGroups } from "@/lib/researchGroups";

const bridge = vi.hoisted(() => ({ config: null as any, embedded: true, listeners: new Set<(value: any) => void>() }));
vi.mock("@/lib/vibedesk", () => ({
  getVibeDeskConfig: () => bridge.config,
  waitForVibeDeskConfig: async () => bridge.config,
  get isVibeDeskEmbedded() { return bridge.embedded; },
  subscribeVibeDeskConfig: (fn: (value: any) => void) => { bridge.listeners.add(fn); return () => bridge.listeners.delete(fn); },
}));
const empty = { schemaVersion: 1 as const, trackedIds: [], customEvents: [], outcomes: {} };
const tracked = { ...empty, trackedIds: ["private-event"] };
beforeEach(() => {
  const storage = new Map<string, string>();
  vi.stubGlobal("localStorage", { getItem: (key: string) => storage.get(key) ?? null, setItem: (key: string, value: string) => storage.set(key, value) });
  bridge.listeners.clear(); bridge.embedded = true;
  bridge.config = { apiOrigin: "https://desk.test", moduleId: "catalyst-calendar", userId: "alice", workspaceId: "one",
    instanceId: "instance-a", accessToken: "synthetic", storageGateway: "https://desk.test/api/mods/catalyst-calendar/storage", permissions: ["storage.read", "storage.write"] };
  vi.stubGlobal("fetch", vi.fn());
});
afterEach(() => vi.unstubAllGlobals());

it("does not import an old browser tracker into an empty signed account", async () => {
  localStorage.setItem("newma-desk.catalyst-tracker.v1", JSON.stringify(tracked));
  expect(loadLocalCatalystTracker()).toEqual(empty);
  vi.mocked(fetch).mockResolvedValue(new Response("{}", { status: 404 }));
  expect(await hydrateCatalystTracker()).toEqual(empty);
  vi.mocked(fetch).mockResolvedValue(new Response(JSON.stringify({ revision: 1, value: tracked })));
  await persistCatalystTracker(tracked);
  expect(fetch).toHaveBeenLastCalledWith("https://desk.test/api/mods/catalyst-calendar/storage/catalyst-calendar/tracker", expect.objectContaining({
    method: "PUT", credentials: "omit", redirect: "error", cache: "no-store", body: JSON.stringify({ expectedRevision: 0, value: tracked }),
  }));
  expect(JSON.parse(localStorage.getItem("newma-desk.catalyst-tracker.v1")!)).toEqual(tracked);
});

it("reports revision conflicts without retrying or claiming saved", async () => {
  vi.mocked(fetch).mockResolvedValueOnce(new Response(JSON.stringify({ revision: 2, value: empty })))
    .mockResolvedValueOnce(new Response("{}", { status: 409 }));
  await hydrateCatalystTracker();
  await expect(persistCatalystTracker(tracked)).rejects.toThrow("本次未覆盖");
  expect(fetch).toHaveBeenCalledTimes(2);
  expect(localStorage.getItem("newma-desk.catalyst-tracker.v1")).toBeNull();
});

it("rejects readonly writes and unavailable signed reads", async () => {
  bridge.config.permissions = ["storage.read"];
  await expect(persistCatalystTracker(tracked)).rejects.toThrow("未获授权");
  expect(fetch).not.toHaveBeenCalled();
  vi.mocked(fetch).mockResolvedValue(new Response("{}", { status: 403 }));
  await expect(hydrateCatalystTracker()).rejects.toThrow("读取失败");
});

it("discards a read after A to B and back to A", async () => {
  let finish!: (response: Response) => void;
  vi.mocked(fetch).mockImplementation(() => new Promise(resolve => { finish = resolve; }));
  const pending = hydrateCatalystTracker().catch(error => error);
  const a = bridge.config;
  bridge.config = { ...a, workspaceId: "two" }; bridge.listeners.forEach(fn => fn(bridge.config));
  bridge.config = a; bridge.listeners.forEach(fn => fn(a));
  finish(new Response(JSON.stringify({ revision: 1, value: tracked })));
  expect((await pending).message).toContain("工作区已切换");
});

it("keeps custom research groups local but account scoped, never loading the legacy key", () => {
  const groups = [{ id: "custom:one", name: "个人研究", source: "custom" as const, sourceLabel: "用户自定义", symbols: [], concepts: [], includeMacro: true, editable: true }];
  localStorage.setItem("vibedesk.research.catalyst-groups.v1", JSON.stringify(groups));
  expect(loadLocalCatalystResearchGroups()).toEqual([]);
  saveLocalCatalystResearchGroups(groups);
  expect(loadLocalCatalystResearchGroups()).toEqual(groups);
  bridge.config = { ...bridge.config, workspaceId: "two" };
  expect(loadLocalCatalystResearchGroups()).toEqual([]);
});
