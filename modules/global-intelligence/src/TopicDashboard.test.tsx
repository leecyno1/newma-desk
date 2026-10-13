import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { chartPath, GlobalTopicDashboard, type TopicSnapshot } from "./TopicDashboard";
import { buildGlobalTopicContext, GLOBAL_TOPICS, type GlobalTopicId } from "./topicContext";

beforeEach(() => {
  const values = new Map<string, string>();
  vi.stubGlobal("localStorage", {
    getItem: (key: string) => values.get(key) ?? null,
    setItem: (key: string, value: string) => values.set(key, value),
    removeItem: (key: string) => values.delete(key),
  });
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

function snapshot(topicId: GlobalTopicId = "fed-rates", value = 58): TopicSnapshot {
  return {
    topicId, title: GLOBAL_TOPICS[topicId].title, subtitle: "专题示例", question: "如何变化？", accent: "cyan",
    metrics: [{ label: "示例指标", value: "5.50%", change: "参考" }],
    factors: [{ id: "pressure", label: "压力", min: 0, max: 100, value }],
    series: [{ id: "rate", label: "参考利率", color: "#38bdf8" }],
    observations: [{ seriesId: "rate", date: "2026-08", value: 5.5, unit: "%", source: "参考" }],
    events: Array.from({ length: 6 }, (_, index) => ({ id: `${topicId}-${index}`, date: "2026-08-12", title: `${topicId} 示例事件 ${index}`, summary: "待核验", source: "参考来源", sourceUrl: "https://example.com", impact: "medium", confidence: 0.9 })),
    transmission: ["参考输入", "示例输出"], sources: ["参考来源"],
    forecast: { generatedAt: "2026-08-20T08:00:00Z", probabilities: [{ label: `示例情景 ${value}`, probability: 100 }], dominantScenario: `示例情景 ${value}`, confidence: 0.6, method: "规则模型", disclaimer: "非投资建议" },
    dataMode: "reference-baseline", updatedAt: "2026-08-20T08:00:00Z",
  };
}

const json = (value: unknown, status = 200) => new Response(JSON.stringify(value), { status, headers: { "Content-Type": "application/json" } });
const deferred = <T,>() => {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => { resolve = done; });
  return { promise, resolve };
};

function maritimeEvidence() {
  return {
    status: "stale", reason: "来源缓存已过期", source: "NGA", sourceUrl: "https://msi.nga.mil/",
    collectedAt: "2026-08-12T14:01:51Z", cacheExpiresAt: "2026-08-12T15:01:51Z",
    scannedCount: 386, matchedCount: 1, counts: { "hormuz-mentioned": 0, "nearby-coordinate": 0, regional: 1 },
    selectionRule: "完整正文筛选，区域不等于海峡。", limitations: "警告数量不是风险分数。",
    warnings: [{ id: "P:2024-1", reference: "HYDROPAC 2024-1", title: "PERSIAN GULF. SURVEY WORKS.",
      text: "PERSIAN GULF. FULL WARNING TEXT.", textTruncated: false, publishedAt: "2024-05-08T16:53:00Z",
      publicationDateRaw: "081653Z MAY 2024", scope: "regional", scopeLabel: "区域性公告", authority: "NAVAREA IX 1/24",
      sourceUrl: "https://msi.nga.mil/", status: "not-cancelled-in-snapshot", currentValidity: "unverified" }],
  };
}

describe("topic page and Agent share one state", () => {
  it("restores reading controls per user and workspace, but reloads the selected evidence", async () => {
    const identity = { userId: "reader-a", workspaceId: "desk-a" };
    let maritime = maritimeEvidence();
    vi.stubGlobal("fetch", vi.fn().mockImplementation(() => Promise.resolve(json({ ...snapshot("hormuz"), maritime }))));
    const publish = vi.fn();
    const props = { topicId: "hormuz" as const, refreshNonce: 0, cacheIdentity: identity, onContextChange: publish };
    const first = render(<GlobalTopicDashboard {...props} />);
    await screen.findByText("HYDROPAC 2024-1");
    fireEvent.click(screen.getByRole("button", { name: "区域公告" }));
    fireEvent.change(screen.getByRole("textbox", { name: "警告关键词" }), { target: { value: "HYDROPAC" } });
    fireEvent.change(screen.getByRole("combobox", { name: "警告排序" }), { target: { value: "newest" } });
    fireEvent.click(screen.getByText("HYDROPAC 2024-1"));
    first.unmount();

    maritime = { ...maritime, warnings: maritime.warnings.map((warning) => ({ ...warning, text: "RELOADED OFFICIAL TEXT." })) };
    const reopened = render(<GlobalTopicDashboard {...props} />);
    await waitFor(() => expect(screen.getByText("RELOADED OFFICIAL TEXT.")).toBeVisible());
    expect(screen.getByRole("textbox", { name: "警告关键词" })).toHaveValue("HYDROPAC");
    expect(screen.getByRole("combobox", { name: "警告排序" })).toHaveValue("newest");
    const current = () => buildGlobalTopicContext("hormuz", publish.mock.calls.at(-1)![0]);
    expect(current().selection?.warningId).toBe("P:2024-1");
    expect(current().data.summary?.maritimeView).toMatchObject({ scope: "regional", selectedWarning: { text: "RELOADED OFFICIAL TEXT." } });

    for (const cacheIdentity of [{ ...identity, workspaceId: "desk-b" }, { ...identity, userId: "reader-b" }]) {
      reopened.rerender(<GlobalTopicDashboard {...props} cacheIdentity={cacheIdentity} />);
      await screen.findByText("HYDROPAC 2024-1");
      expect(current().selection?.warningId).toBeNull();
      expect(screen.getByRole("textbox", { name: "警告关键词" })).toHaveValue("");
      expect(screen.getByRole("button", { name: /^全部$/ })).toHaveAttribute("aria-pressed", "true");
    }
    maritime = { ...maritime, warnings: [] };
    reopened.rerender(<GlobalTopicDashboard {...props} />);
    await screen.findByText("本次快照未匹配到相关记录，不代表海峡安全或没有警告。");
    expect(current().selection?.warningId).toBeNull();
    expect(current().visibleBlocks?.some((block) => block.id === "topic-maritime-detail")).toBe(false);
  });

  it("shares maritime filters, selected text and dates, clearing hidden or removed selections", async () => {
    const maritime = maritimeEvidence();
    maritime.warnings.push({ ...maritime.warnings[0]!, id: "P:2026-2", reference: "HYDROPAC 2026-2", title: "HORMUZ. DANGER AREA.", text: "OTHER OFFICIAL TEXT", scope: "hormuz-mentioned", scopeLabel: "明确提及霍尔木兹", publishedAt: "2026-09-01T12:00:00Z" });
    maritime.matchedCount = 2;
    maritime.counts["hormuz-mentioned"] = 1;
    const data = { ...snapshot("hormuz"), dataMode: "source-backed", freshness: "stale", maritime };
    vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce(json(data)).mockResolvedValueOnce(json({ ...data, maritime: { ...maritime, warnings: [], matchedCount: 0, counts: { regional: 0, "hormuz-mentioned": 0, "nearby-coordinate": 0 } } })));
    const publish = vi.fn();
    render(<GlobalTopicDashboard topicId="hormuz" refreshNonce={0} onContextChange={publish} />);
    await screen.findByText("旧快照 · 当前有效性待核验");
    expect(screen.getByText("发布 2024-05-08 16:53 UTC")).toBeVisible();
    expect(screen.getByText("最近成功采集 2026-08-12 14:01 UTC")).toBeVisible();
    fireEvent.click(screen.getByText("HYDROPAC 2024-1"));
    expect(screen.getByText("PERSIAN GULF. FULL WARNING TEXT.")).toBeVisible();
    const context = buildGlobalTopicContext("hormuz", publish.mock.calls.at(-1)![0]);
    expect(context.data.summary?.maritime).toEqual(maritime);
    expect(context.visibleBlocks?.some((block) => block.id === "topic-maritime")).toBe(true);
    expect(context.data.summary?.maritimeSemantics).toContain("不能证明无警告");
    expect(context.selection?.warningId).toBe("P:2024-1");
    expect(context.data.summary?.maritimeView).toMatchObject({ selectedWarning: maritime.warnings[0], filterCoverage: "loaded-records-only" });
    expect(context.visibleBlocks?.some((block) => block.id === "topic-maritime-detail")).toBe(true);
    const current = () => buildGlobalTopicContext("hormuz", publish.mock.calls.at(-1)![0]);
    fireEvent.change(screen.getByRole("textbox", { name: "警告关键词" }), { target: { value: "FULL WARNING TEXT" } });
    expect(current().selection?.warningId).toBeNull();
    expect(current().filters?.maritime).toMatchObject({ query: "FULL WARNING TEXT", coverage: "loaded-records-only" });
    expect(current().data.summary?.maritimeView).toMatchObject({ visibleWarningIds: ["P:2024-1"] });
    fireEvent.click(screen.getByRole("button", { name: /^明确提及霍尔木兹$/ }));
    expect(screen.getByText("当前筛选在已载入记录中没有匹配，不代表来源没有相关警告。")).toBeVisible();
    expect(current().data.summary?.maritime).toEqual(maritime); // Filtering does not alter source-wide counts.
    fireEvent.click(screen.getByRole("button", { name: "清除筛选" }));
    fireEvent.change(screen.getByRole("combobox", { name: "警告排序" }), { target: { value: "newest" } });
    const list = screen.getByRole("region", { name: "匹配的航行警告" });
    expect(within(list).getAllByRole("article")[0]).toHaveTextContent("HYDROPAC 2026-2");
    fireEvent.click(screen.getByText("HYDROPAC 2026-2"));
    expect(current().selection?.warningId).toBe("P:2026-2");
    fireEvent.click(screen.getByText("HYDROPAC 2026-2"));
    expect(current().selection?.warningId).toBeNull();
    fireEvent.click(screen.getByText("HYDROPAC 2026-2"));
    fireEvent.click(screen.getByRole("button", { name: "刷新专题" }));
    await screen.findByText("本次快照未匹配到相关记录，不代表海峡安全或没有警告。");
    expect(current().selection?.warningId).toBeNull();
    expect(current().visibleBlocks?.some((block) => block.id === "topic-maritime-detail")).toBe(false);
  });

  it("spaces observations by date, centers a flat series and never draws a single-point trend", async () => {
    expect(chartPath([{ date: "2026-01-01", value: 5 }, { date: "2026-01-02", value: 5 }, { date: "2026-01-11", value: 5 }], 100, 60)).toBe("M0.0,30.0 L10.0,30.0 L100.0,30.0");
    const data = { ...snapshot(), dataMode: "source-backed", freshness: "fresh", sourceStatus: [{ id: "fred", label: "FRED", url: "https://fred.stlouisfed.org", status: "ready" }], dataWarning: "来源观测，非实时行情", gaps: ["市场定价尚未接入"] };
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(json(data)));
    const publish = vi.fn();
    render(<GlobalTopicDashboard topicId="fed-rates" refreshNonce={0} onContextChange={publish} />);
    await screen.findByText("仅 1 个观测，暂无连续曲线");
    expect(screen.queryByRole("img", { name: /趋势图/ })).toBeNull();
    expect(screen.getByText("来源观测 · 6 条事件")).toBeVisible();
    expect(screen.getByText("市场定价尚未接入")).toBeVisible();
    const state = publish.mock.calls.at(-1)![0];
    expect(buildGlobalTopicContext("fed-rates", state).data.freshness).toBe("fresh");
    expect(state.sourceStatus[0].status).toBe("ready");
  });

  it("separates available metrics from missing events and exposes source collection time", async () => {
    const data = {
      ...snapshot("hormuz"), events: [], eventCoverage: { count: 0, readySourceCount: 0, staleSourceCount: 0 },
      dataMode: "source-backed", freshness: "stale" as const,
      sourceStatus: [{ id: "nga", label: "NGA", url: "https://example.com/nga", status: "stale", collectedAt: "2026-08-12T14:01:51Z", reason: "来源缓存已过期" }],
    };
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(json(data)));
    const publish = vi.fn();
    render(<GlobalTopicDashboard topicId="hormuz" refreshNonce={0} onContextChange={publish} />);
    await screen.findByText("来源观测 · 暂无相关事件");
    expect(screen.getByText("当前来源未返回相关记录，不代表没有发生事件。")).toBeVisible();
    expect(screen.getByText(/采集 .*来源缓存已过期/)).toBeVisible();
    expect(screen.getByText(/不是事件发生概率/)).toBeVisible();
    const context = buildGlobalTopicContext("hormuz", publish.mock.calls.at(-1)![0]);
    expect(context.data.summary).toMatchObject({ eventCoverage: { count: 0 }, freshness: "stale" });
  });
  it.each(Object.keys(GLOBAL_TOPICS) as GlobalTopicId[])("uses the correct %s identity and does not call baseline generation a data timestamp", (topicId) => {
    const context = buildGlobalTopicContext(topicId, { ...snapshot(topicId), generatedAt: new Date().toISOString() });
    expect(context.view).toEqual(GLOBAL_TOPICS[topicId]);
    expect(context.data).toMatchObject({ freshness: "unknown", summary: { dataMode: "reference-baseline", dataWarning: expect.stringContaining("内置示例") } });
    expect(context.data.asOf).toBeUndefined();
    expect(context.visibleBlocks?.map((block) => block.id)).not.toContain("global-intelligence-map");
    const switching = buildGlobalTopicContext(topicId, { topicId: "other", metrics: [{ value: "old" }], forecast: { dominantScenario: "old" } });
    expect(switching.visibleBlocks).toEqual([]);
    expect(switching.data.summary).not.toHaveProperty("forecast");
  });

  it("publishes edited and applied parameters separately, retaining all evidence through failure and retry", async () => {
    const initial = snapshot();
    const nextForecast = { ...initial.forecast, dominantScenario: "更新结果", probabilities: [{ label: "更新结果", probability: 100 }] };
    const fetcher = vi.fn<typeof fetch>().mockResolvedValueOnce(json(initial)).mockResolvedValueOnce(json({}, 503)).mockResolvedValueOnce(json(nextForecast));
    vi.stubGlobal("fetch", fetcher);
    const publish = vi.fn();
    render(<GlobalTopicDashboard topicId="fed-rates" refreshNonce={0} gatewayBaseUrl="http://127.0.0.1:8911" onContextChange={publish} />);
    const state = () => publish.mock.calls.at(-1)![0];
    await screen.findByText("5.50%");
    expect(screen.getByText(/指标、曲线和事件为内置示例/)).toBeVisible();
    expect(screen.queryByText(/置信度 90%/)).toBeNull();
    fireEvent.change(screen.getByRole("slider", { name: "压力" }), { target: { value: "80" } });
    expect(state()).toMatchObject({ factors: { pressure: 80 }, forecastFactors: { pressure: 58 }, forecastPending: true });
    expect(screen.getByRole("status")).toHaveTextContent("当前结果仍对应上次参数");
    fireEvent.click(screen.getByRole("button", { name: "重新推演" }));
    await screen.findByRole("alert");
    expect(screen.getByRole("alert")).toHaveTextContent("推演失败");
    expect(state()).toMatchObject({ forecastStatus: "error", forecast: initial.forecast, factors: { pressure: 80 } });
    fireEvent.click(screen.getByRole("button", { name: "重新推演" }));
    await screen.findByText("更新结果");
    expect(state()).toMatchObject({
      metrics: initial.metrics, events: initial.events, observations: initial.observations,
      forecast: nextForecast, forecastFactors: { pressure: 80 }, forecastPending: false,
      generatedAt: initial.updatedAt, dataMode: "reference-baseline",
    });
    expect(fetcher.mock.calls[2]![0]).toBe("http://127.0.0.1:8911/api/global-topics/fed-rates/forecast");
    expect(JSON.parse(fetcher.mock.calls[2]![1]!.body as string)).toEqual({ factors: { pressure: 80 } });
  });

  it("keeps the previous page after a failed refresh, then resets visible results and context together on success", async () => {
    const initial = snapshot();
    const updated = snapshot("fed-rates", 42);
    vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce(json(initial)).mockResolvedValueOnce(json({}, 503)).mockResolvedValueOnce(json(updated)));
    const publish = vi.fn();
    render(<GlobalTopicDashboard topicId="fed-rates" refreshNonce={0} onContextChange={publish} />);
    await screen.findByText("5.50%");
    fireEvent.change(screen.getByRole("slider"), { target: { value: "80" } });
    fireEvent.click(screen.getByRole("button", { name: "刷新专题" }));
    await screen.findByRole("alert");
    expect(screen.getByText("5.50%")).toBeVisible();
    expect(screen.getByRole("slider")).toHaveValue("80");
    expect(publish.mock.calls.at(-1)![0]).toMatchObject({ loadState: "error", displayingPreviousData: true, forecastPending: true });
    fireEvent.click(screen.getByRole("button", { name: "重试" }));
    await screen.findByText("示例情景 42");
    expect(screen.getByRole("slider")).toHaveValue("42");
    expect(publish.mock.calls.at(-1)![0]).toMatchObject({ loadState: "ready", displayingPreviousData: false, factors: { pressure: 42 }, forecastFactors: { pressure: 42 }, forecastPending: false });
  });

  it("ignores a superseded forecast response after refreshing the snapshot", async () => {
    const oldRequest = deferred<Response>();
    const initial = snapshot();
    const fetcher = vi.fn<typeof fetch>().mockResolvedValueOnce(json(initial)).mockReturnValueOnce(oldRequest.promise).mockResolvedValueOnce(json(snapshot("fed-rates", 42)));
    vi.stubGlobal("fetch", fetcher);
    const publish = vi.fn();
    render(<GlobalTopicDashboard topicId="fed-rates" refreshNonce={0} onContextChange={publish} />);
    await screen.findByText("5.50%");
    fireEvent.click(screen.getByRole("button", { name: "重新推演" }));
    fireEvent.click(screen.getByRole("button", { name: "刷新专题" }));
    await screen.findByText("示例情景 42");
    expect(fetcher.mock.calls[1]![1]!.signal!.aborted).toBe(true);
    await act(async () => oldRequest.resolve(json(initial.forecast)));
    expect(publish.mock.calls.at(-1)![0].forecast.dominantScenario).toBe("示例情景 42");
    expect(screen.queryByText("示例情景 58")).toBeNull();
  });

  it("clears the old topic immediately and ignores its late response", async () => {
    const oldRequest = deferred<Response>();
    const newRequest = deferred<Response>();
    const fetcher = vi.fn<typeof fetch>().mockReturnValueOnce(oldRequest.promise).mockReturnValueOnce(newRequest.promise);
    vi.stubGlobal("fetch", fetcher);
    const publish = vi.fn();
    const { rerender } = render(<GlobalTopicDashboard topicId="fed-rates" refreshNonce={0} onContextChange={publish} />);
    rerender(<GlobalTopicDashboard topicId="hormuz" refreshNonce={0} onContextChange={publish} />);
    expect(publish.mock.calls.at(-1)![0]).toMatchObject({ topicId: "hormuz", loadState: "loading" });
    expect(publish.mock.calls.at(-1)![0]).not.toHaveProperty("metrics");
    expect(fetcher.mock.calls[0]![1]!.signal!.aborted).toBe(true);
    await act(async () => newRequest.resolve(json(snapshot("hormuz"))));
    await act(async () => oldRequest.resolve(json(snapshot())));
    await waitFor(() => expect(publish.mock.calls.at(-1)![0].topicId).toBe("hormuz"));
    expect(screen.getByText("hormuz 示例事件 0")).toBeVisible();
    expect(screen.queryByText("fed-rates 示例事件 0")).toBeNull();
  });
});
