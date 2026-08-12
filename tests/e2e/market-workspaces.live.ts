import { expect, test, type Page } from "@playwright/test";

const shellOrigin = process.env.VIBE_E2E_SHELL_ORIGIN || "http://127.0.0.1:5888";
const apiOrigin = process.env.VIBE_E2E_API_ORIGIN || "http://127.0.0.1:8911";

function embeddedWorkspace(page: Page, modId: string) {
  return page.locator(`[data-vibedesk-mod-id="${modId}"]`);
}

function workspaceTitle(page: Page, modId: string) {
  return embeddedWorkspace(page, modId).locator(".workspace-title strong");
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
    const intelligenceProject = navigation.getByRole("button", { name: "情报 项目", exact: true });
    await expect(intelligenceProject).toHaveAttribute("aria-current", "page");
    const intelligenceSecondary = page.getByRole("complementary", { name: "情报 二级导航" });
    await expect(intelligenceSecondary).toBeVisible();
    for (const label of ["全球情报", "新闻与舆情", "个股事件轴", "催化剂日历"]) {
      await expect(intelligenceSecondary.getByRole("button", { name: label, exact: true })).toBeVisible();
    }
    const globalSituation = embeddedWorkspace(page, "global-situation");
    await expect(globalSituation).toHaveAttribute("data-vibedesk-frame-state", "ready");
    await expect(globalSituation.getByText("全球情报", { exact: true }).first()).toBeVisible();
    await expect(globalSituation.getByLabel("全球情报地图")).toBeVisible();
    await expect(globalSituation.locator(".intel-hud")).toContainText("综合风险");
    await expect(globalSituation.locator(".intel-event-list article").first()).toBeVisible();
    await expect(globalSituation.locator(".intel-load-card strong")).toHaveText("47/47", { timeout: 120_000 });

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
    await expect(marketSecondary.locator(".module-button")).toHaveCount(5);
    await expect(marketSecondary.locator(".module-button").first()).toHaveText("终端");
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
      ["market-scanner", "市场扫描器"],
      ["multi-timeframe", "多周期看盘"],
      ["relative-strength", "相对强弱地图"],
      ["event-timeline", "事件时间轴"],
      ["trading-replay", "交易回放室"],
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

  test("renders all five shared-runtime workspaces with working primary interactions", async ({ page }) => {
    const errors = collectConsoleErrors(page);

    await page.goto(`${shellOrigin}/?mod=market-scanner`);
    const scanner = embeddedWorkspace(page, "market-scanner");
    await expect(scanner.getByText("市场扫描器", { exact: true })).toBeVisible();
    await expect(scanner.getByRole("table")).toBeVisible();
    await scanner.getByRole("button", { name: /趋势走强/ }).click();
    await expect(scanner.getByText(/个候选/).first()).toBeVisible();

    await page.goto(`${shellOrigin}/?mod=multi-timeframe`);
    const multiTimeframe = embeddedWorkspace(page, "multi-timeframe");
    await expect(multiTimeframe.getByText("多周期看盘", { exact: true })).toBeVisible();
    await expect(multiTimeframe.locator('[aria-label$="K 线图"]')).toHaveCount(4);
    await multiTimeframe.getByRole("button", { name: "MACD" }).click();
    await expect(multiTimeframe.getByRole("button", { name: "MACD" })).toHaveAttribute("aria-pressed", "true");

    await page.goto(`${shellOrigin}/?mod=relative-strength`);
    const relativeStrength = embeddedWorkspace(page, "relative-strength");
    await expect(workspaceTitle(page, "relative-strength")).toHaveText("相对强弱地图");
    await expect(relativeStrength.getByRole("img", { name: "相对强弱走势" })).toBeVisible();
    await expect(relativeStrength.getByText("阶段排名", { exact: true })).toBeVisible();

    await page.goto(`${shellOrigin}/?mod=event-timeline`);
    const eventTimeline = embeddedWorkspace(page, "event-timeline");
    await expect(eventTimeline.getByText("事件时间轴", { exact: true })).toBeVisible();
    await expect(eventTimeline.getByLabel("事件时间轴 K 线图")).toBeVisible();
    await expect(eventTimeline.getByRole("group", { name: "事件筛选" })).toBeVisible();

    await page.goto(`${shellOrigin}/?mod=trading-replay`);
    const tradingReplay = embeddedWorkspace(page, "trading-replay");
    await expect(tradingReplay.getByText("交易回放室", { exact: true })).toBeVisible();
    await expect(tradingReplay.getByText(/未来数据已隐藏/)).toBeVisible();
    await tradingReplay.getByRole("button", { name: "模拟买入" }).click();
    await expect(tradingReplay.getByText("决策次数").locator("..")).toContainText("1");
    await expect(tradingReplay.getByRole("button", { name: "模拟卖出" })).toBeEnabled();

    expect(errors).toEqual([]);
  });

  test("replays security selection into another Mod and persists structured Agent context", async ({ page, request }) => {
    const errors = collectConsoleErrors(page);
    await page.goto(`${shellOrigin}/?mod=market-scanner`);
    const scanner = embeddedWorkspace(page, "market-scanner");
    await expect(scanner.getByText("市场扫描器", { exact: true })).toBeVisible();
    await scanner.locator("button.scanner-row").filter({ hasText: "中芯国际" }).first().click();

    await page
      .locator('[data-module-id="multi-timeframe"] .module-button')
      .click();
    const multi = embeddedWorkspace(page, "multi-timeframe");
    await expect(multi.getByText("中芯国际", { exact: true }).first()).toBeVisible();
    await page.getByRole("button", { name: "问当前 Mod" }).click();
    await expect(page.getByRole("complementary", { name: "多周期看盘 Agent" })).toBeVisible();

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
    expect(saved?.context.view).toEqual({ id: "multi-timeframe", title: "多周期看盘" });
    expect(saved?.context.selection).toMatchObject({ symbol: "688981", name: "中芯国际", market: "CN" });
    expect(saved?.context.filters).toMatchObject({ workspace: "multi-timeframe" });
    expect(saved?.context.visibleBlocks).toEqual(expect.arrayContaining([
      expect.objectContaining({ id: "multi-chart-grid", type: "klinechart-grid" }),
    ]));
    expect(errors).toEqual([]);
  });

  test("keeps the scanner usable at a narrow viewport", async ({ page }) => {
    const errors = collectConsoleErrors(page);
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto(`${shellOrigin}/?mod=market-scanner`);
    const scanner = embeddedWorkspace(page, "market-scanner");
    await expect(scanner.getByText("市场扫描器", { exact: true })).toBeVisible();
    await expect(scanner.getByRole("table")).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    expect(errors).toEqual([]);
  });
});
