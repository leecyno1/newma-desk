import { expect, test, type Page } from "@playwright/test";

const shellOrigin = process.env.VIBE_E2E_SHELL_ORIGIN || "http://127.0.0.1:5888";
const apiOrigin = process.env.VIBE_E2E_API_ORIGIN || "http://127.0.0.1:8911";

function embeddedWorkspace(page: Page, modId: string) {
  return page.locator(`[data-vibedesk-mod-id="${modId}"]`);
}

function workspaceTitle(page: Page, modId: string) {
  return embeddedWorkspace(page, modId).locator(".frame-toolbar-heading h1");
}

function collectConsoleErrors(page: Page) {
  const errors: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error") errors.push(message.text());
  });
  page.on("pageerror", (error) => errors.push(error.message));
  return errors;
}

test.describe("Newma-Desk chart workspace Mods", () => {
  test("uses global intelligence as the Desk landing page and keeps Market trading-only", async ({ page }, testInfo) => {
    const errors = collectConsoleErrors(page);
    await page.addInitScript(() => {
      localStorage.removeItem("vibedesk.sidebarNavigation.v1");
      localStorage.removeItem("vibedesk.moduleCategories.v1");
    });
    await page.goto(shellOrigin);

    const navigation = page.getByRole("navigation", { name: "Newma-Desk Mod 导航" });
    const intelligenceProject = navigation.getByRole("button", { name: "全球 项目", exact: true });
    await expect(intelligenceProject).toHaveAttribute("aria-current", "page");
    const intelligenceSecondary = page.getByRole("complementary", { name: "全球 二级导航" });
    await expect(intelligenceSecondary).toBeVisible();
    for (const label of ["全球情报", "新闻与舆情", "催化剂日历", "联储加息", "美伊战争", "中美贸易"]) {
      await expect(intelligenceSecondary.getByRole("button", { name: label, exact: true })).toBeVisible();
    }
    const globalSituation = embeddedWorkspace(page, "global-situation");
    await expect(globalSituation).toHaveAttribute("data-vibedesk-frame-state", "ready");
    await expect(globalSituation.getByText("全球情报", { exact: true }).first()).toBeVisible();
    await expect(globalSituation.getByLabel("全球情报地图")).toBeVisible();
    await expect(globalSituation.locator(".intel-hud")).toContainText("综合风险");
    const dataUpdateCard = globalSituation.locator(".intel-health-card");
    await expect(dataUpdateCard).toContainText(/\d+\/\d+/, { timeout: 120_000 });
    await expect(dataUpdateCard).not.toContainText("等待更新");
    await expect(globalSituation.locator(".intel-live-state")).not.toHaveAttribute("data-status", "connecting");
    const firstEvent = globalSituation.locator(".intel-event-list article").first();
    const settledEmpty = globalSituation.locator('.intel-empty[data-state="settled"]');
    await expect(firstEvent.or(settledEmpty)).toBeVisible();
    if (await settledEmpty.isVisible()) {
      await expect(settledEmpty).toContainText("数据已结算，暂无实时事件");
      await expect(settledEmpty).toContainText(/\d+\/\d+ 个数据任务已完成/);
    }

    const presetButton = globalSituation.getByRole("button", { name: /态势：/ });
    await expect(presetButton).toContainText("态势：综合");
    await presetButton.click();
    await globalSituation.getByRole("menuitem").filter({ hasText: "冲突" }).click();
    await expect(presetButton).toContainText("态势：冲突");
    await expect(globalSituation.getByRole("button", { name: "7 天" })).toHaveAttribute("aria-pressed", "true");
    await expect(globalSituation.getByRole("button", { name: "仅高优先级" })).toHaveAttribute("aria-pressed", "true");
    await expect(globalSituation.getByRole("button", { name: "热力" })).toHaveAttribute("aria-pressed", "true");
    await globalSituation.getByRole("button", { name: "24 小时" }).click();
    await expect(presetButton).toContainText("态势：手动");
    await presetButton.click();
    await globalSituation.getByRole("menuitem").filter({ hasText: "综合" }).click();

    await globalSituation.locator(".intel-health-card").getByRole("button", { name: "详情" }).click();
    const healthConsole = globalSituation.getByRole("complementary", { name: "数据源健康控制台" });
    await expect(healthConsole).toBeVisible();
    await expect(healthConsole).toContainText("有效缓存");
    await globalSituation.getByRole("button", { name: "关闭数据源健康控制台" }).click();

    await globalSituation.locator(".intel-risk-card").getByRole("button", { name: "研判" }).click();
    const strategicBriefing = globalSituation.getByRole("complementary", { name: "全球态势研判" });
    await expect(strategicBriefing).toBeVisible();
    await expect(strategicBriefing).toContainText("风险域分布");
    await expect(strategicBriefing).toContainText("当前研判");
    await expect(strategicBriefing).toContainText("活跃告警");
    await globalSituation.getByRole("button", { name: "关闭全球态势研判" }).click();

    await globalSituation.locator(".intel-priority-card").getByRole("button", { name: "趋势" }).click();
    const trendRadar = globalSituation.getByRole("complementary", { name: "时间趋势雷达" });
    await expect(trendRadar).toBeVisible();
    await expect(trendRadar).toContainText("活跃基线异常");
    await expect(trendRadar).toContainText("高波动指标");
    await expect(trendRadar).toContainText("空间信号汇聚");
    await trendRadar.getByRole("button", { name: /中东/ }).click();
    await expect(globalSituation.locator(".intel-map-focus-chip")).toContainText("中东");
    await globalSituation.locator(".intel-map-focus-chip").click();

    await navigation.getByRole("button", { name: "市场 项目", exact: true }).click();
    const marketSecondary = page.getByRole("complementary", { name: "市场 二级导航" });
    await expect(marketSecondary).toBeVisible();
    await expect(marketSecondary.locator(".module-button")).toHaveCount(9);
    await expect(marketSecondary.locator(".module-button").first()).toHaveText("行情");
    await expect(marketSecondary.getByRole("button", { name: "日线时间轴", exact: true })).toBeVisible();
    await expect(marketSecondary.getByRole("button", { name: "全球情报", exact: true })).toHaveCount(0);
    await expect(embeddedWorkspace(page, "market-daily")).toHaveAttribute("data-vibedesk-frame-state", "ready");
    await page.screenshot({
      path: testInfo.outputPath("global-intelligence-cockpit.png"),
      fullPage: true,
    });

    expect(errors).toEqual([]);
  });

  test("grants every embedded workspace the market data actions it uses", async ({ page }) => {
    const errors = collectConsoleErrors(page);
    const workspaces = [
      ["market-sentiment", "情绪分析"],
      ["market-technical", "技术分析"],
      ["multi-timeframe", "多周期分析"],
      ["relative-strength", "强弱对比"],
      ["event-timeline", "日线时间轴"],
      ["trading-replay", "复盘回放"],
    ] as const;

    for (const [modId, title] of workspaces) {
      await page.goto(`${shellOrigin}/?mod=${modId}`);
      const workspace = embeddedWorkspace(page, modId);
      await expect(workspace).toHaveAttribute("data-vibedesk-frame-state", "ready");
      await expect(workspaceTitle(page, modId)).toHaveText(title);
      await expect(workspace.locator(".workspace-current-price strong")).toHaveText(/\d/);
      await expect(workspace.getByText("Action is not granted", { exact: false })).toHaveCount(0);
    }

    expect(errors).toEqual([]);
  });

  test("renders current shared-runtime workspaces with working primary interactions", async ({ page }) => {
    const errors = collectConsoleErrors(page);

    await page.goto(`${shellOrigin}/?mod=market-sentiment`);
    const sentiment = embeddedWorkspace(page, "market-sentiment");
    await expect(sentiment.getByText("情绪分析", { exact: true }).first()).toBeVisible();
    await expect(sentiment.getByText("市场宽度", { exact: true })).toBeVisible();
    await sentiment.getByRole("button", { name: "中芯国际", exact: true }).click();
    await expect(sentiment.locator(".workspace-current-security")).toContainText("688981");

    await page.goto(`${shellOrigin}/?mod=market-technical`);
    const technical = embeddedWorkspace(page, "market-technical");
    await expect(technical.getByText("技术分析", { exact: true }).first()).toBeVisible();
    await expect(technical.getByText("趋势与波动", { exact: true })).toBeVisible();
    await technical.getByRole("button", { name: "中际旭创", exact: true }).click();
    await expect(technical.locator(".workspace-current-security")).toContainText("300308");

    await page.goto(`${shellOrigin}/?mod=multi-timeframe`);
    const multiTimeframe = embeddedWorkspace(page, "multi-timeframe");
    await expect(multiTimeframe.getByText("多周期分析", { exact: true }).first()).toBeVisible();
    await expect(multiTimeframe.locator('[aria-label$="K 线图"]')).toHaveCount(4);
    await multiTimeframe.getByRole("button", { name: "MACD" }).click();
    await expect(multiTimeframe.getByRole("button", { name: "MACD" })).toHaveAttribute("aria-pressed", "true");

    await page.goto(`${shellOrigin}/?mod=relative-strength`);
    const relativeStrength = embeddedWorkspace(page, "relative-strength");
    await expect(workspaceTitle(page, "relative-strength")).toHaveText("强弱对比");
    await expect(relativeStrength.getByRole("img", { name: "相对强弱走势" })).toBeVisible();
    await expect(relativeStrength.getByText("阶段排名", { exact: true })).toBeVisible();

    await page.goto(`${shellOrigin}/?mod=event-timeline`);
    const eventTimeline = embeddedWorkspace(page, "event-timeline");
    await expect(eventTimeline.getByText("日线时间轴", { exact: true }).first()).toBeVisible();
    await expect(eventTimeline.getByLabel("日线时间轴 K 线图")).toBeVisible();
    await expect(eventTimeline.getByRole("group", { name: "事件筛选" })).toBeVisible();

    await page.goto(`${shellOrigin}/?mod=trading-replay`);
    const tradingReplay = embeddedWorkspace(page, "trading-replay");
    await expect(workspaceTitle(page, "trading-replay")).toHaveText("复盘回放");
    await expect(tradingReplay.getByText(/未来数据已隐藏/)).toBeVisible();
    await tradingReplay.getByRole("button", { name: "模拟买入" }).click();
    await expect(tradingReplay.getByText("决策次数").locator("..")).toContainText("1");
    await expect(tradingReplay.getByRole("button", { name: "模拟卖出" })).toBeEnabled();

    expect(errors).toEqual([]);
  });

  test("loads stock, ETF and open fund timelines from code or name search", async ({ page }) => {
    const errors = collectConsoleErrors(page);
    await page.goto(`${shellOrigin}/?mod=event-timeline`);
    const workspace = embeddedWorkspace(page, "event-timeline");
    const search = workspace.getByRole("textbox", { name: "搜索证券" });
    const currentSecurity = workspace.locator(".workspace-current-security");
    const timelineCount = workspace.locator(".event-chart-panel .workspace-section-title small");

    const selectSecurity = async (query: string, code: string) => {
      await search.fill(query);
      const result = workspace.getByRole("listbox").getByRole("button").filter({ hasText: code }).first();
      await expect(result).toBeVisible({ timeout: 30_000 });
      await result.click();
      await expect(currentSecurity).toContainText(code);
      await expect(timelineCount).not.toHaveText("等待数据", { timeout: 30_000 });
      await expect(workspace.locator(".workspace-error-banner")).toHaveCount(0);
      await expect(workspace.locator(".workspace-update-note.workspace-error")).toHaveCount(0);
    };

    await selectSecurity("zjxc", "300308");
    await expect(currentSecurity.locator("i")).toHaveText("CN");

    await selectSecurity("00981", "00981");
    await expect(currentSecurity.locator("i")).toHaveText("HK");

    await selectSecurity("AAPL", "AAPL");
    await expect(currentSecurity.locator("i")).toHaveText("US");

    await selectSecurity("510300", "510300");
    await expect(currentSecurity.locator("i")).toHaveText("ETF");
    await expect(workspace.getByText("ETF 日线事件", { exact: true })).toBeVisible();

    await selectSecurity("易方达消费", "110022");
    await expect(currentSecurity.locator("i")).toHaveText("基金");
    await expect(workspace.getByText("基金净值事件", { exact: true })).toBeVisible();
    await expect(workspace.getByText("data service upstream failed", { exact: false })).toHaveCount(0);
    expect(errors).toEqual([]);
  });

  test("repairs a previously cached stock that was misclassified as an open fund", async ({ page }) => {
    const errors = collectConsoleErrors(page);
    await page.addInitScript(() => {
      localStorage.setItem("vibedesk.event-timeline.security.v1", JSON.stringify({
        symbol: "300308",
        name: "中际旭创",
        market: "CN",
        exchange: "OTC",
        assetType: "fund",
      }));
    });

    await page.goto(`${shellOrigin}/?mod=event-timeline`);
    const workspace = embeddedWorkspace(page, "event-timeline");
    const currentSecurity = workspace.locator(".workspace-current-security");

    await expect(currentSecurity).toContainText("中际旭创");
    await expect(currentSecurity).toContainText("300308 · SZ", { timeout: 30_000 });
    await expect(currentSecurity.locator("i")).toHaveText("CN");
    await expect(workspace.getByText("基金", { exact: true })).toHaveCount(0);
    await expect(workspace.getByText("data service upstream failed", { exact: false })).toHaveCount(0);
    await expect(workspace.locator(".event-chart-panel .workspace-section-title small")).not.toHaveText("等待数据", {
      timeout: 30_000,
    });
    await expect.poll(async () => workspace.evaluate(() => {
      const saved = localStorage.getItem("vibedesk.event-timeline.security.v1");
      return saved ? JSON.parse(saved) : null;
    })).toMatchObject({ symbol: "300308", exchange: "SZ", assetType: "stock" });
    expect(errors).toEqual([]);
  });

  test("replays security selection into another Mod and persists structured Agent context", async ({ page, request }) => {
    const errors = collectConsoleErrors(page);
    await page.goto(`${shellOrigin}/?mod=market-sentiment`);
    const sentiment = embeddedWorkspace(page, "market-sentiment");
    await expect(sentiment.getByText("情绪分析", { exact: true }).first()).toBeVisible();
    await sentiment.getByRole("button", { name: "中芯国际", exact: true }).click();

    await page
      .locator('[data-module-id="multi-timeframe"] .module-button')
      .click();
    const multi = embeddedWorkspace(page, "multi-timeframe");
    await expect(multi.getByText("中芯国际", { exact: true }).first()).toBeVisible();
    await page.getByRole("button", { name: "问当前 Mod" }).click();
    await expect(page.getByRole("complementary", { name: "多周期分析 Agent" })).toBeVisible();

    await expect.poll(async () => {
      return page.evaluate(() => ({
        userId: localStorage.getItem("vibedesk.userId.v1"),
        workspaceId: localStorage.getItem("vibedesk.workspaceId.v1"),
      }));
    }).toMatchObject({ userId: expect.any(String), workspaceId: expect.any(String) });

    const identity = await page.evaluate(() => ({
      userId: localStorage.getItem("vibedesk.userId.v1") || "",
      workspaceId: localStorage.getItem("vibedesk.workspaceId.v1") || "",
    }));
    let saved: Record<string, any> | undefined;
    await expect.poll(async () => {
      const response = await request.get(`${apiOrigin}/api/mods/multi-timeframe/context`, {
        headers: {
          "X-User-Id": identity.userId,
          "X-Workspace-Id": identity.workspaceId,
        },
      });
      if (!response.ok()) return undefined;
      const body = await response.json();
      if (body?.context?.selection?.symbol === "688981") saved = body;
      return body?.context?.selection;
    }).toMatchObject({ symbol: "688981", name: "中芯国际", market: "CN" });
    expect(saved).toBeDefined();
    expect(saved?.context.view).toEqual({ id: "multi-timeframe", title: "多周期分析" });
    expect(saved?.context.selection).toMatchObject({ symbol: "688981", name: "中芯国际", market: "CN" });
    expect(saved?.context.filters).toMatchObject({ workspace: "multi-timeframe" });
    expect(saved?.context.visibleBlocks).toEqual(expect.arrayContaining([
      expect.objectContaining({ id: "multi-chart-grid", type: "klinechart-grid" }),
    ]));
    expect(errors).toEqual([]);
  });

  test("keeps market sentiment usable at a narrow viewport", async ({ page }) => {
    const errors = collectConsoleErrors(page);
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto(`${shellOrigin}/?mod=market-sentiment`);
    const sentiment = embeddedWorkspace(page, "market-sentiment");
    await expect(sentiment.getByText("情绪分析", { exact: true }).first()).toBeVisible();
    await expect(sentiment.getByText("市场宽度", { exact: true })).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    expect(errors).toEqual([]);
  });
});
