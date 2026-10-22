import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ModHostConnection } from "@newma-desk/mod-sdk";
import { GlobalIntelligenceApp } from "./App";
import type { TopicSnapshot } from "./TopicDashboard";

vi.mock("./IntelligenceMap", () => ({ IntelligenceMap: () => <div>地图</div> }));
beforeEach(() => {
  const values = new Map<string, string>();
  vi.stubGlobal("localStorage", { getItem: (key: string) => values.get(key) ?? null,
    setItem: vi.fn((key: string, value: string) => values.set(key, value)) });
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

const snapshot = (value: string): TopicSnapshot => ({
  topicId: "fed-rates", title: "联储加息", subtitle: "测试", question: "测试假设", accent: "cyan",
  metrics: [{ label: "测试指标", value, change: "合成测试，非真实数据" }], factors: [], series: [],
  observations: [], events: [], transmission: [], sources: [], dataMode: "source-observations",
  forecast: { generatedAt: "2026-10-22", probabilities: [], dominantScenario: "", confidence: 0,
    method: "测试", disclaimer: "测试" }, updatedAt: "2026-10-22",
});
const json = (value: unknown, status = 200) => new Response(JSON.stringify(value), { status });

function setup(workspaceId = "test") {
  let handler!: (id: string, input: Record<string, unknown>) => unknown;
  const publishContext = vi.fn();
  const host = {
    embedded: true,
    config: { environment: { theme: "light" }, user: { id: "reader" }, workspace: { id: workspaceId }, gateways: { data: window.location.origin } },
    subscribe: () => () => {}, setContextProvider: () => () => {}, publishContext,
    setUiActionHandler: (next: typeof handler) => { handler = next; return () => {}; },
  } as unknown as Extract<ModHostConnection, { embedded: true }>;
  const view = render(<GlobalIntelligenceApp embedded hostConnection={host} topicId="fed-rates" />);
  return { ...view, publishContext, invoke: (id = "global-intel.refresh") => Promise.resolve(handler(id, {})) };
}

describe("page refresh action receipt", () => {
  it("keeps saved views inside the current user, workspace and page", async () => {
    vi.stubGlobal("fetch", vi.fn().mockImplementation(async () => json(snapshot("视图数据"))));
    const first = setup();
    await screen.findByText("视图数据");
    await first.invoke("workspace.save-layout");
    first.unmount();
    const second = setup("another");
    await screen.findByText("视图数据");
    await second.invoke("workspace.save-layout");
    const keys = vi.mocked(localStorage.setItem).mock.calls.map(([key]) => key).filter((key) => key.startsWith("newma-desk.global-intelligence.layouts.v1:"));
    expect(keys).toEqual([
      'newma-desk.global-intelligence.layouts.v1:["reader","test","fed-rates"]',
      'newma-desk.global-intelligence.layouts.v1:["reader","another","fed-rates"]',
    ]);
  });

  it("waits for this refresh and publishes its actual context before success", async () => {
    let resolve!: (response: Response) => void;
    const request = new Promise<Response>((done) => { resolve = done; });
    vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce(json(snapshot("初始值"))).mockReturnValueOnce(request));
    const page = setup();
    await screen.findByText("初始值");
    let result!: Promise<unknown>;
    let completed = false;
    await act(async () => { result = page.invoke(); result.then(() => { completed = true; }); });
    expect(completed).toBe(false);
    await screen.findByText("刷新中");
    await act(async () => { resolve(json(snapshot("更新值"))); });
    await expect(result).resolves.toMatchObject({ refreshed: true, context: { data: { summary: { metrics: [{ value: "更新值" }] } } } });
    expect(page.publishContext.mock.calls.at(-1)?.[0].data.summary.metrics[0].value).toBe("更新值");
  });

  it("rejects a failed refresh even while previous data remains visible", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce(json(snapshot("保留旧值"))).mockResolvedValueOnce(json({}, 503)));
    const page = setup();
    await screen.findByText("保留旧值");
    let failure!: Promise<unknown>;
    await act(async () => { failure = page.invoke().catch((error) => error); });
    expect(await failure).toBeInstanceOf(Error);
    expect(await screen.findByText("保留旧值")).toBeVisible();
    await waitFor(() => expect(page.publishContext.mock.calls.at(-1)?.[0].data.summary).toMatchObject({ loadState: "error", displayingPreviousData: true }));
  });

  it("rejects concurrent execution and page exit without retrying the request", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce(json(snapshot("初始值"))).mockImplementation(() => new Promise(() => {})));
    const page = setup();
    await screen.findByText("初始值");
    let failure!: Promise<unknown>;
    await act(async () => { failure = page.invoke().catch((error) => error); });
    await expect(page.invoke()).rejects.toThrow("刷新");
    page.unmount();
    expect(await failure).toBeInstanceOf(Error);
    expect(fetch).toHaveBeenCalledTimes(2);
  });
});
