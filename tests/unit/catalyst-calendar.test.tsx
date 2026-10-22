// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { CatalystCalendar } from "@/pages/CatalystCalendar";

const bridge = vi.hoisted(() => ({ config: null as any, listeners: new Set<(config: any) => void>(), context: undefined as any }));
vi.mock("@/lib/vibedesk", () => ({
  getVibeDeskConfig: () => bridge.config,
  waitForVibeDeskConfig: async () => bridge.config,
  isVibeDeskEmbedded: true,
  subscribeVibeDeskConfig: (fn: (value: any) => void) => { bridge.listeners.add(fn); return () => bridge.listeners.delete(fn); },
  createVibeDeskSnapshotCache: () => ({ read: () => null, write: vi.fn() }),
  publishVibeDeskContext: vi.fn(),
  registerVibeDeskContextProvider: (fn: any) => { bridge.context = fn; return () => {}; },
}));
vi.mock("@/lib/api", () => ({
  usesDeskResearch: () => true,
  researchDataScope: () => JSON.stringify(bridge.config),
  api: { catalysts: vi.fn(async () => ({ items: [], generatedAt: "2026-10-23", sources: [], gaps: [] })) },
}));
beforeEach(() => {
  bridge.listeners.clear();
  bridge.config = { moduleId: "catalyst-calendar", apiOrigin: "https://desk.test", storageGateway: "https://desk.test/api/mods/catalyst-calendar/storage",
    userId: "alice", workspaceId: "a", instanceId: "one", accessToken: "synthetic", permissions: ["storage.read", "storage.write"] };
  vi.stubGlobal("localStorage", { getItem: () => null, setItem: vi.fn() });
  vi.stubGlobal("fetch", vi.fn(async (url: string) => url.endsWith("/api/watchlists")
    ? new Response(JSON.stringify({ userId: "alice", workspaceId: bridge.config.workspaceId, revision: 0, groups: [] }))
    : new Response("{}", { status: 404 })));
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

async function compose() {
  const view = render(<CatalystCalendar />);
  const add = screen.getByRole("button", { name: "添加事件" });
  await waitFor(() => expect((add as HTMLButtonElement).disabled).toBe(false));
  fireEvent.click(add);
  fireEvent.change(screen.getByPlaceholderText("事件标题"), { target: { value: "合成跟踪事件" } });
  fireEvent.change(view.container.querySelector('input[type="date"]')!, { target: { value: "2026-10-25" } });
  return view;
}

it("save conflict keeps the draft and never marks an unsaved event as tracked", async () => {
  await compose();
  vi.mocked(fetch).mockResolvedValueOnce(new Response("{}", { status: 409 }));
  fireEvent.click(screen.getByRole("button", { name: "保存并跟踪" }));
  await screen.findByText(/本次未覆盖/);
  expect(screen.getByDisplayValue("合成跟踪事件")).toBeTruthy();
  expect(bridge.context().data.summary.trackedCount).toBe(0);
});

it("account change clears drafts and readonly permission disables writing", async () => {
  await compose();
  act(() => {
    bridge.config = { ...bridge.config, workspaceId: "b", permissions: ["storage.read"] };
    bridge.listeners.forEach(fn => fn(bridge.config));
  });
  expect(screen.queryByDisplayValue("合成跟踪事件")).toBeNull();
  await waitFor(() => expect((screen.getByRole("button", { name: "添加事件" }) as HTMLButtonElement).disabled).toBe(true));
  expect(bridge.context().actions.every((action: any) => !action.available)).toBe(true);
});
