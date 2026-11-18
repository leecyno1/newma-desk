import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ModHostConnection } from "@newma-desk/mod-sdk";
import { GlobalIntelligenceApp } from "./App";
import type { TopicSnapshot } from "./TopicDashboard";
import type { GlobalIntelDataSource } from "./data";

vi.mock("./IntelligenceMap", () => ({ IntelligenceMap: () => <div>地图</div> }));
beforeEach(() => {
  const values = new Map<string, string>();
  vi.stubGlobal("localStorage", { getItem: (key: string) => values.get(key) ?? null,
    setItem: vi.fn((key: string, value: string) => values.set(key, value)), removeItem: (key: string) => values.delete(key) });
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

function setup(workspaceId = "test", dataSource?: GlobalIntelDataSource) {
  let handler!: (id: string, input: Record<string, unknown>) => unknown;
  const publishContext = vi.fn();
  const host = {
    embedded: true,
    config: { instanceId: "topic-one", session: { accessToken: "synthetic-topic-token" }, grants: { permissions: ["market.read", "storage.write"], actions: [] }, environment: { theme: "light" }, user: { id: "reader" }, workspace: { id: workspaceId }, gateways: { data: window.location.origin } },
    subscribe: () => () => {}, setContextProvider: () => () => {}, publishContext,
    setUiActionHandler: (next: typeof handler) => { handler = next; return () => {}; },
  } as unknown as Extract<ModHostConnection, { embedded: true }>;
  const view = render(<GlobalIntelligenceApp embedded hostConnection={host} topicId={dataSource ? undefined : "fed-rates"} dataSource={dataSource} />);
  return { ...view, publishContext, invoke: (id = "global-intel.refresh") => Promise.resolve(handler(id, {})) };
}

describe("page refresh action receipt", () => {
  it("restores an interrupted forecast when the signed Desk page is reopened", async () => {
    const fetcher = vi.fn<typeof fetch>().mockResolvedValueOnce(json(snapshot("初始观测")))
      .mockReturnValueOnce(new Promise<Response>(() => {})).mockResolvedValueOnce(json(snapshot("重新读取的观测")));
    vi.stubGlobal("fetch", fetcher);
    const first = setup();
    await screen.findByText("初始观测");
    fireEvent.click(screen.getByRole("button", {name: "重新推演"}));
    first.unmount();
    const reopened = setup();
    await screen.findByText("重新读取的观测");
    expect(screen.getByRole("button", {name: "重新推演"})).toBeDisabled();
    await waitFor(() => expect(reopened.publishContext.mock.calls.at(-1)?.[0].data.summary).toMatchObject({
      forecastStatus: "unconfirmed", forecastRecovery: {persistence: "browser-local", readbackReady: true},
    }));
    expect(fetcher.mock.calls.map(call => call[1]?.method ?? "GET")).toEqual(["GET", "POST", "GET"]);
  });

  it("rejects Agent refresh during a forecast without interrupting the POST, then restores refresh", async () => {
    let finish!: (response: Response) => void;
    const fetcher = vi.fn<typeof fetch>().mockResolvedValueOnce(json(snapshot("初始观测")))
      .mockReturnValueOnce(new Promise<Response>(resolve => { finish = resolve; }))
      .mockResolvedValueOnce(json(snapshot("刷新观测")));
    vi.stubGlobal("fetch", fetcher);
    const page = setup();
    await screen.findByText("初始观测");
    fireEvent.click(screen.getByRole("button", { name: "重新推演" }));
    await waitFor(() => expect(page.publishContext.mock.calls.at(-1)?.[0].actions
      .find((action: {id: string}) => action.id === "global-intel.refresh")?.available).toBe(false));
    await expect(page.invoke()).rejects.toThrow("推演正在进行");
    expect(fetcher).toHaveBeenCalledTimes(2);
    expect(fetcher.mock.calls[1]?.[1]?.signal?.aborted).toBe(false);
    await act(async () => finish(json(snapshot("已保存").forecast)));
    let receipt!: Promise<unknown>;
    act(() => { receipt = page.invoke(); });
    await expect(receipt).resolves.toMatchObject({refreshed: true});
    await screen.findByText("刷新观测");
    expect(fetcher).toHaveBeenCalledTimes(3);
  });

  it("disables the standalone header refresh during a forecast and restores it on completion", async () => {
    let finish!: (response: Response) => void;
    const fetcher = vi.fn<typeof fetch>().mockResolvedValueOnce(json(snapshot("初始观测")))
      .mockReturnValueOnce(new Promise<Response>(resolve => { finish = resolve; }))
      .mockResolvedValueOnce(json(snapshot("刷新观测")));
    vi.stubGlobal("fetch", fetcher);
    render(<GlobalIntelligenceApp topicId="fed-rates" />);
    await screen.findByText("初始观测");
    fireEvent.click(screen.getByRole("button", { name: "重新推演" }));
    const refresh = screen.getByRole("button", { name: "刷新情报" });
    expect(refresh).toBeDisabled();
    fireEvent.click(refresh);
    expect(fetcher).toHaveBeenCalledTimes(2);
    await act(async () => finish(json(snapshot("已保存").forecast)));
    expect(refresh).toBeEnabled();
    fireEvent.click(refresh);
    await screen.findByText("刷新观测");
  });

  it.each(['renewal', 'runtime'] as const)('%s preserves unsubmitted topic assumptions in the same session', async change => {
    type Host = Extract<ModHostConnection, {embedded: true}>;
    let notify!: (config: Host['config']) => void;
    const config = {modId: 'fed-rates', instanceId: 'frame-one', user: {id: 'reader'}, workspace: {id: 'a'},
      environment: {theme: 'light'}, gateways: {data: window.location.origin},
      grants: {permissions: ['market.read', 'storage.write'], actions: []},
      session: {id: 'same-session', accessToken: 'first-token', expiresAt: '2030-01-01T00:00:00Z'}} as unknown as Host['config'];
    const host = {embedded: true, config, subscribe: (callback: typeof notify) => {notify = callback; return () => {};},
      setContextProvider: () => () => {}, publishContext: vi.fn(), setUiActionHandler: () => () => {}} as unknown as Host;
    const observation = {...snapshot('当前来源'), factors: [{id: 'growth', label: '增长假设', value: 30, min: 0, max: 100, unit: '%'}]};
    const fetcher = vi.fn().mockImplementation(async () => json(observation));
    vi.stubGlobal('fetch', fetcher);
    render(<GlobalIntelligenceApp embedded hostConnection={host} topicId="fed-rates" />);
    const slider = await screen.findByRole('slider');
    fireEvent.change(slider, {target: {value: '70'}});
    await act(async () => notify(change === 'renewal'
      ? {...config, session: {...config.session!, accessToken: 'renewed-token', expiresAt: '2030-02-01T00:00:00Z'}}
      : {...config, grants: {...config.grants, permissions: [...config.grants.permissions]},
        runtime: {owner: 'desk', aiExecution: 'gateway'}} as Host['config']));
    await waitFor(() => expect(screen.getByRole('slider')).toHaveValue('70'));
    expect(screen.getByRole('slider')).toBe(slider);
    expect(fetcher).toHaveBeenCalledTimes(change === 'renewal' ? 2 : 1);
    if (change === 'renewal') expect(new Headers(fetcher.mock.calls.at(-1)?.[1]?.headers).get('Authorization')).toBe('Bearer renewed-token');
  });

  it('keeps overview watch regions separated by workspace and does not claim unowned legacy records', async () => {
    type Host = Extract<ModHostConnection, {embedded: true}>;
    let notify!: (config: Host['config']) => void;
    let context!: () => ReturnType<typeof import('./App').buildGlobalIntelligenceContext>;
    const config = {instanceId: 'global-one', environment: {theme: 'light'}, user: {id: 'reader'}, workspace: {id: 'a'},
      gateways: {data: 'https://desk.example/api/data-services'}, grants: {permissions: ['market.read'], actions: []},
      session: {accessToken: 'a-token'}} as unknown as Host['config'];
    const host = {embedded: true, config, subscribe: (callback: typeof notify) => {notify = callback; return () => {};},
      setContextProvider: (provider: typeof context) => {context = provider; return () => {};}, publishContext: vi.fn(),
      setUiActionHandler: () => () => {}} as unknown as Host;
    const region = (name: string) => [{id: name, name, bounds: {west: 1, east: 2, south: 1, north: 2},
      createdAt: '2026-10-01T00:00:00Z', baselinePointIds: []}];
    const key = 'newma-desk.global-intelligence.watch-regions.v1';
    const legacy = JSON.stringify(region('无归属旧记录'));
    localStorage.setItem(key, legacy);
    localStorage.setItem(`${key}:["reader","a"]`, JSON.stringify(region('A 的关注')));
    localStorage.setItem(`${key}:["reader","b"]`, JSON.stringify(region('B 的关注')));
    const source: GlobalIntelDataSource = {health: async () => ({}), overview: async () => ({}), staticSnapshot: async () => ({}), crucixSnapshot: async () => ({}), subscribe: () => () => {}};
    render(<GlobalIntelligenceApp embedded hostConnection={host} dataSource={source} />);
    await waitFor(() => expect(JSON.stringify(context())).toContain('A 的关注'));
    expect(JSON.stringify(context())).not.toContain('无归属旧记录');
    await act(async () => {notify({...config, workspace: {id: 'b'}});});
    await waitFor(() => expect(JSON.stringify(context())).toContain('B 的关注'));
    expect(JSON.stringify(context())).not.toContain('A 的关注');
    expect(localStorage.getItem(key)).toBe(legacy);
    await act(async () => {notify(config);});
    await waitFor(() => expect(JSON.stringify(context())).toContain('A 的关注'));
    await act(async () => {notify({...config, grants: {permissions: [], actions: []}});});
    expect(JSON.stringify(context())).not.toContain('A 的关注');
    expect(screen.getByRole('status').textContent).toContain('权限');
  });

  it.each(['fed-rates', 'hormuz', 'us-china-trade'] as const)("%s clears old topic and context on batched A → B → A host changes", async topicId => {
    type Host = Extract<ModHostConnection, { embedded: true }>;
    let notify!: (config: Host['config']) => void;
    let context!: () => ReturnType<typeof import('./App').buildGlobalIntelligenceContext>;
    let handler!: (id: string, input: Record<string, unknown>) => unknown;
    const config = {
      instanceId: 'frame-one', environment: { theme: 'light' }, user: { id: 'reader' }, workspace: { id: 'a' },
      gateways: { data: 'https://desk.example/api/data-services' }, grants: { permissions: ['market.read', 'storage.write'], actions: [] },
      session: { accessToken: 'a-token' },
    } as unknown as Host['config'];
    const host = { embedded: true, config, subscribe: (callback: typeof notify) => { notify = callback; return () => {}; },
      setContextProvider: (provider: typeof context) => {context = provider; return () => {};},
      publishContext: vi.fn(), setUiActionHandler: (next: typeof handler) => {handler = next; return () => {};},
    } as unknown as Host;
    let finish!: (response: Response) => void;
    const fetcher = vi.fn().mockResolvedValueOnce(json({...snapshot('A 的旧证据'), topicId}))
      .mockImplementationOnce(() => new Promise<Response>(resolve => { finish = resolve; }));
    vi.stubGlobal('fetch', fetcher);
    render(<GlobalIntelligenceApp embedded hostConnection={host} topicId={topicId} />);
    await screen.findByText('A 的旧证据');
    let blocked!: Promise<unknown>;
    await act(async () => {
      notify({...config, workspace: {id: 'b'}, session: {...config.session!, accessToken: 'b-token'}});
      expect(document.body.innerHTML).not.toContain('A 的旧证据');
      expect(JSON.stringify(context())).not.toContain('A 的旧证据');
      blocked = Promise.resolve(handler('workspace.save-layout', {})).catch(error => error);
      notify(config);
    });
    expect(await blocked).toBeInstanceOf(Error);
    expect(screen.queryByText('A 的旧证据')).toBeNull();
    expect(JSON.stringify(context())).not.toContain('A 的旧证据');
    await waitFor(() => expect(fetcher).toHaveBeenCalledTimes(2));
    await act(async () => { finish(json({...snapshot('A 的新证据'), topicId})); });
    await screen.findByText('A 的新证据');
    const count = fetcher.mock.calls.length;
    await act(async () => { notify({...config, environment: {...config.environment, theme: 'dark'}}); });
    expect(fetcher).toHaveBeenCalledTimes(count);
    expect(screen.getByText('A 的新证据')).toBeVisible();
  });

  it("marks an in-flight refresh unconfirmed on an A → B → A transition", async () => {
    type Host = Extract<ModHostConnection, {embedded: true}>;
    let notify!: (config: Host['config']) => void;
    let handler!: (id: string, input: Record<string, unknown>) => unknown;
    const config = {instanceId: 'frame-one', environment: {theme: 'light'}, user: {id: 'reader'}, workspace: {id: 'a'},
      gateways: {data: 'https://desk.example/api/data-services'}, grants: {permissions: ['market.read'], actions: []},
      session: {accessToken: 'a-token'}} as unknown as Host['config'];
    const host = {embedded: true, config, subscribe: (callback: typeof notify) => {notify = callback; return () => {};},
      setContextProvider: () => () => {}, publishContext: vi.fn(),
      setUiActionHandler: (next: typeof handler) => {handler = next; return () => {};}} as unknown as Host;
    let release!: (response: Response) => void;
    const fetcher = vi.fn().mockResolvedValueOnce(json(snapshot('初始数据')))
      .mockImplementationOnce(() => new Promise<Response>(resolve => {release = resolve;}))
      .mockResolvedValueOnce(json(snapshot('新会话数据')));
    vi.stubGlobal('fetch', fetcher);
    render(<GlobalIntelligenceApp embedded hostConnection={host} topicId="fed-rates" />);
    await screen.findByText('初始数据');
    let receipt!: Promise<unknown>;
    await act(async () => {receipt = Promise.resolve(handler('global-intel.refresh', {})).catch(error => error);});
    await waitFor(() => expect(fetcher).toHaveBeenCalledTimes(2));
    await act(async () => {notify({...config, workspace: {id: 'b'}}); notify(config);});
    expect(String(await receipt)).toContain('未确认');
    await screen.findByText('新会话数据');
    await act(async () => {release(json(snapshot('迟到旧数据')));});
    expect(screen.queryByText('迟到旧数据')).toBeNull();
    expect(fetcher).toHaveBeenCalledTimes(3);
  });

  it.each(["ready", "partial"])("does not return an Agent refresh receipt until the current stream settles as %s", async (expected) => {
    let payload!: (value: Record<string, unknown>) => void;
    const dataSource: GlobalIntelDataSource = {
      health: async () => ({}), overview: async () => ({}), staticSnapshot: async () => ({}), crucixSnapshot: async () => ({}),
      subscribe: (onPayload) => { payload = onPayload; return () => {}; },
    };
    const page = setup("stream-check", dataSource);
    await act(async () => payload({ _complete: true, _done: 1, _total: 1, nav_warnings: { warnings: [] } }));
    let result!: Promise<unknown>;
    let completed = false;
    await act(async () => { result = page.invoke(); void result.then(() => { completed = true; }); });
    await act(async () => payload({ _cached: true, _stale: true, _complete: true, _done: 48, _total: 48,
      nav_warnings: { warnings: [] }, timestamp: "2026-10-23T00:00:00Z" }));
    expect(completed).toBe(false);
    await act(async () => payload({ _cached: false, _stale: false, _complete: false, _done: 1, _total: 2,
      nav_warnings: { warnings: [] }, ...(expected === "partial" ? { earthquakes: { error: "source unavailable" } } : {}) }));
    expect(completed).toBe(false);
    await act(async () => payload({ _cached: false, _stale: false, _complete: true, _done: 2, _total: 2,
      timestamp: new Date().toISOString() }));
    await expect(result).resolves.toMatchObject({ refreshed: true, status: expected,
      context: { data: { summary: { refresh: { status: expected } } } } });
    expect(page.publishContext.mock.calls.at(-1)?.[0].data.summary.refresh.status).toBe(expected);
    page.unmount();
  });

  it("signs topic reads and forecast writes without client-chosen ownership", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce(json(snapshot("专题数据")))
      .mockResolvedValueOnce(json(snapshot("结果").forecast)));
    const page = setup();
    await screen.findByText("专题数据");
    fireEvent.click(screen.getByRole("button", { name: "重新推演" }));
    await waitFor(() => expect(fetch).toHaveBeenCalledTimes(2));
    const [url, options] = vi.mocked(fetch).mock.calls[1]!;
    expect(String(url)).toMatch(/\/api\/global-topics\/fed-rates\/forecast$/);
    expect(options).toMatchObject({ method: "POST", credentials: "omit", redirect: "error" });
    expect(new Headers(options?.headers).get("Authorization")).toBe("Bearer synthetic-topic-token");
    expect(new Headers(options?.headers).get("X-Newma-Desk-Instance-Id")).toBe("topic-one");
    expect(JSON.parse(String(options?.body))).toEqual({ factors: {} });
    await waitFor(() => expect(screen.getByRole("button", { name: "重新推演" })).not.toBeDisabled());
    page.unmount();
  });

  it("signs overview requests and replaces the active stream when host authorization changes", async () => {
    const cancellations: ReturnType<typeof vi.fn>[] = [];
    vi.stubGlobal("fetch", vi.fn().mockImplementation(async (url: string) => {
      if (!url.endsWith("/stream")) return json({});
      const cancel = vi.fn();
      cancellations.push(cancel);
      return new Response(new ReadableStream({ cancel }), { headers: { "content-type": "text/event-stream" } });
    }));
    type Host = Extract<ModHostConnection, { embedded: true }>;
    let notify!: (config: Host["config"]) => void;
    const config = {
      instanceId: "frame-one", environment: { theme: "light" }, user: { id: "reader" }, workspace: { id: "test" },
      gateways: { data: "https://desk.example/api/data-services" }, grants: { permissions: ["market.read"], actions: [] },
      session: { accessToken: "first-token" },
    } as unknown as Host["config"];
    const host = { embedded: true, config, subscribe: (callback: typeof notify) => { notify = callback; return () => {}; },
      setContextProvider: () => () => {}, publishContext: vi.fn(), setUiActionHandler: () => () => {},
    } as unknown as Host;
    const page = render(<GlobalIntelligenceApp embedded hostConnection={host} />);
    await waitFor(() => expect(fetch).toHaveBeenCalledTimes(3));
    for (const [url, options] of vi.mocked(fetch).mock.calls) {
      expect(String(url)).toMatch(/^https:\/\/desk.example\/api\//);
      expect(new Headers(options?.headers).get("Authorization")).toBe("Bearer first-token");
      expect(new Headers(options?.headers).get("X-Newma-Desk-Instance-Id")).toBe("frame-one");
    }
    await act(async () => notify({ ...config, session: { ...config.session!, accessToken: "second-token" } }));
    await waitFor(() => expect(fetch).toHaveBeenCalledTimes(6));
    expect(cancellations[0]).toHaveBeenCalledOnce();
    expect(new Headers(vi.mocked(fetch).mock.calls.at(-1)?.[1]?.headers).get("Authorization")).toBe("Bearer second-token");
    await act(async () => notify({ ...config, grants: { permissions: [], actions: [] } }));
    expect(cancellations[1]).toHaveBeenCalledOnce();
    expect(fetch).toHaveBeenCalledTimes(6);
    page.unmount();
  });

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
