import { expect, test, type Page } from "@playwright/test";
import type { MacroMonitorFeed } from "../../bundled-runtimes/vibe-research/frontend/src/lib/api";
import type { CrucixSnapshot } from "../../bundled-runtimes/vibe-research/frontend/src/lib/crucix";

const shellOrigin = process.env.VIBE_E2E_DOMAIN_SUITES_ORIGIN;
const apiOrigin = process.env.VIBE_E2E_DOMAIN_SUITES_API_ORIGIN;
const generatedAt = "2026-09-09T01:00:00Z";
type MacroWindow = Window & { __macroMessages: Record<string, unknown>[] };

function macroFeed(days: number, freshness: "fresh" | "stale"): MacroMonitorFeed {
  const dimension = { label: "测试维度", signal: "neutral" as const, summary: "测试证据", evidenceIds: [] };
  const source = { id: "test", label: "测试公开源", url: "https://example.com/macro" };
  return {
    schemaVersion: "newma-desk.macro-monitor.v1", generatedAt,
    horizon: { start: "2026-09-09", end: "2026-10-09", days },
    regime: {
      overall: { label: `${days} 天宏观快照`, summary: "测试宏观状态", signals: [], evidenceIds: [] },
      growth: { ...dimension, label: "增长" }, inflation: { ...dimension, label: "价格" }, liquidity: { ...dimension, label: "流动性" },
      confidence: { level: "medium", score: 0.5, rationale: "测试" }, transmission: [], scenarios: [],
    },
    indicators: [{
      id: "test-indicator", name: "测试核心指标", region: "中国", category: "growth", unit: "%", period: "2026-08",
      releaseDate: "2026-09-09", value: 2.1, previous: 2, change: 0.1, forecast: null, direction: "higher", source,
      evidenceId: "test-evidence", asOf: generatedAt, freshness: { status: freshness },
      confidence: { level: "medium", score: 0.5, rationale: "测试" }, history: [],
    }],
    events: Array.from({ length: 49 }, (_, index) => ({
      id: `event-${index}`, date: "2026-09-10", time: "10:00", region: index < 7 ? "中国" : "美国", currency: null,
      title: `${days} 天事件 ${index}`, importance: index < 9 ? "high" : "low", status: "scheduled",
      actual: null, forecast: null, previous: null, source, evidenceId: `event-evidence-${index}`, asOf: generatedAt,
    })),
    sources: [{ id: "test", label: "测试公开源", status: "ok", count: 50, asOf: generatedAt }], gaps: [], disclaimer: "测试数据",
  };
}

const crucixSnapshot: CrucixSnapshot = {
  contract: "newma-desk.crucix-intelligence.v1", asOf: generatedAt,
  freshness: { status: "fresh", ageSeconds: 0, staleAfterSeconds: 900 },
  sourceHealth: { queried: 1, ok: 1, failed: 0, items: [{ source: "测试全球源", status: "ok" }] }, news: [],
  macro: { gscpi: { value: 0.3, date: "2026-08", period: "2026-08", interpretation: "测试",
    freshness: { status: "fresh", ageSeconds: 864000, staleAfterSeconds: 4320000 } },
    energy: { wti: 70, brent: null, naturalGas: null, crudeStocks: null, wtiRecent: [], signals: [], observations: [{
      id: "wti", label: "WTI现货", value: 70, kind: "spot", unit: "美元/桶", frequency: "daily",
      period: "2026-09-08", observedAt: null, note: "测试现货统计期",
      source: { id: "EIA", label: "美国能源信息署 EIA", seriesId: "RWTC", url: "https://www.eia.gov/" },
      freshness: { status: "fresh", ageSeconds: 86400, staleAfterSeconds: 604800 },
    }] } },
  provenance: { project: "test", license: "test", mode: "test" },
};

async function setupMacro(page: Page, initiallyFailed = false) {
  const state = { failMacro: initiallyFailed, failCrucix: initiallyFailed, freshness: "stale" as "fresh" | "stale",
    macroCalls: 0, crucixCalls: 0, waitFor14: undefined as Promise<void> | undefined };
  await page.addInitScript(() => {
    (window as MacroWindow).__macroMessages = [];
    window.addEventListener("message", (event) => {
      if (event.data?.modId === "macro-monitor") (window as MacroWindow).__macroMessages.push(event.data);
    });
  });
  await page.route("**/api/research/macro-monitor?*", async (route) => {
    state.macroCalls += 1;
    const days = Number(new URL(route.request().url()).searchParams.get("days"));
    if (days === 14) await state.waitFor14;
    return state.failMacro
      ? route.fulfill({ status: 503, json: { detail: "测试宏观源暂不可用" } })
      : route.fulfill({ json: { data: macroFeed(days, state.freshness) } });
  });
  await page.route("**/api/crucix/snapshot", (route) => {
    state.crucixCalls += 1;
    return state.failCrucix
      ? route.fulfill({ status: 503, json: { detail: "测试全球源暂不可用" } })
      : route.fulfill({ json: crucixSnapshot });
  });
  await page.goto(`${shellOrigin}/?mod=macro-monitor&workspace=e2e-macro-${Date.now()}`);
  const frame = page.frameLocator('iframe[title="宏观观察"]');
  await expect(frame.getByLabel("日历范围")).toBeVisible();
  await expect.poll(() => readContext(page)).toMatchObject({ data: { summary: { loading: false } } });
  return { frame, state };
}

const readContext = (page: Page) => page.evaluate(() =>
  (window as MacroWindow).__macroMessages.filter((message) => message.type === "vibedesk:context").at(-1)?.context,
);

async function sendBridgeRequest(page: Page, requestId: string, action = false) {
  const child = page.frames().find((frame) => frame.url().includes("/mod-runtime/research/macro-monitor"))!;
  const instanceId = await child.evaluate(() =>
    (window as MacroWindow).__macroMessages.find((message) => message.type === "vibedesk:init")?.instanceId,
  );
  await page.evaluate(({ instanceId, requestId, action }) => {
    const element = document.querySelector<HTMLIFrameElement>('iframe[title="宏观观察"]')!;
    element.contentWindow!.postMessage({
      type: action ? "vibedesk:ui-action-request" : "vibedesk:context-request", modId: "macro-monitor", instanceId, requestId,
      ...(action ? { actionId: "macro.refresh", input: {} } : { reason: "agent" }),
    }, new URL(element.src).origin);
  }, { instanceId, requestId, action });
  return () => page.evaluate((requestId) =>
    (window as MacroWindow).__macroMessages.find((message) => message.requestId === requestId), requestId,
  );
}

test.describe("Macro Monitor current-page evidence", () => {
  test.skip(!shellOrigin || !apiOrigin, "Run with playwright.domain-suites.config.ts against the local Desk stack");

  test("keeps CPI statistical month, calculation and revision caveat aligned with Agent context", async ({ page }) => {
    const { frame } = await setupMacro(page);
    const feed = macroFeed(7, "fresh");
    const source = {
      id: "fred-cpi", label: "FRED · BLS CPI-U", url: "https://fred.stlouisfed.org/series/CPIAUCNS",
      seriesId: "CPIAUCNS", originalSource: "美国劳工统计局 BLS", originalSeriesId: "CUUR0000SA0",
      seasonalAdjustment: "not-seasonally-adjusted",
      calculation: "同月指数比上年同月指数减 1，四舍五入至 0.1 个百分点",
      fallbackReason: "使用 FRED 转发的 BLS CPI-U 全项目未经季调指数计算同比；不是独立调查。",
    };
    feed.indicators[0] = {
      ...feed.indicators[0], id: "us-cpi-yoy", name: "美国 CPI 同比（CPI-U，未经季调）",
      region: "US", category: "inflation", period: "2026-08", releaseDate: null,
      dateBasis: "period", revisionStatus: "not-tracked", value: 3.4, previous: 3.3,
      evidenceId: "macro:us-cpi-yoy:fred:2026-08", source,
    };
    await page.route("**/api/research/macro-monitor?*", (route) => route.fulfill({ json: { data: feed } }));
    await frame.getByRole("button", { name: "刷新", exact: true }).click();
    await expect(frame.getByText("美国 CPI 同比（CPI-U，未经季调）", { exact: true })).toBeVisible();
    await expect(frame.getByText("数据期 2026-08", { exact: true })).toBeVisible();
    await expect(frame.getByText("发布日期未核实", { exact: true })).toBeVisible();
    await expect(frame.getByText("历史修订未跟踪", { exact: true })).toBeVisible();
    await expect(frame.getByText("发布 2026-08", { exact: true })).toHaveCount(0);
    await frame.getByText("来源说明", { exact: true }).click();
    await expect(frame.getByText("原始统计：美国劳工统计局 BLS · CUUR0000SA0；当前序列：CPIAUCNS。", { exact: true })).toBeVisible();
    await expect(frame.getByText(`计算：${source.calculation}。`, { exact: true })).toBeVisible();
    await expect.poll(() => readContext(page)).toMatchObject({ data: { summary: {
      indicators: [{ id: "us-cpi-yoy", period: "2026-08", releaseDate: null,
        dateBasis: "period", revisionStatus: "not-tracked", source }],
    } } });
  });

  for (const provider of ["bls", "fred"] as const) {
    test(`keeps ${provider} monthly observations and provenance aligned in UI and Agent context`, async ({ page }) => {
      const { frame } = await setupMacro(page);
      const feed = macroFeed(7, "fresh");
      const source = provider === "bls"
        ? { id: "bls-unemployment", label: "美国劳工统计局 BLS", url: "https://data.bls.gov/timeseries/LNS14000000", seriesId: "LNS14000000" }
        : { id: "fred-unemployment", label: "FRED · BLS 失业率", url: "https://fred.stlouisfed.org/series/UNRATE", seriesId: "UNRATE",
          originalSource: "美国劳工统计局 BLS", originalSeriesId: "LNS14000000",
          fallbackReason: "Tushare 与 BLS 直连均未取得有效期内的数据，使用 FRED 转发的同口径 U-3 季调月度序列；不是独立调查。" };
      feed.indicators[0] = {
        ...feed.indicators[0], id: "us-unemployment-rate", name: "美国失业率（U-3，季调）",
        region: "US", category: "labour", period: "2026-08", releaseDate: null, dateBasis: "period",
        value: 4.1, previous: 4.1, change: 0, evidenceId: `macro:us-unemployment-rate:${provider}:2026-08`, source,
      };
      await page.route("**/api/research/macro-monitor?*", (route) => route.fulfill({ json: { data: feed } }));
      await frame.getByRole("button", { name: "刷新", exact: true }).click();
      await expect(frame.getByText("美国失业率（U-3，季调）", { exact: true })).toBeVisible();
      await expect(frame.getByText("数据期 2026-08", { exact: true })).toBeVisible();
      await expect(frame.getByText("发布 2026-08", { exact: true })).toHaveCount(0);
      await expect(frame.getByRole("link", { name: source.label })).toHaveAttribute("href", source.url);
      if (provider === "fred") {
        await frame.getByText("来源说明", { exact: true }).click();
        await expect(frame.getByText("原始统计：美国劳工统计局 BLS · LNS14000000；当前序列：UNRATE。", { exact: true })).toBeVisible();
        await expect(frame.getByText(source.fallbackReason!, { exact: true })).toBeVisible();
      } else {
        await expect(frame.getByText("来源说明", { exact: true })).toHaveCount(0);
      }
      await expect.poll(() => readContext(page)).toMatchObject({ data: { summary: {
        loading: false, indicators: [{ id: "us-unemployment-rate", value: 4.1, period: "2026-08",
          releaseDate: null, dateBasis: "period", source }],
      } } });
    });
  }

  test("keeps calendar filters, full counts and data freshness aligned", async ({ page }) => {
    const { frame } = await setupMacro(page);
    await expect.poll(() => readContext(page)).toMatchObject({
      data: { asOf: generatedAt, freshness: "stale", summary: { totalMatchingEvents: 49, highImportanceEventCount: 9, eventsTruncated: true } },
    });
    await expect(frame.getByText("高重要性事件", { exact: true }).locator("..").locator("strong")).toHaveText("9");
    await frame.getByLabel("地区", { exact: true }).selectOption("US");
    await frame.getByLabel("重要性", { exact: true }).selectOption("high");
    await expect.poll(() => readContext(page)).toMatchObject({
      filters: { region: "US", importance: "high", horizonDays: 7 },
      data: { summary: { totalMatchingEvents: 2, highImportanceEventCount: 2, eventsTruncated: false,
        upcomingEvents: [{ id: "event-7" }, { id: "event-8" }], indicators: [{ id: "test-indicator" }] } },
    });
    await frame.getByLabel("地区", { exact: true }).selectOption("EU");
    await expect(frame.getByText("当前筛选范围暂无已收录事件，不代表没有经济事件。", { exact: true })).toBeVisible();
    await expect.poll(() => readContext(page)).toMatchObject({ data: { summary: { totalMatchingEvents: 0, upcomingEvents: [] } } });
  });

  test("shows adoption evidence without a fabricated liquidity forecast and expands the calendar", async ({ page }) => {
    const { frame } = await setupMacro(page);
    const feed = macroFeed(7, "fresh");
    feed.decisionReview = {
      adoption: "可采纳为待核验研究假设", thesis: "增长分化", scope: "仅供复核，不推出仓位",
      supportingEvidence: [{ dimension: "增长", signal: "mixed", summary: "指标分化", evidenceIds: ["test-evidence"] }],
      counterEvidence: ["价格与增长不同步"], checks: ["核对官方原文"],
      nextReviewEvents: [{ id: "event-0", date: "2026-09-10", title: "测试发布", importance: "high", evidenceId: "event-evidence-0" }],
    };
    feed.liquidity = { groups: [], indicators: [], assessment: {
      signal: "mixed", complete: true, supportiveCount: 1, restrictiveCount: 1, observedCount: 2,
      method: "只比较有效观测，不外推", items: [],
    }, coverage: { available: 0, total: 9, asOf: null }, source: "测试源", note: "无预测" };
    await page.route("**/api/research/macro-monitor?*", (route) => route.fulfill({ json: { data: feed } }));
    await frame.getByRole("button", { name: "刷新", exact: true }).click();
    await expect(frame.getByLabel("投资决策证据")).toContainText("采纳意见：可采纳为待核验研究假设");
    await expect(frame.getByLabel("投资决策证据")).toContainText("价格与增长不同步");
    await expect(frame.getByText("2 项有效观测参与方向评估 · 非预测")).toBeVisible();
    await expect(frame.getByText("5 日趋势基线")).toHaveCount(0);
    await expect.poll(() => readContext(page)).toMatchObject({ data: { summary: {
      decisionReview: { adoption: "可采纳为待核验研究假设" },
      liquidity: { assessment: { observedCount: 2 } },
      totalMatchingEvents: 49, visibleEventCount: 12, eventsTruncated: true,
    } } });
    await frame.getByRole("button", { name: /再显示 20 项/ }).click();
    await expect.poll(() => readContext(page)).toMatchObject({ data: { summary: { visibleEventCount: 32 } } });
    await expect(frame.getByText("7 天事件 30", { exact: true })).toBeVisible();
  });

  test("shows partial-only collection and every failure reason without a healthy badge", async ({ page }) => {
    const { frame, state } = await setupMacro(page);
    state.freshness = "fresh";
    const snapshot = structuredClone(crucixSnapshot);
    snapshot.sourceHealth = { queried: 3, ok: 1, failed: 0, partial: 1, stale: 0, unknown: 1, items: [
      { source: "EIA", status: "ok", reason: "采集完成" },
      { source: "YFinance", status: "partial", reason: "仅部分数据可用（1/15）" },
      { source: "Maritime", status: "unknown", reason: "尚未采集船舶位置" },
    ] };
    await page.route("**/api/crucix/snapshot", route => route.fulfill({ json: snapshot }));
    await frame.getByRole("button", { name: "刷新", exact: true }).click();
    const health = frame.getByLabel("Crucix 来源健康", { exact: true });
    await expect(health).toContainText("1/3");
    await expect(health).toContainText("部分降级");
    await expect(health).toContainText("0 不可用 · 1 部分可用 · 0 陈旧 · 1 待核验");
    await health.getByText("全部来源明细（3）", { exact: true }).click();
    await expect(health.getByText("尚未采集船舶位置", { exact: true })).toBeVisible();
    await expect.poll(() => readContext(page)).toMatchObject({ data: { freshness: "unknown", summary: {
      degraded: true, crucix: { sourceHealth: snapshot.sourceHealth },
    } } });
    snapshot.sourceHealth = { queried: 3, ok: 0, failed: 3, partial: 0, stale: 0, unknown: 0, items: [
      { source: "EIA", status: "error", reason: "来源请求超时" },
      { source: "YFinance", status: "error", reason: "未取得有效数据（0/15）" },
      { source: "FRED", status: "error", reason: "未配置来源凭据" },
    ] };
    await frame.getByRole("button", { name: "刷新", exact: true }).click();
    await expect(health).toContainText("0/3");
    await expect(health.getByText("来源请求超时", { exact: true })).toBeVisible();
    await expect(health.getByText("未配置来源凭据", { exact: true })).toBeVisible();
    await expect.poll(() => readContext(page)).toMatchObject({ data: { summary: {
      degraded: true, crucix: { sourceHealth: snapshot.sourceHealth },
    } } });
  });

  test("keeps public energy provenance, stale dates and inventory units aligned with Agent context", async ({ page }) => {
    const { frame } = await setupMacro(page);
    const snapshot = structuredClone(crucixSnapshot);
    const source = { id: "FRED-public", label: "FRED · EIA", seriesId: "DCOILWTICO", collectorId: "EIA",
      url: "https://fred.stlouisfed.org/series/DCOILWTICO", originalSource: "美国能源信息署 EIA", originalSeriesId: "RWTC",
      originalUrl: "https://www.eia.gov/", fallbackReason: "未配置 EIA API Key，改用同口径公开数据。" };
    snapshot.macro.energy.observations = [{
      ...snapshot.macro.energy.observations![0], value: 91.48, period: "2026-09-01", source,
      note: "FRED 转发 EIA 日度现货统计，不是期货。",
      freshness: { status: "stale", ageSeconds: 777600, staleAfterSeconds: 604800 },
    }, {
      id: "crudeStocks", label: "美国商业原油库存（不含战略储备）", value: 424460, kind: "inventory", frequency: "weekly",
      unit: "千桶", period: "2026-08-28", observedAt: null, note: "EIA 周报表 4：百万桶 × 1000 转为千桶。",
      source: { id: "EIA", label: "EIA 公开周报", seriesId: "WCESTUS1", url: "https://ir.eia.gov/wpsr/table4.csv" },
      freshness: { status: "fresh", ageSeconds: 1123200, staleAfterSeconds: 1209600 },
    }];
    await page.route("**/api/crucix/snapshot", route => route.fulfill({ json: snapshot }));
    await frame.getByRole("button", { name: "刷新", exact: true }).click();
    const evidence = frame.getByLabel("全球供应链与能源旁证", { exact: true });
    const oil = evidence.getByLabel("WTI现货", { exact: true });
    await expect(oil).toContainText("91.48");
    await expect(oil).toContainText("数据期 2026-09-01");
    await expect(oil).toContainText("更新滞后");
    await expect(oil.getByRole("link")).toHaveAttribute("href", source.url);
    await expect(evidence.getByLabel("美国商业原油库存（不含战略储备）")).toContainText("千桶");
    await evidence.getByText("报价口径与缺口", { exact: true }).click();
    await expect(evidence.getByText(source.fallbackReason, { exact: true })).toBeVisible();
    await expect(evidence.getByText("原始统计：美国能源信息署 EIA · RWTC；当前序列：DCOILWTICO。", { exact: true })).toBeVisible();
    await expect.poll(() => readContext(page)).toMatchObject({ data: { summary: { crucix: { energy: { observations: [
      { value: 91.48, kind: "spot", period: "2026-09-01", source, freshness: { status: "stale" } },
      { value: 424460, kind: "inventory", unit: "千桶", period: "2026-08-28" },
    ] } } } } });
  });

  test("does not let a fresh sweep hide stale months or relabel futures as EIA spot prices", async ({ page }) => {
    const { frame, state } = await setupMacro(page);
    state.freshness = "fresh";
    const snapshot = structuredClone(crucixSnapshot);
    snapshot.macro.gscpi = { ...snapshot.macro.gscpi!, date: "2025-08", period: "2025-08",
      freshness: { status: "stale", ageSeconds: 32572800, staleAfterSeconds: 4320000 } };
    snapshot.macro.energy.observations = [{
      id: "wti", label: "WTI期货", value: 72, kind: "futures", unit: "美元/桶", frequency: "quote",
      period: null, observedAt: "2026-09-09T18:00:00Z", note: "期货公开报价，可能延迟；不是 EIA 现货价。",
      source: { id: "YFinance", label: "Yahoo Finance", seriesId: "CL=F", url: "https://finance.yahoo.com/quote/CL%3DF/" },
      freshness: { status: "fresh", ageSeconds: 21600, staleAfterSeconds: 259200 },
    }];
    await page.route("**/api/crucix/snapshot", route => route.fulfill({ json: snapshot }));
    await frame.getByRole("button", { name: "刷新", exact: true }).click();
    const evidence = frame.getByLabel("全球供应链与能源旁证", { exact: true });
    await expect(evidence.getByText("数据期 2025-08 · 标准差 · 更新滞后", { exact: true })).toBeVisible();
    const oil = evidence.getByLabel("WTI期货", { exact: true });
    await expect(oil).toContainText("72.00");
    await expect(oil).toContainText("报价 2026-09-09T18:00:00Z");
    await expect(oil.getByRole("link")).toHaveText("Yahoo Finance · CL=F");
    await expect(evidence.getByText("EIA 等公开源", { exact: true })).toHaveCount(0);
    await expect.poll(() => readContext(page)).toMatchObject({ data: { freshness: "stale", summary: { crucix: {
      freshness: { status: "fresh" }, gscpi: { period: "2025-08", freshness: { status: "stale" } },
      energy: { observations: [{ kind: "futures", value: 72, observedAt: "2026-09-09T18:00:00Z", source: { seriesId: "CL=F" } }] },
    } } } });
    snapshot.macro.gscpi = structuredClone(crucixSnapshot.macro.gscpi);
    delete snapshot.macro.energy.observations;
    await frame.getByRole("button", { name: "刷新", exact: true }).click();
    const legacy = evidence.getByLabel("WTI（口径待核验）", { exact: true });
    await expect(legacy).toContainText("单位待核验");
    await expect(legacy).toContainText("数据时间未知");
    await expect.poll(() => readContext(page)).toMatchObject({ data: { freshness: "unknown", summary: { crucix: {
      energy: { observations: expect.arrayContaining([expect.objectContaining({ id: "wti", kind: "unknown", source: null,
        freshness: expect.objectContaining({ status: "unknown" }) })]) },
    } } } });
  });

  for (const partial of [false, true]) {
    test(`shows ${partial ? "missing" : "queried"} calendar dates and unrated events consistently to the Agent`, async ({ page }) => {
      const { frame } = await setupMacro(page);
      const feed = macroFeed(30, "fresh");
      feed.events = [{ ...feed.events[0], title: "美国测试 CPI", region: "美国", importance: "unknown",
        previous: 4.1, previousText: "4.1%", forecast: 4.2, forecastText: "4.2%" }];
      feed.calendarCoverage = {
        sourceId: "tushare-economic-calendar", start: "2026-09-09", end: "2026-10-09",
        requestedDays: 31, queriedDays: partial ? 30 : 31, eventDays: 1,
        status: partial ? "partial" : "queried", missingDates: partial ? ["2026-10-09"] : [],
        emptyDates: ["2026-09-09"], note: "已查询来源日程，不保证收录全部事件。",
      };
      await page.route("**/api/research/macro-monitor?*", (route) => route.fulfill({ json: { data: feed } }));
      await frame.getByLabel("日历范围").selectOption("30");
      await expect(frame.getByLabel("经济日历覆盖")).toContainText(`已查询 ${partial ? 30 : 31}/31 日（含今天）`);
      await expect(frame.getByText("前值 4.1% · 预期 4.2% · 公布 —", { exact: true })).toBeVisible();
      await expect(frame.getByText("待评级", { exact: true })).toBeVisible();
      await expect.poll(() => readContext(page)).toMatchObject({ data: { summary: {
        calendarCoverage: feed.calendarCoverage, unratedEventCount: 1, highImportanceEventCount: 0,
        upcomingEvents: [{ importance: "unknown", forecast: 4.2, forecastText: "4.2%" }],
      } } });
      if (partial) {
        await frame.getByText("未覆盖 1 日，不能判定为空日程", { exact: true }).click();
        await expect(frame.getByLabel("经济日历覆盖").getByText("2026-10-09", { exact: true })).toBeVisible();
      }
      await frame.getByLabel("重要性", { exact: true }).selectOption("unknown");
      await expect(frame.getByText("美国测试 CPI", { exact: true })).toBeVisible();
      await frame.getByLabel("重要性", { exact: true }).selectOption("low");
      await expect(frame.getByText(partial ? "已查询范围暂无匹配事件；未覆盖日期不能判定为空。" : "当前筛选范围暂无已收录事件，不代表没有经济事件。", { exact: true })).toBeVisible();
    });
  }

  test("exposes merged records, rating reasons and conflicts consistently to the Agent", async ({ page }) => {
    const { frame } = await setupMacro(page);
    const feed = macroFeed(7, "fresh");
    const record = { ...feed.events[0], title: "美国失业率", region: "美国", status: "released" as const,
      importance: "high" as const, actual: 4.2, actualText: "4.2%", forecast: 4.1, forecastText: "4.1%",
      importanceBasis: { kind: "rule" as const, ruleId: "employment", version: "1", reason: "就业与失业率发布，建议优先关注" } };
    feed.events = [{ ...record, recordCount: 2, conflictFields: ["actual"],
      records: [record, { ...record, title: "美国失业率(%)", actual: 4.3, actualText: "4.3%" }] }];
    await page.route("**/api/research/macro-monitor?*", (route) => route.fulfill({ json: { data: feed } }));
    await frame.getByRole("button", { name: "刷新", exact: true }).click();
    await expect(frame.getByText("当前筛选 1 项事件 · 已展示 1 项 · 2 条来源记录 · 合并 1 条重复记录", { exact: true })).toBeVisible();
    await expect(frame.getByText("规则建议 高", { exact: true }).last()).toBeVisible();
    await expect(frame.getByText("前值 — · 预期 4.1% · 公布 待核验", { exact: true }).last()).toBeVisible();
    await expect(frame.getByText(/较预期 \+/)).toHaveCount(0);
    const details = frame.locator("details").last();
    await details.locator("summary").click();
    await expect(details).toContainText("记录有分歧，待核验");
    await expect(details).toContainText("Desk 规则建议，非来源或官方评级");
    await expect(details.getByText("美国失业率(%)", { exact: true })).toBeVisible();
    await expect.poll(() => readContext(page)).toMatchObject({ data: { summary: {
      totalMatchingEvents: 1, rawRecordCount: 2, ruleRatedEventCount: 1, conflictingEventCount: 1,
      upcomingEvents: [{ recordCount: 2, conflictFields: ["actual"], importanceBasis: record.importanceBasis,
        records: [{ actualText: "4.2%" }, { actualText: "4.3%" }] }],
    } } });
    await frame.getByLabel("重要性", { exact: true }).selectOption("unknown");
    await expect.poll(() => readContext(page)).toMatchObject({ data: { summary: { totalMatchingEvents: 0, rawRecordCount: 0, ruleRatedEventCount: 0 } } });
  });

  test("separates regional filters and preserves source time meaning in Agent context", async ({ page }) => {
    const { frame } = await setupMacro(page);
    const feed = macroFeed(7, "fresh");
    const base = { ...feed.events[0], importance: "unknown" as const,
      timeBasis: { kind: "unconfirmed" as const, timeZone: null, timestamp: null, note: "来源时刻，时区未注明" } };
    feed.events = [
      { ...base, id: "mainland", title: "中国内地测试事件", region: "中国", regionCode: "CN", regionGroup: "CN" },
      { ...base, id: "hongkong", title: "中国香港测试事件", region: "中国香港", regionCode: "HK", regionGroup: "HK",
        time: "09:30", timeBasis: { kind: "explicit-offset", timeZone: "UTC+08:00", timestamp: "2026-09-10T09:30:00+08:00", note: "保留来源显式偏移" } },
      { ...base, id: "britain", title: "英国测试事件", region: "英国", regionCode: "GB", regionGroup: "EU" },
      { ...base, id: "disputed", title: "以色列消费者信心测试", region: "地区待核验", regionCode: null, regionGroup: "UNKNOWN",
        regionBasis: { kind: "conflict", titleRegion: "以色列", reportedRegion: "西班牙", reason: "标题与来源地区不一致，等待核验" } },
    ];
    await page.route("**/api/research/macro-monitor?*", (route) => route.fulfill({ json: { data: feed } }));
    await frame.getByRole("button", { name: "刷新", exact: true }).click();
    await expect(frame.getByLabel("日历口径提示")).toContainText("3 项时区未注明");
    await expect(frame.getByLabel("日历口径提示")).toContainText("1 项地区缺失或冲突");
    await frame.getByLabel("地区", { exact: true }).selectOption("CN");
    await expect(frame.getByText("中国内地测试事件", { exact: true })).toBeVisible();
    await expect(frame.getByText("中国香港测试事件", { exact: true })).toHaveCount(0);
    await frame.getByLabel("地区", { exact: true }).selectOption("HK");
    await expect(frame.getByText("UTC+08:00", { exact: true })).toBeVisible();
    await expect.poll(() => readContext(page)).toMatchObject({ filters: { region: "HK" }, data: { summary: {
      totalMatchingEvents: 1, unconfirmedTimeZoneEventCount: 0,
      upcomingEvents: [{ regionCode: "HK", time: "09:30", timeBasis: { timestamp: "2026-09-10T09:30:00+08:00" } }],
    } } });
    await frame.getByLabel("地区", { exact: true }).selectOption("EU");
    await expect(frame.getByText("英国测试事件", { exact: true })).toBeVisible();
    await frame.getByLabel("地区", { exact: true }).selectOption("UNKNOWN");
    await frame.getByText("地区核验依据", { exact: true }).click();
    await expect(frame.getByText(/标题地区：以色列 · 来源地区：西班牙/)).toBeVisible();
    await expect.poll(() => readContext(page)).toMatchObject({ data: { summary: {
      totalMatchingEvents: 1, unresolvedRegionEventCount: 1, unconfirmedTimeZoneEventCount: 1,
      upcomingEvents: [{ regionGroup: "UNKNOWN", regionBasis: { kind: "conflict" }, timeBasis: { timestamp: null } }],
    } } });
  });

  test("ignores late responses from a previous calendar range", async ({ page }) => {
    const { frame, state } = await setupMacro(page);
    let release14!: () => void;
    state.waitFor14 = new Promise<void>((resolve) => { release14 = resolve; });
    const pending14 = page.waitForRequest((request) => request.url().includes("/macro-monitor?days=14"));
    await frame.getByLabel("日历范围").selectOption("14");
    await pending14;
    await expect.poll(() => readContext(page)).toMatchObject({ filters: { horizonDays: 14 }, data: { summary: { loading: true, horizon: null } } });
    await frame.getByLabel("日历范围").selectOption("30");
    await expect(frame.getByRole("heading", { name: "30 天宏观快照" })).toBeVisible();
    await expect(frame.getByRole("heading", { name: "未来经济事件" })).toBeVisible();
    const finished14 = page.waitForResponse((response) => response.url().includes("/macro-monitor?days=14"));
    release14();
    await (await finished14).finished();
    const child = page.frames().find((item) => item.url().includes("/mod-runtime/research/macro-monitor"))!;
    await child.evaluate(() => new Promise<void>((resolve) => requestAnimationFrame(() => requestAnimationFrame(() => resolve()))));
    const result = await sendBridgeRequest(page, "after-late-response");
    await expect.poll(result).toMatchObject({ context: { filters: { horizonDays: 30 }, data: { summary: { horizon: { days: 30 }, loading: false } } } });
    await expect(frame.getByRole("heading", { name: "30 天宏观快照" })).toBeVisible();
    await expect(frame.getByRole("heading", { name: "14 天宏观快照" })).toHaveCount(0);
  });

  test("refreshes through the Agent bridge and reports unavailable or retained evidence honestly", async ({ page, request }) => {
    const mods = await (await request.get(`${apiOrigin}/api/mods`)).json();
    expect(mods.find((mod: { moduleId: string }) => mod.moduleId === "macro-monitor").manifest.actions["macro.refresh"])
      .toMatchObject({ binding: { type: "local" } });
    const { frame, state } = await setupMacro(page, true);
    await expect.poll(() => readContext(page)).toMatchObject({ data: { freshness: "unknown", summary: { degraded: true, indicators: [], crucix: null } } });
    const empty = await readContext(page) as { data: { asOf?: string } };
    expect(empty.data.asOf).toBeUndefined();
    await expect(frame.getByText("经济事件数据暂不可用，请刷新重试。", { exact: true })).toBeVisible();
    state.failMacro = false;
    state.failCrucix = false;
    state.freshness = "fresh";
    const before = { macro: state.macroCalls, crucix: state.crucixCalls };
    const result = await sendBridgeRequest(page, "macro-refresh-start", true);
    await expect.poll(result).toMatchObject({ type: "vibedesk:ui-action-result", ok: true, result: { status: "running", horizonDays: 7 } });
    await expect.poll(() => readContext(page)).toMatchObject({ data: { freshness: "fresh", asOf: generatedAt, summary: { loading: false, degraded: false } } });
    expect(state.macroCalls).toBeGreaterThan(before.macro);
    expect(state.crucixCalls).toBeGreaterThan(before.crucix);
    state.failMacro = true;
    state.failCrucix = true;
    await frame.getByRole("button", { name: "刷新", exact: true }).click();
    await expect.poll(() => readContext(page)).toMatchObject({ data: { freshness: "stale", asOf: generatedAt,
      summary: { error: "更新失败，当前为上次数据", crucixError: "测试全球源暂不可用", loading: false, indicators: [{ id: "test-indicator" }], crucix: { asOf: generatedAt } } } });
    await expect(frame.getByRole("heading", { name: "7 天宏观快照" })).toBeVisible();
    await expect(frame.getByRole("alert")).toContainText("全球旁证更新失败，保留上次数据");
  });
});
