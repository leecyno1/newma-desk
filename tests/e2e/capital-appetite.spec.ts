import { expect, test } from "@playwright/test";
import type { AppetiteResearchData, AppetiteWindow, ConnectResearchData, ConnectResearchWindow, SectorResearchData } from "../../modules/capital-flow/src/types";

const shell = "http://127.0.0.1:5888", api = "http://127.0.0.1:8911";
test.beforeEach(async ({ page }, info) => {
  if (!info.title.startsWith("真实")) await page.route("**/api/capital-flow/connect-research**", route => route.fulfill({ status: 503 }));
});

function connectFixture(): ConnectResearchData {
  const window = (days: number, south: boolean): ConnectResearchWindow => ({
    direction: south ? "southbound" : "northbound", days, currency: south ? "HKD" : "CNY", unit: south ? "港元亿元" : "人民币亿元",
    current: true, start: days === 5 ? "2026-10-08" : south ? "2026-09-16" : "2026-09-09", asOf: "2026-10-14",
    available: days, closedDays: [], missingDates: [], points: [],
    summary: { turnoverYi: days * 100, buyYi: south ? days * 60 : null, sellYi: south ? days * 40 : null,
      netBuyYi: south ? days * 20 : null, positiveDays: south ? days : null, streakDays: south ? days : null,
      streakDirection: south ? "buy" : "unavailable", streakCensored: south, prior20MeanTurnoverYi: 100, latestVsPrior20: 1 },
    momentum: { days: 5, current: true, missingDates: [], netChangeYi: south ? 20 : null, intensityChangePp: south ? 4 : null, turnoverRatio: 1,
      recent: { start: "2026-10-08", end: "2026-10-14", available: 5, current: true, turnoverYi: 500, netBuyYi: south ? 100 : null, netIntensityPct: south ? 20 : null },
      previous: { start: "2026-09-23", end: "2026-09-29", available: 5, current: true, turnoverYi: 500, netBuyYi: south ? 80 : null, netIntensityPct: south ? 16 : null } },
  });
  return { generatedAt: "2026-10-15T04:00:00Z", cutoff: "2026-10-14", source: "测试HKEX", completed: 33, expected: 33, remaining: 0,
    failedDates: [], canContinue: false, notes: ["测试来源，币种不相加"],
    windows: { "5": { northbound: window(5, false), southbound: window(5, true) }, "20": { northbound: window(20, false), southbound: window(20, true) } } };
}

function fixture(): AppetiteResearchData {
  const window = (days: number): AppetiteWindow => ({ days, start: days === 5 ? "2026-10-08" : "2026-09-09", end: "2026-10-14",
    evidence: ["price", "etf", "margin", "dr007", "spreadBp", "credit"].map((id, i) => ({ id, name: ["沪深300区间涨跌", "宽基ETF申赎估算", "沪深北融资净增加", "DR007成本变化", "利差变化", "近3月社融同比多增"][i],
      value: id === "credit" ? -6000 : days === 5 ? -3.21 : -7.48, unit: i === 0 ? "%" : i < 3 || i === 5 ? "亿元" : "bp", current: true,
      asOf: i === 5 ? "2026-09" : "2026-10-14", scope: i === 5 ? "3个月" : `${days}${i < 3 ? "交易日" : "观测日"}`, source: "测试来源", note: "测试数据，不代表真实行情" })),
    etfs: ["510300.SH", "510500.SH", "159915.SZ"].map(code => ({ code, name: code, value: days, current: true, asOf: "2026-10-14", note: "份额变化×净值" })),
    relationships: [{ id: "price-etf", inputs: ["price", "etf"], status: "aligned", title: "价格回落、宽基配置净赎回", watch: "核查份额公告" },
      { id: "price-margin", inputs: ["price", "margin"], status: "aligned", title: "价格回落、融资净减少", watch: "不等于账户风险" }],
    conditions: { id: "cost-spread", inputs: ["dr007", "spreadBp"], status: "aligned", title: "成本与分层利差同时下降", watch: "独立解读" },
    verifiedRelationships: 2, divergences: 0 });
  return { schemaVersion: "newma-desk.appetite.v1", generatedAt: "2026-10-15T04:00:00Z", expectedDate: "2026-10-14",
    windows: { "5": window(5), "20": window(20) },
    leverage: { status: "ready", source: "测试融资", sourceNote: "", fetchStatus: "ready", usingSaved: false, receivedAt: "2026-10-15T04:00:00Z",
      asOf: "2026-10-14", expectedDate: "2026-10-14", currency: "CNY", unit: "亿元", scope: ["SSE", "SZSE", "BSE"], note: "不混加不同口径",
      latest: { balanceYi: 25000, buyYi: 1000, repayYi: 1100, netYi: -100 },
      points: Array.from({ length: 60 }, (_, i) => ({ date: new Date(Date.UTC(2026, 7, 16 + i)).toISOString().slice(0, 10), balanceYi: 25000, buyYi: 1000, repayYi: 1100, netYi: -100, complete: true, exchanges: ["SSE", "SZSE", "BSE"], byExchange: [] })),
      summary: { net1dYi: -100, net5dYi: -500, net20dYi: -2000, baseline: { samples: 59, expected: 60, mean: 25000, percentile: 20 } } },
    market: { code: "000300.SH", name: "沪深300", asOf: "2026-10-14", current: true,
      points: Array.from({ length: 60 }, (_, i) => ({ date: new Date(Date.UTC(2026, 7, 16 + i)).toISOString().slice(0, 10), close: 4000 - i, pct: -.2 })),
      return5dPct: -3.21, return20dPct: -7.48, volatility20dPct: 13, maxDrawdown60dPct: -12, volatilitySamples: 20, drawdownSamples: 60, source: "Tushare index_daily", note: "样本标准差×√252；价格不含分红" },
    breadth: { asOf: "2026-10-14", current: true, total: 10, comparable: 10, source: "测试来源", note: "单日行业样本存在重叠",
      buckets: [{ id: "weak", name: "下跌且净流出", count: 10, examples: [{ code: "BK1", name: "测试行业" }] }] },
    credit: { money: { current: true, month: "2026-09", m1ChangePp: -.9, m2ChangePp: -.3, gapChangePp: .6 },
      social: { current: true, month: "2026-09", stockYoyChangePp: -.1, flow3mYi: 66000, flow3mPriorYearYi: 72000, flow3mYoYDiffYi: -6000 },
      transmission: [{ id: "credit", name: "信用扩张验证", signal: "lower", evidence: "2026-09 社融同比少增", implication: "尚未形成扩张", watch: "私人需求" }] },
    sources: { calendar: { status: "ready", dates: [], sessions: 60, reason: "" }, benchmark: { status: "ready", reason: "", usingSaved: false },
      leverage: { status: "ready", fetchStatus: "ready", usingSaved: false, sourceNote: "三所", asOf: "2026-10-14" }, sectors: { status: "ready" }, liquidity: [] },
    notes: ["不合成情绪分数"],
  };
}

test("风险偏好独立加载：窗口、矩阵与Agent同步，移动端无页面溢出", async ({ page }) => {
  const contexts: any[] = [], legacyRequests: string[] = [];
  page.on("request", r => {
    const path = new URL(r.url()).pathname;
    if (r.method() === "PUT" && path === "/api/mods/capital-emotion/context") contexts.push(r.postDataJSON().context);
    if (["/api/capital-flow", "/api/capital-flow/research"].includes(path)) legacyRequests.push(path);
  });
  await page.route("**/api/capital-flow/appetite-research**", route => route.fulfill({ json: fixture() }));
  await page.goto(`${shell}/?mod=capital-emotion&workspace=appetite-${Date.now()}`);
  const frame = page.frameLocator('iframe[title="资金风险偏好"]');
  await expect(frame.getByRole("region", { name: "风险偏好证据研究" })).toBeVisible();
  await expect(frame.locator('[data-evidence="price"]')).toContainText("-3.21");
  await expect.poll(() => contexts.at(-1)?.data.summary.page.appetiteResearch.selectedWindow.days).toBe(5);
  await frame.getByRole("button", { name: "20交易日", exact: true }).click();
  await expect(frame.locator('[data-evidence="price"]')).toContainText("-7.48");
  await expect.poll(() => contexts.at(-1)?.filters.horizonDays).toBe(20);
  const context = contexts.at(-1);
  expect(context.data.summary.page.appetiteResearch.selectedWindow.days).toBe(20);
  expect(context.data.summary.page.appetiteResearch.windows).toBeUndefined();
  expect(context.data.summary.page.appetiteResearch.market.points).toHaveLength(60);
  expect(context.data.summary.page.appetiteResearch.leverage.points).toHaveLength(20);
  expect(context.data.summary.page.appetiteResearch.credit.social.month).toBe("2026-09");
  expect(context.data.freshness).toBe("fresh");
  expect(legacyRequests).toHaveLength(0);
  await frame.getByText("融资原始日明细与交易所覆盖", { exact: true }).click();
  await expect(frame.locator(".appetite-leverage tbody tr")).toHaveCount(20);
  await expect(frame.locator(".appetite-leverage")).toContainText("SSE / SZSE / BSE");
  await page.setViewportSize({ width: 390, height: 850 });
  expect(await frame.locator(".capital-root").evaluate(el => el.scrollWidth <= el.clientWidth + 1)).toBe(true);
});

test("风险偏好整体刷新失败保留快照，Agent不把历史关系当本次确认", async ({ page }) => {
  const contexts: any[] = [];
  let count = 0;
  page.on("request", r => { if (r.method() === "PUT" && new URL(r.url()).pathname === "/api/mods/capital-emotion/context") contexts.push(r.postDataJSON().context); });
  await page.route("**/api/capital-flow/appetite-research**", route => ++count === 1 ? route.fulfill({ json: fixture() }) : route.fulfill({ status: 503 }));
  await page.goto(`${shell}/?mod=capital-emotion&workspace=appetite-refresh-${Date.now()}`);
  const frame = page.frameLocator('iframe[title="资金风险偏好"]');
  await expect(frame.locator('[data-evidence="price"]')).toContainText("-3.21");
  await frame.getByRole("button", { name: "刷新", exact: true }).click();
  await expect(frame.locator(".error-banner")).toContainText("保留上次快照");
  await expect(frame.locator(".appetite-relations")).toContainText("历史快照 / 待更新");
  await expect.poll(() => contexts.at(-1)?.data.summary.error).toContain("503");
  expect(contexts.at(-1).data.freshness).toBe("unknown");
  expect(contexts.at(-1).data.summary.page.appetiteResearch.snapshotOnly).toBe(true);
});

test("风险偏好局部缺失不补零，独立页面可用", async ({ page }) => {
  const data = fixture();
  for (const window of Object.values(data.windows)) {
    window.evidence[1].value = null; window.evidence[1].current = false;
    window.relationships[0].status = "incomplete"; window.relationships[0].title = "证据未齐，暂不能确认";
    window.verifiedRelationships = 1;
  }
  data.market.points[58].close = null;
  await page.route("**/api/capital-flow/appetite-research**", route => route.fulfill({ json: data }));
  await page.goto(`${api}/mod-runtime/capital-flow/?view=emotion&mod=capital-emotion`);
  await expect(page.locator('[data-evidence="etf"]')).toContainText("--");
  await expect(page.locator(".appetite-relations")).toContainText("证据未齐，暂不能确认");
  await expect(page.getByRole("img", { name: "沪深300最近60交易日收盘价" })).toContainText("缺");
  await expect(page.getByRole("status")).toContainText("1/2 组权益关系可核对");
});

test("真实风险偏好：接口和Desk展示一致", async ({ page, request }, info) => {
  const response = await request.get(`${api}/api/capital-flow/appetite-research`);
  expect(response.ok()).toBe(true);
  const data: AppetiteResearchData = await response.json();
  expect(data.market.points).toHaveLength(60);
  expect(data.windows["5"].etfs).toHaveLength(3);
  expect(data.windows["5"].evidence).toHaveLength(6);
  expect(data.sectorSnapshot?.level).toBe("L1");
  expect(data.breadth.classification?.matched).toBe(data.breadth.classification?.total);
  expect(data.sectorSnapshot?.boards.every(row => row.level === "L1")).toBe(true);
  await page.setViewportSize({ width: 1560, height: 1900 });
  await page.goto(`${shell}/?mod=capital-emotion&workspace=appetite-live-${Date.now()}`);
  const frame = page.frameLocator('iframe[title="资金风险偏好"]');
  await expect(frame.locator(".appetite-relations")).toContainText(data.windows["5"].relationships[0].title);
  await expect(frame.locator('[data-evidence="price"]')).toContainText(data.market.return5dPct?.toLocaleString("zh-CN", { maximumFractionDigits: 2 }) ?? "--");
  await frame.locator(".capital-root").screenshot({ path: info.outputPath("appetite-live.png") });
});

test("资金总览复用证据，窗口下钻不重复请求研究并保留选择", async ({ page }, info) => {
  const data = fixture(), contexts: any[] = [], requests: string[] = [];
  const snapshot: SectorResearchData = { schemaVersion: "v1", generatedAt: data.generatedAt, source: "测试分类来源", category: "industry", categoryLabel: "行业",
    expectedDate: data.expectedDate, asOf: data.expectedDate, level: "L1", selected: null,
    boards: [{ code: "BK0486.DC", name: "传媒", net: 8, pct: 1, level: "L1" }],
    classification: { source: "测试目录", url: "https://tushare.pro", current: true, status: "ready", usingSaved: false, reason: "", asOf: data.expectedDate,
      total: 3, matched: 3, counts: { L1: 1, L2: 1, L3: 1, unknown: 0 }, conflicts: 0, constituentsVerified: false, selectedLevel: "L1", selectedCount: 1, note: "成分交叉未核验" },
    calendar: { status: "ready", reason: "", dates: [] }, coverage: { status: "ready", reason: "", usingSaved: false, duplicatesRemoved: 0, classified: 1, aggregateSafe: false, hierarchyVerified: true, selectedNotFound: false }, notes: [] };
  data.sectorSnapshot = snapshot;
  data.breadth.classification = snapshot.classification;
  page.on("request", r => { const path = new URL(r.url()).pathname; requests.push(path);
    if (r.method() === "PUT" && path === "/api/mods/capital-overview/context") contexts.push(r.postDataJSON().context); });
  await page.route("**/api/capital-flow", route => route.fulfill({ status: 503 }));
  await page.route("**/api/capital-flow/appetite-research**", route => route.fulfill({ json: data }));
  await page.route("**/api/capital-flow/sector-research**", route => {
    const params = new URL(route.request().url()).searchParams;
    expect(params.get("level")).toBe("L1"); expect(params.get("code")).toBe("BK0486.DC");
    return route.fulfill({ json: snapshot });
  });
  await page.goto(`${shell}/?mod=capital-overview&workspace=overview-${Date.now()}`);
  const frame = page.frameLocator('iframe[title="资金总览"]');
  await expect(frame.locator('[data-overview-evidence="price"]')).toContainText("-3.21");
  await frame.getByRole("button", { name: "20交易日", exact: true }).click();
  await expect.poll(() => contexts.at(-1)?.filters.horizonDays).toBe(20);
  expect(contexts.at(-1).data.summary.page.overviewResearch.selectedWindow.days).toBe(20);
  expect(contexts.at(-1).data.summary.page.sectors).toHaveLength(1);
  expect(requests.filter(path => ["/api/capital-flow/research", "/api/capital-flow/sector-research"].includes(path))).toHaveLength(0);
  await frame.locator('[data-overview-evidence="price"]').click();
  await expect(frame.getByRole("button", { name: "20交易日", exact: true })).toHaveAttribute("aria-pressed", "true");
  await expect.poll(() => contexts.at(-1)?.view.title).toBe("风险偏好");
  expect(requests.filter(path => path === "/api/capital-flow/appetite-research")).toHaveLength(1);
  await frame.getByRole("button", { name: "资金总览", exact: true }).click();
  await frame.getByRole("button", { name: "传媒 ↗", exact: true }).click();
  await expect.poll(() => contexts.at(-1)?.filters.sectorLevel).toBe("L1");
  expect(contexts.at(-1).selection.sectorCode).toBe("BK0486.DC");
  await expect(frame.getByRole("button", { name: "东财一级", exact: true })).toHaveAttribute("aria-pressed", "true");
  await page.setViewportSize({ width: 390, height: 850 });
  expect(await frame.locator(".capital-root").evaluate(el => el.scrollWidth <= el.clientWidth + 1)).toBe(true);
  await frame.getByRole("button", { name: "资金总览", exact: true }).click();
  await expect(frame.locator('[data-overview-evidence="price"]')).toBeVisible();
  expect(await frame.locator(".capital-root").evaluate(el => el.scrollWidth <= el.clientWidth + 1)).toBe(true);
  await page.screenshot({ path: info.outputPath("overview-mobile.png") });
});

test("总览跨境联动：独立加载、窗口下钻复用，失败与缺口不被旧结论覆盖", async ({ page }, info) => {
  const data = connectFixture(), contexts: any[] = [];
  let calls = 0, fail = false;
  page.on("request", r => { if (r.method() === "PUT" && new URL(r.url()).pathname === "/api/mods/capital-overview/context") contexts.push(r.postDataJSON().context); });
  await page.route("**/api/capital-flow", route => route.fulfill({ status: 503 }));
  await page.route("**/api/capital-flow/appetite-research**", route => route.fulfill({ json: fixture() }));
  await page.route("**/api/capital-flow/connect-research**", route => { calls++; return fail ? route.fulfill({ status: 503 }) : route.fulfill({ json: data }); });
  await page.goto(`${shell}/?mod=capital-overview&workspace=overview-connect-${Date.now()}`);
  const frame = page.frameLocator('iframe[title="资金总览"]');
  const brief = frame.getByRole("region", { name: "跨境资金总览研究" });
  const south = brief.locator('[data-connect-brief="southbound"]');
  await expect(south).toContainText("100 亿港元");
  await expect(south).toContainText("窗口数据齐备");
  await expect.poll(() => contexts.at(-1)?.filters.connectDays).toBe(5);
  expect(contexts.at(-1).data.summary.page.connectResearch.selectedWindow.southbound.points).toBeUndefined();
  expect(contexts.at(-1).data.summary.page.connectResearch.selectedWindow.northbound.summary.netBuyYi).toBeNull();
  await frame.getByRole("button", { name: "20交易日", exact: true }).click();
  await expect(south).toContainText("400 亿港元");
  await expect(south).toContainText("2026-09-16");
  await expect(brief.locator('[data-connect-brief="northbound"]')).toContainText("2026-09-09");
  await expect.poll(() => contexts.at(-1)?.filters.connectDays).toBe(20);
  await brief.getByRole("button", { name: "查看跨境证据 →", exact: true }).click();
  await expect(frame.getByRole("button", { name: "20个通道交易日", exact: true })).toHaveAttribute("aria-pressed", "true");
  await expect.poll(() => contexts.at(-1)?.view.title).toBe("跨境资金");
  expect(contexts.at(-1).data.summary.page.connectResearch.selectedWindow.southbound.points).toEqual([]);
  expect(calls).toBe(1);
  await frame.getByRole("button", { name: "资金总览", exact: true }).click();
  await expect(south).toContainText("400 亿港元");
  expect(calls).toBe(1);
  await page.setViewportSize({ width: 390, height: 850 });
  expect(await frame.locator(".capital-root").evaluate(el => el.scrollWidth <= el.clientWidth + 1)).toBe(true);
  await brief.screenshot({ path: info.outputPath("connect-brief-mobile.png") });
  fail = true;
  await frame.getByRole("button", { name: "刷新", exact: true }).click();
  await expect(brief).toContainText("不用旧单日快照代替研究结论");
  await expect(south).toContainText("400 亿港元");
  await expect(south).not.toContainText("窗口数据齐备");
  await expect(south).toContainText("相邻五日对照未确认");
  await expect.poll(() => contexts.at(-1)?.data.summary.page.connectResearch.snapshotOnly).toBe(true);
  expect(contexts.at(-1).data.summary.page.connectResearch.selectedWindow.southbound.current).toBe(false);
  expect(contexts.at(-1).data.summary.page.connectResearch.selectedWindow.southbound.momentum.current).toBe(false);
  expect(contexts.at(-1).data.freshness).toBe("unknown");
  fail = false;
  data.windows["20"].southbound.current = false;
  data.windows["20"].southbound.available = 19;
  data.windows["20"].southbound.missingDates = ["2026-09-16"];
  data.windows["20"].southbound.summary.netBuyYi = null;
  await frame.getByRole("button", { name: "刷新", exact: true }).click();
  await expect(south).toContainText("窗口缺口：2026-09-16");
  await expect(south).toContainText("-- 亿港元");
  await expect(brief.locator('[data-connect-brief="northbound"]')).toContainText("窗口数据齐备");
  await expect.poll(() => contexts.at(-1)?.data.summary.page.connectResearch.selectedWindow.southbound.current).toBe(false);
  await expect.poll(() => contexts.at(-1)?.data.summary.page.connectResearch.selectedWindow.northbound.current).toBe(true);
});

test("真实总览：一级行业目录与排行对齐", async ({ page, request }, info) => {
  const response = await request.get(`${api}/api/capital-flow/appetite-research`);
  const data: AppetiteResearchData = await response.json();
  await page.setViewportSize({ width: 1500, height: 1600 });
  await page.goto(`${shell}/?mod=capital-overview&workspace=overview-live-${Date.now()}`);
  const frame = page.frameLocator('iframe[title="资金总览"]');
  await expect(frame.locator(".overview-sector-scope")).toContainText(`一级 ${data.breadth.classification?.counts.L1}`);
  await expect(frame.locator(".overview-relations")).toContainText(data.windows["5"].relationships[0].title);
  await expect(frame.getByRole("status")).not.toContainText("正在读取");
  const connectResponse = await request.get(`${api}/api/capital-flow/connect-research`);
  expect(connectResponse.ok()).toBe(true);
  const connect: ConnectResearchData = await connectResponse.json();
  await expect(frame.locator('[data-connect-brief="southbound"]')).toContainText(connect.windows["5"].southbound.summary.netBuyYi?.toLocaleString("zh-CN", { maximumFractionDigits: 2 }) ?? "--");
  await expect(frame.locator('[data-connect-brief="southbound"]')).toContainText(connect.windows["5"].southbound.asOf!);
  await frame.locator(".capital-root").screenshot({ path: info.outputPath("overview-live.png") });
});
