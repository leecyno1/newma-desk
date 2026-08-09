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
