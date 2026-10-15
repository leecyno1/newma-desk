import { expect, test } from "@playwright/test";
import type { LiquidityResearchData } from "../../modules/capital-flow/src/types";

const shell = "http://127.0.0.1:5888", api = "http://127.0.0.1:8911";

function fixture(): LiquidityResearchData {
  const points = Array.from({ length: 65 }, (_, i) => ({
    date: new Date(Date.UTC(2026, 7, 11 + i)).toISOString().slice(0, 10),
    dr007: i === 60 ? null : 1.3 + i / 1000, r007: 1.4 + i / 1000,
    shibor1w: 1.4, shibor3m: 1.5, spreadBp: i === 60 ? null : 10,
  }));
  const monthly = Array.from({ length: 12 }, (_, i) => ({
    month: new Date(Date.UTC(2025, 9 + i, 1)).toISOString().slice(0, 7),
    m1Yoy: 3 + i / 10, m2Yoy: 7, m2M1GapPp: 4 - i / 10,
    socialFlowYi: 35000, socialPriorYearYi: 36000, socialYoYDiffYi: -1000,
    socialStockWanYi: 468, socialStockYoy: 7.1,
  }));
  return { schemaVersion: "newma-desk.liquidity.v1", generatedAt: "2026-10-15T04:00:00Z",
    query: { dailyStart: "2026-03-09", dailyEnd: "2026-10-14", monthlyStart: "2024-07", monthlyEnd: "2026-09" },
    daily: { asOf: "2026-10-14", points, note: "观测日不是股票交易日历，分位不是风险概率",
      series: (["dr007", "r007", "shibor1w", "shibor3m", "spreadBp"] as const).map(id => ({
        id, name: id === "spreadBp" ? "R007 − DR007" : id.toUpperCase(), definition: "测试来源定义",
        value: points.at(-1)![id], unit: id === "spreadBp" ? "bp" : "%", asOf: "2026-10-14", ageDays: 1,
        current: true, change1Bp: 1, change5Bp: null, change20Bp: null, baselineSamples: 59, baselineExpected: 60, percentile: 10,
      })) },
    credit: { points: monthly, note: "月度是所属期不是发布日期；M1新旧口径不拼接",
      money: { ...monthly.at(-1), current: true, m1ChangePp: .1, m2ChangePp: 0, gapChangePp: -.1 },
      social: { ...monthly.at(-1), current: true, stockYoyChangePp: -.1, flow3mYi: 105000, flow3mPriorYearYi: 108000, flow3mYoYDiffYi: -3000 } },
    transmission: ["funding", "spread", "money", "credit"].map(id => ({ id, name: id === "credit" ? "信用扩张验证" : id, signal: id === "credit" ? "mixed" : "unknown",
      evidence: "测试观察样本", implication: "不形成预测结论", watch: "核查季节性与发布时间" })),
    feeds: ["dr007", "r007", "shibor", "money", "social"].map(id => ({ id, name: `Tushare ${id}`, url: "https://tushare.pro/document/2", status: "ready", reason: "", receivedAt: "2026-10-15T04:00:00Z", cached: false, usingSaved: false, count: 65, asOf: "2026-10-14" })),
    operations: { status: "unavailable", grossYi: null, maturitiesYi: null, netYi: null, url: "https://www.pbc.gov.cn", note: "缺少到期明细，不以投放冒充净投放" },
    notes: ["测试数据，不是真实样本"],
  };
}

test("流动性独立加载，图表窗口与Agent证据同步，缺值断线", async ({ page }) => {
  const contexts: any[] = [], baseRequests: string[] = [];
  page.on("request", request => {
    const path = new URL(request.url()).pathname;
    if (request.method() === "PUT" && path === "/api/mods/capital-liquidity/context") contexts.push(request.postDataJSON().context);
    if (path === "/api/capital-flow") baseRequests.push(path);
  });
  await page.route("**/api/capital-flow/liquidity-research**", route => route.fulfill({ json: fixture() }));
  await page.goto(`${shell}/?mod=capital-liquidity&workspace=liquidity-context-${Date.now()}`);
  const frame = page.frameLocator('iframe[title="流动性"]'), panel = frame.getByRole("region", { name: "流动性传导研究" });
  await expect(panel.getByRole("img", { name: "DR007、R007与SHIBOR3月历史" })).toBeVisible();
  await expect(panel.getByRole("img", { name: "DR007、R007与SHIBOR3月历史" })).toContainText("缺");
  await expect(panel).toContainText("增量 / 存量背离");
  await expect(panel).not.toContainText("5 日趋势基线");
  await expect.poll(() => contexts.at(-1)?.data.summary.page.liquidityResearch.daily.points.length).toBe(60);
  await panel.getByRole("button", { name: "20观测日", exact: true }).click();
  await panel.getByRole("button", { name: "分层利差", exact: true }).click();
  await expect(panel.getByRole("img", { name: "R007减DR007同日利差历史" })).toBeVisible();
  await expect.poll(() => contexts.at(-1)?.filters.liquidityChart).toBe("spread");
  expect(contexts.at(-1).filters.historyDays).toBe(20);
  expect(contexts.at(-1).data.summary.page.liquidityResearch.daily.points).toHaveLength(20);
  expect(contexts.at(-1).data.summary.page.liquidityResearch.credit.points).toHaveLength(12);
  expect(contexts.at(-1).data.summary.page.liquidityResearch.operations.netYi).toBeNull();
  expect(baseRequests).toHaveLength(0);
  await page.setViewportSize({ width: 390, height: 850 });
  expect(await frame.locator(".capital-root").evaluate(el => el.scrollWidth <= el.clientWidth + 1)).toBe(true);
});

test("流动性来源失败保留历史，页面与Agent均不宣称最新方向", async ({ page }) => {
  const data = fixture(), contexts: any[] = [];
  data.feeds.forEach(feed => Object.assign(feed, { status: "permission-denied", reason: "接口权限不足", usingSaved: true }));
  data.daily.series.forEach(row => { row.current = false; });
  data.credit.money.current = data.credit.social.current = false;
  data.transmission.forEach(row => { row.signal = "unknown"; });
  page.on("request", r => { if (r.method() === "PUT" && new URL(r.url()).pathname === "/api/mods/capital-liquidity/context") contexts.push(r.postDataJSON().context); });
  await page.route("**/api/capital-flow/liquidity-research**", route => route.fulfill({ json: data }));
  await page.goto(`${shell}/?mod=capital-liquidity&workspace=liquidity-saved-${Date.now()}`);
  const frame = page.frameLocator('iframe[title="流动性"]');
  await expect(frame.getByRole("region", { name: "流动性传导研究" })).toContainText("相关来源不参与当期方向判断");
  await expect(frame.getByLabel("投资传导提示").locator("summary")).toHaveCount(4);
  await expect.poll(() => contexts.at(-1)?.data.summary.loading).toBe(false);
  expect(contexts.at(-1).data.freshness).toBe("unknown");
  expect(contexts.at(-1).data.summary.page.liquidityResearch.feeds.every((feed: any) => feed.usingSaved)).toBe(true);
});

test("流动性整体请求失败后可以刷新重试，独立页可用", async ({ page }) => {
  let count = 0;
  await page.route("**/api/capital-flow/liquidity-research**", route => ++count === 1 ? route.fulfill({ status: 503 }) : route.fulfill({ json: fixture() }));
  await page.goto(`${api}/mod-runtime/capital-flow/?view=liquidity&mod=capital-liquidity`);
  await expect(page.getByRole("region", { name: "流动性传导研究" })).toContainText("流动性研究读取失败（503）");
  await page.getByRole("button", { name: "刷新", exact: true }).click();
  await expect(page.getByRole("img", { name: "M1与M2公布同比历史" })).toBeVisible();
  await expect(page.getByRole("region", { name: "流动性传导研究" })).not.toContainText("读取失败");
});

test("真实流动性：本地五来源、利率单位与页面展示一致", async ({ page, request }, info) => {
  const response = await request.get(`${api}/api/capital-flow/liquidity-research`);
  expect(response.ok()).toBe(true);
  const data: LiquidityResearchData = await response.json();
  expect(data.feeds).toHaveLength(5);
  const last = data.daily.points.at(-1)!;
  if (last.r007 != null && last.dr007 != null) expect(last.spreadBp).toBeCloseTo((last.r007 - last.dr007) * 100, 4);
  expect(data.operations.netYi).toBeNull();
  await page.setViewportSize({ width: 1440, height: 2200 });
  await page.goto(`${shell}/?mod=capital-liquidity&workspace=liquidity-live-${Date.now()}`);
  const frame = page.frameLocator('iframe[title="流动性"]');
  await expect(frame.getByRole("status")).not.toContainText("正在读取");
  const dr = data.daily.series.find(row => row.id === "dr007")!;
  await expect(frame.locator(".liquidity-pulse > div").first()).toContainText(dr.value == null ? "--" : dr.value.toLocaleString("zh-CN", { maximumFractionDigits: 4 }));
  await expect(frame.getByRole("region", { name: "流动性传导研究" })).toContainText("央行净投放：未接入完整明细");
  await frame.locator(".capital-root").screenshot({ path: info.outputPath("liquidity-live.png") });
});
