import { expect, test, type Page } from "@playwright/test";

const shellOrigin = process.env.VIBE_E2E_SHELL_ORIGIN || "http://127.0.0.1:5888";
const apiOrigin = process.env.VIBE_E2E_API_ORIGIN || "http://127.0.0.1:8911";
const moduleOrigin = process.env.VIBE_E2E_MODULE_ORIGIN || "http://127.0.0.1:5891";

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
      const frame = page.frameLocator(`iframe[title="${title}"]`);
      await expect(frame.getByText(title, { exact: true })).toBeVisible();
      await expect(frame.locator(".workspace-current-price strong")).toHaveText(/\d/);
      await expect(frame.getByText("Action is not granted", { exact: false })).toHaveCount(0);
    }

    expect(errors).toEqual([]);
  });

  test("renders all five shared-runtime workspaces with working primary interactions", async ({ page }) => {
    const errors = collectConsoleErrors(page);

    await page.goto(`${moduleOrigin}/mods/market-daily/?workspace=scanner`);
    await expect(page.getByText("市场扫描器", { exact: true })).toBeVisible();
    await expect(page.getByRole("table")).toBeVisible();
    await page.getByRole("button", { name: /趋势走强/ }).click();
    await expect(page.getByText(/个候选/).first()).toBeVisible();

    await page.goto(`${moduleOrigin}/mods/market-daily/?workspace=multi-timeframe`);
    await expect(page.getByText("多周期看盘", { exact: true })).toBeVisible();
    await expect(page.locator('[aria-label$="K 线图"]')).toHaveCount(4);
    await page.getByRole("button", { name: "MACD" }).click();
    await expect(page.getByRole("button", { name: "MACD" })).toHaveAttribute("aria-pressed", "true");

    await page.goto(`${moduleOrigin}/mods/market-daily/?workspace=relative-strength`);
    await expect(page.getByText("相对强弱地图", { exact: true })).toBeVisible();
    await expect(page.getByRole("img", { name: "相对强弱走势" })).toBeVisible();
    await expect(page.getByText("阶段排名", { exact: true })).toBeVisible();

    await page.goto(`${moduleOrigin}/mods/market-daily/?workspace=event-timeline`);
    await expect(page.getByText("事件时间轴", { exact: true })).toBeVisible();
    await expect(page.getByLabel("事件时间轴 K 线图")).toBeVisible();
    await expect(page.getByRole("group", { name: "事件筛选" })).toBeVisible();

    await page.goto(`${moduleOrigin}/mods/market-daily/?workspace=trading-replay`);
    await expect(page.getByText("交易回放室", { exact: true })).toBeVisible();
    await expect(page.getByText(/未来数据已隐藏/)).toBeVisible();
    await page.getByRole("button", { name: "模拟买入" }).click();
    await expect(page.getByText("决策次数").locator("..")).toContainText("1");
    await expect(page.getByRole("button", { name: "模拟卖出" })).toBeEnabled();

    expect(errors).toEqual([]);
  });

  test("replays security selection into another Mod and persists structured Agent context", async ({ page, request }) => {
    const errors = collectConsoleErrors(page);
    await page.goto(`${shellOrigin}/?mod=market-scanner`);
    const scanner = page.frameLocator('iframe[title="市场扫描器"]');
    await expect(scanner.getByText("市场扫描器", { exact: true })).toBeVisible();
    await scanner.locator("button.scanner-row").filter({ hasText: "中芯国际" }).first().click();

    await page
      .locator('[data-module-id="multi-timeframe"] .module-button')
      .click();
    const multi = page.frameLocator('iframe[title="多周期看盘"]');
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
      if (!response.ok()) return response.status();
      saved = await response.json();
      return response.status();
    }).toBe(200);
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
    await page.goto(`${moduleOrigin}/mods/market-daily/?workspace=scanner`);
    await expect(page.getByText("市场扫描器", { exact: true })).toBeVisible();
    await expect(page.getByRole("table")).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    expect(errors).toEqual([]);
  });
});
