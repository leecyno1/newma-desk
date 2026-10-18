import { expect, test, type Page } from "@playwright/test";
import { readFile } from "node:fs/promises";
import type { PolicyDashboard, PolicyDocument, PolicyEvent } from "../../modules/policy-analysis/src/types";

const shell = process.env.VIBE_E2E_DOMAIN_SUITES_ORIGIN || "http://127.0.0.1:5888";
const api = process.env.VIBE_E2E_DOMAIN_SUITES_API_ORIGIN || "http://127.0.0.1:8911";
const officialUrl = "https://www.gov.cn/zhengce/content/202508/content_7037861.htm";

test("真实人工智能政策：导入、底稿、上下文与导出一致", async ({ page }, info) => {
  test.skip(process.env.POLICY_E2E_LIVE !== "1", "Opt-in: saves a real public policy document, never holdings or trades");
  const contexts: any[] = [];
  const modelRequests: string[] = [];
  page.on("request", (request) => {
    const path = new URL(request.url()).pathname;
    if (request.method() === "PUT" && path === "/api/mods/policy-interpretation/context") contexts.push(request.postDataJSON().context);
    if (request.method() === "POST" && /copilot\/(ask|chat|stream)|agent-tasks/.test(path)) modelRequests.push(path);
  });
  await page.goto(`${shell}/?mod=policy-interpretation&workspace=e2e-policy-live-${Date.now()}`);
  const frame = page.frameLocator('iframe[title="政策解读"]');
  await frame.getByLabel("官方政策链接").fill(officialUrl);
  await frame.getByRole("button", { name: "导入官方政策", exact: true }).click();
  await expect(frame.locator(".interpretation-header")).toContainText("人工智能+");
  const evidence = frame.getByRole("region", { name: "官方正文证据" });
  await expect(evidence).toContainText("2025-08-21");
  await expect(evidence).toContainText("2025-08-26");
  await expect(evidence).toContainText("未明确，不默认视为已生效");
  await frame.getByRole("button", { name: "生成研究底稿", exact: true }).click();
  await expect(frame.locator(".transmission-row")).toContainText(["财政", "技术", "绿色"]);
  await expect.poll(() => contexts.at(-1)?.data?.summary?.ruleAnalysis?.reviewStatus).toBe("unreviewed");
  const context = contexts.at(-1);
  expect(context.data.summary.officialDocument.text).toContain("人工智能");
  expect(context.data.summary.ruleAnalysis.transmission.some((row: any) => row.id === "technology")).toBe(true);
  expect(context.data.summary.ruleAnalysis.document).toBeUndefined(); // Full text is sent once, not duplicated.
  expect(modelRequests).toEqual([]); // Generating a deterministic baseline does not silently call a model.
  const downloadPromise = page.waitForEvent("download");
  await frame.getByRole("button", { name: "导出研究底稿" }).click();
  const download = await downloadPromise;
  const artifact = JSON.parse(await readFile((await download.path())!, "utf8"));
  expect(artifact.schemaVersion).toBe("newma-desk.policy-research.v1");
  expect(artifact.document.revision).toBe(context.data.summary.officialDocument.revision);
  expect(artifact.reviewStatus).toBe("unreviewed");
  expect(artifact.transcriptComparison.status).toBe("unavailable"); // One real document is not a version pair.
  await frame.getByLabel("研究跟踪结论").fill("验收记录：技术政策传导待验证，不直接触发组合告警。");
  await frame.getByLabel("政策验证观察").fill("后续核验财政支持的实际执行与企业订单证据。");
  await frame.getByLabel("下一复核日期").fill("2026-11-01");
  await frame.getByRole("button", { name: "保存跟踪与底稿", exact: true }).click();
  await expect(frame.getByRole("region", { name: "政策研究跟踪" })).toContainText("已保存到当前用户与工作区");
  await frame.locator(".interpretation-pane").screenshot({ path: info.outputPath("real-policy-research.png") });
  await page.reload();
  await frame.getByPlaceholder("搜索政策、机构、行业").fill("人工智能+");
  await frame.getByRole("button", { name: /国务院关于深入实施“人工智能\+”行动的意见/ }).click();
  await expect(evidence).toContainText("2025-08-21");
  await expect(frame.getByLabel("下一复核日期")).toHaveValue("2026-11-01");
  await expect(frame.getByLabel("研究跟踪结论")).toHaveValue("验收记录：技术政策传导待验证，不直接触发组合告警。");
  await frame.getByRole("button", { name: "查看已保存底稿" }).click();
  await expect(frame.locator(".transmission-row")).toContainText(["财政", "技术", "绿色"]);
  await expect.poll(() => contexts.at(-1)?.data?.summary?.researchFollowup?.nextReview).toBe("2026-11-01");
});

const event: PolicyEvent = {
  id: "policy-test-a", title: "测试政策条例 A", date: "2026-09-24", institution: "测试官方源", category: "产业政策",
  level: 2, status: "published", certainty: "official", summary: "测试摘要，非真实政策", rationale: ["测试量级判断"],
  sourceUrl: "https://www.gov.cn/test-a", marketScope: ["测试行业"], assessmentConfidence: .7, assessmentStatus: "machine",
  documentType: "formal-policy", lifecycleStage: "published", policySeriesKey: "test-a", relatedPolicyIds: [], entities: [], comparison: null,
};
const document: PolicyDocument = {
  status: "available", sourceUrl: event.sourceUrl, title: event.title, revision: 77,
  issuer: "测试机关", publishedAt: "2026-09-24", issuedAt: "2026-09-19", effectiveAt: "2026-12-01",
  effectiveDateQuote: "本测试条例自2026年12月1日起施行。", fetchedAt: "2026-10-13T01:00:00Z",
  text: "测试正文 A，不是真实政策。", paragraphs: ["测试正文 A，不是真实政策。"], note: "合成测试证据", attachments: [],
};
const dashboard: PolicyDashboard = {
  schemaVersion: "newma-desk.policy-analysis.v1", generatedAt: "2026-10-13T02:00:00Z", today: "2026-10-13",
  events: [event, { ...event, id: "policy-test-b", title: "测试政策条例 B", sourceUrl: "https://www.gov.cn/test-b" }],
  sources: [{ id: "gov", name: "测试官方源", url: "https://www.gov.cn/", categories: ["产业政策"], rssHubPath: "/test" }],
  summary: { total: 2, level3: 0, upcoming: 0, nextDate: null, lifecycle: { scheduled: 0, solicitation: 0, published: 2, effective: 0, amended: 0, adjusted: 0, repealed: 0, expired: 0 } },
  assessment: [], collector: { foundation: "测试采集", revision: "test", mode: "cache", status: "degraded", note: "合成测试",
    collectedAt: "2026-10-13T01:00:00Z", feeds: [{ sourceId: "gov", status: "failed", items: 0, lastSuccessAt: "2026-09-01T01:00:00Z", lastAttemptAt: "2026-10-13T01:00:00Z", reason: "测试源不可用" }] },
};

async function mockEvidence(page: Page) {
  await page.route("**/api/policy-analysis", (route) => route.fulfill({ json: dashboard }));
  await page.route("**/api/policy-analysis/events/*/document", (route) => {
    if (route.request().method() === "POST") return route.fulfill({ status: 502, json: { detail: "测试官方来源读取失败" } });
    return route.fulfill({ json: route.request().url().includes("policy-test-b") ? { status: "missing", note: "无正文" } : document });
  });
}

test("正文读取失败保留旧证据，并同步错误给 Desk 上下文", async ({ page }) => {
  await mockEvidence(page);
  const contexts: any[] = [];
  page.on("request", (request) => {
    if (request.method() === "PUT" && new URL(request.url()).pathname === "/api/mods/policy-interpretation/context") contexts.push(request.postDataJSON().context);
  });
  await page.goto(`${shell}/?mod=policy-interpretation&workspace=e2e-policy-errors-${Date.now()}`);
  const frame = page.frameLocator('iframe[title="政策解读"]');
  const panel = frame.getByRole("region", { name: "官方正文证据" });
  await expect(panel).toContainText("2026-09-19");
  await frame.getByRole("button", { name: "重新抓取正文" }).click();
  await expect(panel.getByRole("alert")).toContainText("测试官方来源读取失败");
  await expect(panel).toContainText("2026-09-19");
  await expect.poll(() => contexts.at(-1)?.data?.summary?.documentRead?.status).toBe("failed");
  expect(contexts.at(-1)?.data?.freshness).toBe("stale");
  expect(contexts.at(-1)?.data?.asOf).toBe(dashboard.collector.collectedAt);
  await frame.getByRole("button", { name: /测试政策条例 B/ }).click();
  await expect(panel).toContainText("尚无正文证据");
  await expect.poll(() => contexts.at(-1)?.selection?.policyId).toBe("policy-test-b");
  expect(contexts.at(-1)?.data?.summary?.officialDocument?.text).toBeUndefined();
  expect(contexts.at(-1)?.data?.summary?.documentRead?.error).toBeNull();
});

test("独立页展示真实日期分层，不强制连接 Newma", async ({ page }) => {
  await mockEvidence(page);
  await page.goto(`${api}/mod-runtime/policy-analysis/?view=interpretation&mod=policy-interpretation`);
  await expect(page.getByRole("region", { name: "官方正文证据" })).toContainText("2026-12-01");
  await expect(page.getByText("AI 分析需从 Newma 中打开。", { exact: true })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "生成研究底稿", exact: true })).toBeEnabled();
  await expect(page.locator(".collection-health")).toContainText("0/1");
  expect(await page.locator(".policy-root").evaluate((element) => element.scrollWidth <= element.clientWidth)).toBe(true);
});

test("政策四个 Desk 入口可用，标题与子视图一致", async ({ page }) => {
  for (const [id, name] of [["policy-calendar", "政策日历"], ["policy-flow", "政策流"], ["policy-interpretation", "政策解读"], ["policy-analysis", "政策渠道"]]) {
    await page.goto(`${shell}/?mod=${id}&workspace=e2e-policy-smoke-${Date.now()}`);
    const frame = page.frameLocator(`iframe[title="${name}"]`);
    await expect(frame.locator(".policy-root")).toBeVisible();
    await expect(frame.locator("h1")).toHaveCount(0);
    await expect(frame.locator(".segmented")).toHaveCount(0);
    await expect(frame.locator(".collection-health")).toContainText("刷新页面不代表政策已更新");
    if (id === "policy-analysis") await expect(frame.getByRole("heading", { name: "官方来源与采集状态" })).toBeVisible();
  }
});

test("日历默认当前月，发布与施行分离且空月不选取别月政策", async ({ page }) => {
  await mockEvidence(page);
  await page.route("**/api/policy-analysis", (route) => route.fulfill({ json: {
    ...dashboard, events: [{ ...event, documentEvidence: document }],
  } }));
  const contexts: any[] = [];
  page.on("request", (request) => {
    if (request.method() === "PUT" && new URL(request.url()).pathname === "/api/mods/policy-calendar/context") contexts.push(request.postDataJSON().context);
  });
  await page.goto(`${shell}/?mod=policy-calendar&workspace=e2e-policy-calendar-${Date.now()}`);
  const frame = page.frameLocator('iframe[title="政策日历"]');
  await expect(frame.getByLabel("政策月份")).toHaveValue("2026-10");
  await expect(frame.locator(".detail-pane")).toContainText("选择一条政策");
  await frame.getByLabel("政策月份").fill("2026-12");
  await expect(frame.locator(".calendar-event")).toContainText("明确施行");
  await expect(frame.locator(".detail-pane")).toContainText("2026-12-01");
  await expect.poll(() => contexts.at(-1)?.filters?.selectedDate?.kind).toBe("effective");
  expect(contexts.at(-1).selection.date).toBe("2026-09-24");
  await frame.getByRole("button", { name: "议程", exact: true }).click();
  await expect(frame.locator(".calendar-agenda")).toContainText("12-01");
  await frame.getByRole("button", { name: "发布记录", exact: true }).click();
  await expect(frame.locator(".detail-pane")).toContainText("选择一条政策");
  await expect.poll(() => contexts.at(-1)?.selection?.policyId).toBeUndefined();
});

test("政策流日期和正文筛选与页面上下文一致", async ({ page }) => {
  await mockEvidence(page);
  await page.route("**/api/policy-analysis", (route) => route.fulfill({ json: {
    ...dashboard, events: [{ ...event, documentEvidence: document }, { ...event, id: "policy-old", date: "2019-10-01", title: "历史政策" }],
  } }));
  const contexts: any[] = [];
  page.on("request", (request) => {
    if (request.method() === "PUT" && new URL(request.url()).pathname === "/api/mods/policy-flow/context") contexts.push(request.postDataJSON().context);
  });
  await page.goto(`${shell}/?mod=policy-flow&workspace=e2e-policy-feed-${Date.now()}`);
  const frame = page.frameLocator('iframe[title="政策流"]');
  await expect(frame.locator(".policy-row")).toHaveCount(1);
  await frame.getByLabel("发布范围").selectOption("0");
  await expect(frame.locator(".policy-row")).toHaveCount(2);
  await frame.getByLabel("已有正文").check();
  await expect(frame.locator(".policy-row")).toHaveCount(1);
  await expect.poll(() => contexts.at(-1)?.filters?.evidenceOnly).toBe(true);
  expect(contexts.at(-1).filters.visiblePolicyIds).toEqual([event.id]);
});

test("渠道覆盖不把标题当正文，小屏保留失败与最近成功状态", async ({ page }) => {
  await mockEvidence(page);
  await page.setViewportSize({ width: 700, height: 850 });
  await page.goto(`${api}/mod-runtime/policy-analysis/?view=sources&mod=policy-analysis`);
  await expect(page.locator(".source-coverage")).toContainText("0 / 2");
  await expect(page.locator(".source-adapter")).toBeVisible();
  await page.getByText("查看失败原因", { exact: true }).click();
  await expect(page.locator(".source-adapter")).toContainText("测试源不可用");
});

test("研究跟踪遇到版本冲突保留草稿，不自动覆盖", async ({ page }) => {
  await mockEvidence(page);
  const report = {
    policyId: event.id, title: event.title, sourceUrl: event.sourceUrl, mode: "rule", document,
    transmission: [], impactAnalysis: { facts: [], inferences: [], uncertainties: [] },
    historicalComparison: { matchedPolicies: [], added: [], removed: [], shared: [], note: "合成测试" },
    transcriptComparison: { status: "unavailable", basis: "none", note: "合成测试" },
  };
  await page.route("**/api/policy-analysis/events/*/interpretation", (route) => route.fulfill({ json: report }));
  await page.route("**/api/mods/policy-interpretation/storage/policy-research/*", (route) => route.fulfill({
    status: route.request().method() === "PUT" ? 409 : 404, json: { detail: "test revision conflict" },
  }));
  await page.goto(`${shell}/?mod=policy-interpretation&workspace=e2e-policy-conflict-${Date.now()}`);
  const frame = page.frameLocator('iframe[title="政策解读"]');
  await frame.getByRole("button", { name: "生成研究底稿", exact: true }).click();
  await frame.getByLabel("研究跟踪结论").fill("我的研究草稿");
  await frame.getByRole("button", { name: "保存跟踪与底稿", exact: true }).click();
  await expect(frame.getByRole("region", { name: "政策研究跟踪" }).getByRole("alert")).toContainText("本页草稿保留");
  await expect(frame.getByLabel("研究跟踪结论")).toHaveValue("我的研究草稿");
});
