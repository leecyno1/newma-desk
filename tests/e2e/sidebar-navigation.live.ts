import { expect, test } from "@playwright/test";

const shellOrigin = process.env.VIBE_E2E_SIDEBAR_ORIGIN ?? "http://127.0.0.1:5888";

test("embedded Desk reuses the host navigation and conversation surfaces", async ({
  page,
}) => {
  const pageErrors: string[] = [];
  const consoleIssues: string[] = [];
  page.on("pageerror", (error) => pageErrors.push(error.message));
  page.on("console", (message) => {
    if (["error", "warning"].includes(message.type())) {
      consoleIssues.push(`${message.type()}: ${message.text()}`);
    }
  });

  await page.setContent(`
    <!doctype html>
    <html lang="zh-CN">
      <body style="margin:0">
        <iframe
          title="Newma WebUI Desk host"
          src="${shellOrigin}/?mod=quant-overview&copilot=1"
          style="width:100vw;height:100vh;border:0"
        ></iframe>
      </body>
    </html>
  `);

  const embeddedDesk = page.frameLocator(
    'iframe[title="Newma WebUI Desk host"]',
  );
  await expect(embeddedDesk.locator(".shell-layout")).toHaveAttribute(
    "data-embedded",
    "true",
  );
  await expect(
    embeddedDesk.getByRole("complementary", {
      name: "Newma-Desk 项目导航",
    }),
  ).toHaveCount(0);
  await expect(
    embeddedDesk.getByRole("complementary", {
      name: "Vibe Trading 二级导航",
    }),
  ).toHaveCount(0);
  await expect(
    embeddedDesk.getByRole("button", { name: "问当前 Mod" }),
  ).toHaveCount(0);
  await expect(
    embeddedDesk.getByRole("button", { name: "关闭 Agent 侧栏" }),
  ).toHaveCount(0);
  await expect(embeddedDesk.locator('iframe[title="量化总览"]')).toBeVisible();

  const quantRuntime = embeddedDesk.frameLocator('iframe[title="量化总览"]');
  await expect(quantRuntime.locator("h1")).toBeVisible();
  await expect(quantRuntime.locator("h1")).toContainText(/Quant|量化/i);
  expect(pageErrors).toEqual([]);
  expect(consoleIssues).toEqual([]);
});

test("project navigation supports switching, scoped sections, freezing, persistence, and narrow layout", async ({
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
  await page.goto(`${shellOrigin}/?mod=market-daily`, {
    waitUntil: "domcontentloaded",
  });

  const navigation = page.getByRole("navigation", {
    name: "Newma-Desk Mod 导航",
  });
  const marketProject = navigation.getByRole("button", {
    name: "市场面 项目",
    exact: true,
  });
  const macroProject = navigation.getByRole("button", {
    name: "宏观面 项目",
    exact: true,
  });
  await expect(marketProject).toHaveAttribute("aria-current", "page");
  await expect(macroProject).toBeVisible();

  let secondary = page.getByRole("complementary", {
    name: "市场面 二级导航",
  });
  await expect(secondary).toBeVisible();
  await expect(secondary.locator(".module-button")).toHaveCount(6);
  await expect(
    secondary.getByRole("button", { name: "终端", exact: true }),
  ).toBeVisible();
  await expect(
    secondary.getByRole("button", { name: "交易回放", exact: true }),
  ).toBeVisible();

  await macroProject.click();
  const macroSecondary = page.getByRole("complementary", {
    name: "宏观面 二级导航",
  });
  await expect(macroProject).toHaveAttribute("aria-current", "page");
  await expect(marketProject).not.toHaveAttribute("aria-current", "page");
  await expect(
    macroSecondary.getByRole("button", { name: "每日复盘", exact: true }),
  ).toBeVisible();

  await marketProject.click();
  secondary = page.getByRole("complementary", {
    name: "市场面 二级导航",
  });
  await expect(secondary).toBeVisible();

  const multiTimeframeRow = secondary
    .getByRole("button", { name: "多周期", exact: true })
    .locator("..");
  const terminalRow = secondary
    .getByRole("button", { name: "终端", exact: true })
    .locator("..");
  await multiTimeframeRow.dragTo(terminalRow);
  await expect(secondary.locator(".module-button").first()).toHaveText("多周期");

  await page.getByRole("button", { name: "界面设置" }).click();
  await expect(page.getByRole("heading", { name: "项目导航" })).toBeVisible();
  const marketProjectTitle = page.getByRole("textbox", {
    name: "市场面 一级标题",
  });
  await marketProjectTitle.fill("重点行情");
  await page.getByRole("button", { name: "保存导航" }).click();
  await expect(page.getByRole("status")).toContainText("项目导航已保存");
  const renamedMarketProject = navigation.getByRole("button", {
    name: "重点行情 项目",
    exact: true,
  });
  await expect(renamedMarketProject).toHaveAttribute("aria-current", "page");
  await expect(page.getByRole("complementary", {
    name: "重点行情 二级导航",
  })).toBeVisible();

  await page.reload({ waitUntil: "domcontentloaded" });
  await expect(marketProjectTitle).toHaveValue("重点行情");
  await page.getByRole("button", { name: "恢复 市场面 默认标题" }).click();
  await page.getByRole("button", { name: "保存导航" }).click();
  await expect(page.getByRole("status")).toContainText("项目导航已保存");

  await marketProject.click();
  secondary = page.getByRole("complementary", {
    name: "市场面 二级导航",
  });
  await expect(secondary.locator(".module-button").first()).toHaveText("多周期");

  const scannerRow = secondary
    .getByRole("button", { name: "扫描器", exact: true })
    .locator("..");
  await scannerRow.dragTo(macroProject.locator(".."));
  await macroProject.click();
  await expect(
    macroSecondary.getByRole("button", { name: "扫描器", exact: true }),
  ).toHaveCount(0);
  await marketProject.click();
  secondary = page.getByRole("complementary", {
    name: "市场面 二级导航",
  });
  await expect(
    secondary.getByRole("button", { name: "扫描器", exact: true }),
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

  await marketProject.hover();
  await navigation
    .getByRole("button", { name: "冻结 市场面 项目" })
    .click();
  await expect(marketProject.locator("..")).toHaveAttribute("draggable", "false");

  secondary = page.getByRole("complementary", {
    name: "市场面 二级导航",
  });
  const groupedScannerRow = secondary
    .getByRole("button", { name: "扫描器", exact: true })
    .locator("..");
  await groupedScannerRow.hover();
  await secondary.getByRole("button", { name: "冻结 扫描器" }).click();
  await expect(groupedScannerRow).toHaveAttribute("draggable", "false");

  const stored = await page.evaluate(() =>
    JSON.parse(localStorage.getItem("vibedesk.sidebarNavigation.v1") || "{}"),
  );
  expect(stored.projects["market-surface"].pinned).toBe(true);
  expect(stored.modules["market-scanner"].pinned).toBe(true);

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
  secondary = page.getByRole("complementary", {
    name: "市场面 二级导航",
  });
  await expect(secondary).toBeVisible();
  await expect(secondary).toHaveCSS("position", "absolute");
  await expect(
    secondary.getByRole("button", { name: "扫描器", exact: true }),
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
    page.getByRole("heading", { name: "项目导航" }),
  ).toBeVisible();
  await expect(
    page.getByRole("textbox", { name: "市场面 一级标题" }),
  ).toHaveValue("市场面");
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

  const frame = page.locator(
    '.module-frame[data-vibedesk-mod-id="multi-timeframe"]',
  );
  await expect(frame).toHaveAttribute("data-vibedesk-frame-state", "ready");
  const before = await frame.boundingBox();
  expect(before).not.toBeNull();

  await page.getByRole("button", { name: "问当前 Mod" }).click();
  const copilot = page.getByRole("complementary", { name: "多周期看盘 Agent" });
  await expect(copilot).toBeVisible();
  await expect(copilot).toHaveCSS("position", "absolute");
  const after = await frame.boundingBox();
  expect(after).not.toBeNull();
  expect(Math.abs((after?.width ?? 0) - (before?.width ?? 0))).toBeLessThan(1);

  const innerOverflow = await frame.evaluate((element) =>
    element.scrollWidth - element.clientWidth,
  );
  expect(innerOverflow).toBeLessThanOrEqual(1);
  await expect(
    frame.locator(".timeframe-panel header em").first(),
  ).toContainText("已同步", { timeout: 15_000 });

  const secondary = page.getByRole("complementary", {
    name: "市场面 二级导航",
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
