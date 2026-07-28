import { expect, test } from "@playwright/test";

const shellOrigin = process.env.VIBE_E2E_SIDEBAR_ORIGIN ?? "http://127.0.0.1:5888";

test("secondary sidebar supports opening, freezing, dragging, persistence, and narrow layout", async ({
  page,
}, testInfo) => {
  const pageErrors: string[] = [];
  const consoleIssues: string[] = [];
  page.on("pageerror", (error) => pageErrors.push(error.message));
  page.on("console", (message) => {
    if (["error", "warning"].includes(message.type())) {
      consoleIssues.push(`${message.type()}: ${message.text()}`);
    }
  });

  await page.addInitScript(() => {
    if (sessionStorage.getItem("vibedesk.sidebar.e2e.initialized")) return;
    localStorage.removeItem("vibedesk.sidebarNavigation.v1");
    localStorage.removeItem("vibedesk.moduleCategories.v1");
    localStorage.setItem("vibedesk.themeMode", "system");
    localStorage.setItem("vibedesk.userId.v1", "e2e-sidebar-user");
    localStorage.setItem("vibedesk.workspaceId.v1", "e2e-sidebar-workspace");
    sessionStorage.setItem("vibedesk.sidebar.e2e.initialized", "true");
  });
  await page.goto(`${shellOrigin}/?mod=watchlist`, {
    waitUntil: "domcontentloaded",
  });

  const navigation = page.getByRole("navigation", {
    name: "Newma-Desk Mod 导航",
  });
  const marketDirectory = navigation.locator(".directory-nav-row", {
    hasText: "行情工具",
  });
  const deepseeDirectory = navigation.locator(".directory-nav-row", {
    hasText: "Deepsee 功能",
  });
  await expect(marketDirectory).toBeVisible();
  await expect(deepseeDirectory).toBeVisible();
  await expect(marketDirectory.locator("small")).toHaveText("6");
  await expect(deepseeDirectory.locator("small")).toHaveText("11");

  await marketDirectory.locator(".directory-button").click();
  const secondary = page.getByRole("complementary", {
    name: "行情工具 二级导航",
  });
  await expect(secondary).toBeVisible();
  await expect(secondary.locator(".module-button")).toHaveCount(6);
  await expect(
    secondary.getByRole("button", { name: "终端", exact: true }),
  ).toBeVisible();
  await expect(
    secondary.getByRole("button", { name: "交易回放", exact: true }),
  ).toBeVisible();

  await secondary.getByRole("button", { name: "项目设置", exact: true }).click();
  await expect(page).toHaveURL(/view=suite-settings/);
  await expect(page).toHaveURL(/directory=market-suite/);
  await expect(secondary).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "行情工具 · 项目设置" }),
  ).toBeVisible();
  await expect(page.getByRole("heading", { name: "统一数据接口" })).toBeVisible();
  const quoteProvider = page.getByRole("combobox", {
    name: "market.quote Provider",
  });
  await expect(quoteProvider).toBeVisible();
  await expect(quoteProvider).toHaveValue("");
  await quoteProvider.selectOption("market-data");
  await page.getByRole("button", { name: "保存数据路由" }).click();
  await expect(page.getByRole("status")).toContainText("项目数据路由已保存");
  await page.reload({ waitUntil: "domcontentloaded" });
  await expect(secondary).toBeVisible();
  await expect(quoteProvider).toHaveValue("market-data");
  await page.screenshot({
    path: testInfo.outputPath("suite-settings.png"),
    fullPage: true,
  });

  await quoteProvider.selectOption("");
  await page.getByRole("button", { name: "保存数据路由" }).click();
  await expect(page.getByRole("status")).toContainText("项目数据路由已保存");
  const unifiedQuoteResponse = page.waitForResponse((response) =>
    response.request().method() === "POST" &&
    response.url().includes("/api/mods/market-daily/actions/market.quote"),
  );
  await secondary.getByRole("button", { name: "终端", exact: true }).click();
  await expect(page).toHaveURL(/mod=market-daily/);
  expect((await unifiedQuoteResponse).status()).toBe(200);

  await secondary.getByRole("button", { name: "冻结 扫描器" }).click();
  const scannerRow = secondary
    .getByRole("button", { name: "扫描器", exact: true })
    .locator("..");
  await expect(scannerRow).toHaveAttribute("draggable", "false");

  const watchlistRow = navigation
    .getByRole("button", { name: "自选股", exact: true })
    .locator("..");
  await watchlistRow.dragTo(marketDirectory);
  await expect(
    secondary.getByRole("button", { name: "自选股", exact: true }),
  ).toBeVisible();
  await expect(
    navigation.getByRole("button", { name: "自选股", exact: true }),
  ).toHaveCount(0);

  const stored = await page.evaluate(() =>
    JSON.parse(localStorage.getItem("vibedesk.sidebarNavigation.v1") || "{}"),
  );
  expect(stored.modules["market-scanner"].pinned).toBe(true);
  expect(stored.modules.watchlist.directory).toEqual({
    id: "market-suite",
    label: "行情工具",
  });

  await page.screenshot({
    path: testInfo.outputPath("sidebar-desktop.png"),
    fullPage: true,
  });

  await secondary.getByRole("button", { name: "收起一级与二级导航" }).click();
  const sidebarShell = page.locator(".sidebar-shell");
  await expect(sidebarShell).toHaveAttribute("data-navigation-collapsed", "true");
  await expect(navigation).toBeHidden();
  await page.screenshot({
    path: testInfo.outputPath("sidebar-collapsed.png"),
    fullPage: true,
  });
  await page.getByRole("button", { name: "展开一级与二级导航" }).click();
  await expect(sidebarShell).toHaveAttribute("data-navigation-collapsed", "false");
  await expect(secondary).toBeVisible();

  await page.setViewportSize({ width: 420, height: 820 });
  await page.reload({ waitUntil: "domcontentloaded" });
  await expect(secondary).toBeVisible();
  await expect(secondary).toHaveCSS("position", "absolute");
  await expect(
    secondary.getByRole("button", { name: "自选股", exact: true }),
  ).toBeVisible();
  await expect(
    secondary
      .getByRole("button", { name: "扫描器", exact: true })
      .locator(".."),
  ).toHaveAttribute("draggable", "false");
  await page.screenshot({
    path: testInfo.outputPath("sidebar-narrow.png"),
    fullPage: true,
  });

  await page.emulateMedia({ colorScheme: "dark" });
  await page.reload({ waitUntil: "domcontentloaded" });
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await expect(secondary).toBeVisible();
  await page.screenshot({
    path: testInfo.outputPath("sidebar-dark.png"),
    fullPage: true,
  });

  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto(`${shellOrigin}/?view=interface-settings`, {
    waitUntil: "domcontentloaded",
  });
  await expect(
    page.getByRole("heading", { name: "侧边栏与二级目录" }),
  ).toBeVisible();
  await expect(
    page.getByRole("combobox", { name: "市场终端二级目录" }),
  ).toHaveValue("行情工具");
  await page.screenshot({
    path: testInfo.outputPath("sidebar-settings.png"),
    fullPage: true,
  });

  expect(pageErrors).toEqual([]);
  expect(consoleIssues).toEqual([]);
});

test("Agent drawer preserves the current Mod layout and bound navigation releases space", async ({
  page,
}, testInfo) => {
  const pageErrors: string[] = [];
  const consoleIssues: string[] = [];
  page.on("pageerror", (error) => pageErrors.push(error.message));
  page.on("console", (message) => {
    if (["error", "warning"].includes(message.type())) {
      consoleIssues.push(`${message.type()}: ${message.text()}`);
    }
  });
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.goto(`${shellOrigin}/?mod=multi-timeframe`, {
    waitUntil: "domcontentloaded",
  });

  const frame = page.locator(".module-frame");
  const iframe = page.getByTitle("多周期看盘");
  await expect(iframe).toBeVisible();
  const before = await frame.boundingBox();
  expect(before).not.toBeNull();

  await page.getByRole("button", { name: "问当前 Mod" }).click();
  const copilot = page.getByRole("complementary", { name: "多周期看盘 Agent" });
  await expect(copilot).toBeVisible();
  await expect(copilot).toHaveCSS("position", "absolute");
  const after = await frame.boundingBox();
  expect(after).not.toBeNull();
  expect(Math.abs((after?.width ?? 0) - (before?.width ?? 0))).toBeLessThan(1);

  const innerOverflow = await page
    .frameLocator('iframe[title="多周期看盘"]')
    .locator("html")
    .evaluate((documentElement) =>
      documentElement.scrollWidth - documentElement.clientWidth,
    );
  expect(innerOverflow).toBeLessThanOrEqual(1);
  await expect(
    page
      .frameLocator('iframe[title="多周期看盘"]')
      .locator(".timeframe-panel header em")
      .first(),
  ).toContainText("已同步", { timeout: 15_000 });

  const secondary = page.getByRole("complementary", {
    name: "行情工具 二级导航",
  });
  await secondary.getByRole("button", { name: "收起一级与二级导航" }).click();
  await expect(page.locator(".sidebar-shell")).toHaveAttribute(
    "data-navigation-collapsed",
    "true",
  );
  const expandedFrame = await frame.boundingBox();
  expect((expandedFrame?.width ?? 0)).toBeGreaterThan(after?.width ?? 0);
  await page.screenshot({
    path: testInfo.outputPath("multi-timeframe-agent-overlay.png"),
    fullPage: true,
  });

  expect(pageErrors).toEqual([]);
  expect(consoleIssues).toEqual([]);
});
