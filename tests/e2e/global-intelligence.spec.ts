import { expect, test } from "@playwright/test";
import type { ModPageContext } from "@newma-desk/contracts";

const shellOrigin = process.env.VIBE_E2E_DOMAIN_SUITES_ORIGIN;

function topicFixture(topicId: string, title: string) {
  return {
    topicId, title, subtitle: "E2E 来源观测", question: "如何变化？", accent: "cyan",
    metrics: [{ label: "E2E 利率观测", value: "3.50", unit: "%", date: "2026-09-09", source: "E2E 来源", sourceUrl: "https://example.com", status: "ready", change: "测试来源数据" }],
    factors: [{ id: "pressure", label: "压力", min: 0, max: 100, value: 50 }],
    series: [{ id: "rate", label: "E2E 利率", color: "#38bdf8" }],
    observations: [{ seriesId: "rate", date: "2026-09-09", value: 3.5, unit: "%", source: "E2E 来源" }],
    events: [{ id: "e2e-document", title: "E2E 来源文件", date: "2026-09-09", publishedAt: "2026-09-09", collectedAt: "2026-09-10T08:00:00Z", sourceStatus: "ready", evidenceKey: "https://example.com", source: "E2E 来源", sourceUrl: "https://example.com", summary: "用于交互测试", evidenceType: "official-document" }],
    eventCoverage: { count: 1, readySourceCount: 1, staleSourceCount: 0 },
    transmission: ["输入", "输出"], sources: ["E2E 来源"], sourceStatus: [{ id: "test", label: "E2E 来源", status: "ready", url: "https://example.com" }],
    dataMode: "source-backed", freshness: "fresh", dataAsOf: null, dataWarning: "测试观测，非实时行情", gaps: ["E2E 未接入指标"], factorSource: "user-assumptions",
    generatedAt: "2026-09-10T08:00:00Z", updatedAt: "2026-09-10T08:00:00Z",
    forecast: { generatedAt: "2026-09-10T08:00:00Z", probabilities: [{ label: "初始情景", probability: 100 }], dominantScenario: "初始情景", confidence: 0.5, method: "E2E 规则模型", disclaimer: "非真实发生概率" },
  };
}

for (const [topicId, modId, title] of [
  ["fed-rates", "fed-rates", "联储加息"],
  ["hormuz", "hormuz-conflict", "美伊战争"],
  ["us-china-trade", "us-china-trade", "中美贸易"],
]) {
  test(`${title}: keeps source identity, parameters and Agent evidence aligned through retries`, async ({ page }) => {
    test.skip(!shellOrigin, "Run against the local Desk stack");
    let context: ModPageContext | undefined;
    let savedContext: ModPageContext | undefined;
    let refreshFails = false;
    let forecastAttempts = 0;
    page.on("request", (request) => {
      if (request.method() === "PUT" && new URL(request.url()).pathname === `/api/mods/${modId}/context`) context = request.postDataJSON().context;
    });
    page.on("response", async (response) => {
      if (response.ok() && response.request().method() === "PUT" && new URL(response.url()).pathname === `/api/mods/${modId}/context`) {
        // Navigation can discard the previous page's response body.
        const body = await response.json().catch(() => undefined);
        if (body) savedContext = body.context;
      }
    });
    // Deterministic evidence and failures; no test forecast is saved to the user's database.
    await page.route(`**/api/global-topics/${topicId}**`, (route) => {
      const request = route.request();
      if (request.method() === "POST") {
        forecastAttempts++;
        if (forecastAttempts === 1) return route.fulfill({ status: 503, json: { detail: "E2E forecast failure" } });
        return route.fulfill({ json: {
          generatedAt: new Date().toISOString(), probabilities: [{ label: "E2E 新情景", probability: 100 }],
          dominantScenario: "E2E 新情景", confidence: 0.6, method: "E2E 规则模型", disclaimer: "测试情景，非真实预测",
        } });
      }
      return refreshFails ? route.fulfill({ status: 503, json: { detail: "E2E refresh failure" } }) : route.fulfill({ json: topicFixture(topicId!, title!) });
    });
    await page.goto(`${shellOrigin}/?mod=${modId}&workspace=e2e-topic-${topicId}-${Date.now()}`);
    const root = page.locator(".global-topic-root");
    await expect(root.getByText("来源观测 · 1 条事件", { exact: true })).toBeVisible();
    await expect.poll(() => context?.view).toEqual({ id: modId, title });
    await expect.poll(() => context?.data.summary?.loadState).toBe("ready");
    await expect.poll(() => savedContext?.data.summary?.loadState).toBe("ready");
    expect(context?.data.freshness).toBe("fresh");
    expect(context?.data.asOf).toBeUndefined();
    expect(context?.data.summary?.dataMode).toBe("source-backed");
    expect(context?.data.summary?.eventCoverage).toMatchObject({ count: 1, readySourceCount: 1 });
    await expect(root.getByText("仅 1 个观测，暂无连续曲线")).toBeVisible();
    const evidence = context?.data.summary?.events;
    const observations = context?.data.summary?.observations;
    expect(Array.isArray(evidence) && evidence.length > 0).toBe(true);
    expect(Array.isArray(observations) && observations.length > 0).toBe(true);
    const slider = root.getByRole("slider").first();
    const initialValue = await slider.inputValue();
    await slider.focus();
    await slider.press("ArrowRight");
    await expect.poll(() => context?.data.summary?.forecastPending).toBe(true);
    await root.getByRole("button", { name: "重新推演" }).click();
    await expect(root.getByRole("alert")).toContainText("推演失败");
    await root.getByRole("button", { name: "重新推演" }).click();
    await expect(root.locator(".topic-probabilities")).toContainText("E2E 新情景");
    await expect.poll(() => context?.data.summary).toMatchObject({
      events: evidence, observations, forecastPending: false,
      forecast: { dominantScenario: "E2E 新情景" },
    });
    expect(context?.data.summary?.forecastFactors).toEqual(context?.data.summary?.factors);
    refreshFails = true;
    await root.getByRole("button", { name: "刷新专题", exact: true }).click();
    await expect(root.getByRole("alert")).toContainText("当前保留上次数据与参数");
    await expect(root.locator(".topic-probabilities")).toContainText("E2E 新情景");
    await expect.poll(() => context?.data.summary?.displayingPreviousData).toBe(true);
    refreshFails = false;
    await root.getByRole("button", { name: "重试", exact: true }).click();
    await expect(slider).toHaveValue(initialValue);
    await expect(root.locator(".topic-probabilities")).not.toContainText("E2E 新情景");
    await expect.poll(() => context?.data.summary?.loadState).toBe("ready");
    if (topicId === "fed-rates") {
      await page.screenshot({ path: "/tmp/newma-desk-topic-context-verified.png", animations: "disabled" });
      const standaloneUrl = await page.getByRole("link", { name: "独立打开", exact: true }).getAttribute("href");
      expect(standaloneUrl).toContain("standalone=1");
      context = undefined;
      savedContext = undefined;
      await page.goto(new URL(standaloneUrl!, shellOrigin).toString());
      await expect(root.getByText("来源观测 · 1 条事件", { exact: true })).toBeVisible();
      await expect.poll(() => context?.view).toEqual({ id: modId, title });
      await expect.poll(() => context?.data.summary?.loadState).toBe("ready");
      await expect.poll(() => context?.data.summary?.events).toEqual(evidence);
      await expect.poll(() => savedContext?.data.summary?.events).toEqual(evidence);
      await expect.poll(() => context?.data.asOf).toBeUndefined();
    }
  });
}

test("keeps warning publication time separate from collection and Agent tracking context", async ({ page }) => {
  test.skip(!shellOrigin, "Run against the local Desk stack");
  const now = new Date().toISOString();
  const payload = {
    timestamp: now, _done: 1, _total: 1,
    nav_warnings: {
      timestamp: "2026-08-12T14:01:51Z", collected_at: "2026-08-12T14:01:51Z", freshness: "stale",
      warnings: [
        { id: "2024-517", navarea: "4", issue_date: "081653Z MAY 2024", status: "active", text: "DANGER AREA", lat: 20, lon: 60 },
        { id: "2024-518", navarea: "4", issue_date: null, status: "active", text: "SECOND DANGER AREA", lat: 21, lon: 60 },
      ],
    },
  };
  let context: Record<string, any> = {};
  page.on("request", (request) => {
    if (request.method() === "PUT" && new URL(request.url()).pathname === "/api/mods/global-situation/context") {
      context = request.postDataJSON();
    }
  });
  await page.route("**/api/global-intel/**", (route) => {
    if (new URL(route.request().url()).pathname.endsWith("/stream")) {
      return route.fulfill({ contentType: "text/event-stream", body: `data: ${JSON.stringify(payload)}\n\n` });
    }
    return route.fulfill({ json: payload });
  });
  await page.route("**/api/crucix/snapshot", (route) => route.fulfill({ json: {} }));
  await page.goto(`${shellOrigin}/?mod=global-situation&workspace=e2e-warning-time-${Date.now()}`);
  const list = page.locator(".intel-event-list");
  const old = list.getByRole("button", { name: /2024-517/ });
  await expect(old).toBeVisible();
  await expect(old).toContainText(/发布 \d+ 天前/);
  await expect(old).not.toContainText("刚刚");
  await expect(old).toContainText("旧缓存");
  await old.click();
  await expect(page.getByText("最近成功采集", { exact: true })).toBeVisible();
  await expect.poll(() => context.context?.data?.summary ?? context.data?.summary).toMatchObject({
    selectedEvent: { timestamp: "2024-05-08T16:53:00.000Z", timestampBasis: "published", collectedAt: "2026-08-12T14:01:51.000Z", sourceFreshness: "stale" },
    filters: { timeBasis: "tracking-activity" },
  });
  await page.getByRole("button", { name: "关闭详情", exact: true }).click();
  await list.getByRole("button", { name: /2024-518/ }).click();
  await expect.poll(() => context.context?.data?.summary ?? context.data?.summary).toMatchObject({
    selectedEvent: { timestamp: "", timestampBasis: "unknown", firstSeenAt: expect.any(String) },
  });
  await expect(page.locator(".intel-evidence-chain")).not.toContainText("Invalid Date");
  await page.screenshot({ path: "/tmp/newma-desk-warning-time-verified.png", fullPage: false, animations: "disabled" });
});

test("Hormuz maritime evidence stays aligned with the Agent through stale, empty and failed source states", async ({ page }) => {
  test.skip(!shellOrigin, "Run against the local Desk stack");
  const maritime = {
    status: "stale", reason: "来源缓存已过期", source: "NGA", sourceUrl: "https://msi.nga.mil/",
    collectedAt: "2026-08-12T14:01:51Z", cacheExpiresAt: "2026-08-12T15:01:51Z",
    scannedCount: 386 as number | null, matchedCount: 1 as number | null,
    counts: { "hormuz-mentioned": 0, "nearby-coordinate": 0, regional: 1 } as Record<string, number> | null,
    selectionRule: "扫描完整正文，区域公告不等于海峡事件。", limitations: "未匹配不代表海峡安全；警告数量不是风险分数。",
    warnings: [{ id: "P:2024-1", reference: "HYDROPAC 2024-1", title: "E2E PERSIAN GULF. SURVEY WORKS.",
      text: "E2E FULL OFFICIAL WARNING TEXT.", textTruncated: false, publishedAt: "2024-05-08T16:53:00Z",
      publicationDateRaw: "081653Z MAY 2024", scope: "regional", scopeLabel: "区域性公告", authority: "NAVAREA IX 1/24",
      sourceUrl: "https://msi.nga.mil/", status: "not-cancelled-in-snapshot", currentValidity: "unverified" }],
  };
  let context: ModPageContext | undefined;
  let savedContext: ModPageContext | undefined;
  page.on("request", (request) => {
    if (request.method() === "PUT" && new URL(request.url()).pathname === "/api/mods/hormuz-conflict/context") context = request.postDataJSON().context;
  });
  page.on("response", async (response) => {
    if (response.ok() && response.request().method() === "PUT" && new URL(response.url()).pathname === "/api/mods/hormuz-conflict/context") {
      const body = await response.json().catch(() => undefined);
      if (body) savedContext = body.context;
    }
  });
  await page.route("**/api/global-topics/hormuz", (route) => route.fulfill({ json: { ...topicFixture("hormuz", "美伊战争"), maritime } }));
  await page.goto(`${shellOrigin}/?mod=hormuz-conflict&workspace=e2e-topic-maritime-${Date.now()}`);
  const panel = page.getByRole("region", { name: "霍尔木兹与周边航行警告", exact: true });
  await expect(panel).toContainText("旧快照 · 当前有效性待核验");
  await expect(panel).toContainText("发布 2024-05-08 16:53 UTC");
  await expect(panel).toContainText("最近成功采集 2026-08-12 14:01 UTC");
  await panel.locator("summary").filter({ hasText: "HYDROPAC 2024-1" }).click();
  await expect(panel.getByText("E2E FULL OFFICIAL WARNING TEXT.")).toBeVisible();
  await expect.poll(() => context?.data.summary?.maritime).toEqual(maritime);
  await expect.poll(() => savedContext?.data.summary?.maritime).toEqual(maritime);
  await expect.poll(() => savedContext?.selection?.warningId).toBe("P:2024-1");
  await expect.poll(() => savedContext?.data.summary?.maritimeView).toMatchObject({ selectedWarning: maritime.warnings[0], visibleWarningIds: ["P:2024-1"] });
  await panel.getByRole("textbox", { name: "警告关键词" }).fill("not-a-matching-warning");
  await expect(panel).toContainText("当前筛选在已载入记录中没有匹配");
  await expect.poll(() => savedContext?.selection?.warningId).toBeNull();
  await expect.poll(() => savedContext?.filters?.maritime).toMatchObject({ query: "not-a-matching-warning", coverage: "loaded-records-only" });
  await panel.getByRole("button", { name: "清除筛选" }).click();
  await panel.getByRole("button", { name: "明确提及霍尔木兹", exact: true }).click();
  await expect(panel).toContainText("当前筛选在已载入记录中没有匹配");
  await panel.getByRole("button", { name: "区域公告", exact: true }).click();
  await panel.locator("summary").filter({ hasText: "HYDROPAC 2024-1" }).focus();
  await panel.locator("summary").filter({ hasText: "HYDROPAC 2024-1" }).press("Enter");
  await expect(panel.getByText("E2E FULL OFFICIAL WARNING TEXT.")).toBeVisible();
  await expect.poll(() => savedContext?.selection?.warningId).toBe("P:2024-1");
  await expect.poll(() => savedContext?.filters?.maritime).toMatchObject({ scope: "regional" });
  await page.screenshot({ path: "/tmp/newma-desk-maritime-e2e.png", animations: "disabled" });
  const standaloneUrl = await page.getByRole("link", { name: "独立打开", exact: true }).getAttribute("href");
  context = undefined;
  savedContext = undefined;
  await page.goto(new URL(standaloneUrl!, shellOrigin).toString());
  await expect(panel).toContainText("旧快照");
  await expect.poll(() => context?.data.summary?.maritime).toEqual(maritime);
  await expect.poll(() => savedContext?.data.summary?.maritime).toEqual(maritime);
  await expect(panel.getByRole("button", { name: "区域公告", exact: true })).toHaveAttribute("aria-pressed", "true");
  await expect(panel.getByText("E2E FULL OFFICIAL WARNING TEXT.")).toBeVisible();
  await expect.poll(() => savedContext?.selection?.warningId).toBe("P:2024-1");
  // A browser reload must restore controls, but obtain evidence from the source again.
  maritime.warnings = maritime.warnings.map((warning) => ({ ...warning, text: "E2E RELOADED OFFICIAL WARNING TEXT." }));
  savedContext = undefined;
  await page.reload();
  await expect(panel.getByText("E2E RELOADED OFFICIAL WARNING TEXT.")).toBeVisible();
  await expect.poll(() => savedContext?.selection?.warningId).toBe("P:2024-1");
  await expect.poll(() => savedContext?.data.summary?.maritimeView).toMatchObject({ selectedWarning: { text: "E2E RELOADED OFFICIAL WARNING TEXT." } });
  maritime.status = "ready";
  maritime.reason = "";
  maritime.warnings = [];
  maritime.matchedCount = 0;
  maritime.counts = { "hormuz-mentioned": 0, "nearby-coordinate": 0, regional: 0 };
  await page.locator(".global-topic-root").getByRole("button", { name: "刷新专题", exact: true }).click();
  await expect(panel).toContainText("本次快照未匹配到相关记录，不代表海峡安全");
  await expect.poll(() => savedContext?.selection?.warningId).toBeNull();
  maritime.status = "unavailable";
  maritime.reason = "读取失败";
  maritime.scannedCount = maritime.matchedCount = null;
  maritime.counts = null;
  maritime.collectedAt = "";
  await page.locator(".global-topic-root").getByRole("button", { name: "刷新专题", exact: true }).click();
  await expect(panel).toContainText("未获得可用警告数据，不能判断当前是否有警告");
  await expect(panel).not.toContainText("匹配 0 条");
  await expect.poll(() => context?.data.summary?.maritime).toEqual(maritime);
  await expect.poll(() => savedContext?.data.summary?.maritime).toEqual(maritime);
});

test("keeps undated news and earthquake records usable without calling them new publications", async ({ page }) => {
  test.skip(!shellOrigin, "Run against the local Desk stack");
  const now = new Date().toISOString();
  const payload = {
    timestamp: now, _done: 1, _total: 1,
    news_feed: { timestamp: now, items: [
      { title: "E2E 无日期新闻", feed_name: "Test News", published: null },
      { title: "E2E 仅有来源更新时间", feed_name: "Test News", published: null, updated: now, freshness: "fresh", collected_at: now },
    ] },
    earthquakes: { timestamp: now, collected_at: now, freshness: "stale", earthquakes: [
      { id: "undated", place: "E2E 无发生时间地震", magnitude: 6, latitude: 20, longitude: 60 },
    ] },
  };
  let context: Record<string, any> = {};
  page.on("request", (request) => {
    if (request.method() === "PUT" && new URL(request.url()).pathname === "/api/mods/global-situation/context") context = request.postDataJSON().context;
  });
  await page.route("**/api/global-intel/**", (route) => new URL(route.request().url()).pathname.endsWith("/stream")
    ? route.fulfill({ contentType: "text/event-stream", body: `data: ${JSON.stringify(payload)}\n\n` })
    : route.fulfill({ json: payload }));
  await page.route("**/api/crucix/snapshot", (route) => route.fulfill({ json: {
    news: [{ title: "E2E GDELT 收录记录", source: "GDELT", publishedAt: null, indexedAt: now }],
  } }));
  await page.goto(`${shellOrigin}/?mod=global-situation&workspace=e2e-news-time-${Date.now()}`);
  const list = page.locator(".intel-event-list");
  const news = list.getByRole("button", { name: /E2E 无日期新闻/ });
  await expect(news).toContainText("发布日期未知");
  await news.click();
  await expect.poll(() => context.data).toMatchObject({ freshness: "unknown", summary: { selectedEvent: { timestamp: "", timestampBasis: "unknown" } } });
  expect(context.data.asOf).toBeUndefined();
  await page.getByRole("button", { name: "关闭详情", exact: true }).click();
  const update = list.getByRole("button", { name: /E2E 仅有来源更新时间/ });
  await expect(update).toContainText("来源更新");
  await update.click();
  await expect(page.locator(".intel-detail-body dt").filter({ hasText: /^来源更新时间$/ })).toBeVisible();
  await expect.poll(() => context.data?.summary?.selectedEvent).toMatchObject({ timestamp: now, timestampBasis: "updated", updatedAt: now });
  await page.getByRole("button", { name: "关闭详情", exact: true }).click();
  const earthquake = list.getByRole("button", { name: /E2E 无发生时间地震/ });
  await expect(earthquake).toContainText("发生时间未知");
  await earthquake.click();
  await expect.poll(() => context.data).toMatchObject({ freshness: "stale", summary: { selectedEvent: { timestamp: "", timestampBasis: "unknown", collectedAt: now } } });
  await expect(page.locator(".intel-detail-drawer")).not.toContainText("Invalid Date");
  await page.getByRole("button", { name: "关闭详情", exact: true }).click();
  const indexed = list.getByRole("button", { name: /E2E GDELT 收录记录/ });
  await expect(indexed).toContainText("来源收录");
  await indexed.click();
  await expect.poll(() => context.data?.summary?.selectedEvent).toMatchObject({ timestampBasis: "indexed", timestamp: now });
  await page.screenshot({ path: "/tmp/newma-desk-news-time-verified.png", animations: "disabled" });
});
