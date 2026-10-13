import { expect, test, type Page } from "@playwright/test";

const shellOrigin = process.env.VIBE_E2E_DOMAIN_SUITES_ORIGIN;
type NewsWindow = Window & { __newsMessages: Record<string, unknown>[] };

function topic(id: string, headline: string) {
  return {
    id, headline, label: headline, industry_key: "tech", industry_name: "科技",
    mention_count: 1, current_mentions: 1, previous_mentions: 0,
    heat_velocity_pct: null, velocity_state: "new", heat_score: 30,
    attention_score: 40, attention_level: "观察", spread_score: 10, spread_level: "单一来源",
    source_count: 1, sources: ["测试公开源"], language_count: 1, languages: ["zh"], cross_language: false,
    sentiment: "neutral", sentiment_score: 0, sentiment_counts: {}, source_frames: [],
    framing_divergence: false, framing_divergence_score: 0,
    verification_status: "常规报道", verification_flags: [], signal: "watch",
    signal_reasons: ["测试事件"], latest_at: new Date().toISOString(), keywords: [],
    items: [{ title: headline, source: "测试公开源", url: `https://example.com/${id}`, time: "09-09 10:00" }],
  };
}

async function setupNews(page: Page, state = { failRadar: false, failFeed: false, feedCalls: 0, radarRefreshes: 0 }) {
  const first = topic("initial", "首屏事件");
  const more = topic("beyond-initial", "分页后的独立事件");
  const filtered = topic("filtered", "筛选命中的事件");
  const generated = new Date(Date.now() - 20 * 60_000).toISOString();
  const radar = {
    generated_at: generated, generated_at_iso: generated, recent_days: 7,
    industries: [{ key: "tech", name: "科技", accent: "#a87432", total: 3, items: [first.items[0], filtered.items[0],
      { id: "category-only", title: "科技｜风险动态", zh: "自动聚类：科技｜风险动态", summary: "", source: "测试公开源", url: "https://example.com/category", time: "09-09 10:00" }] }],
    stats: { industries: 1, total_sources: 1, healthy_sources: 1, source_health: [] },
    refresh: { refreshing: false, stale: true, interval_minutes: 15 },
    monitor: {
      topics: [first], keywords: [], source_frames: [], method: "test", caveat: "测试数据",
      summary: { analyzed_items: 3, topic_count: 3, risk_topic_count: 0, opportunity_topic_count: 0,
        flagged_topic_count: 0, sentiment: { positive_pct: 0, neutral_pct: 100, negative_pct: 0 } },
    },
  };
  await page.addInitScript(() => {
    (window as NewsWindow).__newsMessages = [];
    window.addEventListener("message", (event) => {
      if (event.data?.modId === "news-radar") (window as NewsWindow).__newsMessages.push(event.data);
    });
    localStorage.setItem("vibedesk.research.watch-groups.v1", JSON.stringify([
      { id: "test", name: "测试自选", symbols: [{ symbol: "002371", name: "测试公司", market: "CN" }] },
    ]));
  });
  await page.route("**/api/crucix/snapshot", (route) => route.fulfill({ status: 503, json: { detail: "测试未启用补充源" } }));
  await page.route("**/api/research/**", async (route) => {
    const url = new URL(route.request().url());
    let data: unknown;
    if (url.pathname.endsWith("/radar/topics")) {
      const query = url.searchParams.get("q");
      const items = query ? query.includes("不存在") ? [] : [filtered]
        : Number(url.searchParams.get("offset")) > 0 ? [more] : [first];
      data = { items, total: query ? items.length : 2, industry_counts: { tech: 2 }, generated_at_iso: generated };
    } else if (url.pathname.endsWith("/radar") || url.pathname.endsWith("/radar/refresh")) {
      if (url.pathname.endsWith("/refresh")) state.radarRefreshes += 1;
      if (state.failRadar) return route.fulfill({ status: 503, json: { detail: "测试雷达不可用" } });
      data = radar;
    } else if (url.pathname.endsWith("/quote")) {
      data = { "002371": { name: "测试公司" } };
    } else if (url.pathname.endsWith("/announcements") || url.pathname.endsWith("/news")) {
      state.feedCalls += 1;
      if (state.failFeed) return route.fulfill({ status: 503, json: { detail: "测试资讯源故障" } });
      data = url.pathname.endsWith("/announcements")
        ? [{ title: "测试公司：公告重点", date: "2026-09-09", type: "公告", url: "https://example.com/filing" }]
        : [{ 新闻标题: "自选重点", 发布时间: "2026-09-09 10:00", 文章来源: "测试公开源", 新闻链接: "https://example.com/watch", 新闻内容: "测试公司已发布消息" }];
    } else return route.continue();
    return route.fulfill({ json: { data } });
  });
  await page.goto(`${shellOrigin}/?mod=news-radar&workspace=e2e-news-${Date.now()}`);
  const frame = page.frameLocator('iframe[title="新闻与舆情"]');
  await expect(frame.getByRole("navigation", { name: "新闻与舆情栏目" })).toBeVisible();
  return { frame, state };
}

const readContext = (page: Page) => page.evaluate(() =>
  (window as NewsWindow).__newsMessages.filter((message) => message.type === "vibedesk:context").at(-1)?.context,
);

test.describe("News Radar current-page evidence", () => {
  test.skip(!shellOrigin, "Run with playwright.domain-suites.config.ts against the local Desk stack");

  test("never presents a category-only cached row as a news headline", async ({ page }) => {
    const { frame } = await setupNews(page);
    await frame.getByRole("button", { name: "全部资讯", exact: true }).click();
    await expect(frame.locator(".news-result-count")).toHaveText("2 条资讯");
    await expect(frame.locator(".news-raw-list")).not.toContainText("科技｜风险动态");
    await expect.poll(() => readContext(page)).toMatchObject({ data: { summary: { totalMatchingItems: 2 } } });
  });

  test("keeps paginated, filtered and raw news aligned with Agent Context", async ({ page }) => {
    const { frame } = await setupNews(page);
    await expect(frame.locator(".news-freshness")).toHaveClass(/is-stale/);
    await frame.getByRole("button", { name: "加载更多主题" }).click();
    await frame.locator(".news-topic-row").filter({ hasText: "分页后的独立事件" }).click();
    await expect(frame.locator(".news-detail h2")).toHaveText("分页后的独立事件");
    await expect.poll(() => readContext(page)).toMatchObject({
      selection: { topicId: "beyond-initial", topic: { headline: "分页后的独立事件" } },
    });
    await frame.getByPlaceholder("搜索主题、公司、行业或来源").fill("筛选");
    await expect(frame.locator(".news-detail h2")).toHaveText("筛选命中的事件");
    await expect.poll(() => readContext(page)).toMatchObject({ selection: { topicId: "filtered" }, filters: { query: "筛选" } });
    await frame.getByPlaceholder("搜索主题、公司、行业或来源").fill("不存在");
    await expect.poll(() => readContext(page)).toMatchObject({ selection: { topicId: null, topic: null }, data: { summary: { totalMatchingTopics: 0 } } });
    await frame.getByRole("button", { name: "全部资讯", exact: true }).click();
    await frame.getByPlaceholder("搜索全部新闻、来源或主题").fill("筛选");
    await expect.poll(() => readContext(page)).toMatchObject({
      selection: { tab: "raw", topicId: null }, filters: { query: "筛选", industry: "all" },
      visibleBlocks: [{ id: "news-raw" }],
      data: { summary: { totalMatchingItems: 1, items: [{ title: "筛选命中的事件" }] } },
    });
  });

  test("keeps feeds usable without radar and refreshes the active feed through the Agent bridge", async ({ page }) => {
    const { frame, state } = await setupNews(page, { failRadar: true, failFeed: false, feedCalls: 0, radarRefreshes: 0 });
    await frame.getByRole("button", { name: "A股公告", exact: true }).click();
    await expect(frame.locator(".news-watch-feed")).toContainText("公告重点");
    await expect.poll(() => readContext(page)).toMatchObject({
      selection: { tab: "filings", topic: null }, visibleBlocks: [{ id: "news-filings" }],
      data: { summary: { items: [{ title: "公告重点" }], loading: false } },
    });
    const child = page.frames().find((item) => item.url().includes("/mod-runtime/research/intel"))!;
    const instanceId = await child.evaluate(() =>
      (window as NewsWindow).__newsMessages.find((message) => message.type === "vibedesk:init")?.instanceId,
    );
    const before = state.feedCalls;
    await page.evaluate((instanceId) => {
      const element = document.querySelector<HTMLIFrameElement>('iframe[title="新闻与舆情"]')!;
      element.contentWindow!.postMessage({ type: "vibedesk:ui-action-request", modId: "news-radar", instanceId,
        requestId: "test-active-news-refresh", actionId: "news.refresh", input: {} }, new URL(element.src).origin);
    }, instanceId);
    await expect.poll(() => page.evaluate(() =>
      (window as NewsWindow).__newsMessages.find((message) => message.requestId === "test-active-news-refresh"),
    )).toMatchObject({ type: "vibedesk:ui-action-result", ok: true, result: { rowCount: 1 } });
    expect(state.feedCalls).toBeGreaterThan(before);
    expect(state.radarRefreshes).toBe(0);
    state.failFeed = true;
    await frame.getByRole("button", { name: "更新", exact: true }).click();
    await expect(frame.locator(".news-watch-feed")).toContainText("公告重点");
    await expect.poll(() => readContext(page)).toMatchObject({
      data: { freshness: "stale", summary: { error: "更新失败，正在显示上次数据", items: [{ title: "公告重点" }] } },
    });
    state.failFeed = false;
    await frame.getByRole("button", { name: "自选新闻", exact: true }).click();
    await frame.getByPlaceholder("搜索公司、新闻或来源").fill("自选重点");
    await expect.poll(() => readContext(page)).toMatchObject({
      selection: { tab: "watch-news", topic: null }, filters: { query: "自选重点" },
      data: { summary: { items: [{ title: "自选重点" }] } },
    });
  });
});
