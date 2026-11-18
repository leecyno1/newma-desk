import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { GlobalIntelligenceDashboard } from "./Dashboard";
import { buildGlobalIntelligenceContext } from "./App";
import type { GlobalIntelDataSource } from "./data";

vi.mock("./IntelligenceMap", () => ({ IntelligenceMap: () => <div>地图</div> }));

beforeEach(() => {
  for (const key of ["localStorage", "sessionStorage"]) {
    const values = new Map<string, string>();
    vi.stubGlobal(key, {
      getItem: (name: string) => values.get(name) ?? null,
      setItem: (name: string, value: string) => values.set(name, value),
      removeItem: (name: string) => values.delete(name),
    });
  }
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

describe("navigation warning page and Agent evidence", () => {
  it('does not read or write private browser records while an embedded identity is absent', async () => {
    const legacyKey = 'newma-desk.global-intelligence.watch-regions.v1';
    localStorage.setItem(legacyKey, JSON.stringify([{id: 'legacy', name: '无归属旧关注', bounds: {west: 1, east: 2, south: 1, north: 2}, baselinePointIds: []}]));
    const read = vi.spyOn(localStorage, 'getItem');
    const write = vi.spyOn(localStorage, 'setItem');
    const sessionRead = vi.spyOn(sessionStorage, 'getItem');
    const sessionWrite = vi.spyOn(sessionStorage, 'setItem');
    const context = vi.fn();
    const source: GlobalIntelDataSource = {health: async () => ({}), overview: async () => ({}), staticSnapshot: async () => ({}), crucixSnapshot: async () => ({}), subscribe: () => () => {}};
    render(<GlobalIntelligenceDashboard dataSource={source} theme="light" refreshNonce={0} scopedStorage onRefresh={() => {}} onContextChange={context} />);
    await waitFor(() => expect(context).toHaveBeenCalled());
    expect(JSON.stringify(context.mock.calls)).not.toContain('无归属旧关注');
    expect(read).not.toHaveBeenCalled();
    expect(write).not.toHaveBeenCalled();
    expect(sessionRead).not.toHaveBeenCalled();
    expect(sessionWrite).not.toHaveBeenCalled();
  });

  it('writes overview preferences and history only to the active user and workspace', async () => {
    const write = vi.spyOn(localStorage, 'setItem');
    const sessionWrite = vi.spyOn(sessionStorage, 'setItem');
    const context = vi.fn();
    const source: GlobalIntelDataSource = {health: async () => ({}), overview: async () => ({}), staticSnapshot: async () => ({}), crucixSnapshot: async () => ({}), subscribe: () => () => {}};
    render(<GlobalIntelligenceDashboard dataSource={source} theme="light" refreshNonce={0} scopedStorage
      cacheIdentity={{userId: 'reader', workspaceId: 'desk-a'}} onRefresh={() => {}} onContextChange={context} />);
    await waitFor(() => expect(context).toHaveBeenCalled());
    const expected = ['watch-regions.v1', 'route-alerts.v1', 'event-history.v1', 'event-dispositions.v1', 'media-watch-rules.v1', 'media-topic-history.v2'];
    const names = write.mock.calls.map(([name]) => name);
    for (const item of expected) expect(names).toContain(`newma-desk.global-intelligence.${item}:["reader","desk-a"]`);
    expect(sessionWrite.mock.calls.map(([name]) => name)).toContain('newma-desk.global-intelligence.military-tracks.v1:["reader","desk-a"]');
    expect(names.every(name => name.endsWith(':["reader","desk-a"]'))).toBe(true);
  });

  it.each(["light", "dark"] as const)("keeps missing seismic coverage unknown in the %s page and Agent", async (theme) => {
    const onContextChange = vi.fn();
    let send!: (value: Record<string, unknown>) => void;
    const dataSource: GlobalIntelDataSource = {
      health: async () => ({}), overview: async () => ({}), staticSnapshot: async () => ({}), crucixSnapshot: async () => ({}),
      subscribe: (payload) => { send = payload; return () => {}; },
    };
    render(<GlobalIntelligenceDashboard dataSource={dataSource} theme={theme} refreshNonce={0} onRefresh={() => {}} onContextChange={onContextChange} />);
    act(() => send({ _complete: true, _done: 4, _total: 4,
      source_health: { usgs: { status: "closed" } },
      earthquakes: { status: "unavailable", count: null, error: "USGS目录未取得" },
      nuclear_monitor: { status: "unavailable", total_flagged_events: null, error: "近场样本未知" },
      population_exposure: { status: "partial", coverage: { available: 1, expected: 3 }, note: "静态城市名录人口，非实际受灾人数" },
      signal_convergence: { status: "unavailable", error: "区域样本未知", hotspots: [{ name: "middle_east", lat: 33, lon: 44, convergence_score: null, signals: { earthquakes: null } }] },
    }));
    await waitFor(() => expect(onContextChange.mock.calls.at(-1)?.[0].sourceHealth.items).toContainEqual(expect.objectContaining({ id: "earthquakes", status: "error" })));
    const context = onContextChange.mock.calls.at(-1)![0];
    expect(context.trendRadar).toMatchObject({ maxConvergence: null, hotspots: [expect.objectContaining({ score: null, earthquakeCount: null })] });
    expect(context.sourceHealth.items).toContainEqual(expect.objectContaining({ id: "population_exposure", status: "degraded", reason: expect.stringContaining("覆盖 1/3") }));
    fireEvent.click(screen.getByRole("button", { name: "详情" }));
    const panel = screen.getByRole("complementary", { name: "数据源健康控制台" });
    expect(panel).toHaveTextContent("USGS目录未取得");
    expect(panel).toHaveTextContent("非实际受灾人数");
    act(() => send({ earthquakes: { status: "ok", freshness: "fresh", count: 0, source_updated_at: new Date().toISOString(), cache_expires_at: "2020-01-01T00:00:00Z" } }));
    expect(onContextChange.mock.calls.at(-1)?.[0].sourceHealth.items).toContainEqual(expect.objectContaining({ id: "earthquakes", status: "stale" }));
  });

  it("reports FAA failure and legacy false-zero coverage to the page and Agent", async () => {
    const onContextChange = vi.fn();
    let send!: (value: Record<string, unknown>) => void;
    const dataSource: GlobalIntelDataSource = {
      health: async () => ({}), overview: async () => ({}), staticSnapshot: async () => ({}), crucixSnapshot: async () => ({}),
      subscribe: (payload) => { send = payload; return () => {}; },
    };
    render(<GlobalIntelligenceDashboard dataSource={dataSource} theme="light" refreshNonce={0} onRefresh={() => {}} onContextChange={onContextChange} />);
    act(() => send({ _complete: true, _done: 1, _total: 1, airport_delays: { delayed: [], delayed_count: 0, errors: 20, total_checked: 20 } }));
    await waitFor(() => expect(onContextChange.mock.calls.at(-1)?.[0].sourceHealth.items).toContainEqual(expect.objectContaining({ id: "airport_delays", status: "degraded", reason: expect.stringContaining("不能据此判断无延误") })));
    fireEvent.click(screen.getByRole("button", { name: "详情" }));
    const panel = screen.getByRole("complementary", { name: "数据源健康控制台" });
    expect(panel).toHaveTextContent("旧机场查询没有完整来源回执");
    act(() => send({ airport_delays: { observation_basis: "faa-nas-airport-advisories", status: "unavailable", error: "FAA取数失败", reported_airport_count: null, delayed: [] } }));
    expect(panel).toHaveTextContent("未知 个机场");
    expect(onContextChange.mock.calls.at(-1)?.[0].sourceHealth.items).toContainEqual(expect.objectContaining({ id: "airport_delays", status: "error" }));
    act(() => send({ airport_delays: { observation_basis: "faa-nas-airport-advisories", status: "ok", freshness: "fresh", updated_at: "2020-01-01T00:00:00Z", reported_airport_count: 0, delayed: [] } }));
    expect(onContextChange.mock.calls.at(-1)?.[0].sourceHealth.items).toContainEqual(expect.objectContaining({ id: "airport_delays", status: "stale" }));
    act(() => send({ airport_delays: { observation_basis: "faa-nas-airport-advisories", status: "ok", freshness: "fresh", updated_at: "2099-01-01T00:00:00Z", reported_airport_count: 0, delayed: [] } }));
    expect(onContextChange.mock.calls.at(-1)?.[0].sourceHealth.items).toContainEqual(expect.objectContaining({ id: "airport_delays", status: "degraded" }));
  });
  it.each(["light", "dark"] as const)("shows update-only dates, gaps and sample comparison consistently in %s UI and Agent", async (theme) => {
    const onContextChange = vi.fn();
    let send!: (value: Record<string, unknown>) => void;
    const dataSource: GlobalIntelDataSource = {
      health: async () => ({}), overview: async () => ({}), staticSnapshot: async () => ({}), crucixSnapshot: async () => ({}),
      subscribe: (payload) => { send = payload; return () => {}; },
    };
    const { container } = render(<GlobalIntelligenceDashboard dataSource={dataSource} theme={theme} refreshNonce={0} onRefresh={() => {}} onContextChange={onContextChange} />);
    const timestamp = new Date().toISOString();
    const url = "https://example.com/shipping-update";
    const time = { timestamp, timestamp_basis: "updated", time_status: "valid", updated: timestamp };
    const coverage = { status: "complete", total: 2, dated: 2, published: 0, updated: 2, unknown: 0, future: 0, outside_window: 0 };
    const topic = { id: "update", label: "Shipping update", headline: "Shipping correction", mention_count: 2,
      time_coverage: coverage, current_mentions: 1, previous_mentions: 1, heat_velocity_pct: 0, velocity_state: "flat",
      items: [{ title: "Shipping correction", url, source: "Maritime", ...time }, { title: "Shipping earlier", source: "Maritime", ...time }],
      verification_timeline: [{ title: "Shipping correction", source: "Maritime", status: "出现纠正", flag: "correction", ...time }],
    };
    act(() => send({ _complete: true, _done: 1, _total: 1,
      news_feed: { items: [{ title: "Shipping correction", feed_name: "Maritime", link: url, updated: timestamp }] },
      media_monitor: { status: "ok", timestamp, summary: { analyzed_items: 2, window_hours: 6, ...topic }, topics: [topic],
        annotations: [{ title: "Shipping correction", url, topic_id: "update", ...topic }] },
    }));
    fireEvent.click(within(container.querySelector(".intel-media-card") as HTMLElement).getByRole("button", { name: "查看" }));
    const panel = screen.getByRole("complementary", { name: "全球舆情雷达" });
    expect(panel).toHaveTextContent("有效时间 2/2 · 发布 0 · 更新 2");
    expect(panel).toHaveTextContent("6h 已知样本 1 / 前段 1");
    expect(panel).toHaveTextContent("不代表新发布量或全网热度");
    fireEvent.click(within(panel).getByRole("button", { name: /Shipping update/ }));
    const related = container.querySelector(".intel-media-related-reports")!;
    expect(related).toHaveTextContent("更新 ·");
    expect(related).not.toHaveTextContent("发布 ·");
    expect(container.querySelector(".intel-media-verification-timeline time")).toHaveTextContent("更新 ·");
    await waitFor(() => expect(onContextChange.mock.calls.at(-1)?.[0].mediaMonitor).toMatchObject({
      currentMentions: 1, previousMentions: 1, heatVelocityPct: 0,
      timeCoverage: { dated: 2, published: 0, updated: 2 },
      topTopics: [expect.objectContaining({ items: expect.arrayContaining([expect.objectContaining({ timestampBasis: "updated", published: "" })]) })],
    }));
    act(() => send({ media_monitor: { status: "ok", summary: { analyzed_items: 2, velocity_state: "flat", heat_velocity_pct: 0,
      time_coverage: { status: "unknown", total: 2, dated: 0, published: 0, updated: 0, unknown: 1, future: 1, outside_window: 0 },
    }, topics: [] } }));
    fireEvent.click(within(container.querySelector(".intel-media-card") as HTMLElement).getByRole("button", { name: "查看" }));
    const refreshedPanel = screen.getByRole("complementary", { name: "全球舆情雷达" });
    expect(refreshedPanel).toHaveTextContent("缺日期 1 · 未来日期 1");
    expect(within(refreshedPanel).getByText("样本时段对比").parentElement).toHaveTextContent("待核验");
    expect(onContextChange.mock.calls.at(-1)?.[0].mediaMonitor).toMatchObject({ velocityState: "unknown", heatVelocityPct: null });
  });

  it.each(["light", "dark"] as const)("preserves unassessed lexical coverage on the %s page and in Agent evidence", async (theme) => {
    const onContextChange = vi.fn();
    let send!: (value: Record<string, unknown>) => void;
    const dataSource: GlobalIntelDataSource = {
      health: async () => ({}), overview: async () => ({}), staticSnapshot: async () => ({}), crucixSnapshot: async () => ({}),
      subscribe: (payload) => { send = payload; return () => {}; },
    };
    const { container } = render(<GlobalIntelligenceDashboard dataSource={dataSource} theme={theme} refreshNonce={0} onRefresh={() => {}} onContextChange={onContextChange} />);
    const caveat = "语气为有限词典信号；未命中不等于中性。";
    const frame = { group: "wire", label: "通讯社", count: 4, positive: 0, negative: 1, neutral: 0, mixed: 0, unknown: 3,
      dominant_sentiment: "unknown", dominant_label: "语气未完整判定", sources: ["Wire"] };
    act(() => send({ _complete: true, _done: 1, _total: 1, media_monitor: {
      status: "ok", caveat, timestamp: new Date().toISOString(),
      summary: { analyzed_items: 4, sentiment: { assessed_items: 1, unknown: 3, unknown_pct: 75, negative_pct: 25, net_score: null } },
      topics: [{ id: "sample", label: "Shipping", sentiment: "unknown", sentiment_score: null, attention_score: null,
        sentiment_counts: { positive: 0, negative: 1, neutral: 0, mixed: 0, unknown: 3 } }], media_frames: [frame],
    } }));
    fireEvent.click(within(container.querySelector(".intel-media-card") as HTMLElement).getByRole("button", { name: "查看" }));
    const panel = screen.getByRole("complementary", { name: "全球舆情雷达" });
    expect(panel).toHaveTextContent("语气词典命中 1/4 条");
    expect(panel).toHaveTextContent("未判定 3 条");
    expect(panel).toHaveTextContent("未命中不等于中性");
    expect(panel.querySelector('em[data-sentiment="unknown"]')).toHaveStyle({ width: "75%" });
    await waitFor(() => expect(onContextChange.mock.calls.at(-1)?.[0].mediaMonitor).toMatchObject({ caveat,
      sentiment: { assessedItems: 1, unknown: 3, unknownPct: 75, negativePct: 25, netScore: null },
      topTopics: [expect.objectContaining({ sentiment: "unknown", sentimentScore: null, attentionScore: null, sentimentCounts: expect.objectContaining({ unknown: 3 }) })],
    }));
    act(() => send({ media_monitor: { status: "ok", caveat,
      summary: { analyzed_items: 4, sentiment: { assessed_items: 0, unknown: 4, unknown_pct: 100, negative_pct: null, net_score: null } },
      media_frames: [{ ...frame, negative: 0, unknown: 4 }],
    } }));
    expect(panel).toHaveTextContent("语气词典命中 0/4 条");
    expect(within(panel).getByText("报道语气").parentElement).toHaveTextContent("—");
    expect(panel.querySelector('em[data-sentiment="unknown"]')).toHaveStyle({ width: "100%" });
  });

  it("isolates keyword-matched topic baselines, history, acknowledgement and direct follows", async () => {
    localStorage.setItem("newma-desk.global-intelligence.media-watch-rules.v1", JSON.stringify([
      { id: "topic-a", label: "Shipping A", keywords: ["shipping"], createdAt: "2026-10-27T12:00:00Z" },
    ]));
    const onContextChange = vi.fn();
    let send!: (value: Record<string, unknown>) => void;
    const dataSource: GlobalIntelDataSource = {
      health: async () => ({}), overview: async () => ({}), staticSnapshot: async () => ({}), crucixSnapshot: async () => ({}),
      subscribe: (payload) => { send = payload; return () => {}; },
    };
    const { container, unmount } = render(<GlobalIntelligenceDashboard dataSource={dataSource} theme="light" refreshNonce={0} onRefresh={() => {}} onContextChange={onContextChange} />);
    const emit = (a: number, b: number) => {
      const topics = [["a", a], ["b", b]].map(([id, count]) => ({
        id: `topic-${id}`, label: `Shipping ${String(id).toUpperCase()}`, headline: `Shipping report ${id}`, keywords: ["shipping"],
        mention_count: count, source_count: 2, heat_score: 20, attention_score: 25, spread_score: 30,
        velocity_state: "new", time_coverage: { status: "complete", total: count, dated: count, published: count, updated: 0, unknown: 0, future: 0, outside_window: 0 },
        verification_status: "常规报道", framing_divergence: false,
        items: [{ title: `Shipping report ${id}`, url: `https://example.com/${id}` }],
      }));
      act(() => send({ _complete: true, _done: 1, _total: 1,
        news_feed: { items: topics.map((topic) => ({ title: topic.headline, link: topic.items[0]!.url, feed_name: "Test wire", published: new Date().toISOString() })) },
        media_monitor: { status: "partial", timestamp: new Date().toISOString(), summary: { analyzed_items: a + b }, topics,
          annotations: topics.map((topic) => ({ topic_id: topic.id, title: topic.headline, url: topic.items[0]!.url })),
        },
      }));
    };
    emit(2, 10);
    await waitFor(() => expect(onContextChange.mock.calls.at(-1)?.[0].mediaMonitor).toMatchObject({ watchedTopicCount: 2, watchedTopicChangeCount: 0, watchedTopicIncompleteCount: 0 }));
    const history = JSON.parse(localStorage.getItem("newma-desk.global-intelligence.media-topic-history.v2")!);
    expect(history.map((topic: { id: string }) => topic.id).sort()).toEqual(["topic-a", "topic-b"]);
    fireEvent.click(within(container.querySelector(".intel-media-card") as HTMLElement).getByRole("button", { name: "查看" }));
    const panel = screen.getByRole("complementary", { name: "全球舆情雷达" });
    const bRow = within(panel).getByRole("button", { name: /Shipping B/ }).parentElement!;
    expect(bRow).toHaveTextContent("关键词命中");
    fireEvent.click(within(bRow).getByRole("button", { name: "关注" }));
    fireEvent.click(within(bRow).getByRole("button", { name: "已关注" }));
    expect(JSON.parse(localStorage.getItem("newma-desk.global-intelligence.media-watch-rules.v1")!).map((rule: { id: string }) => rule.id)).toEqual(["topic-a"]);
    emit(3, 11);
    await waitFor(() => expect(onContextChange.mock.calls.at(-1)?.[0].mediaMonitor.watchedTopicChangeCount).toBe(2));
    fireEvent.click(within(panel).getByRole("button", { name: /Shipping B/ }));
    fireEvent.click(await screen.findByRole("button", { name: "标记本次变化已查看" }));
    await waitFor(() => expect(onContextChange.mock.calls.at(-1)?.[0].mediaMonitor.watchedTopicChangeCount).toBe(1));
    const rule = JSON.parse(localStorage.getItem("newma-desk.global-intelligence.media-watch-rules.v1")!)[0];
    expect(rule.topicBaselines["topic-a"].split("|")[1]).toBe("2");
    expect(rule.topicBaselines["topic-b"].split("|")[1]).toBe("11");
    unmount();
    onContextChange.mockClear();
    render(<GlobalIntelligenceDashboard dataSource={dataSource} theme="light" refreshNonce={0} onRefresh={() => {}} onContextChange={onContextChange} />);
    emit(3, 11);
    await waitFor(() => expect(onContextChange.mock.calls.at(-1)?.[0].mediaMonitor).toMatchObject({ watchedTopicCount: 2, watchedTopicChangeCount: 1 }));
  });

  it("keeps missing topic judgments unknown through the panel, news detail and Agent", async () => {
    const onContextChange = vi.fn();
    const title = "Shipping observation without classified inputs";
    const url = "https://example.com/unclassified";
    const dataSource: GlobalIntelDataSource = {
      health: async () => ({}), overview: async () => ({}), staticSnapshot: async () => ({}), crucixSnapshot: async () => ({}),
      subscribe: (payload) => {
        payload({ _complete: true, _done: 1, _total: 1,
          news_feed: { items: [{ title, link: url, feed_name: "Test wire", published: new Date().toISOString() }] },
          media_monitor: { status: "partial", summary: { analyzed_items: 1 },
            topics: [{ id: "missing", label: "Unclassified topic", headline: title, items: [{ title, url }] }],
            annotations: [{ title, url, topic_id: "missing" }], media_frames: [{ label: "Missing frame" }],
          },
        });
        return () => {};
      },
    };
    const { container } = render(<GlobalIntelligenceDashboard dataSource={dataSource} theme="light" refreshNonce={0} onRefresh={() => {}} onContextChange={onContextChange} />);
    await waitFor(() => expect(onContextChange.mock.calls.at(-1)?.[0].mediaMonitor?.topTopics).toHaveLength(1));
    fireEvent.click(within(container.querySelector(".intel-media-card") as HTMLElement).getByRole("button", { name: "查看" }));
    const panel = screen.getByRole("complementary", { name: "全球舆情雷达" });
    expect(panel).toHaveTextContent("语种待核验");
    expect(panel).toHaveTextContent("语气分布数据不完整");
    expect(panel).not.toHaveTextContent("有限传播");
    expect(panel.querySelector('[data-sentiment="neutral"]')).toBeNull();
    expect(panel.querySelector(".intel-media-frame-list b")).not.toHaveTextContent("中性");
    expect(panel.querySelector(".intel-media-frame-list em")).toBeNull();
    expect(onContextChange.mock.calls.at(-1)?.[0].mediaMonitor.topTopics[0]).toMatchObject({
      spreadScore: null, attentionScore: null, sentiment: "unknown", verificationStatus: "待核验",
    });
    fireEvent.click(within(panel).getByRole("button", { name: /Unclassified topic/ }));
    const dossier = container.querySelector(".intel-media-dossier") as HTMLElement;
    await waitFor(() => expect(dossier).toBeVisible());
    expect(dossier).not.toHaveTextContent("单语主题");
    expect(dossier).not.toHaveTextContent("null/100");
    expect(dossier).not.toHaveTextContent("常规报道");
    expect(within(dossier).getByText("传播范围").nextElementSibling).toHaveTextContent("—");
    expect(onContextChange.mock.calls.at(-1)?.[0].selectedEvent.facts).toEqual(expect.arrayContaining([
      { label: "报道语气", value: "待核验" }, { label: "传播范围", value: "待核验" },
    ]));
  });

  it("does not treat missing fields or legacy defaults as watched-topic changes", async () => {
    const legacyHistory = '[{"id":"old","verificationStatus":"常规报道"}]';
    localStorage.setItem("newma-desk.global-intelligence.media-topic-history.v1", legacyHistory);
    localStorage.setItem("newma-desk.global-intelligence.media-watch-rules.v1", JSON.stringify([
      { id: "watched", label: "Shipping", keywords: ["shipping"], baselineSignature: "0|0|0|0|0|常规报道|false" },
      { id: "other", label: "Unrelated", keywords: [] },
    ]));
    const onContextChange = vi.fn();
    let send!: (value: Record<string, unknown>) => void;
    const dataSource: GlobalIntelDataSource = {
      health: async () => ({}), overview: async () => ({}), staticSnapshot: async () => ({}), crucixSnapshot: async () => ({}),
      subscribe: (payload) => { send = payload; return () => {}; },
    };
    const { container } = render(<GlobalIntelligenceDashboard dataSource={dataSource} theme="dark" refreshNonce={0} onRefresh={() => {}} onContextChange={onContextChange} />);
    const topic = { id: "watched", label: "Shipping", headline: "Shipping", mention_count: 2, source_count: 2,
      velocity_state: "new", time_coverage: { status: "complete", total: 2, dated: 2, published: 2, updated: 0, unknown: 0, future: 0, outside_window: 0 },
      heat_score: 20, attention_score: 25, spread_score: 30, verification_status: "常规报道", framing_divergence: false };
    const emit = (value: Record<string, unknown>, timestamp: string, stale = false) => act(() => send({ _complete: true, _done: 1, _total: 1, _stale: stale,
      media_monitor: { status: "partial", timestamp, summary: { analyzed_items: 2 }, topics: [value] },
    }));
    emit(topic, "2026-10-27T12:00:00Z");
    await waitFor(() => expect(onContextChange.mock.calls.at(-1)?.[0].mediaMonitor).toMatchObject({ watchedTopicCount: 1, watchedTopicChangeCount: 0, watchedTopicIncompleteCount: 0 }));
    emit({ ...topic, mention_count: 9 }, "2026-10-27T11:00:00Z", true);
    await waitFor(() => expect(onContextChange.mock.calls.at(-1)?.[0].mediaMonitor).toMatchObject({ status: "stale", watchedTopicChangeCount: 0, watchedTopicIncompleteCount: 1 }));
    expect(JSON.parse(localStorage.getItem("newma-desk.global-intelligence.media-topic-history.v2")!)[0]).toMatchObject({ mentionCount: 2, lastSeenAt: "2026-10-27T12:00:00.000Z" });
    emit({ id: "watched", label: "Shipping" }, "2026-10-27T12:01:00Z");
    await waitFor(() => expect(onContextChange.mock.calls.at(-1)?.[0].mediaMonitor).toMatchObject({ watchedTopicChangeCount: 0, watchedTopicIncompleteCount: 1 }));
    fireEvent.click(within(container.querySelector(".intel-media-card") as HTMLElement).getByRole("button", { name: "查看" }));
    expect(screen.getByRole("complementary", { name: "全球舆情雷达" })).toHaveTextContent("1 个主题对比不完整");
    const history = JSON.parse(localStorage.getItem("newma-desk.global-intelligence.media-topic-history.v2")!);
    expect(history[0]).toMatchObject({ mentionCount: 2, lastChangedAt: "2026-10-27T12:00:00.000Z" });
    expect(history[0].verificationHistory).toHaveLength(1);
    emit({ ...topic, mention_count: 3 }, "2026-10-27T12:02:00Z");
    await waitFor(() => expect(onContextChange.mock.calls.at(-1)?.[0].mediaMonitor).toMatchObject({ watchedTopicChangeCount: 1, watchedTopicIncompleteCount: 0 }));
    expect(JSON.parse(localStorage.getItem("newma-desk.global-intelligence.media-topic-history.v2")!)[0].lastChangedAt).toBe("2026-10-27T12:02:00.000Z");
    expect(localStorage.getItem("newma-desk.global-intelligence.media-topic-history.v1")).toBe(legacyHistory);
  });

  it("keeps media coverage visible and clears invented zeros when an open panel loses its input", async () => {
    const onContextChange = vi.fn();
    let send!: (value: Record<string, unknown>) => void;
    const dataSource: GlobalIntelDataSource = {
      health: async () => ({}), overview: async () => ({}), staticSnapshot: async () => ({}), crucixSnapshot: async () => ({}),
      subscribe: (payload) => { send = payload; return () => {}; },
    };
    const { container } = render(<GlobalIntelligenceDashboard dataSource={dataSource} theme="light" refreshNonce={0} onRefresh={() => {}} onContextChange={onContextChange} />);
    act(() => send({ _complete: true, _done: 1, _total: 1, media_monitor: {
      status: "partial", sample_basis: "available_rss_sample", coverage: { expected: 3, available: 2, complete: 1, stale: 1, failed: 1 },
      summary: { analyzed_items: 4, topic_count: 1, spread_score: 35, sentiment: { negative_pct: 25, positive_pct: 0 } }, topics: [],
    } }));
    await waitFor(() => expect(container.querySelector(".intel-media-card")).toHaveTextContent("4 条报道"));
    fireEvent.click(within(container.querySelector(".intel-media-card") as HTMLElement).getByRole("button", { name: "查看" }));
    const panel = screen.getByRole("complementary", { name: "全球舆情雷达" });
    expect(panel).toHaveTextContent("完整来源 1/3");
    await waitFor(() => expect(onContextChange.mock.calls.at(-1)?.[0].mediaMonitor).toMatchObject({
      status: "partial", coverage: { complete: 1, expected: 3, stale: 1, failed: 1 },
    }));
    const context = buildGlobalIntelligenceContext(onContextChange.mock.calls.at(-1)?.[0]);
    expect(context.visibleBlocks.some((block) => block.id === "global-intelligence-media")).toBe(true);
    act(() => send({ media_monitor: { status: "unavailable", error: "failed", summary: {} } }));
    await waitFor(() => expect(panel).toHaveTextContent("舆情输入不可用"));
    expect(panel).not.toHaveTextContent("负面 0%");
    expect(within(panel).getByText("传播范围").parentElement).toHaveTextContent("—");
    expect(within(panel).getByText("主题聚类").parentElement).toHaveTextContent("—");
    expect(onContextChange.mock.calls.at(-1)?.[0].mediaMonitor).toMatchObject({ status: "unavailable", analyzedItems: null, spreadScore: null, watchedTopicCount: null, watchedTopicChangeCount: null });
    act(() => send({ media_monitor: {
      status: "ok", coverage: { expected: 3, available: 3, complete: 3, stale: 0, failed: 0 },
      summary: { analyzed_items: 0, topic_count: 0 }, topics: [],
    } }));
    await waitFor(() => expect(panel).toHaveTextContent("舆情样本已分析"));
    expect(panel).toHaveTextContent("完整来源 3/3");
    expect(within(panel).getByText("主题聚类").parentElement).toHaveTextContent("0");
    expect(within(panel).getByText("报道语气").parentElement).toHaveTextContent("—");
    expect(onContextChange.mock.calls.at(-1)?.[0].mediaMonitor).toMatchObject({ status: "ok", analyzedItems: 0, spreadScore: null, watchedTopicCount: 0 });
    fireEvent.click(within(panel).getByRole("button", { name: "关闭全球舆情雷达" }));
    expect(screen.queryByRole("complementary", { name: "全球舆情雷达" })).toBeNull();
    await waitFor(() => expect(buildGlobalIntelligenceContext(onContextChange.mock.calls.at(-1)?.[0]).visibleBlocks.some((block) => block.id === "global-intelligence-media")).toBe(false));
  });

  it.each(["metadata", "social-only", "stale"])("keeps %s media evidence qualified on the page and in Agent context", async (kind) => {
    const onContextChange = vi.fn();
    const timestamp = "2026-10-26T12:00:00Z";
    const media = kind === "metadata" ? { timestamp, method: "lexicon" } : {
      status: "partial", timestamp, sample_basis: "social_sample_news_unavailable",
      summary: { analyzed_items: 2, news_items: 0, social_items: 2, topic_count: 1, sentiment: { negative_pct: 50 } },
      coverage: { expected: 3, available: 0, complete: 0, failed: 3, stale: 0 }, topics: [],
    };
    const dataSource: GlobalIntelDataSource = {
      health: async () => ({}), overview: async () => ({}), staticSnapshot: async () => ({}), crucixSnapshot: async () => ({}),
      subscribe: (payload) => {
        payload({ _complete: true, _done: 1, _total: 1, _stale: kind === "stale", media_monitor: media });
        return () => {};
      },
    };
    const { container } = render(<GlobalIntelligenceDashboard dataSource={dataSource} theme="dark" refreshNonce={0} onRefresh={() => {}} onContextChange={onContextChange} />);
    await waitFor(() => expect(onContextChange.mock.calls.at(-1)?.[0].dataAvailability.media).toBe(kind !== "metadata"));
    fireEvent.click(within(container.querySelector(".intel-media-card") as HTMLElement).getByRole("button", { name: "查看" }));
    const panel = screen.getByRole("complementary", { name: "全球舆情雷达" });
    expect(panel).toHaveTextContent(kind === "metadata" ? "舆情覆盖待核验" : kind === "stale" ? "历史舆情快照" : "舆情证据不完整");
    expect(panel).toHaveTextContent("生成分析，非新闻发布时间");
    const evidence = onContextChange.mock.calls.at(-1)?.[0].mediaMonitor;
    expect(evidence.timestamp).toBe("2026-10-26T12:00:00.000Z");
    expect(evidence.timestampBasis).toBe("analysis-generated");
    if (kind === "metadata") {
      expect(evidence.analyzedItems).toBeNull();
      expect(panel).toHaveTextContent("尚无可评估样本，不代表没有热点。");
    } else {
      expect(panel).toHaveTextContent("仅社交样本，新闻输入不可用");
      expect(panel).toHaveTextContent("完整来源 0/3");
      expect(evidence).toMatchObject({ newsItems: 0, socialItems: 2, status: kind === "stale" ? "stale" : "partial" });
    }
  });

  it("keeps partial observations and reports the stream failure to the page and Agent", async () => {
    const onContextChange = vi.fn();
    const message = "情报引擎连接中断；已收到的数据保留，可手动刷新";
    const dataSource: GlobalIntelDataSource = {
      health: async () => ({}), overview: async () => ({}), staticSnapshot: async () => ({}), crucixSnapshot: async () => ({}),
      subscribe: (payload, status, failure) => {
        payload({ _complete: false, _done: 1, _total: 48,
          earthquakes: { earthquakes: [{ id: "one", place: "Observed location", magnitude: 5.1, latitude: 30, longitude: 100 }] } });
        failure?.({ code: "world_stream_disconnected", message });
        status("degraded");
        return () => {};
      },
    };
    render(<GlobalIntelligenceDashboard dataSource={dataSource} theme="dark" refreshNonce={0} onRefresh={() => {}} onContextChange={onContextChange} />);
    await waitFor(() => expect(onContextChange.mock.calls.at(-1)?.[0]).toMatchObject({
      streamStatus: "degraded", progress: { done: 1, total: 48 },
      refresh: { status: "partial" }, dataAvailability: { error: message },
    }));
    expect(onContextChange.mock.calls.at(-1)?.[0].pointCount).toBe(1);
    expect(screen.getByText(message)).toBeVisible();
  });

  it("keeps partial risk coverage visible in the page and Agent without inventing a total", async () => {
    const onContextChange = vi.fn();
    const dataSource: GlobalIntelDataSource = {
      health: async () => ({}), overview: async () => ({}), staticSnapshot: async () => ({}), crucixSnapshot: async () => ({}),
      subscribe: (payload) => {
        payload({ _complete: true, _done: 1, _total: 1,
          strategic_posture: { status: "partial", composite_score: null, risk_level: "UNKNOWN",
            coverage: { available: 1, complete: 0, expected: 9 },
            domain_scores: { cyber: { score: 66, status: "partial", level: "HIGH", signals: ["33 threat records"] },
              political: { score: null, status: "unavailable", level: "UNKNOWN" } } },
          alert_digest: { status: "partial", alert_count: 0, alerts: [], coverage: { available: 1, complete: 1, expected: 7 } },
        });
        return () => {};
      },
    };
    render(<GlobalIntelligenceDashboard dataSource={dataSource} theme="dark" refreshNonce={0} onRefresh={() => {}} onContextChange={onContextChange} />);
    await waitFor(() => expect(onContextChange.mock.calls.at(-1)?.[0].strategicBriefing).toMatchObject({
      score: null, alertCount: 0, postureCoverage: { available: 1, expected: 9 }, alertCoverage: { available: 1, expected: 7 },
    }));
    expect(onContextChange.mock.calls.at(-1)?.[0].sourceHealth.items).toEqual(expect.arrayContaining([
      expect.objectContaining({ id: "strategic_posture:coverage", status: "degraded" }),
      expect.objectContaining({ id: "alert_digest:coverage", status: "degraded" }),
    ]));
    fireEvent.click(screen.getByRole("button", { name: "研判" }));
    expect(await screen.findByText(/评分覆盖 1\/9 域/)).toBeVisible();
    expect(screen.getByText(/告警检查覆盖 1\/7 项/)).toBeVisible();
    expect(screen.getByText("部分证据 · 样本评分")).toBeVisible();
    expect(screen.getByText("本次返回的告警样本为空。")).toBeVisible();
  });

  it.each([false, true])("keeps unavailable and valid-empty briefing alerts distinct (empty=%s)", async (empty) => {
    const onContextChange = vi.fn();
    const dataSource: GlobalIntelDataSource = {
      health: async () => ({}), overview: async () => ({}), staticSnapshot: async () => ({}), crucixSnapshot: async () => ({}),
      subscribe: (payload) => {
        payload({ _complete: true, _done: 1, _total: 1,
          strategic_posture: { error: "timeout", composite_score: 0, risk_level: "LOW" },
          alert_digest: empty ? { alert_count: 0, alerts: [] } : { error: "timeout", alert_count: 0, alerts: [] },
          situation_brief: { brief: "有效来源不足，不判断低风险", status: "partial", coverage: { available: 6, expected: 12 } },
        });
        return () => {};
      },
    };
    render(<GlobalIntelligenceDashboard dataSource={dataSource} theme="dark" refreshNonce={0} onRefresh={() => {}} onContextChange={onContextChange} />);
    await waitFor(() => expect(onContextChange.mock.calls.at(-1)?.[0].strategicBriefing).toMatchObject({
      score: null, level: "风险待核验", alertCount: empty ? 0 : null,
    }));
    expect(onContextChange.mock.calls.at(-1)?.[0].sourceHealth.items).toEqual(expect.arrayContaining([
      expect.objectContaining({ id: "situation_brief:coverage", status: "degraded", reason: expect.stringContaining("6/12") }),
    ]));
    fireEvent.click(screen.getByRole("button", { name: "研判" }));
    expect(await screen.findByText(empty ? "本次返回的告警样本为空。" : "告警数据未取得，不能判断当前是否存在战略告警。")).toBeVisible();
    expect(screen.getByText("风险域数据未就绪")).toBeVisible();
  });

  it("reports historical central bank references as unverified to the page and Agent", async () => {
    const onContextChange = vi.fn();
    const dataSource: GlobalIntelDataSource = {
      health: async () => ({}), overview: async () => ({}), staticSnapshot: async () => ({}), crucixSnapshot: async () => ({}),
      subscribe: (payload) => {
        payload({ _complete: true, _done: 1, _total: 1, central_bank_rates: { rates: [
          { bank: "Reference Bank", rate: 4.5, source: "curated", as_of: "2025-01-29" },
          { bank: "Undated Bank", rate: 0, source: "fred" },
        ] } });
        return () => {};
      },
    };
    render(<GlobalIntelligenceDashboard dataSource={dataSource} theme="dark" refreshNonce={0} onRefresh={() => {}} onContextChange={onContextChange} />);
    await waitFor(() => expect(onContextChange.mock.calls.at(-1)?.[0].refresh.status).toBe("partial"));
    expect(onContextChange.mock.calls.at(-1)?.[0].sourceHealth.items).toEqual(expect.arrayContaining([
      expect.objectContaining({ id: "central_bank_rates:reference", status: "degraded", reason: expect.stringContaining("1 条历史手工参考") }),
    ]));
    fireEvent.click(screen.getByRole("button", { name: "详情" }));
    expect(await screen.findByText("央行利率口径")).toBeVisible();
  });

  it("reports partial public-rate coverage alongside separate historical references", async () => {
    const onContextChange = vi.fn();
    const dataSource: GlobalIntelDataSource = {
      health: async () => ({}), overview: async () => ({}), staticSnapshot: async () => ({}), crucixSnapshot: async () => ({}),
      subscribe: (payload) => {
        payload({ _complete: true, _done: 1, _total: 1, central_bank_rates: {
          status: "partial", coverage: { tracked: 15, queried: 3, available: 2, stale: 0, failed: 1, reference_only: 12 },
          rates: [{ bank: "Missing", rate: null, reference: { rate: 4.5, as_of: "2025-01-29" } }],
        } });
        return () => {};
      },
    };
    render(<GlobalIntelligenceDashboard dataSource={dataSource} theme="dark" refreshNonce={0} onRefresh={() => {}} onContextChange={onContextChange} />);
    await waitFor(() => expect(onContextChange.mock.calls.at(-1)?.[0].sourceHealth.items).toEqual(expect.arrayContaining([
      expect.objectContaining({ id: "central_bank_rates:coverage", status: "degraded", reason: "2/15 家取得近期观测；3 家已查询，1 失败，0 过期，12 家仅历史参考" }),
      expect.objectContaining({ id: "central_bank_rates:reference", status: "degraded", reason: expect.stringContaining("1 条历史手工参考") }),
    ])));
    fireEvent.click(screen.getByRole("button", { name: "详情" }));
    expect(await screen.findByText("央行实时来源覆盖")).toBeVisible();
    expect(screen.getByText("2/15 家取得近期观测；3 家已查询，1 失败，0 过期，12 家仅历史参考")).toBeVisible();
  });

  it.each(["light", "dark"] as const)("shows SDN metadata in source details and Agent without creating alerts in %s", async (theme) => {
    const onContextChange = vi.fn();
    let send!: (value: Record<string, unknown>) => void;
    const ofac = { status: "ok", reason: "完整读取名单", publishedDate: "2026-11-04",
      entryCount: 19499, recordCount: 19499, complete: true, countBasis: "sdn-entries",
      collectedAt: "2026-11-05T00:00:00Z", checkedAt: "2026-11-05T00:00:00Z", collectionFreshness: { status: "fresh" },
      sourceUrl: "https://sanctionslistservice.ofac.treas.gov/api/PublicationPreview/exports/SDN.XML",
      note: "仅美国 OFAC SDN 名单观察，未覆盖非 SDN 名单；数量不是新增制裁，非合规筛查或风险评级。" };
    const normalized = (value: typeof ofac) => ({
      freshness: { status: "fresh" }, global: { ofac: value },
      sourceHealth: { queried: 1, ok: 1, items: [{ source: "OFAC", status: "ok", reason: "完整读取名单" }] },
    });
    const dataSource: GlobalIntelDataSource = { health: async () => ({}), overview: async () => ({}),
      staticSnapshot: async () => ({}), crucixSnapshot: async () => normalized(ofac),
      subscribe: (payload) => { send = payload; return () => {}; } };
    render(<GlobalIntelligenceDashboard dataSource={dataSource} theme={theme} refreshNonce={0} onRefresh={() => {}} onContextChange={onContextChange} />);
    const push = (value: typeof ofac) => act(() => send({ _done: 1, _total: 1, crucix_intelligence: normalized(value) }));
    await waitFor(() => expect(onContextChange.mock.calls.at(-1)?.[0].sourceHealth.items).toContainEqual(
      expect.objectContaining({ id: "crucix:OFAC", status: "healthy", observation: ofac })));
    const state = onContextChange.mock.calls.at(-1)![0];
    expect(state.filters.showObservations).toBe(false);
    expect(state.actionableEventCount).toBe(0);
    expect(state.countryRisk.countries).toEqual({});
    expect(state.events).toEqual([]);
    fireEvent.click(screen.getByRole("button", { name: "详情" }));
    expect(await screen.findByText(/名单发布日 2026-11-04（仅日期）.*实际解析 19499 条.*声明 19499 条/)).toBeVisible();
    expect(screen.getByText(/数量不是新增制裁，非合规筛查/)).toBeVisible();
    expect(buildGlobalIntelligenceContext(state).data?.summary).toMatchObject({ sourceHealth: { items: [expect.objectContaining({ observation: ofac })] } });
    push({ ...ofac, status: "error", reason: "名单请求失败", publishedDate: null,
      entryCount: null, recordCount: null, complete: false, collectedAt: null,
      collectionFreshness: { status: "unknown" } } as unknown as typeof ofac);
    await waitFor(() => expect(onContextChange.mock.calls.at(-1)?.[0].sourceHealth.items).toContainEqual(
      expect.objectContaining({ id: "crucix:OFAC", status: "error", observation: expect.objectContaining({ entryCount: null }) })));
    expect(screen.queryByText(/实际解析 19499 条/)).toBeNull();
    expect(screen.getByText(/实际解析 未知 条/)).toBeVisible();
    expect(screen.getByText(/检查于 2026-11-05T00:00:00Z · 未取得已核验名单/)).toBeVisible();
    push({ ...ofac, entryCount: 0, recordCount: 0 });
    await waitFor(() => expect(screen.getByText(/实际解析 0 条.*声明 0 条/)).toBeVisible());
    push({ ...ofac, collectionFreshness: { status: "stale" } });
    await waitFor(() => expect(onContextChange.mock.calls.at(-1)?.[0].sourceHealth.items).toContainEqual(
      expect.objectContaining({ id: "crucix:OFAC", status: "stale" })));
  });

  it.each(["light", "dark"] as const)("keeps metal and supply evidence visible to page and Agent in %s", async (theme) => {
    const context = vi.fn();
    let send!: (value: Record<string, unknown>) => void;
    const gold = { id: "gold", label: "黄金", value: 0, kind: "futures", unit: "USD/troy-ounce",
      frequency: "quote", observedAt: "2026-11-13T20:00:00Z", freshness: { status: "fresh" }, basisVerified: true,
      source: { id: "YFinance", seriesId: "GC=F", url: "https://finance.yahoo.com/quote/GC%3DF/" },
      previousCloseDate: null, prevClose: 2700, previousCloseBasis: "daily-bars", note: "连续期货可能换月，不是现货；前收日期未知。" };
    const gscpi = { value: 0, period: "2026-10", date: "2026-10", unit: "standard-deviations", frequency: "monthly",
      vintage: "46327", vintageBasis: "source-column-id", rejected: 2, missing: 1, status: "partial", basisVerified: true,
      collectedAt: "2026-11-14T10:00:00Z", freshness: { status: "fresh" },
      note: "修订列标识不是发布日期；零代表历史均值。" };
    const normalized = (metal = gold, supply = gscpi) => ({ asOf: "2026-11-14T10:00:00Z", freshness: { status: "fresh" },
      macro: { metals: { observations: [metal] }, gscpi: supply },
      sourceHealth: { queried: 2, ok: 1, partial: 1, items: [{ source: "YFinance", status: "ok" }, { source: "GSCPI", status: "partial" }] } });
    const source: GlobalIntelDataSource = { health: async () => ({}), overview: async () => ({}), staticSnapshot: async () => ({}),
      crucixSnapshot: async () => normalized(), subscribe: (payload) => { send = payload; return () => {}; } };
    render(<GlobalIntelligenceDashboard dataSource={source} theme={theme} refreshNonce={0} onRefresh={() => {}} onContextChange={context} />);
    await waitFor(() => expect(context.mock.calls.at(-1)?.[0].sourceHealth.items).toContainEqual(
      expect.objectContaining({ id: "crucix:metal:gold", status: "healthy", observation: gold })));
    const state = context.mock.calls.at(-1)![0];
    expect(state.filters.showObservations).toBe(false);
    expect(state.events).toEqual([]);
    expect(state.actionableEventCount).toBe(0);
    const summary = buildGlobalIntelligenceContext(state).data?.summary;
    expect(summary).toMatchObject({ sourceHealth: { items: expect.arrayContaining([
      expect.objectContaining({ observation: gold }), expect.objectContaining({ observation: gscpi }),
    ]) } });
    fireEvent.click(screen.getByRole("button", { name: "详情" }));
    const panel = screen.getByRole("complementary", { name: "数据源健康控制台" });
    expect(panel).toHaveTextContent("0 USD/金衡盎司");
    expect(panel).toHaveTextContent("GC=F");
    expect(panel).toHaveTextContent("2026-11-13T20:00:00Z");
    expect(panel).toHaveTextContent("2026-10");
    expect(panel).toHaveTextContent("46327");
    expect(panel).toHaveTextContent("拒绝 2");
    expect(panel).toHaveTextContent("缺格 1");
    act(() => send({ _complete: true, crucix_intelligence: normalized(
      { ...gold, value: null, freshness: { status: "unknown" }, basisVerified: false } as unknown as typeof gold,
      { ...gscpi, value: null, status: "error", freshness: { status: "unknown" }, basisVerified: false } as unknown as typeof gscpi,
    ) }));
    await waitFor(() => expect(context.mock.calls.at(-1)?.[0].sourceHealth.items).toContainEqual(
      expect.objectContaining({ id: "crucix:GSCPI", status: "error", observation: expect.objectContaining({ value: null }) })));
    expect(panel).toHaveTextContent("价格 未知");
    expect(panel).toHaveTextContent("指数 未知");
    expect(panel).not.toHaveTextContent("0 USD/金衡盎司");
  });

  it("shows individual Crucix source failures to the user and Agent without double-counting the roll-up", async () => {
    const onContextChange = vi.fn();
    const dataSource: GlobalIntelDataSource = {
      health: async () => ({}), overview: async () => ({}), staticSnapshot: async () => ({}),
      crucixSnapshot: async () => ({
        freshness: { status: "fresh", ageSeconds: 2 },
        sourceHealth: { queried: 4, ok: 1, failed: 1, partial: 2, items: [
          { source: "OpenSanctions", status: "error", reason: "未配置 OpenSanctions 授权凭据；制裁风险未知" },
          { source: "OFAC", status: "partial", reason: "OFAC SDN 解析数量与声明数量不一致；非合规筛查" },
          { source: "Treasury", status: "partial", reason: "债务可用，平均付息率缺失" },
          { source: "NOAA", status: "ok", reason: "告警查询完成，含有效空结果" },
        ] },
      }),
      subscribe: (payload) => { payload({ _done: 1, _total: 1 }); return () => {}; },
    };
    render(<GlobalIntelligenceDashboard dataSource={dataSource} theme="dark" refreshNonce={0} onRefresh={() => {}} onContextChange={onContextChange} />);
    await waitFor(() => expect(onContextChange.mock.calls.at(-1)?.[0].sourceHealth.items).toEqual(expect.arrayContaining([
      expect.objectContaining({ id: "crucix:OpenSanctions", status: "error", reason: expect.stringContaining("制裁风险未知") }),
      expect.objectContaining({ id: "crucix:OFAC", status: "degraded", reason: expect.stringContaining("数量不一致") }),
      expect.objectContaining({ id: "crucix:Treasury", status: "degraded", statusLabel: "部分可用" }),
      expect.objectContaining({ id: "crucix:NOAA", status: "healthy" }),
    ])));
    expect(onContextChange.mock.calls.at(-1)?.[0].sourceHealth.items.some((row: { id: string }) => row.id === "crucix")).toBe(false);
    fireEvent.click(screen.getByRole("button", { name: "详情" }));
    expect(await screen.findByText("Crucix / OpenSanctions")).toBeTruthy();
    expect(screen.getByText("未配置 OpenSanctions 授权凭据；制裁风险未知")).toBeTruthy();
    expect(screen.getByText("OFAC SDN 解析数量与声明数量不一致；非合规筛查")).toBeTruthy();
  });

  it("overrides closed World RSS circuits with actual parsing receipts for the user and Agent", async () => {
    const onContextChange = vi.fn();
    const dataSource: GlobalIntelDataSource = {
      health: async () => ({}), overview: async () => ({}), staticSnapshot: async () => ({}), crucixSnapshot: async () => ({}),
      subscribe: (payload) => {
        payload({ _done: 1, _total: 1, source_health: { "rss:bad": { status: "closed" } },
          cache_freshness: { news: { last_updated_s_ago: 0, is_stale: false } },
          news_feed: { status: "partial", items: [], count: 0, coverage: { expected: 3, available: 2, complete: 1 }, source_results: [
            { id: "rss:empty", source: "Empty", status: "ok", count: 0, freshness: "fresh", reason: "订阅有效" },
            { id: "rss:bad", source: "Bad", status: "unavailable", count: null, freshness: "fresh", reason: "响应不是有效 RSS/Atom 订阅" },
            { id: "rss:old", source: "Old", status: "stale", count: 4, freshness: "stale", reason: "保留过期订阅", collected_at: "2026-10-26T01:00:00Z" },
          ] } });
        return () => {};
      },
    };
    render(<GlobalIntelligenceDashboard dataSource={dataSource} theme="dark" refreshNonce={0} onRefresh={() => {}} onContextChange={onContextChange} />);
    await waitFor(() => expect(onContextChange.mock.calls.at(-1)?.[0].refresh.status).toBe("partial"));
    const rows = onContextChange.mock.calls.at(-1)?.[0].sourceHealth.items;
    expect(rows).toEqual(expect.arrayContaining([
      expect.objectContaining({ id: "rss:empty", status: "healthy", statusLabel: "有效空源" }),
      expect.objectContaining({ id: "rss:bad", status: "error", reason: expect.stringContaining("数量未知") }),
      expect.objectContaining({ id: "rss:old", status: "stale", reason: expect.stringContaining("2026-10-26T01:00:00Z") }),
    ]));
    expect(rows.filter((row: { id: string }) => row.id === "rss:bad")).toHaveLength(1);
    expect(rows.some((row: { id: string }) => row.id === "news")).toBe(false);
    fireEvent.click(screen.getByRole("button", { name: "详情" }));
    expect(await screen.findByText("World RSS / Bad")).toBeVisible();
  });

  it("keeps cached RSS available when every live source fails and reports it to the Agent", async () => {
    const onContextChange = vi.fn();
    const dataSource: GlobalIntelDataSource = {
      health: async () => ({}), overview: async () => ({}), staticSnapshot: async () => ({}),
      crucixSnapshot: async () => ({
        sourceHealth: { queried: 1, ok: 0, failed: 1 },
        news: [{ title: "Retained report", type: "rss", cached: true, collectedAt: "2026-10-26T00:00:00Z" }],
        newsCoverage: { mode: "cache", status: "partial", cachedSources: 1,
          cache: { status: "error", reason: "缓存读取异常" },
          coverage: { requested: 1, succeeded: 0, failed: 1 }, items: [
            { source: "Retained", status: "error", count: null, cached: true, availableCount: 1,
              dataAsOf: "2026-10-26T00:00:00Z", reason: "HTTP 503", freshness: { status: "fresh" } },
          ] },
      }),
      subscribe: (payload) => { payload({ _done: 1, _total: 1 }); return () => {}; },
    };
    render(<GlobalIntelligenceDashboard dataSource={dataSource} theme="dark" refreshNonce={0} onRefresh={() => {}} onContextChange={onContextChange} />);
    await waitFor(() => expect(onContextChange.mock.calls.at(-1)?.[0].refresh.status).toBe("partial"));
    expect(onContextChange.mock.calls.at(-1)?.[0].sourceHealth.items).toEqual(expect.arrayContaining([
      expect.objectContaining({ label: "RSS / Retained", status: "stale", statusLabel: "保留旧缓存",
        reason: expect.stringContaining("本次未联网") }),
      expect.objectContaining({ label: "RSS 缓存", status: "degraded", reason: "缓存读取异常" }),
    ]));
    fireEvent.click(screen.getByRole("button", { name: "详情" }));
    expect(await screen.findByText("RSS / Retained")).toBeTruthy();
  });

  it.each(["light", "dark"] as const)("retains RSS failure evidence in source details and Agent in %s", async theme => {
    const context = vi.fn();
    const row = { source: "BBC", status: "error", count: null, errorCode: "RSS_CONNECTION_REFUSED", httpStatus: null,
      sourceUrl: "https://feeds.bbci.co.uk/news/world/rss.xml", reason: "来源连接被拒绝，未收到 HTTP 响应",
      asOf: "2026-11-14T11:00:00Z", cached: false, dataAsOf: null, freshness: { status: "fresh" } };
    const source: GlobalIntelDataSource = { health: async () => ({}), overview: async () => ({}), staticSnapshot: async () => ({}),
      crucixSnapshot: async () => ({ newsCoverage: { status: "error", coverage: { requested: 1, failed: 1 }, items: [row] } }),
      subscribe: () => () => {} };
    render(<GlobalIntelligenceDashboard dataSource={source} theme={theme} refreshNonce={0} onRefresh={() => {}} onContextChange={context} />);
    await waitFor(() => expect(context.mock.calls.at(-1)?.[0].sourceHealth.items).toContainEqual(
      expect.objectContaining({ id: "rss:BBC", status: "error", observation: row })));
    expect(buildGlobalIntelligenceContext(context.mock.calls.at(-1)![0]).data?.summary).toMatchObject({
      sourceHealth: { items: expect.arrayContaining([expect.objectContaining({ observation: row })]) } });
    fireEvent.click(screen.getByRole("button", { name: "详情" }));
    expect(screen.getByText(/来源连接被拒绝，未收到 HTTP 响应.*数量未知/)).toBeVisible();
  });

  it.each([0, 1])("surfaces RSS outcomes with %s other healthy sources, not a fully successful refresh", async (otherHealthy) => {
    const onContextChange = vi.fn();
    const dataSource: GlobalIntelDataSource = {
      health: async () => ({}), overview: async () => ({}), staticSnapshot: async () => ({}),
      crucixSnapshot: async () => ({
        freshness: { status: "fresh" }, sourceHealth: { queried: 1, ok: otherHealthy },
        news: [{ title: "Actual usable story", publishedAt: new Date().toISOString() }],
        newsCoverage: { status: "partial", coverage: { requested: 3, succeeded: 2, failed: 1 }, items: [
          { source: "Healthy", status: "ok", count: 4, reason: "解析成功", freshness: { status: "fresh", ageSeconds: 1 } },
          { source: "Empty", status: "ok", count: 0, reason: "订阅有效", freshness: { status: "fresh", ageSeconds: 1 } },
          { source: "Failed", status: "error", count: null, reason: "HTTP 403", freshness: { status: "fresh", ageSeconds: 1 } },
        ] },
      }),
      subscribe: (payload) => { payload({ _done: 1, _total: 1 }); return () => {}; },
    };
    render(<GlobalIntelligenceDashboard dataSource={dataSource} theme="dark" refreshNonce={0} onRefresh={() => {}} onContextChange={onContextChange} />);
    await waitFor(() => expect(onContextChange.mock.calls.at(-1)?.[0].refresh.status).toBe("partial"));
    const health = onContextChange.mock.calls.at(-1)?.[0].sourceHealth;
    expect(health.items).toEqual(expect.arrayContaining([
      expect.objectContaining({ label: "RSS / Empty", status: "healthy", statusLabel: "有效空源" }),
      expect.objectContaining({ label: "RSS / Failed", status: "error", reason: "HTTP 403 · 数量未知" }),
    ]));
    fireEvent.click(screen.getByRole("button", { name: "详情" }));
    expect(await screen.findByText("RSS / Failed")).toBeTruthy();
    expect(screen.getByText("HTTP 403 · 数量未知")).toBeTruthy();
  });
  it("settles refresh only after its source requests and stream finish, never from retained data", async () => {
    const onContextChange = vi.fn();
    let payload!: (value: Record<string, unknown>) => void;
    let status!: (value: "connecting" | "live" | "degraded") => void;
    let fail = false;
    const dataSource: GlobalIntelDataSource = {
      health: async () => ({}), overview: async () => ({}),
      staticSnapshot: async () => { if (fail) throw new Error("unavailable"); return { nav_warnings: { warnings: [] } }; },
      crucixSnapshot: async () => ({}),
      subscribe: (onPayload, onStatus) => { payload = onPayload; status = onStatus; onStatus("connecting"); return () => {}; },
    };
    const props = { dataSource, theme: "dark" as const, onRefresh: () => {}, onContextChange };
    const view = render(<GlobalIntelligenceDashboard {...props} refreshNonce={0} />);
    await waitFor(() => expect(onContextChange.mock.calls.at(-1)?.[0]).toMatchObject({ pointCount: 0, refresh: { nonce: 0, status: "loading" } }));
    act(() => { payload({ _done: 0, _total: 2 }); });
    expect(onContextChange.mock.calls.at(-1)?.[0].refresh.status).toBe("loading");
    act(() => { payload({ _done: 2, _total: 2 }); });
    await waitFor(() => expect(onContextChange.mock.calls.at(-1)?.[0].refresh).toMatchObject({ nonce: 0, status: "ready" }));
    fail = true;
    view.rerender(<GlobalIntelligenceDashboard {...props} refreshNonce={1} />);
    expect(onContextChange.mock.calls.at(-1)?.[0].refresh).toMatchObject({ nonce: 1, status: "loading" });
    act(() => { status("degraded"); });
    await waitFor(() => expect(onContextChange.mock.calls.at(-1)?.[0]).toMatchObject({ pointCount: 0, refresh: { nonce: 1, status: "error" } }));
  });

  it("waits beyond stale complete replay and explicit incomplete frames, then clears replaced errors", async () => {
    const onContextChange = vi.fn();
    let payload!: (value: Record<string, unknown>) => void;
    const dataSource: GlobalIntelDataSource = {
      health: async () => ({}), overview: async () => ({}), staticSnapshot: async () => ({}), crucixSnapshot: async () => ({}),
      subscribe: (onPayload) => { payload = onPayload; return () => {}; },
    };
    render(<GlobalIntelligenceDashboard dataSource={dataSource} theme="dark" refreshNonce={1} onRefresh={() => {}} onContextChange={onContextChange} />);
    await act(async () => {});
    act(() => payload({ _cached: true, _stale: true, _complete: true, _done: 48, _total: 48,
      nav_warnings: { warnings: [], error: "previous failure" }, timestamp: "2026-10-23T00:00:00Z" }));
    expect(onContextChange.mock.calls.at(-1)?.[0].refresh.status).toBe("loading");
    act(() => payload({ _cached: false, _stale: false, _complete: false, _done: 48, _total: 48,
      nav_warnings: { warnings: [] } }));
    expect(onContextChange.mock.calls.at(-1)?.[0].refresh.status).toBe("loading");
    act(() => payload({ _cached: false, _stale: false, _complete: true, _done: 48, _total: 48,
      source_health: {}, cache_freshness: {}, timestamp: new Date().toISOString() }));
    await waitFor(() => expect(onContextChange.mock.calls.at(-1)?.[0].refresh.status).toBe("ready"));
    expect(onContextChange.mock.calls.at(-1)?.[0].sourceHealth.items).not.toEqual(expect.arrayContaining([
      expect.objectContaining({ reason: "previous failure" }),
    ]));
  });

  it("does not let a late static-layer 1/1 response settle the live cycle", async () => {
    const onContextChange = vi.fn();
    let resolveStatic!: (value: Record<string, unknown>) => void;
    let payload!: (value: Record<string, unknown>) => void;
    const dataSource: GlobalIntelDataSource = {
      health: async () => ({}), overview: async () => ({}), crucixSnapshot: async () => ({}),
      staticSnapshot: () => new Promise((resolve) => { resolveStatic = resolve; }),
      subscribe: (onPayload) => { payload = onPayload; return () => {}; },
    };
    render(<GlobalIntelligenceDashboard dataSource={dataSource} theme="dark" refreshNonce={0} onRefresh={() => {}} onContextChange={onContextChange} />);
    await act(async () => payload({ _complete: false, _done: 1, _total: 48, nav_warnings: { warnings: [] } }));
    await act(async () => resolveStatic({ _static: true, _complete: true, _done: 1, _total: 1, military_bases: { bases: [] } }));
    expect(onContextChange.mock.calls.at(-1)?.[0].refresh.status).toBe("loading");
    expect(screen.queryByText("数据已结算，暂无实时事件")).not.toBeInTheDocument();
    act(() => payload({ _complete: true, _done: 48, _total: 48 }));
    await waitFor(() => expect(onContextChange.mock.calls.at(-1)?.[0].refresh.status).toBe("ready"));
  });

  it.each(["failure", "disconnect"])("does not erase a current-cycle %s when its completion frame contains only metadata", async (outcome) => {
    const onContextChange = vi.fn();
    let payload!: (value: Record<string, unknown>) => void;
    let status!: (value: "connecting" | "live" | "degraded") => void;
    const dataSource: GlobalIntelDataSource = {
      health: async () => ({}), overview: async () => ({}), staticSnapshot: async () => ({}), crucixSnapshot: async () => ({}),
      subscribe: (onPayload, onStatus) => { payload = onPayload; status = onStatus; return () => {}; },
    };
    render(<GlobalIntelligenceDashboard dataSource={dataSource} theme="dark" refreshNonce={0} onRefresh={() => {}} onContextChange={onContextChange} />);
    await act(async () => {});
    act(() => payload({ _cached: true, _stale: true, _complete: true, _done: 2, _total: 2, nav_warnings: { warnings: [] } }));
    expect(onContextChange.mock.calls.at(-1)?.[0].refresh.status).toBe("loading");
    if (outcome === "disconnect") act(() => status("degraded"));
    else {
      act(() => payload({ _stale: false, _complete: false, _done: 1, _total: 2,
        nav_warnings: { warnings: [] }, earthquakes: { error: "current source unavailable" } }));
      act(() => payload({ _stale: false, _complete: true, _done: 2, _total: 2 }));
    }
    await waitFor(() => expect(onContextChange.mock.calls.at(-1)?.[0].refresh.status).toBe("partial"));
  });

  it.each(["stale", "unknown"])("does not confirm a fully fresh refresh from a %s Crucix snapshot", async (freshness) => {
    const onContextChange = vi.fn();
    const dataSource: GlobalIntelDataSource = {
      health: async () => ({}), overview: async () => ({}), staticSnapshot: async () => ({}),
      crucixSnapshot: async () => ({
        asOf: "2026-08-24T00:00:00Z", freshness: { status: freshness },
        sourceHealth: { ok: 1 }, news: [{ title: "Retained report" }],
      }),
      subscribe: (payload) => { payload({ _done: 1, _total: 1 }); return () => {}; },
    };
    render(<GlobalIntelligenceDashboard dataSource={dataSource} theme="dark" refreshNonce={0} onRefresh={() => {}} onContextChange={onContextChange} />);
    await waitFor(() => expect(onContextChange.mock.calls.at(-1)?.[0].refresh).toMatchObject({ status: "partial" }));
  });

  it("keeps a connected source with expired observations degraded in refresh and Agent context", async () => {
    const onContextChange = vi.fn();
    const payload = {
      _done: 1, _total: 1, _stale: true,
      earthquakes: { earthquakes: [], freshness: "stale" },
      source_health: { seismology: { status: "closed" } },
      cache_freshness: { seismology: { is_stale: true, last_updated_s_ago: 900 } },
    };
    const dataSource: GlobalIntelDataSource = {
      health: async () => ({}), overview: async () => payload, staticSnapshot: async () => payload,
      crucixSnapshot: async () => ({}),
      subscribe: (onPayload, onStatus) => { onPayload(payload); onStatus("degraded"); return () => {}; },
    };
    render(<GlobalIntelligenceDashboard dataSource={dataSource} theme="dark" refreshNonce={0} onRefresh={() => {}} onContextChange={onContextChange} />);
    await waitFor(() => expect(onContextChange.mock.calls.at(-1)?.[0]).toMatchObject({
      refresh: { status: "partial" }, dataAvailability: { status: "partial" },
    }));
  });

  it("does not present unavailable feeds as zero risk or an empty filtered result", async () => {
    const onContextChange = vi.fn();
    const unavailable = async () => { throw new Error("source unavailable"); };
    const dataSource: GlobalIntelDataSource = {
      health: unavailable, overview: unavailable, staticSnapshot: unavailable,
      crucixSnapshot: unavailable,
      subscribe: (_payload, status) => { status("degraded"); return () => {}; },
    };
    const { container } = render(<GlobalIntelligenceDashboard dataSource={dataSource} theme="dark" refreshNonce={0} onRefresh={() => {}} onContextChange={onContextChange} />);
    await waitFor(() => expect(screen.getByText("数据不可用，无法判断当前风险")).toBeVisible());
    const hud = container.querySelector(".intel-hud")!;
    expect(hud).not.toHaveTextContent("负面 0%");
    expect(hud).not.toHaveTextContent("0 个事件");
    expect(hud).not.toHaveTextContent("连接中");
    expect(container).not.toHaveTextContent("当前筛选没有重点变化");
    expect(onContextChange.mock.calls.at(-1)?.[0]).toMatchObject({
      dataAvailability: { status: "unavailable", world: false, media: false },
      pointCount: null, eventCount: null, highPriorityCount: null,
      eventLifecycle: null, mediaMonitor: null, trendRadar: null,
      routes: { alerts: null, affected: null },
    });
  });

  it("keeps an explicit empty successful feed as a real zero, but not missing media", async () => {
    const onContextChange = vi.fn();
    const payload = { timestamp: new Date().toISOString(), _done: 1, _total: 1, nav_warnings: { warnings: [] } };
    const dataSource: GlobalIntelDataSource = {
      health: async () => ({}), overview: async () => payload, staticSnapshot: async () => payload,
      crucixSnapshot: async () => ({}),
      subscribe: (_payload, status) => { status("live"); return () => {}; },
    };
    const { container } = render(<GlobalIntelligenceDashboard dataSource={dataSource} theme="dark" refreshNonce={0} onRefresh={() => {}} onContextChange={onContextChange} />);
    await waitFor(() => expect(onContextChange.mock.calls.at(-1)?.[0]).toMatchObject({
      dataAvailability: { status: "available", world: true, media: false },
      pointCount: 0, eventCount: 0, highPriorityCount: 0,
    }));
    expect(container.querySelector(".intel-priority-card strong")).toHaveTextContent("0");
    expect(container.querySelector(".intel-media-card")).toHaveTextContent("舆情数据未接入");
    expect(screen.getByText("数据已结算，暂无实时事件")).toBeVisible();
  });

  it("does not count an error-only settled snapshot as available evidence", async () => {
    const onContextChange = vi.fn();
    const payload = { timestamp: new Date().toISOString(), _done: 1, _total: 1, nav_warnings: { error: "upstream unavailable" } };
    const dataSource: GlobalIntelDataSource = {
      health: async () => ({}), overview: async () => payload, staticSnapshot: async () => payload,
      crucixSnapshot: async () => ({}),
      subscribe: (_payload, status) => { status("degraded"); return () => {}; },
    };
    render(<GlobalIntelligenceDashboard dataSource={dataSource} theme="dark" refreshNonce={0} onRefresh={() => {}} onContextChange={onContextChange} />);
    await waitFor(() => expect(onContextChange.mock.calls.at(-1)?.[0]).toMatchObject({
      dataAvailability: { status: "unavailable" }, eventCount: null,
    }));
    expect(screen.getByText("数据不可用，无法判断当前风险")).toBeVisible();
    expect(screen.queryByText("数据已结算，暂无实时事件")).not.toBeInTheDocument();
  });

  it("reports the selected route/point and only the currently visible evidence blocks", () => {
    const route = { id: "shipping", name: "Test corridor" };
    const context = buildGlobalIntelligenceContext({ selectedRoute: route, presentation: { mapExpanded: true }, events: [{ sourceFreshness: "fresh" }] });
    expect(context.selection).toEqual({ route });
    expect(context.data.freshness).toBe("unknown");
    expect(context.visibleBlocks?.map((block) => block.id)).not.toContain("global-intelligence-events");
    expect(context.visibleBlocks?.map((block) => block.id)).not.toContain("global-intelligence-sources");
    expect(buildGlobalIntelligenceContext({ selectedPoint: { id: "point", sourceFreshness: "stale", collectedAt: "2026-10-01" } }).data).toMatchObject({ freshness: "stale", asOf: "2026-10-01" });
  });
  it("does not treat a live connection as proof of fresh data", () => {
    const context = buildGlobalIntelligenceContext({ streamStatus: "live", lastUpdate: new Date().toISOString(), selectedEvent: { title: "Undated report", timestamp: "", timestampBasis: "unknown", sourceFreshness: "unknown" } });
    expect(context.data.freshness).toBe("unknown");
    expect(context.data.asOf).toBeUndefined();
  });

  it("shows old publication, collection and tracking separately, including unknown dates", async () => {
    const observedAt = new Date().toISOString();
    const snapshot = {
      timestamp: observedAt, _done: 1, _total: 1,
      nav_warnings: {
        timestamp: "2026-08-12T14:01:51Z", collected_at: "2026-08-12T14:01:51Z", freshness: "stale",
        warnings: [
          { id: "2024-517", navarea: "4", issue_date: "081653Z MAY 2024", status: "active", text: "DANGER AREA", lat: 20, lon: 60 },
          { id: "2024-518", navarea: "4", issue_date: null, status: "active", text: "SECOND DANGER AREA", lat: 21, lon: 60 },
        ],
      },
    };
    const onContextChange = vi.fn();
    const dataSource: GlobalIntelDataSource = {
      health: async () => ({}), overview: async () => snapshot,
      staticSnapshot: async () => snapshot, crucixSnapshot: async () => ({}),
      subscribe: (_payload, status) => { status("live"); return () => {}; },
    };
    const { container } = render(<GlobalIntelligenceDashboard dataSource={dataSource} theme="dark" refreshNonce={0} onRefresh={() => {}} onContextChange={onContextChange} />);
    const list = container.querySelector(".intel-event-list") as HTMLElement;
    await waitFor(() => expect(within(list).getByRole("button", { name: /2024-517/ })).toBeVisible());
    const oldWarning = within(list).getByRole("button", { name: /2024-517/ });
    expect(oldWarning).toHaveTextContent(/发布 \d+ 天前/);
    expect(oldWarning).not.toHaveTextContent("刚刚");
    expect(oldWarning).toHaveTextContent("首次收录");
    expect(oldWarning).toHaveTextContent("旧缓存");
    const unknownWarning = within(list).getByRole("button", { name: /2024-518/ });
    expect(unknownWarning).toHaveTextContent("发布日期未知");
    fireEvent.click(oldWarning);
    const state = () => onContextChange.mock.calls.at(-1)?.[0] as Record<string, unknown>;
    await waitFor(() => expect(state().selectedEvent).toMatchObject({
      title: "NAVAREA 4 · 2024-517", timestamp: "2024-05-08T16:53:00.000Z", timestampBasis: "published",
      collectedAt: "2026-08-12T14:01:51.000Z", sourceFreshness: "stale", firstSeenAt: expect.any(String),
    }));
    expect(screen.getByText("最近成功采集")).toBeVisible();
    expect(screen.getByText("发布日期", { selector: "dt" })).toBeVisible();
    expect(buildGlobalIntelligenceContext(state()).data).toMatchObject({ freshness: "stale", asOf: "2026-08-12T14:01:51.000Z" });
    expect(buildGlobalIntelligenceContext(state()).data?.summary).toMatchObject({
      timeSemantics: { tracking: expect.stringContaining("首次收录不等于新发生") },
      filters: { timeBasis: "tracking-activity" },
    });
    fireEvent.click(unknownWarning);
    await waitFor(() => expect(state().selectedEvent).toMatchObject({ timestamp: "", timestampBasis: "unknown" }));
    expect(container).not.toHaveTextContent("Invalid Date");
  });
});
