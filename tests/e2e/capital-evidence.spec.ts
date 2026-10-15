import { expect, test } from "@playwright/test";
import type { CapitalFlowDashboard, CapitalResearch, SectorCategory, SectorResearchData, SecurityResearchData, SecurityEvidenceData } from "../../modules/capital-flow/src/types";

const shell = "http://127.0.0.1:5888";
const api = "http://127.0.0.1:8911";
const dates = Array.from({ length: 90 }, (_, i) => new Date(Date.UTC(2026, 6, 16 + i)))
  .filter(date => date.getUTCDay() !== 0 && date.getUTCDay() !== 6).map(date => date.toISOString().slice(0, 10)).slice(-60);
const researchFixture: CapitalResearch = {
  schemaVersion: "newma-desk.capital-research.v1", generatedAt: "2026-10-14T02:00:00Z", expectedDate: dates.at(-1)!,
  calendar: { status: "ready", sessions: 60, dates, reason: "" },
  coverage: { etfAvailable: 2, etfTotal: 2, sampleOnly: true, primaryStatus: "permission-denied", primaryReason: "新ETF接口权限不足" },
  etfs: [["510300.SH", "沪深300ETF"], ["518880.SH", "黄金ETF"]].map(([code, name]) => ({
    code: code!, name: name!, category: code === "510300.SH" ? "宽基" : "商品", currency: "CNY",
    source: "Tushare fund_share + fund_nav", sourceNote: "", receivedAt: "2026-10-14T02:00:00Z", fetchStatus: "ready", usingSaved: false,
    status: "ready", asOf: dates.at(-1)!, expectedDate: dates.at(-1)!, note: "代表样本，不是全市场",
    latest: { date: dates.at(-1)!, sharesWan: 10000, nav: 4, shareChangeWan: 100, navChangePct: 1, flowYi: .04 },
    points: dates.map((day, i) => ({ date: day, sharesWan: 10000, nav: 4, shareChangeWan: 100, shareChangePct: 1,
      flowYi: i === dates.length - 2 ? null : i % 2 ? .04 : -.02, navChangePct: 1, suspectedSplit: false })),
    summary: { flow1dYi: .04, flow5dYi: null, flow20dYi: null, baseline: { samples: 58, expected: 59, percentile: 80, mean: .01 } },
  })),
  groups: [{ category: "宽基", count: 1, available: 1, flow1dYi: .04, flow5dYi: null, flow20dYi: null }],
  leverage: { status: "ready", source: "Tushare margin / 沪深北交易所", sourceNote: "", fetchStatus: "ready", receivedAt: "2026-10-14T02:00:00Z", usingSaved: false,
    currency: "CNY", unit: "亿元", scope: ["SSE", "SZSE", "BSE"], asOf: dates.at(-1)!, expectedDate: dates.at(-1)!, note: "融资增减不是市场现金净流入",
    latest: { balanceYi: 25000, buyYi: 1000, repayYi: 1100, netYi: -100 },
    points: dates.map(day => ({ date: day, exchanges: ["SSE", "SZSE", "BSE"], complete: true, balanceYi: 25000, buyYi: 1000, repayYi: 1100, netYi: -100, byExchange: [] })),
    summary: { net1dYi: -100, net5dYi: -500, net20dYi: -2000, baseline: { samples: 59, expected: 59, percentile: 20, mean: 26000 } } },
  notes: ["测试数据；代表观察池，不代表全市场", "缺失不补零"],
};

test.beforeEach(async ({ page }, info) => {
  if (!info.title.startsWith("真实")) {
    await page.route("**/api/capital-flow/connect-research**", route => route.fulfill({ status: 503 }));
    await page.route("**/api/capital-flow/security-evidence**", route => {
      const params = new URL(route.request().url()).searchParams;
      return route.fulfill({ json: evidenceFixture(params.get("code") ?? "300308", params.get("board_date") ?? "2026-10-13", params.get("audit_date") ?? "2026-09-15") });
    });
    await page.route("**/api/capital-flow/security-research**", route => route.fulfill({ json: securityResearchFixture(new URL(route.request().url()).searchParams.get("code") ?? "300308") }));
    await page.route("**/api/capital-flow/supply-verification**", route => route.fulfill({ json: verificationFixture(new URL(route.request().url()).searchParams.get("code") ?? "300308") }));
    await page.route("**/api/capital-flow/supply-research**", route => route.fulfill({ json: supplyFixture(new URL(route.request().url()).searchParams.get("code") ?? "300308") }));
    await page.route("**/api/capital-flow/research**", route => route.fulfill({ json: researchFixture }));
    await page.route("**/api/capital-flow/sector-research**", route => route.fulfill({ json: {
      ...sectorFixture(), boards: [], selected: null, coverage: { ...sectorFixture().coverage, classified: 0, status: "unavailable", reason: "测试缺口" },
    } }));
  }
});

function evidenceFixture(code: string, boardDate = "2026-10-13", auditDate = "2026-09-15"): SecurityEvidenceData {
  const ready = { status: "ready", reason: "", usingSaved: false, receivedAt: "2026-10-14T02:00:00Z" };
  const makeComparison = (residual: number) => ({ status: "agree" as const, referenceResidualYuan: residual,
    fields: ["前日融资余额", "当日融资买入", "当日融资偿还", "当日融资余额"].map((field, i) => ({ field, tushareYuan: [1000, 30, 20, 1010 + residual][i]!, referenceYuan: [1000, 30, 20, 1010 + residual][i]!, differenceYuan: 0 })) });
  const sourceName = code.startsWith("6") ? "上交所" : code.startsWith("92") ? "北交所" : "深交所";
  const officialComparison = makeComparison(auditDate === "2026-09-17" ? -2 : auditDate === "2026-10-13" ? 0 : 800);
  return { schemaVersion: "newma-desk.security-evidence.v1", code, symbol: `${code}.${code.startsWith("6") ? "SH" : code.startsWith("92") ? "BJ" : "SZ"}`, generatedAt: ready.receivedAt,
    board: { date: boardDate, dates: ["2026-10-12", "2026-10-13"], calendarStatus: "ready", recordsCoverage: boardDate === "2026-10-12" ? { ...ready, status: "empty" } : ready,
      seatsCoverage: ready, unmatchedSeats: 0, aggregateSafe: false, notes: ["测试披露；不同上榜理由不相加"],
      groups: boardDate === "2026-10-12" ? [] : ["日涨幅达到15%的前5只证券", "连续三个交易日内，涨幅偏离值累计达到30%的证券"].map((reason, i) => ({
        reason, reasonKey: reason, window: { label: i ? "三交易日累计" : "单交易日", sessions: i ? 3 : 1, start: i ? "2026-10-09" : boardDate, end: boardDate },
        buyYuan: 500, sellYuan: 100, netYuan: 400, amountConflict: false, records: [{ reason, buy: 500 }],
        seats: [{ name: "具名营业部", sides: ["0", "1"], buyYuan: 500, sellYuan: 100, netYuan: 400, ambiguousIdentity: false, possibleRepeat: false, disclosureCount: 2, residualYuan: 0, raw: {} },
          ...["0", "1"].map(side => ({ name: "机构专用", sides: [side], buyYuan: 300, sellYuan: 100, netYuan: 200, ambiguousIdentity: true, possibleRepeat: true, disclosureCount: 1, residualYuan: 0, raw: {} }))],
        rawSeatCount: 4, repeatedNamedRows: 1, ambiguousSeatRows: 2, aggregateSafe: false,
      })) },
    audit: { expectedDate: "2026-10-13", start: "2026-09-14", end: "2026-10-13", checked: 20, expected: 20, dates: ["2026-09-15", "2026-09-17", "2026-10-13"],
      cases: ["2026-09-15", "2026-09-17"].map((day, i) => ({ date: day, previousDate: i ? "2026-09-16" : "2026-09-14", previousBalanceYuan: 1000, buyYuan: 30, repayYuan: 20,
        balanceYuan: i ? 1008 : 1810, expectedBalanceYuan: 1010, residualYuan: i ? -2 : 800, size: i ? "small" as const : "review" as const, raw: {}, previousRaw: {}, mirrorComparison: makeComparison(i ? -2 : 800) })),
      smallDifferences: 1, reviewDifferences: 1, coverage: ready, calendarStatus: "ready", confirmedInputs: true, mirror: ready,
      official: { date: auditDate, previousDate: auditDate === "2026-09-15" ? "2026-09-14" : auditDate === "2026-10-13" ? "2026-10-12" : "2026-09-16", status: code.startsWith("6") ? "verified" : "partial-verified", sourceName, missingFields: code.startsWith("6") ? [] : ["融资偿还额"],
        reason: code.startsWith("6") ? "四项金额与交易所一致；官方原始数值亦存在该勾稽差额，原因仍待核查" : "三项已披露金额与交易所一致；官方未单列融资偿还额，不反推补齐，不确认完整勾稽差额",
        comparison: code.startsWith("6") ? { ...officialComparison, available: 4, matched: 4, total: 4 } : { ...officialComparison, status: "partial", available: 3, matched: 3, total: 4, referenceResidualYuan: null,
          fields: officialComparison.fields.map((field, i) => i === 2 ? { ...field, referenceYuan: null, differenceYuan: null } : field) } }, notes: ["测试融资样本；官方确认仅覆盖两日数值，不说明业务原因"] },
  };
}

test("席位与融资核验：理由分组、机构不聚合，日期选择同步 Agent", async ({ page }) => {
  const contexts: any[] = [];
  page.on("request", request => { if (request.method() === "PUT" && new URL(request.url()).pathname === "/api/mods/capital-flow/context") contexts.push(request.postDataJSON().context); });
  await page.route(/\/api\/capital-flow(\?|$)/, route => route.fulfill({ json: fixture }));
  await page.goto(`${shell}/?mod=capital-flow&workspace=capital-evidence-selection-${Date.now()}`);
  const frame = page.frameLocator('iframe[title="个股资金"]');
  await frame.getByLabel("股票名称或代码").fill("600519"); await frame.getByLabel("股票名称或代码").press("Enter");
  const panel = frame.getByRole("region", { name: "龙虎榜与融资原始证据核验" });
  await expect(panel.locator("[data-seat-row]")).toHaveCount(3);
  await expect(panel).toContainText("原披露 → 3 行展示");
  await expect(panel).toContainText("四项金额已确认 · 原因未确认");
  await panel.getByLabel("龙虎榜上榜理由").selectOption({ index: 1 });
  await expect(panel).toContainText("三交易日累计 · 2026-10-09 → 2026-10-13");
  await expect.poll(() => contexts.at(-1)?.data.summary.page.securityEvidence.selectedReason).toContain("连续三个");
  expect(contexts.at(-1).data.summary.page.securityEvidence.board.selectedGroup.seats).toHaveLength(3);
  expect(contexts.at(-1).data.summary.page.securityEvidence.board.aggregateSafe).toBe(false);
  await panel.getByRole("button", { name: "核验融资 2026-09-17" }).click();
  await expect(panel.getByLabel("交易所融资原始金额核验")).toContainText("差额 -2 元");
  await expect.poll(() => contexts.at(-1)?.filters.auditDate).toBe("2026-09-17");
  await panel.getByLabel("龙虎榜披露日").selectOption("2026-10-12");
  await expect(panel).toContainText("所选披露日未返回上榜记录");
  await expect(panel.locator("[data-seat-row]")).toHaveCount(0);
  await expect.poll(() => contexts.at(-1)?.filters.boardDate).toBe("2026-10-12");
  expect(contexts.at(-1).data.summary.page.securityEvidence.board.selectedGroup).toBeNull();
  await page.setViewportSize({ width: 390, height: 850 });
  expect(await frame.locator(".capital-root").evaluate(el => el.scrollWidth <= el.clientWidth + 1)).toBe(true);
});

test("席位与融资核验：切换股票清除所选日期、理由及旧官方确认", async ({ page }) => {
  const contexts: any[] = [];
  let release!: () => void;
  const gate = new Promise<void>(resolve => { release = resolve; });
  page.on("request", request => { if (request.method() === "PUT" && new URL(request.url()).pathname === "/api/mods/capital-flow/context") contexts.push(request.postDataJSON().context); });
  await page.route(/\/api\/capital-flow(\?|$)/, route => route.fulfill({ json: fixture }));
  await page.route("**/api/capital-flow/security-evidence**", async route => {
    const params = new URL(route.request().url()).searchParams;
    if (params.get("code") === "300308") { expect(params.get("board_date")).toBeNull(); expect(params.get("audit_date")).toBeNull(); await gate; }
    await route.fulfill({ json: evidenceFixture(params.get("code")!, params.get("board_date") ?? "2026-10-13", params.get("audit_date") ?? "2026-09-15") });
  });
  await page.goto(`${shell}/?mod=capital-flow&workspace=capital-evidence-switch-${Date.now()}`);
  const frame = page.frameLocator('iframe[title="个股资金"]'), input = frame.getByLabel("股票名称或代码");
  await input.fill("600519"); await input.press("Enter");
  const panel = frame.getByRole("region", { name: "龙虎榜与融资原始证据核验" });
  await expect(panel).toContainText("四项金额已确认");
  await panel.getByRole("button", { name: "核验融资 2026-09-17" }).click();
  await expect(panel).toContainText("交易所原始数值勾稽差额 -2 元");
  await input.fill("300308"); await input.press("Enter");
  await expect(panel).toContainText("按披露日读取");
  await expect(panel).not.toContainText("四项金额已确认");
  await expect.poll(() => contexts.at(-1)?.selection.securityCode).toBe("300308");
  expect(contexts.at(-1).data.summary.page.securityEvidence.code).toBeUndefined();
  release();
  await expect(panel).toContainText("官方未单列融资偿还额");
  await expect.poll(() => contexts.at(-1)?.data.summary.page.securityEvidence.code).toBe("300308");
  expect(contexts.at(-1).data.summary.page.securityEvidence.requestedAuditDate).toBeNull();
});

test("席位与融资核验：失败保留旧证据，不把镜像当官方确认", async ({ page }) => {
  const contexts: any[] = [];
  page.on("request", request => { if (request.method() === "PUT" && new URL(request.url()).pathname === "/api/mods/capital-flow/context") contexts.push(request.postDataJSON().context); });
  await page.route(/\/api\/capital-flow(\?|$)/, route => route.fulfill({ status: 503 }));
  await page.route("**/api/capital-flow/security-evidence**", route => {
    const data = evidenceFixture("600519");
    data.board.recordsCoverage = { ...data.board.recordsCoverage, status: "upstream-error", usingSaved: true, reason: "来源更新失败" };
    data.audit.confirmedInputs = false; data.audit.calendarStatus = "upstream-error";
    data.audit.official = { date: "2026-09-15", status: "not-requested", reason: "交易日历或融资来源更新失败，暂不作官方确认", comparison: null };
    return route.fulfill({ json: data });
  });
  await page.goto(`${shell}/?mod=capital-flow&workspace=capital-evidence-failure-${Date.now()}`);
  const frame = page.frameLocator('iframe[title="个股资金"]');
  await frame.getByLabel("股票名称或代码").fill("600519"); await frame.getByLabel("股票名称或代码").press("Enter");
  const panel = frame.getByRole("region", { name: "龙虎榜与融资原始证据核验" });
  await expect(panel).toContainText("更新失败，保留旧记录");
  await expect(panel).toContainText("未完成官方确认");
  await expect(panel).not.toContainText("四项金额已确认");
  await expect(panel.locator("[data-seat-row]")).toHaveCount(3);
  await expect.poll(() => contexts.at(-1)?.data.summary.page.securityEvidence.code).toBe("600519");
  expect(contexts.at(-1).data.freshness).toBe("unknown");
});

test("深市北交所核验：三项一致不补偿还额，普通日期选择同步 Agent", async ({ page }) => {
  const contexts: any[] = [];
  page.on("request", request => { if (request.method() === "PUT" && new URL(request.url()).pathname === "/api/mods/capital-flow/context") contexts.push(request.postDataJSON().context); });
  await page.route(/\/api\/capital-flow(\?|$)/, route => route.fulfill({ status: 503 }));
  await page.route("**/api/capital-flow/security-evidence**", route => {
    const params = new URL(route.request().url()).searchParams;
    const data = evidenceFixture(params.get("code")!, "2026-10-13", params.get("audit_date") ?? "2026-09-15");
    data.audit.cases = []; data.audit.smallDifferences = 0; data.audit.reviewDifferences = 0;
    return route.fulfill({ json: data });
  });
  await page.goto(`${shell}/?mod=capital-flow&workspace=capital-partial-official-${Date.now()}`);
  const frame = page.frameLocator('iframe[title="个股资金"]');
  for (const [code, source] of [["300308", "深交所"], ["920093", "北交所"]]) {
    await frame.getByLabel("股票名称或代码").fill(code!); await frame.getByLabel("股票名称或代码").press("Enter");
    const official = frame.getByLabel("交易所融资原始金额核验");
    await expect(official).toContainText(`${source}原始金额核验`);
    await expect(official).toContainText("已核对3/4项 · 偿还额未披露");
    await expect(official).toContainText("未取得／未披露");
    await expect(official).not.toContainText("四项金额已确认");
    await expect(official).not.toContainText("勾稽差额 0 元");
    await official.getByLabel("融资官方核验日").selectOption("2026-10-13");
    await expect.poll(() => contexts.at(-1)?.filters.auditDate).toBe("2026-10-13");
    await expect.poll(() => contexts.at(-1)?.data.summary.page.securityEvidence.audit?.official.date).toBe("2026-10-13");
    const result = contexts.at(-1).data.summary.page.securityEvidence.audit.official;
    expect(result.status).toBe("partial-verified");
    expect(result.comparison.referenceResidualYuan).toBeNull();
    expect(result.comparison.fields[2].referenceYuan).toBeNull();
    expect(result.missingFields).toEqual(["融资偿还额"]);
  }
  await page.setViewportSize({ width: 390, height: 850 });
  expect(await frame.locator(".capital-root").evaluate(el => el.scrollWidth <= el.clientWidth + 1)).toBe(true);
});

test("真实深市北交所核验：官方精确金额与 Tushare 对齐，未披露项留空", async ({ page, request }, info) => {
  for (const [code, source, balance] of [["300308", "深交所", 29278520594], ["920093", "北交所", 4570965]] as const) {
    const response = await request.get(`${api}/api/capital-flow/security-evidence?code=${code}&audit_date=2026-10-13`);
    expect(response.ok()).toBe(true);
    const data = await response.json() as SecurityEvidenceData;
    expect(data.audit.official.status).toBe("partial-verified");
    expect(data.audit.official.comparison?.matched).toBe(3);
    expect(data.audit.official.comparison?.referenceResidualYuan).toBeNull();
    expect(data.audit.official.current?.rows[0]?.rzye).toBe(balance);
    await page.goto(`${shell}/?mod=capital-flow&workspace=capital-live-official-${code}-${Date.now()}`);
    const frame = page.frameLocator('iframe[title="个股资金"]');
    await frame.getByLabel("股票名称或代码").fill(code); await frame.getByLabel("股票名称或代码").press("Enter");
    const official = frame.getByLabel("交易所融资原始金额核验");
    await official.getByLabel("融资官方核验日").selectOption("2026-10-13");
    await expect(official).toContainText("已核对3/4项 · 偿还额未披露");
    await expect(official).toContainText(`${source}原始金额核验 · 2026-10-13`);
    await expect(official).toContainText(balance.toLocaleString("zh-CN"));
    await official.screenshot({ path: info.outputPath(`${code}-official-partial.png`) });
  }
});

test("真实龙虎榜：301030 单日和三日披露分开，机构重复席位不汇总", async ({ page, request }, info) => {
  const response = await request.get(`${api}/api/capital-flow/security-evidence?code=301030&board_date=2026-10-13`);
  expect(response.ok()).toBe(true);
  const data = await response.json() as SecurityEvidenceData;
  expect(data.board.recordsCoverage.status).toBe("ready");
  expect(data.board.groups).toHaveLength(2);
  expect(data.board.groups.reduce((count, group) => count + group.rawSeatCount, 0)).toBe(20);
  const three = data.board.groups.find(group => group.window.sessions === 3)!;
  expect(three.netYuan).toBeCloseTo(-14844597.2, 1);
  expect(three.seats.some(seat => seat.ambiguousIdentity && seat.possibleRepeat)).toBe(true);
  await page.goto(`${shell}/?mod=capital-flow&workspace=capital-real-board-${Date.now()}`);
  const frame = page.frameLocator('iframe[title="个股资金"]');
  await frame.getByLabel("股票名称或代码").fill("301030"); await frame.getByLabel("股票名称或代码").press("Enter");
  const panel = frame.getByRole("region", { name: "龙虎榜与融资原始证据核验" });
  await panel.getByLabel("龙虎榜披露日").selectOption("2026-10-13");
  await panel.getByLabel("龙虎榜上榜理由").selectOption(three.reasonKey);
  await expect(panel.locator("[data-seat-row]")).toHaveCount(three.seats.length);
  await expect(panel).toContainText("三交易日累计");
  await panel.locator(".evidence-seats").screenshot({ path: info.outputPath("real-board-windows.png") });
});

test("真实融资追溯：茅台交易所四项金额确认，但差额原因仍待核查", async ({ page, request }, info) => {
  const response = await request.get(`${api}/api/capital-flow/security-evidence?code=600519&audit_date=2026-09-15`);
  expect(response.ok()).toBe(true);
  const data = await response.json() as SecurityEvidenceData;
  expect(data.audit.official.status).toBe("verified");
  expect(data.audit.official.comparison?.referenceResidualYuan).toBe(819779);
  expect(data.audit.official.comparison?.fields.every(field => field.differenceYuan === 0)).toBe(true);
  await page.goto(`${shell}/?mod=capital-flow&workspace=capital-real-reconcile-${Date.now()}`);
  const frame = page.frameLocator('iframe[title="个股资金"]');
  await frame.getByLabel("股票名称或代码").fill("600519"); await frame.getByLabel("股票名称或代码").press("Enter");
  const panel = frame.getByRole("region", { name: "龙虎榜与融资原始证据核验" });
  await expect(panel).toContainText("四项金额已确认 · 原因未确认");
  await expect(panel.getByLabel("交易所融资原始金额核验")).toContainText("819,779 元");
  await panel.getByLabel("交易所融资原始金额核验").screenshot({ path: info.outputPath("real-moutai-reconciliation.png") });
});

function securityResearchFixture(code = "300308"): SecurityResearchData {
  const net = code === "300308" ? .1 : .2;
  const points = dates.map((day, i) => ({ date: day, net: i === dates.length - 2 ? null : net,
    largeYi: net * .6, extraYi: net * .4, amountYi: 10, netSharePct: i === dates.length - 2 ? null : net * 10,
    sourceSharePct: null, close: 120 - i * .1, adjFactor: 1, adjustedValue: 120 - i * .1, adjustedPct: -.1, factorChanged: false,
    balanceYi: 10 + i * .1, marginBuyYi: .2, marginRepayYi: .1, marginNetYi: .1, balanceChangeYi: i ? .1 : null, marginResidualYuan: i ? 0 : null }));
  return { schemaVersion: "newma-desk.security-research.v1", code, symbol: `${code}.SZ`, generatedAt: "2026-10-14T02:00:00Z",
    expectedDate: dates.at(-1)!, currency: "CNY", unit: "亿元", source: "Tushare moneyflow_dc", fallbackReason: "",
    calendar: { status: "ready", reason: "", dates },
    feeds: Object.fromEntries(["orders", "daily", "factors", "margin"].map((key, i) => [key, { api: ["moneyflow_dc", "daily", "adj_factor", "margin_detail"][i],
      status: "ready", reason: "", usingSaved: false, receivedAt: "2026-10-14T02:00:00Z", asOf: dates.at(-1), count: 60 }])) as SecurityResearchData["feeds"],
    points, order: { net1dYi: net, net5dYi: null, net20dYi: null, share1dPct: net * 10, share5dPct: null, share20dPct: null,
      streak: { direction: "in", days: 1 }, baseline: { samples: 58, expected: 59, percentile: 50, mean: net } },
    leverage: { net1dYi: .1, net5dYi: .5, net20dYi: 2, balanceChange5dYi: .5, balanceChange20dYi: 2, buyShare5dPct: 2,
      baseline: { samples: 59, expected: 59, percentile: 100, mean: 12.9 }, reconciliationChecked: 20, reconciliationConflicts: 0 },
    price: { change5dPct: -0.4363, change20dPct: -1.7227, method: "测试 close × adj_factor", factorChanges20d: 0 },
    observations: [{ id: "order-price", title: "资金价格对照待核验", detail: "测试缺失日，不给出背离判断。" },
      { id: "leverage-price", title: "下跌期间融资余额增加", detail: "5日融资余额增加0.5亿元，不是上涨预测。" }],
    notes: ["测试数据；固定交易日缺失不补零", "不将融资和订单合成总资金"] };
}

test("个股历史：独立加载、缺失留空、窗口及核验结论同步 Agent", async ({ page }) => {
  const contexts: any[] = [];
  page.on("request", request => { if (request.method() === "PUT" && new URL(request.url()).pathname === "/api/mods/capital-flow/context") contexts.push(request.postDataJSON().context); });
  await page.route(/\/api\/capital-flow(\?|$)/, route => route.fulfill({ status: 503, json: { detail: "快照不可用" } }));
  await page.goto(`${shell}/?mod=capital-flow&workspace=capital-stock-history-${Date.now()}`);
  const frame = page.frameLocator('iframe[title="个股资金"]');
  await frame.getByLabel("股票名称或代码").fill("300308");
  await frame.getByLabel("股票名称或代码").press("Enter");
  const panel = frame.getByRole("region", { name: "个股资金持续性研究" });
  await expect(panel).toContainText("下跌期间融资余额增加");
  await expect(panel).toContainText("1日 +0.1 / 20日 --");
  await expect(panel.locator('[data-flow-bar]')).toHaveCount(19);
  await expect.poll(() => contexts.at(-1)?.data.summary.page.securityResearch.code).toBe("300308");
  expect(contexts.at(-1).data.summary.page.securityResearch.points).toHaveLength(20);
  expect(contexts.at(-1).data.summary.page.securityResearch.order.net5dYi).toBeNull();
  await panel.getByRole("button", { name: "60日", exact: true }).click();
  await expect(panel.locator('[data-flow-bar]')).toHaveCount(59);
  await expect.poll(() => contexts.at(-1)?.filters.historyDays).toBe(60);
  expect(contexts.at(-1).data.summary.page.securityResearch.points).toHaveLength(60);
  expect(contexts.at(-1).data.summary.page.securityResearch.leverage.reconciliationConflicts).toBe(0);
  await panel.getByText("同日订单、复权与融资勾稽明细", { exact: true }).click();
  await expect(panel.locator("tbody tr")).toHaveCount(60);
  await page.setViewportSize({ width: 390, height: 850 });
  expect(await frame.locator(".capital-root").evaluate(el => el.scrollWidth <= el.clientWidth + 1)).toBe(true);
});

test("个股历史切换：等待新股票时撤销旧趋势和 Agent 数据", async ({ page }) => {
  const contexts: any[] = [];
  let release!: () => void;
  const gate = new Promise<void>(resolve => { release = resolve; });
  page.on("request", request => { if (request.method() === "PUT" && new URL(request.url()).pathname === "/api/mods/capital-flow/context") contexts.push(request.postDataJSON().context); });
  await page.route(/\/api\/capital-flow(\?|$)/, route => route.fulfill({ json: fixture }));
  await page.route("**/api/capital-flow/security-research**", async route => {
    const code = new URL(route.request().url()).searchParams.get("code")!;
    if (code === "601318") await gate;
    await route.fulfill({ json: securityResearchFixture(code) });
  });
  await page.goto(`${shell}/?mod=capital-flow&workspace=capital-stock-switch-${Date.now()}`);
  const frame = page.frameLocator('iframe[title="个股资金"]');
  const input = frame.getByLabel("股票名称或代码");
  await input.fill("300308"); await input.press("Enter");
  const panel = frame.getByRole("region", { name: "个股资金持续性研究" });
  await expect(panel).toContainText("1日 +0.1");
  await input.fill("601318"); await input.press("Enter");
  await expect(panel).toContainText("独立读取订单");
  await expect(panel).not.toContainText("1日 +0.1");
  await expect.poll(() => contexts.at(-1)?.selection.securityCode).toBe("601318");
  expect(contexts.at(-1).data.summary.page.securityResearch.code).toBeUndefined();
  release();
  await expect(panel).toContainText("1日 +0.2");
  await expect.poll(() => contexts.at(-1)?.data.summary.page.securityResearch.code).toBe("601318");
});

test("个股历史：旧数据标识、融资缺口和失败不能生成无风险结论", async ({ page }) => {
  await page.route(/\/api\/capital-flow(\?|$)/, route => route.fulfill({ json: fixture }));
  await page.route("**/api/capital-flow/security-research**", route => {
    const data = securityResearchFixture();
    data.feeds.orders = { ...data.feeds.orders, status: "upstream-error", usingSaved: true, reason: "订单更新失败" };
    data.feeds.margin = { ...data.feeds.margin, status: "empty", asOf: null, count: 0 };
    data.points = data.points.map(point => ({ ...point, balanceYi: null, marginBuyYi: null, marginRepayYi: null, marginNetYi: null, balanceChangeYi: null, marginResidualYuan: null }));
    data.leverage = { ...data.leverage, net1dYi: null, net5dYi: null, net20dYi: null, balanceChange5dYi: null, balanceChange20dYi: null,
      buyShare5dPct: null, baseline: { samples: 0, expected: 59, percentile: null, mean: null }, reconciliationChecked: 0 };
    data.observations = data.observations.slice(0, 1);
    return route.fulfill({ json: data });
  });
  await page.goto(`${shell}/?mod=capital-flow&workspace=capital-stock-missing-${Date.now()}`);
  const frame = page.frameLocator('iframe[title="个股资金"]');
  await frame.getByLabel("股票名称或代码").fill("300308");
  await frame.getByLabel("股票名称或代码").press("Enter");
  const panel = frame.getByRole("region", { name: "个股资金持续性研究" });
  await expect(panel).toContainText("更新失败，保留旧历史");
  await expect(panel).toContainText("成功空结果，未确认覆盖");
  await expect(panel).toContainText("融资余额 -- 亿元");
  await expect(panel).not.toContainText("下跌期间融资余额增加");
});

test("真实个股历史：茅台订单单位、价格和融资勾稽与页面一致", async ({ page, request }, info) => {
  const response = await request.get(`${api}/api/capital-flow/security-research?code=600519`);
  expect(response.ok()).toBe(true);
  const data = await response.json() as SecurityResearchData;
  expect(data.source).toBe("Tushare moneyflow_dc");
  expect(data.feeds.orders.status).toBe("ready");
  expect(data.feeds.margin.status).toBe("ready");
  const latest = data.points.at(-1)!;
  expect(Number.isFinite(latest.net)).toBe(true);
  expect(latest.amountYi).toBeGreaterThan(0);
  expect(latest.close).toBeGreaterThan(0);
  expect(latest.netSharePct).toBeCloseTo(latest.net! / latest.amountYi! * 100, 4);
  if (latest.date === "2026-10-13") {
    expect(latest.net).toBeCloseTo(.504012, 6);
    expect(latest.amountYi).toBeCloseTo(33.93315572, 6);
    expect(latest.close).toBe(1274.89);
  }
  expect(data.leverage.reconciliationConflicts).toBe(data.points.slice(-20).filter(point => point.marginResidualYuan != null && Math.abs(point.marginResidualYuan) > 1).length);
  expect(data.observations.some(item => item.id === "margin-conflict")).toBe(data.leverage.reconciliationConflicts > 0);
  expect(data.order.net5dYi).not.toBeNull();
  expect(data.price.change5dPct).not.toBeNull();
  await page.goto(`${shell}/?mod=capital-flow&workspace=capital-real-stock-${Date.now()}`);
  const frame = page.frameLocator('iframe[title="个股资金"]');
  await frame.getByLabel("股票名称或代码").fill("600519");
  await frame.getByLabel("股票名称或代码").press("Enter");
  const panel = frame.getByRole("region", { name: "个股资金持续性研究" });
  await expect(panel).toContainText(data.expectedDate!);
  await expect(panel).toContainText(`${data.leverage.reconciliationConflicts} 日有差异`);
  await expect(panel.locator('[data-flow-bar]')).toHaveCount(20);
  await panel.screenshot({ path: info.outputPath("moutai-order-history.png") });
});

function supplyFixture(code = "300308") {
  const item = { id: "repurchase:0", kind: "repurchase", label: "股份回购", stage: "计划", progress: "股东大会通过",
    annDate: "2026-10-13", eventDate: "2026-10-13", holder: null, beginDate: null, endDate: null, expiryDate: "2027-10-13",
    amountYi: 3, sharesWan: null, ratioPct: null, superseded: false, note: "测试回购计划，不是实施", raw: { amount: 3e8, proc: "股东大会通过" } };
  return { schemaVersion: "newma-desk.capital-supply.v1", code, symbol: `${code}.SZ`, generatedAt: "2026-10-14T02:00:00Z", asOf: "2026-10-14",
    window: { start: "2025-10-14", announcementEnd: "2026-10-14", unlockEnd: "2027-01-12" }, aggregateSafe: false,
    feeds: [{ id: "repurchase", label: "回购披露", source: "Tushare测试", sourceUrl: "https://tushare.pro/document/2?doc_id=124",
      status: "ready", reason: "", receivedAt: "2026-10-14T02:00:00Z", usingSaved: false, asOf: "2026-10-13", count: 1, duplicatesRemoved: 0, items: [item] },
    { id: "share_float", label: "限售解禁", source: "Tushare测试", sourceUrl: "https://tushare.pro/document/2?doc_id=160",
      status: "ready", reason: "", receivedAt: "2026-10-14T02:00:00Z", usingSaved: false, asOf: "2026-10-13", count: 2, duplicatesRemoved: 0,
      items: [{ ...item, id: "share_float:0", kind: "share_float", label: "限售解禁", stage: "待解禁", progress: "股权激励", eventDate: "2026-12-01", amountYi: null, sharesWan: 10, holder: "测试股东", ratioPct: .1 },
        { ...item, id: "share_float:1", kind: "share_float", label: "限售解禁", stage: "待解禁", eventDate: "2026-12-01", annDate: "2026-10-01", amountYi: null, sharesWan: 12, holder: "测试股东", superseded: true }] },
    { id: "stk_holdertrade", label: "股东增减持", source: "Tushare测试", sourceUrl: "https://tushare.pro/document/2?doc_id=175",
      status: "permission-denied", reason: "测试权限不足", receivedAt: "2026-10-14T02:00:00Z", usingSaved: false, asOf: null, count: 0, duplicatesRemoved: 0, items: [] }],
    notes: ["测试数据；回购计划不是实施，解禁不是卖出，不合计资金净流入"] };
}

function verificationFixture(code: string) {
  return { code, kind: "repurchase", annDate: "2026-10-13", status: "ready", reason: "", source: "测试公告镜像", usingSaved: false,
    items: [{ id: "AN202610130000000001", title: "测试股份回购进展公告", date: "2026-10-13", url: "https://data.eastmoney.com/", pdfUrl: "https://pdf.dfcfw.com/",
      text: "测试正文：实施进展，不是完成。", status: "body-read", note: "测试材料，不作真实投资依据", parsed: { planDate: null, planSignature: null, purpose: null,
        cumulativeAmountYi: 3, cumulativeSharesWan: 10, cumulativeAsOf: "2026-10-12", stage: "实施进展", quotes: ["测试累计回购金额3亿元"] } }],
    previousDocument: null, comparison: [{ field: "阶段", sourceValue: "完成", documentValue: "实施进展", status: "conflict" }],
    delta: { status: "unverified", amountYi: null, sharesWan: null, note: "方案尚未确认，不计算执行差额" } };
}

test("公告核验：来源冲突保留两边，未知差额不补零，切换清除正文", async ({ page }) => {
  const contexts: any[] = [];
  page.on("request", request => {
    if (request.method() === "PUT" && new URL(request.url()).pathname === "/api/mods/capital-flow/context") contexts.push(request.postDataJSON().context);
  });
  await page.route(/\/api\/capital-flow(\?|$)/, route => route.fulfill({ json: fixture }));
  await page.goto(`${shell}/?mod=capital-flow&workspace=capital-document-${Date.now()}`);
  const frame = page.frameLocator('iframe[title="个股资金"]');
  await frame.getByLabel("股票名称或代码").fill("300308");
  await frame.getByLabel("股票名称或代码").press("Enter");
  await frame.getByRole("button", { name: "回购披露", exact: true }).click();
  await frame.getByRole("button", { name: "核验公告", exact: true }).click();
  const panel = frame.getByRole("region", { name: "公告正文与执行差额核验" });
  await expect(panel).toContainText("口径冲突 · 保留两边");
  await expect(panel).toContainText("执行差额 -- 亿元 / -- 万股");
  await expect.poll(() => contexts.at(-1)?.data.summary.page.verification.data?.comparison?.[0]?.status).toBe("conflict");
  const data = contexts.at(-1).data.summary.page.verification.data;
  expect(data.items[0].parsed.stage).toBe("实施进展");
  expect(data.delta.amountYi).toBeNull();
  expect(data.contentRole).toContain("仅为证据");
  await frame.getByLabel("股票名称或代码").fill("601318");
  await frame.getByLabel("股票名称或代码").press("Enter");
  await expect(panel).toHaveCount(0);
  await expect.poll(() => contexts.at(-1)?.selection?.securityCode).toBe("601318");
  expect(contexts.at(-1).data.summary.page.verification).toBeNull();
});

test("真实公告核验：茅台阶段冲突和区间执行差额与原文一致", async ({ page, request }, info) => {
  const response = await request.get(`${api}/api/capital-flow/supply-verification?code=600519&kind=repurchase&ann_date=2026-05-08`);
  expect(response.ok()).toBe(true);
  const data = await response.json();
  expect(data.status).toBe("ready");
  expect(data.items[0].status).toBe("body-read");
  expect(data.delta.amountYi).toBeCloseTo(4.088251, 5);
  expect(data.comparison.find((row: any) => row.field === "阶段").status).toBe("conflict");
  await page.goto(`${shell}/?mod=capital-flow&workspace=capital-real-document-${Date.now()}`);
  const frame = page.frameLocator('iframe[title="个股资金"]');
  await frame.getByLabel("股票名称或代码").fill("600519");
  await frame.getByLabel("股票名称或代码").press("Enter");
  await frame.getByRole("button", { name: "回购披露", exact: true }).click();
  const row = frame.locator(".supply-table tbody tr").filter({ hasText: "公告 2026-05-08" });
  await row.getByRole("button", { name: "核验公告" }).click();
  const panel = frame.getByRole("region", { name: "公告正文与执行差额核验" });
  await expect(panel).toContainText("4.088251");
  await expect(panel).toContainText("2026-03-31 之后 — 2026-04-30");
  await expect(panel).toContainText("口径冲突 · 保留两边");
  await panel.getByText("字段提取证据", { exact: true }).click();
  await expect(panel).toContainText("累计已回购金额1,520,943,540.21元");
  await expect(panel.getByRole("link", { name: "公告 PDF ↗" })).toHaveAttribute("href", /H2_AN202605071822034858/);
  await frame.locator(".supply-verification").screenshot({ path: info.outputPath("moutai-verification.png") });
});

test("供需证据：独立加载、计划与未来解禁不混加，筛选同步 Agent", async ({ page }) => {
  const contexts: any[] = [];
  page.on("request", request => {
    if (request.method() === "PUT" && new URL(request.url()).pathname === "/api/mods/capital-flow/context") contexts.push(request.postDataJSON().context);
  });
  await page.route(/\/api\/capital-flow(\?|$)/, route => route.fulfill({ status: 503, body: "test unavailable" }));
  await page.goto(`${shell}/?mod=capital-flow&workspace=capital-supply-${Date.now()}`);
  const frame = page.frameLocator('iframe[title="个股资金"]');
  await frame.getByLabel("股票名称或代码").fill("300308");
  await frame.getByLabel("股票名称或代码").press("Enter");
  const panel = frame.getByRole("region", { name: "回购增减持与解禁证据" });
  await expect(panel.locator(".supply-table tbody tr")).toHaveCount(3);
  await expect(panel.locator(".supply-metrics > div").nth(1).locator("strong")).toContainText("--");
  await expect(panel.locator(".supply-metrics > div").nth(2).locator("strong")).toHaveText("1条");
  await expect(panel).toContainText("2026-12-01");
  await expect(panel).toContainText("旧披露 · 不重复计数");
  await panel.getByRole("button", { name: "回购披露", exact: true }).click();
  await expect(panel.locator(".supply-table tbody tr")).toHaveCount(1);
  await expect(panel.locator(".supply-table")).toContainText("计划");
  await expect.poll(() => contexts.at(-1)?.filters?.supplyType).toBe("repurchase");
  const supply = contexts.at(-1).data.summary.page.supply;
  expect(supply.visibleRows).toHaveLength(1);
  expect(supply.aggregateSafe).toBe(false);
  expect(supply.metrics.upcomingUnlockRecords).toBe(1);
  expect(supply.metrics.holderReports).toBeNull();
  expect(supply.visibleRows[0].stage).toBe("计划");
  await panel.getByRole("button", { name: "股东增减持", exact: true }).click();
  await expect(panel).toContainText("测试权限不足");
  await expect(panel).toContainText("不能据此认定没有供需风险");
});

test("供需切换：旧股票证据及时撤销，小屏无外层溢出", async ({ page }) => {
  let release!: () => void;
  const gate = new Promise<void>(resolve => { release = resolve; });
  await page.route("**/api/capital-flow/supply-research**", async route => {
    const code = new URL(route.request().url()).searchParams.get("code") ?? "300308";
    if (code === "601318") await gate;
    await route.fulfill({ json: supplyFixture(code) });
  });
  await page.route(/\/api\/capital-flow(\?|$)/, route => route.fulfill({ json: fixture }));
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(`${api}/mod-runtime/capital-flow/?view=security&mod=capital-flow`);
  await page.getByLabel("股票名称或代码").fill("300308");
  await page.getByLabel("股票名称或代码").press("Enter");
  await expect(page.locator(".supply-table")).toContainText("300308.SZ");
  expect(await page.locator(".capital-root").evaluate(el => el.scrollWidth <= el.clientWidth)).toBe(true);
  await page.getByLabel("股票名称或代码").fill("601318");
  await page.getByLabel("股票名称或代码").press("Enter");
  await expect(page.locator(".supply-research")).not.toContainText("300308.SZ");
  await expect(page.locator(".supply-research")).toContainText("正在读取");
  release();
  await expect(page.locator(".supply-table")).toContainText("601318.SZ");
});

test("真实回购证据：茅台披露、原始金额与页面一致", async ({ page, request }, info) => {
  const response = await request.get(`${api}/api/capital-flow/supply-research?code=600519`);
  expect(response.ok()).toBe(true);
  const data = await response.json();
  const feed = data.feeds.find((feed: any) => feed.id === "repurchase");
  expect(feed.status).toBe("ready");
  expect(feed.items.length).toBeGreaterThan(0);
  expect(feed.items[0].amountYi).toBeCloseTo(feed.items[0].raw.amount / 1e8, 5);
  await page.goto(`${api}/mod-runtime/capital-flow/?view=security&mod=capital-flow`);
  await page.getByLabel("股票名称或代码").fill("600519");
  await page.getByLabel("股票名称或代码").press("Enter");
  await page.getByRole("button", { name: "回购披露", exact: true }).click();
  await expect(page.locator(".supply-table tbody tr")).toHaveCount(feed.items.length);
  await expect(page.locator(".supply-table")).toContainText("600519.SH");
  await expect(page.locator(".supply-table")).toContainText("不合计为净流入");
  await page.locator(".supply-research").screenshot({ path: info.outputPath("moutai-supply.png") });
});

test("真实未来解禁：金陵体育未来日期不会被行情截止日过滤", async ({ page, request }, info) => {
  const response = await request.get(`${api}/api/capital-flow/supply-research?code=300657`);
  expect(response.ok()).toBe(true);
  const data = await response.json();
  const feed = data.feeds.find((feed: any) => feed.id === "share_float");
  expect(feed.status).toBe("ready");
  const upcoming = feed.items.filter((item: any) => !item.superseded && item.eventDate > data.asOf);
  expect(upcoming.length).toBeGreaterThan(0);
  expect(upcoming[0].sharesWan).toBeCloseTo(upcoming[0].raw.float_share / 1e4, 5);
  await page.goto(`${api}/mod-runtime/capital-flow/?view=security&mod=capital-flow`);
  await page.getByLabel("股票名称或代码").fill("300657");
  await page.getByLabel("股票名称或代码").press("Enter");
  await page.getByRole("button", { name: "限售解禁", exact: true }).click();
  await expect(page.locator(".supply-table")).toContainText(upcoming[0].eventDate);
  await expect(page.locator(".supply-table")).toContainText("待解禁");
  await expect(page.locator(".supply-review")).toContainText("不预设会卖出");
  expect(data.capacity.status).toBe("ready");
  expect(data.capacity.samples).toBe(20);
  expect(upcoming[0].capacityDaysAt5Pct).toBeCloseTo(upcoming[0].sharesWan / (data.capacity.averageVolumeWan * .05), 2);
  await expect(page.locator(".supply-capacity")).toContainText("20日成交容量");
  await expect(page.locator(".supply-table")).toContainText("假设全部卖出，不是预测");
  await page.locator(".supply-research").screenshot({ path: info.outputPath("jinling-unlock.png") });
});

function sectorFixture(category: SectorCategory = "industry", code?: string): SectorResearchData {
  const boards = (category === "concept" ? [["BK1136.DC", "光通信模块"], ["BK1667.DC", "小盘成长"]] : [["BK1340.DC", "印制电路板"], ["BK1329.DC", "集成电路制造"]])
    .map(([code, name]) => ({ code: code!, name: name!, category, pct: 2, net: 2, netSharePct: 3, aggregateSafe: false }));
  const selected = boards.find(row => row.code === code) ?? boards[0]!;
  return {
    schemaVersion: "newma-desk.sector-research.v1", generatedAt: "2026-10-14T02:00:00Z", source: "Tushare测试源", category,
    categoryLabel: category === "concept" ? "概念" : "行业", expectedDate: dates.at(-1)!, asOf: dates.at(-1)!, boards,
    selected: { code: selected.code, name: selected.name, asOf: dates.at(-1)!, fetchStatus: "ready", status: "ready", sourceNote: "", usingSaved: false,
      points: dates.map((day, i) => ({ date: day, net: i === dates.length - 2 ? null : 2, pct: 2, close: 100, netSharePct: 3, superNetYi: .5, largeNetYi: 1.5 })),
      summary: { net1dYi: 2, net5dYi: null, net20dYi: null, price5dPct: 10, price20dPct: 30, streak: { direction: "in", days: 1 }, baseline: { samples: 58, expected: 59, percentile: 80, mean: 1 } } },
    calendar: { status: "ready", reason: "", dates },
    coverage: { status: "ready", reason: "", usingSaved: false, duplicatesRemoved: 1, classified: 2, aggregateSafe: false, hierarchyVerified: false, selectedNotFound: false },
    notes: ["测试数据；层级与成分重叠未核验，不合计全市场"],
  };
}
const fixture: CapitalFlowDashboard = {
  schemaVersion: "newma-desk.capital-flow.v1", generatedAt: "2026-10-14T02:00:00Z", marketDate: "2026-10-14",
  summary: { sectorNetYi: null, sectorInflowYi: null, sectorOutflowYi: null, top20TurnoverYi: 30, active: null },
  sectors: [], turnoverLeaders: [{ code: "300308", name: "中际旭创", amount: 3e9 }], security: null,
  dimensions: [
    { id: "market", name: "市场成交", status: "ready", frequency: "盘中", lag: "5 分钟", source: "测试源", metric: "成交额 · 人民币亿元", asOf: null },
    { id: "sector", name: "行业资金", status: "degraded", frequency: "盘中", lag: "5 分钟", source: "测试源", asOf: null },
    { id: "northbound", name: "北向成交", status: "ready", frequency: "日", lag: "收盘后", source: "测试 HKEX", metric: "成交额 · 人民币亿元", asOf: "2026-10-13" },
  ], sources: [], upstream: { status: "degraded", base: "测试源" },
  crossBorder: { northbound: { sse: {}, szse: {}, date: "2026-10-13", history: { source: "测试历史", unit: "人民币亿元", points: [
    { date: "2026-10-12", northTurnoverYi: 100, sseTurnoverYi: 40, szseTurnoverYi: 60 },
    { date: "2026-10-13", northTurnoverYi: null, sseTurnoverYi: null, szseTurnoverYi: null },
  ] } }, southbound: { sse: {}, szse: {} } },
};

test("资金总览：缺失不补零，Agent 获得证据缺口而非请求时间", async ({ page }) => {
  const contexts: any[] = [];
  page.on("request", request => {
    if (request.method() === "PUT" && new URL(request.url()).pathname === "/api/mods/capital-overview/context") contexts.push(request.postDataJSON().context);
  });
  await page.route("**/api/capital-flow", route => route.fulfill({ json: fixture }));
  await page.route("**/api/capital-flow/appetite-research**", route => route.fulfill({ status: 503 }));
  await page.goto(`${shell}/?mod=capital-overview&workspace=capital-evidence-${Date.now()}`);
  const frame = page.frameLocator('iframe[title="资金总览"]');
  await expect(frame.getByRole("status")).toContainText("部分来源缺失");
  await expect(frame.getByRole("region", { name: "资金决策总览" })).toContainText("研究证据未取得");
  await expect(frame.locator(".flow-panel").first()).toContainText("暂无可用行业记录");
  await frame.getByText("单日快照与来源对照（独立于窗口研究）", { exact: true }).click();
  await expect(frame.getByRole("region", { name: "资金证据总览" })).toContainText("2026-10-13");
  await expect.poll(() => contexts.at(-1)?.data?.summary?.loading).toBe(false);
  const context = contexts.at(-1);
  expect(context.view.title).toBe("资金总览");
  expect(context.data.asOf).toBeUndefined();
  expect(context.data.freshness).not.toBe("fresh");
  expect(context.data.summary.page.turnoverLeaders).toEqual([]);
  expect(context.data.summary.page.turnoverResearch).toBeNull();
  await expect(frame.getByRole("region", { name: "收盘成交活跃度" })).toContainText("成交榜暂无可核验记录");
  expect(context.data.summary.page.overviewResearch).toBeNull();
  expect(context.data.summary.metrics.sectorNetYi).toBeNull();
});

test("成交榜：日期、金额、覆盖与Agent一致，可进入个股研究", async ({ page }, info) => {
  const contexts: any[] = [];
  const turnover = {
    schemaVersion: "newma-desk.turnover.v1", generatedAt: "2026-10-15T04:00:00Z", asOf: "2026-10-14", expectedDate: "2026-10-14",
    status: "ready", current: true, usingSaved: false, cached: false, reason: "", source: "Tushare daily · 测试行情", unit: "人民币亿元", rawUnit: "千元",
    note: "样本不代表全市场，成交额不等于资金净流入", calendarStatus: "ready", nameNote: "测试名称目录",
    coverage: { received: 30, sampleCount: 30, rejected: 0, invalid: 0, duplicates: 0, conflicts: 0, namesMatched: 30, universeVerified: false, valid: true },
    summary: { sampleTurnoverYi: 100, top20TurnoverYi: 30, top20SharePct: 30 },
    exchanges: [{ id: "SZ", name: "深圳", count: 30, turnoverYi: 100 }, { id: "BJ", name: "北京", count: 0, turnoverYi: null }],
    leaders: [{ code: "300308", name: "中际旭创", industry: "通信设备", amount: 3e9, pct: null }],
  };
  let refresh = false;
  page.on("request", request => {
    if (request.method() === "PUT" && new URL(request.url()).pathname === "/api/mods/capital-overview/context") contexts.push(request.postDataJSON().context);
  });
  await page.route(/\/api\/capital-flow(?:\?.*)?$/, route => {
    refresh = new URL(route.request().url()).searchParams.get("refresh") === "true";
    return route.fulfill({ json: { ...fixture, turnover: refresh ? { ...turnover, current: false, status: "upstream-error", usingSaved: true, reason: "分页请求失败，保留快照" } : turnover } });
  });
  await page.route("**/api/capital-flow/appetite-research**", route => route.fulfill({ status: 503 }));
  await page.goto(`${shell}/?mod=capital-overview&workspace=turnover-${Date.now()}`);
  const frame = page.frameLocator('iframe[title="资金总览"]');
  const panel = frame.getByRole("region", { name: "收盘成交活跃度" });
  await expect(panel).toContainText("2026-10-14");
  await expect(panel).toContainText("30 只有效样本");
  await expect(panel.locator(".turnover-summary")).toContainText("30%");
  await expect(panel.locator(".turnover-venues")).toContainText("-- 亿");
  await expect(panel.locator(".turnover-list b")).toHaveText("--");
  await expect.poll(() => contexts.at(-1)?.data.summary.page.turnoverResearch?.current).toBe(true);
  expect(contexts.at(-1).data.summary.page.turnoverResearch.summary.sampleTurnoverYi).toBe(100);
  expect(contexts.at(-1).data.summary.page.turnoverResearch.coverage.universeVerified).toBe(false);
  await page.setViewportSize({ width: 390, height: 850 });
  expect(await frame.locator(".capital-root").evaluate(el => el.scrollWidth <= el.clientWidth + 1)).toBe(true);
  await panel.screenshot({ path: info.outputPath("turnover-mobile.png") });
  await frame.getByRole("button", { name: "刷新", exact: true }).click();
  await expect(panel).toContainText("分页请求失败，保留快照");
  expect(refresh).toBe(true);
  await expect.poll(() => contexts.at(-1)?.data.summary.page.turnoverResearch?.snapshotOnly).toBe(true);
  expect(contexts.at(-1).data.summary.page.turnoverResearch.current).toBe(false);
  await panel.getByRole("button", { name: /中际旭创/ }).click();
  await expect(frame.locator(".security-search input")).toHaveValue("中际旭创");
  await expect.poll(() => contexts.at(-1)?.selection.securityCode).toBe("300308");
});

test("真实成交榜：分页样本和Desk页面核对", async ({ page, request }, info) => {
  const response = await request.get(`${api}/api/capital-flow`, { timeout: 60000 });
  expect(response.ok()).toBe(true);
  const data = await response.json();
  const turnover = data.turnover;
  expect(turnover.current).toBe(true);
  expect(turnover.asOf).toBe(turnover.expectedDate);
  expect(turnover.coverage.sampleCount).toBeGreaterThan(4000);
  expect(turnover.coverage.universeVerified).toBe(false);
  expect(turnover.leaders).toHaveLength(20);
  expect(turnover.summary.top20TurnoverYi).toBeCloseTo(turnover.leaders.reduce((sum: number, row: any) => sum + row.amount / 1e8, 0), 6);
  await page.goto(`${shell}/?mod=capital-overview&workspace=turnover-live-${Date.now()}`);
  const panel = page.frameLocator('iframe[title="资金总览"]').getByRole("region", { name: "收盘成交活跃度" });
  await expect(panel).toContainText(turnover.asOf, { timeout: 60000 });
  await expect(panel.locator(".turnover-list button")).toHaveCount(20);
  await expect(panel.locator(".turnover-list button").first()).toContainText(turnover.leaders[0].name);
  await panel.locator(".turnover-stamp").scrollIntoViewIfNeeded();
  await page.screenshot({ path: info.outputPath("turnover-live.png") });
});

test("成交历史按需分批加载，窗口和失败状态同步Agent", async ({ page }, info) => {
  const contexts: any[] = [], calls: number[] = [];
  let fail = false;
  const history = (days: number, completed = days + 1) => ({
    days, asOf: "2026-10-14", start: "2026-07-01", current: completed === days + 1, completed, expected: days + 1,
    remaining: days + 1 - completed, commonCount: 5000, latestSampleCount: 5563, excludedLatest: 563, note: "测试样本，基线不含最新日，非全市场",
    summary: { latestTurnoverYi: 12000, meanTurnoverYi: 10000, relativeVolume: 1.2, percentilePct: 75, top20SharePct: 12, meanTop20SharePct: 10, concentrationChangePp: 2 },
    points: Array.from({ length: days + 1 }, (_, i) => ({ date: `D${i}`, status: "ready", reason: "", sampleCount: 5563, turnoverYi: 10000 + i, top20SharePct: 10 })),
    generatedAt: "2026-10-15T12:00:00Z", source: "测试 daily", unit: "人民币亿元", calendarStatus: "ready", failedDates: [], fetchedDays: 8,
    canContinue: completed !== days + 1, reason: "",
  });
  page.on("request", r => { if (r.method() === "PUT" && new URL(r.url()).pathname === "/api/mods/capital-overview/context") contexts.push(r.postDataJSON().context); });
  await page.route(/\/api\/capital-flow(?:\?.*)?$/, route => route.fulfill({ json: fixture }));
  await page.route("**/api/capital-flow/appetite-research**", route => route.fulfill({ status: 503 }));
  await page.route("**/api/capital-flow/turnover-history**", route => {
    const days = Number(new URL(route.request().url()).searchParams.get("days")); calls.push(days);
    return fail ? route.fulfill({ status: 503 }) : route.fulfill({ json: history(days, calls.length === 1 ? 8 : days + 1) });
  });
  await page.goto(`${shell}/?mod=capital-overview&workspace=history-${Date.now()}`);
  const frame = page.frameLocator('iframe[title="资金总览"]');
  await expect(frame.getByRole("button", { name: "研究20/60日成交基线" })).toBeVisible();
  expect(calls).toHaveLength(0);
  await frame.getByRole("button", { name: "研究20/60日成交基线" }).click();
  const panel = frame.getByRole("region", { name: "成交历史基线" });
  await expect(panel).toContainText("21/21日");
  await expect(panel).toContainText("1.2 倍");
  expect(calls).toEqual([20, 20]);
  await expect.poll(() => contexts.at(-1)?.filters.turnoverHistoryDays).toBe(20);
  await expect.poll(() => contexts.at(-1)?.data.summary.page.turnoverHistory.data.current).toBe(true);
  fail = true;
  await panel.getByRole("button", { name: "60日基线" }).click();
  await expect(panel).toContainText("503");
  await expect.poll(() => contexts.at(-1)?.data.summary.page.turnoverHistory.days).toBe(60);
  expect(contexts.at(-1).data.summary.page.turnoverHistory.data).toBeNull();
  fail = false;
  await panel.getByRole("button", { name: "重试 / 补齐缺口" }).click();
  await expect(panel).toContainText("61/61日");
  await expect(panel).toContainText("固定共同样本 5000 只");
  fail = true;
  await panel.getByRole("button", { name: "刷新最新日" }).click();
  await expect(panel).toContainText("保留快照不代表更新成功");
  await expect.poll(() => contexts.at(-1)?.data.summary.page.turnoverHistory.data.current).toBe(false);
  await page.setViewportSize({ width: 390, height: 850 });
  expect(await frame.locator(".capital-root").evaluate(el => el.scrollWidth <= el.clientWidth + 1)).toBe(true);
  await panel.screenshot({ path: info.outputPath("turnover-history-mobile.png") });
  await frame.getByRole("button", { name: "收起成交历史" }).click();
  await expect.poll(() => contexts.at(-1)?.data.summary.page.turnoverHistory).toBeNull();
});

test("真实成交历史：20和60日共同样本基线可用", async ({ page, request }, info) => {
  for (const days of [20, 60]) {
    let data: any;
    for (let batch = 0; batch < 8; batch++) {
      const response = await request.get(`${api}/api/capital-flow/turnover-history?days=${days}`, { timeout: 60000 });
      expect(response.ok()).toBe(true); data = await response.json();
      if (!data.canContinue) break;
    }
    expect(data.current).toBe(true);
    expect(data.points).toHaveLength(days + 1);
    expect(data.commonCount).toBeGreaterThan(4000);
    const prior = data.points.slice(0, -1);
    expect(data.summary.meanTurnoverYi).toBeCloseTo(prior.reduce((sum: number, row: any) => sum + row.turnoverYi, 0) / days, 6);
    expect(data.summary.relativeVolume).toBeCloseTo(data.points.at(-1).turnoverYi / data.summary.meanTurnoverYi, 6);
  }
  expect((await request.get(`${api}/api/capital-flow/turnover-history?days=30`)).status()).toBe(422);
  await page.goto(`${api}/mod-runtime/capital-flow/?view=overview&mod=capital-overview`);
  await page.getByRole("button", { name: "研究20/60日成交基线" }).click();
  const panel = page.getByRole("region", { name: "成交历史基线" });
  await expect(panel).toContainText("21/21日");
  await panel.getByRole("button", { name: "60日基线" }).click();
  await expect(panel).toContainText("61/61日");
  await panel.scrollIntoViewIfNeeded();
  await panel.screenshot({ path: info.outputPath("turnover-history-live.png") });
});

test("跨境图：缺失日不画零柱，不生成假的前日变化和沪深占比", async ({ page }) => {
  await page.route("**/api/capital-flow", route => route.fulfill({ json: fixture }));
  await page.goto(`${api}/mod-runtime/capital-flow/?view=cross-border&mod=capital-cross-border`);
  await expect(page.locator(".turnover-column")).toHaveCount(2);
  await expect(page.locator(".turnover-bar")).toHaveCount(1);
  await expect(page.locator(".turnover-column").last()).toContainText("缺");
  await expect(page.locator(".turnover-kpis")).toContainText("-- / --");
  await expect(page.locator(".turnover-kpis")).not.toContainText("-100%");
});

test("名称选股和切换：新对象不能携带上一只的数据，失败不能写未上榜", async ({ page }) => {
  const contexts: any[] = [];
  let release!: () => void;
  const gate = new Promise<void>(resolve => { release = resolve; });
  page.on("request", request => {
    if (request.method() === "PUT" && new URL(request.url()).pathname === "/api/mods/capital-flow/context") contexts.push(request.postDataJSON().context);
  });
  await page.route("**/api/capital-flow/search?**", route => {
    const query = new URL(route.request().url()).searchParams.get("query");
    return route.fulfill({ json: { items: [{ symbol: query?.includes("平安") ? "601318" : "300308", name: query?.includes("平安") ? "中国平安" : "中际旭创", market: "CN", exchange: "SZ" }] } });
  });
  await page.route(/\/api\/capital-flow(\?|$)/, async route => {
    const code = new URL(route.request().url()).searchParams.get("code");
    if (code === "601318") await gate;
    const coverage = { status: "unavailable", count: 0, source: "测试源", asOf: null, note: "请求失败" };
    await route.fulfill({ json: { ...fixture, security: code ? { code, fundFlow: [{ date: "2026-10-13", main_net: code === "300308" ? 9e8 : 2e8 }], margin: [], dragonTiger: { institution: { buy_amt: 999, sell_amt: 888, net_amt: 111 } }, coverage: { fundFlow: { ...coverage, status: "ready", count: 1 }, margin: coverage, dragonTiger: coverage } } : null } });
  });
  await page.goto(`${shell}/?mod=capital-flow&workspace=capital-security-${Date.now()}`);
  const frame = page.frameLocator('iframe[title="个股资金"]');
  await frame.getByLabel("股票名称或代码").fill("中际旭创");
  await frame.getByRole("button", { name: /中际旭创.*300308/ }).click();
  await frame.getByText("旧来源快照与龙虎榜席位 · 独立口径核对", { exact: true }).click();
  await expect(frame.locator(".fund-flow-table")).toContainText("9 亿");
  await frame.getByLabel("股票名称或代码").fill("中国平安");
  await frame.getByRole("button", { name: /中国平安.*601318/ }).click();
  await expect(frame.locator(".security-view")).toContainText("正在读取 601318");
  await expect(frame.locator(".fund-flow-table")).toHaveCount(0);
  await expect.poll(() => contexts.at(-1)?.selection?.securityCode).toBe("601318");
  expect(contexts.at(-1).data.summary.page.security).toBeNull();
  release();
  await frame.getByText("旧来源快照与龙虎榜席位 · 独立口径核对", { exact: true }).click();
  await expect(frame.locator(".fund-flow-table")).toContainText("2 亿");
  await expect(frame.locator(".dragon-tiger-section")).toContainText("请求失败，暂不能判断是否上榜");
  await expect.poll(() => contexts.at(-1)?.data?.summary?.page?.security?.code).toBe("601318");
  expect(contexts.at(-1).selection.securityName).toBe("中国平安");
  expect(contexts.at(-1).data.summary.page.security.dragonTiger.institution).toBeNull();
  expect(contexts.at(-1).data.summary.page.security.dragonTiger.institutionCoverage).toContain("未核验");
});

test("独立模式可切换全部视图，小屏外层没有横向溢出", async ({ page }) => {
  await page.route("**/api/capital-flow", route => route.fulfill({ json: fixture }));
  await page.setViewportSize({ width: 620, height: 900 });
  await page.goto(`${api}/mod-runtime/capital-flow/?view=overview&mod=capital-overview`);
  await expect(page.getByRole("navigation", { name: "资金视图" })).toBeVisible();
  expect(await page.locator(".capital-root").evaluate(el => el.scrollWidth <= el.clientWidth)).toBe(true);
  await page.getByRole("button", { name: "数据口径", exact: true }).click();
  await expect(page.getByRole("heading", { name: "资金数据口径" })).toBeVisible();
  await page.getByRole("button", { name: "个股资金", exact: true }).click();
  await expect(page.getByLabel("股票名称或代码")).toBeVisible();
});

test("七个资金入口：实际页面和 Agent 上下文标题逐项对齐", async ({ page }) => {
  const contexts = new Map<string, any>();
  page.on("request", request => {
    const path = new URL(request.url()).pathname;
    if (request.method() === "PUT" && /\/api\/mods\/capital-[^/]+\/context/.test(path)) contexts.set(path.split("/")[3]!, request.postDataJSON().context);
  });
  await page.route("**/api/capital-flow", route => route.fulfill({ json: fixture }));
  for (const [id, title] of [["capital-overview", "资金总览"], ["capital-sectors", "行业轮动"], ["capital-cross-border", "跨境资金"], ["capital-liquidity", "流动性"], ["capital-etf", "ETF 资金"], ["capital-emotion", "风险偏好"], ["capital-flow", "个股资金"]]) {
    await page.goto(`${shell}/?mod=${id}&workspace=capital-pages-${Date.now()}`);
    const frame = page.frameLocator("iframe").first();
    await expect(frame.getByRole("button", { name: "刷新", exact: true })).toBeVisible();
    await expect.poll(() => contexts.get(id!)?.data?.summary?.loading).toBe(false);
    expect(contexts.get(id!).view.title).toBe(title);
  }
});

test("跨境历史：独立读取、窗口切换、缺口与失败同步Agent", async ({ page }, info) => {
  const contexts: any[] = [];
  let fail = false, calls = 0;
  const window = (days: number, south: boolean) => ({ direction: south ? "southbound" : "northbound", days, currency: south ? "HKD" : "CNY", unit: south ? "港元亿元" : "人民币亿元",
    current: true, start: "2026-09-01", asOf: "2026-10-14", available: days, closedDays: ["2026-10-01"], missingDates: [],
    points: Array.from({ length: days }, (_, i) => ({ date: `2026-09-${String(i + 1).padStart(2, "0")}`, status: "ready", turnoverYi: 100, buyYi: south ? 60 : null, sellYi: south ? 40 : null, netBuyYi: south ? (i % 2 ? -20 : 20) : null })),
    summary: { turnoverYi: days * 100, buyYi: south ? days * 60 : null, sellYi: south ? days * 40 : null, netBuyYi: south ? days * 20 : null,
      positiveDays: south ? 3 : null, streakDays: south ? 2 : null, streakDirection: south ? "sell" : "unknown", streakCensored: false, prior20MeanTurnoverYi: 100, latestVsPrior20: 1 },
    momentum: { days: 5, current: true, missingDates: [], netChangeYi: south ? -50 : null, intensityChangePp: south ? -10 : null, turnoverRatio: 1,
      recent: { start: "2026-10-08", end: "2026-10-14", available: 5, current: true, turnoverYi: 500, netBuyYi: south ? 50 : null, netIntensityPct: south ? 10 : null },
      previous: { start: "2026-09-23", end: "2026-09-29", available: 5, current: true, turnoverYi: 500, netBuyYi: south ? 100 : null, netIntensityPct: south ? 20 : null } },
  });
  const data = { generatedAt: "2026-10-15T01:00:00Z", cutoff: "2026-10-14", source: "测试HKEX", completed: 33, expected: 33, remaining: 0, failedDates: [], canContinue: false,
    windows: { "5": { southbound: window(5, true), northbound: window(5, false) }, "20": { southbound: window(20, true), northbound: window(20, false) } }, notes: ["测试数据：不同币种不混加"] };
  data.windows["20"].southbound.current = false;
  data.windows["20"].southbound.points[10]!.status = "unavailable";
  data.windows["20"].southbound.summary.netBuyYi = null;
  page.on("request", r => { if (r.method() === "PUT" && new URL(r.url()).pathname === "/api/mods/capital-cross-border/context") contexts.push(r.postDataJSON().context); });
  await page.route(/\/api\/capital-flow(?:\?.*)?$/, route => route.fulfill({ status: 503 }));
  await page.route("**/api/capital-flow/connect-research**", route => { calls++; return fail ? route.fulfill({ status: 503 }) : route.fulfill({ json: data }); });
  await page.goto(`${shell}/?mod=capital-cross-border&workspace=connect-research-${Date.now()}`);
  const frame = page.frameLocator('iframe[title="跨境资金"]');
  const research = frame.getByRole("region", { name: "跨境资金历史研究" });
  await expect(research.getByRole("region", { name: "南向净买入研究" })).toContainText("--");
  await expect(research.getByRole("img", { name: "南向逐日净买入" })).toContainText("缺");
  await research.getByRole("button", { name: "5个通道交易日" }).click();
  await expect.poll(() => contexts.at(-1)?.filters.connectDays).toBe(5);
  await expect.poll(() => contexts.at(-1)?.data.summary.page.connectResearch.selectedWindow.southbound.current).toBe(true);
  expect(contexts.at(-1).data.summary.page.connectResearch.selectedWindow.southbound.currency).toBe("HKD");
  expect(contexts.at(-1).data.summary.page.connectResearch.selectedWindow.northbound.summary.netBuyYi).toBeNull();
  expect(calls).toBe(1);
  await expect(research).toContainText("2日卖出");
  const momentum = research.getByRole("group", { name: "南向五日强弱对照" });
  await expect(momentum).toContainText("净买入强度下降");
  await expect(momentum).toContainText("强度变化 -10 个百分点");
  await expect(momentum).toContainText("2026-09-23");
  expect(contexts.at(-1).data.summary.page.connectResearch.selectedWindow.southbound.momentum.intensityChangePp).toBe(-10);
  await page.setViewportSize({ width: 390, height: 850 });
  expect(await frame.locator(".capital-root").evaluate(el => el.scrollWidth <= el.clientWidth + 1)).toBe(true);
  await research.getByRole("region", { name: "南向净买入研究" }).screenshot({ path: info.outputPath("connect-mobile.png") });
  fail = true;
  await frame.getByRole("button", { name: "刷新", exact: true }).click();
  await expect(research).toContainText("保留快照不代表更新成功");
  await expect.poll(() => contexts.at(-1)?.data.summary.page.connectResearch.selectedWindow.southbound.current).toBe(false);
  await expect(momentum).toContainText("对照未确认");
  await expect(momentum).not.toContainText("净买入强度下降");
  await expect.poll(() => contexts.at(-1)?.data.summary.page.connectResearch.selectedWindow.southbound.momentum.current).toBe(false);
  expect(contexts.at(-1).data.summary.page.connectResearch.selectedWindow.southbound.momentum.recent.current).toBe(false);
  fail = false;
  const comparison = data.windows["5"].southbound.momentum;
  comparison.current = false;
  comparison.previous.current = false;
  comparison.previous.available = 4;
  comparison.missingDates = ["2026-09-23"];
  comparison.netChangeYi = null;
  comparison.intensityChangePp = null;
  comparison.turnoverRatio = null;
  await frame.getByRole("button", { name: "刷新", exact: true }).click();
  await expect(momentum).toContainText("近段 5/5、前段 4/5");
  await expect(momentum).toContainText("对照缺口：2026-09-23");
  await expect.poll(() => contexts.at(-1)?.data.summary.page.connectResearch.selectedWindow.southbound.current).toBe(true);
  expect(contexts.at(-1).data.summary.page.connectResearch.selectedWindow.southbound.momentum.current).toBe(false);
});

test("真实跨境历史：逐日官方买卖、日期及币种核验", async ({ page, request }, info) => {
  let data: any;
  for (let i = 0; i < 6; i++) {
    const response = await request.get(`${api}/api/capital-flow/connect-research`, { timeout: 60000 });
    expect(response.ok()).toBe(true); data = await response.json();
    if (!data.canContinue) break;
  }
  const south = data.windows["20"].southbound, north = data.windows["20"].northbound;
  expect(south.current).toBe(true); expect(north.current).toBe(true);
  expect(south.summary.netBuyYi).toBeCloseTo(south.summary.buyYi - south.summary.sellYi, 3);
  expect(north.summary.netBuyYi).toBeNull();
  expect(south.points).toHaveLength(20);
  expect(south.closedDays.length).toBeGreaterThan(0);
  expect(south.momentum.current).toBe(true);
  expect(south.momentum.recent.netIntensityPct).toBeCloseTo(south.momentum.recent.netBuyYi / south.momentum.recent.turnoverYi * 100, 6);
  expect(south.momentum.previous.end < south.momentum.recent.start).toBe(true);
  expect(north.momentum.recent.netBuyYi).toBeNull();
  expect(north.momentum.intensityChangePp).toBeNull();
  await page.goto(`${api}/mod-runtime/capital-flow/?view=cross-border&mod=capital-cross-border`);
  const research = page.getByRole("region", { name: "跨境资金历史研究" });
  await expect(research).toContainText("20/20日可用");
  await expect(research.getByRole("region", { name: "南向净买入研究" })).toContainText(south.asOf);
  await research.screenshot({ path: info.outputPath("connect-live.png") });
});

test("真实 HKEX 跨境快照：北向无净额，南向币种独立", async ({ page }, info) => {
  await page.goto(`${shell}/?mod=capital-cross-border&workspace=capital-live-${Date.now()}`);
  const frame = page.frameLocator('iframe[title="跨境资金"]');
  await expect(frame.locator(".connect-card")).toHaveCount(4);
  await expect(frame.locator(".connect-card").first()).toContainText("人民币亿元");
  await expect(frame.locator(".connect-card").first()).toContainText("不可计算");
  await expect(frame.locator(".connect-card").nth(2)).toContainText("港元亿元");
  await expect(frame.getByRole("status")).not.toContainText("正在读取");
  await expect(frame.locator(".connect-card").first()).toContainText(/\d[\d,]*\.\d+ 人民币亿元/);
  await frame.locator(".capital-root").screenshot({ path: info.outputPath("cross-border-live.png") });
});

test("ETF选择、观察窗口和缺失柱与Agent上下文一致", async ({ page }) => {
  const contexts: any[] = [];
  page.on("request", request => {
    if (request.method() === "PUT" && new URL(request.url()).pathname === "/api/mods/capital-etf/context") contexts.push(request.postDataJSON().context);
  });
  await page.route("**/api/capital-flow", route => route.fulfill({ json: fixture }));
  await page.goto(`${shell}/?mod=capital-etf&workspace=capital-etf-${Date.now()}`);
  const frame = page.frameLocator('iframe[title="ETF资金"]');
  await expect(frame.getByRole("heading", { name: "ETF 配置与申赎" })).toBeVisible();
  await expect(frame.locator("[data-flow-bar]")).toHaveCount(19);
  await expect(frame.getByRole("img", { name: "沪深300ETF申赎估算历史" })).toContainText("缺");
  await frame.getByRole("button", { name: /黄金ETF/ }).click();
  await frame.getByRole("button", { name: "60日", exact: true }).click();
  await expect(frame.locator("[data-flow-bar]")).toHaveCount(59);
  await expect.poll(() => contexts.at(-1)?.selection?.securityCode).toBe("518880.SH");
  await expect.poll(() => contexts.at(-1)?.filters?.historyDays).toBe(60);
  expect(contexts.at(-1).data.summary.page.research.selectedETF.code).toBe("518880.SH");
  expect(contexts.at(-1).data.summary.page.research.selectedETF.points).toHaveLength(60);
  expect(contexts.at(-1).data.summary.page.research.selectedETF.summary.flow5dYi).toBeNull();
});

test("ETF和资金总览研究独立加载，小屏表格不挤出页面", async ({ page }) => {
  await page.route("**/api/capital-flow/appetite-research**", route => route.fulfill({ status: 503 }));
  await page.route("**/api/capital-flow", route => route.fulfill({ status: 503, json: { detail: "行业服务不可用" } }));
  await page.setViewportSize({ width: 390, height: 900 });
  await page.goto(`${api}/mod-runtime/capital-flow/?view=etf&mod=capital-etf`);
  await expect(page.locator(".research-table")).toContainText("沪深300ETF");
  expect(await page.locator(".capital-root").evaluate(el => el.scrollWidth <= el.clientWidth)).toBe(true);
  await page.getByRole("button", { name: "资金总览", exact: true }).click();
  await expect(page.getByRole("region", { name: "资金决策总览" })).toContainText("研究证据未取得");
  await expect(page.locator(".research-metrics")).toHaveCount(0);
  expect(await page.locator(".capital-root").evaluate(el => el.scrollWidth <= el.clientWidth)).toBe(true);
});

test("真实ETF与沪深北融资：份额净值可追溯，缺失不冒充零", async ({ page }, info) => {
  const researchResponse = page.waitForResponse(response => new URL(response.url()).pathname === "/api/capital-flow/research" && response.ok());
  await page.goto(`${api}/mod-runtime/capital-flow/?view=etf&mod=capital-etf`);
  const research = await (await researchResponse).json() as CapitalResearch;
  await expect(page.locator(".research-table tbody tr")).toHaveCount(8);
  const row = page.locator(".research-table tbody tr").filter({ hasText: "510300.SH" });
  await expect(row).toContainText(/份额 \/ 净值齐备|保存历史|部分缺失/);
  await expect(row).toContainText(/2026-\d\d-\d\d/);
  await expect(page.locator(".research-source")).toContainText("Tushare");
  await expect(page.locator("[data-flow-bar]").first()).toBeVisible();
  await page.screenshot({ path: info.outputPath("etf-live.png"), fullPage: true });
  await page.getByRole("button", { name: "风险偏好", exact: true }).click();
  const balance = research.leverage.latest.balanceYi;
  await page.getByText("融资原始日明细与交易所覆盖", { exact: true }).click();
  await expect(page.locator(".appetite-leverage .appetite-stats b").first()).toHaveText(`${balance == null ? "--" : balance.toLocaleString("zh-CN", { maximumFractionDigits: 2 })}亿元`);
  if (balance == null) {
    expect(research.leverage.points.at(-1)?.complete).toBe(false);
    expect(research.leverage.summary.net1dYi).toBeNull();
  }
  await expect(page.locator(".appetite-leverage .research-table")).toContainText("BSE / SSE / SZSE");
  await page.screenshot({ path: info.outputPath("leverage-live.png"), fullPage: true });
});

test("板块分类与对象切换不带旧历史，筛选窗口同步Agent", async ({ page }) => {
  const contexts: any[] = [];
  let release!: () => void;
  const gate = new Promise<void>(resolve => { release = resolve; });
  page.on("request", request => {
    if (request.method() === "PUT" && new URL(request.url()).pathname === "/api/mods/capital-sectors/context") contexts.push(request.postDataJSON().context);
  });
  await page.route("**/api/capital-flow", route => route.fulfill({ json: fixture }));
  await page.route("**/api/capital-flow/sector-research**", async route => {
    const params = new URL(route.request().url()).searchParams;
    if (params.get("code") === "BK1329.DC") await gate;
    await route.fulfill({ json: sectorFixture(params.get("category") as SectorCategory, params.get("code") ?? undefined) });
  });
  await page.goto(`${shell}/?mod=capital-sectors&workspace=sector-research-${Date.now()}`);
  const frame = page.frameLocator("iframe").first();
  await expect(frame.getByRole("region", { name: "所选板块历史" })).toContainText("印制电路板");
  await frame.getByRole("button", { name: /集成电路制造/ }).click();
  await expect(frame.getByRole("region", { name: "所选板块历史" })).toHaveCount(0);
  await expect.poll(() => contexts.at(-1)?.selection?.sectorCode).toBe("BK1329.DC");
  expect(contexts.at(-1).data.summary.page.sectorResearch).toBeNull();
  release();
  await expect(frame.getByRole("region", { name: "所选板块历史" })).toContainText("集成电路制造");
  await frame.getByLabel("板块名称或代码").fill("集成");
  await expect(frame.locator(".sector-research-ranking tbody tr")).toHaveCount(1);
  await frame.getByRole("button", { name: "60日", exact: true }).click();
  await expect(frame.locator("[data-flow-bar]")).toHaveCount(59);
  await expect(frame.getByRole("img", { name: "集成电路制造大额订单净额历史" })).toContainText("缺");
  await expect.poll(() => contexts.at(-1)?.filters?.historyDays).toBe(60);
  expect(contexts.at(-1).data.summary.page.sectorResearch.selected.code).toBe("BK1329.DC");
  expect(contexts.at(-1).data.summary.page.sectorResearch.rowsMatched).toBe(1);
  await frame.getByRole("button", { name: "概念", exact: true }).click();
  await expect(frame.getByRole("region", { name: "所选板块历史" })).toContainText("光通信模块");
  await expect.poll(() => contexts.at(-1)?.filters?.category).toBe("concept");
  expect(contexts.at(-1).selection.sectorCode).toBe("BK1136.DC");
});

test("板块独立来源失败保留缺口，390px外层不溢出", async ({ page }) => {
  await page.route("**/api/capital-flow", route => route.fulfill({ status: 503, json: {} }));
  await page.route("**/api/capital-flow/sector-research**", route => route.fulfill({ json: sectorFixture() }));
  await page.setViewportSize({ width: 390, height: 900 });
  await page.goto(`${api}/mod-runtime/capital-flow/?view=sectors&mod=capital-sectors`);
  await expect(page.getByRole("region", { name: "所选板块历史" })).toContainText("印制电路板");
  expect(await page.locator(".capital-root").evaluate(el => el.scrollWidth <= el.clientWidth)).toBe(true);
  await expect(page.locator(".sector-pattern")).toContainText("证据不完整");
});

test("真实板块分类与历史：日频资金有原始日期和缺口边界", async ({ page }, info) => {
  await page.goto(`${api}/mod-runtime/capital-flow/?view=sectors&mod=capital-sectors`);
  await expect(page.locator(".sector-research-ranking tbody tr").first()).toBeVisible();
  await expect(page.getByRole("region", { name: "所选板块历史" })).toBeVisible();
  await expect(page.locator(".sector-history .research-metrics")).toContainText(/\d[\d,]*\.\d+/);
  await expect(page.locator("[data-flow-bar]").first()).toBeVisible();
  await expect(page.locator(".sector-research > .research-source")).toContainText("东财一级 · 层级按同日目录匹配");
  await expect(page.locator(".sector-research > .research-source")).toContainText("成分交叉未核验");
  await page.getByRole("button", { name: "概念", exact: true }).click();
  await expect(page.getByRole("status")).toContainText("概念板块");
  await expect(page.locator(".sector-research-ranking tbody tr").first()).toBeVisible();
  await page.screenshot({ path: info.outputPath("sector-history-live.png"), fullPage: true });
});

test("概念缺失不套用旧行业，也不伪造历史零值", async ({ page }) => {
  await page.route("**/api/capital-flow", route => route.fulfill({ json: { ...fixture, sectors: [{ name: "旧行业", net: 8, pct: 2 }] } }));
  await page.route("**/api/capital-flow/sector-research**", route => {
    const category = new URL(route.request().url()).searchParams.get("category") as SectorCategory;
    const data = sectorFixture(category);
    if (category === "concept") return route.fulfill({ json: { ...data, boards: [], selected: null,
      coverage: { ...data.coverage, status: "permission-denied", reason: "概念接口权限不足", classified: 0 } } });
    return route.fulfill({ json: data });
  });
  await page.goto(`${api}/mod-runtime/capital-flow/?view=sectors&mod=capital-sectors`);
  await expect(page.getByRole("region", { name: "所选板块历史" })).toBeVisible();
  await page.getByRole("button", { name: "概念", exact: true }).click();
  await expect(page.locator(".sector-research")).toContainText("概念接口权限不足");
  await expect(page.getByRole("region", { name: "所选板块历史" })).toHaveCount(0);
  await expect(page.locator(".capital-root")).not.toContainText("旧行业");
  await expect(page.locator("[data-flow-bar]")).toHaveCount(0);
});

test("行业层级切换清除旧选择，待核验不退回全层级，Agent同步层级", async ({ page }) => {
  const contexts: any[] = [];
  page.on("request", r => { if (r.method() === "PUT" && new URL(r.url()).pathname === "/api/mods/capital-sectors/context") contexts.push(r.postDataJSON().context); });
  await page.route("**/api/capital-flow/sector-research**", route => {
    const params = new URL(route.request().url()).searchParams, level = params.get("level") as "L1" | "L2" | "unknown";
    const data = sectorFixture(); data.level = level;
    data.boards = data.boards.map(row => ({ ...row, level }));
    data.classification = { source: "测试目录", url: "https://tushare.pro", status: "ready", reason: "", current: true, usingSaved: false,
      asOf: data.asOf, total: 4, matched: 4, counts: { L1: 2, L2: 2, L3: 0, unknown: 0 }, conflicts: 0, constituentsVerified: false, note: "同日匹配",
      selectedLevel: level, selectedCount: level === "unknown" ? 0 : 2 };
    if (level === "unknown") { data.boards = []; data.selected = null; }
    return route.fulfill({ json: data });
  });
  await page.goto(`${shell}/?mod=capital-sectors&workspace=levels-${Date.now()}`);
  const frame = page.frameLocator("iframe").first();
  await expect(frame.getByRole("button", { name: "东财一级", exact: true })).toHaveAttribute("aria-pressed", "true");
  await expect(frame.locator(".sector-research-ranking tbody tr")).toHaveCount(2);
  await frame.getByRole("button", { name: "东财二级", exact: true }).click();
  await expect.poll(() => contexts.at(-1)?.filters.sectorLevel).toBe("L2");
  await expect(frame.locator(".sector-research-ranking tbody tr").first()).toContainText("东财二级");
  expect(contexts.at(-1).data.summary.page.sectorResearch.level).toBe("L2");
  await frame.getByRole("button", { name: "待核验", exact: true }).click();
  await expect.poll(() => contexts.at(-1)?.filters.sectorLevel).toBe("unknown");
  await expect(frame.locator(".sector-research-ranking tbody tr")).toHaveCount(0);
  await expect(frame.getByRole("region", { name: "所选板块历史" })).toHaveCount(0);
  expect(contexts.at(-1).data.summary.page.sectorResearch.boards).toHaveLength(0);
});
