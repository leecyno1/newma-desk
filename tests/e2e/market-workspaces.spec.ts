import { expect, test, type Page } from "@playwright/test";

import { apiOrigin, moduleOrigin } from "./runtime-config";

function collectRuntimeErrors(page: Page) {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("console", (message) => {
    if (message.type() === "error") errors.push(message.text());
  });
  return errors;
}

test.describe("Market workspace delivery flows", () => {
  test("saves and restores a composable scanner expression", async ({ page }) => {
    const errors = collectRuntimeErrors(page);
    await page.goto(`${moduleOrigin}/mods/market-daily/?workspace=scanner`);
    await expect(page.getByText("市场扫描器", { exact: true })).toBeVisible();

    await page.getByRole("button", { name: "增加条件" }).click();
    await page.getByLabel("条件字段").selectOption("volumeRatio");
    await page.getByLabel("条件运算符").selectOption("gte");
    await page.getByLabel("条件值").fill("1");
    await page.getByRole("button", { name: "任一满足" }).click();
    await page.getByLabel("表达式名称").fill("E2E 量价组合");
    await page.getByRole("button", { name: "保存", exact: true }).click();
    await expect(page.getByLabel("已保存扫描表达式")).toHaveValue(/.+/);

    await page.reload();
    await page.getByLabel("已保存扫描表达式").selectOption({ label: "E2E 量价组合" });
    await expect(page.getByRole("button", { name: "任一满足" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    await expect(page.getByLabel("条件字段")).toHaveValue("volumeRatio");
    await expect(page.getByLabel("条件值")).toHaveValue("1");
    expect(errors).toEqual([]);
  });

  test("shows evidence-backed events and explicit source health", async ({ page }) => {
    const errors = collectRuntimeErrors(page);
    await page.goto(`${moduleOrigin}/mods/market-daily/?workspace=event-timeline`);
    await expect(page.getByText("事件时间轴", { exact: true })).toBeVisible();
    await expect(page.getByText("贵州茅台2026年半年度业绩预告", { exact: true })).toBeVisible();
    await expect(page.getByText("贵州茅台：渠道韧性与中长期现金流观察", { exact: true })).toBeVisible();
    await expect(page.getByText("贵州茅台披露最新渠道运营信息", { exact: true })).toBeVisible();
    await expect(page.getByText(/东方财富公告 · #announcement:/)).toBeVisible();
    await expect(page.getByRole("link", { name: /打开证据来源 贵州茅台2026年半年度业绩预告/ })).toHaveAttribute(
      "href",
      "https://example.test/evidence/announcement-600519",
    );
    const sourceStatuses = page.locator(".event-source-statuses i");
    await expect(sourceStatuses).toHaveCount(3);
    expect(await sourceStatuses.evaluateAll((items) => items.map((item) => item.getAttribute("data-status")))).toEqual([
      "ok",
      "ok",
      "ok",
    ]);
    expect(errors).toEqual([]);
  });

  test("persists a replay Artifact and exposes its safe rendered view", async ({ page, request }) => {
    const errors = collectRuntimeErrors(page);
    await page.goto(`${moduleOrigin}/mods/market-daily/?workspace=trading-replay`);
    await expect(page.getByText("交易回放室", { exact: true })).toBeVisible();
    await page.getByRole("button", { name: "模拟买入" }).click();
    await page.getByRole("button", { name: "沉淀回放" }).click();

    const artifactLink = page.getByRole("link", { name: /最近沉淀/ });
    await expect(artifactLink).toBeVisible();
    const href = await artifactLink.getAttribute("href");
    expect(href).toMatch(/\/api\/artifacts\/replays\/[0-9a-f]{32}\/view$/);

    const latest = await request.get(`${apiOrigin}/api/artifacts/replays/latest?module_id=trading-replay`);
    expect(latest.status()).toBe(200);
    const artifact = await latest.json() as Record<string, any>;
    expect(artifact).toMatchObject({
      moduleId: "trading-replay",
      kind: "replay",
      renderer: "replay-html",
      status: "draft",
      spec: {
        security: { symbol: "600519", market: "CN" },
        metadata: { simulationOnly: true },
        metrics: { decisionCount: 1 },
      },
    });
    const rendered = await request.get(`${apiOrigin}${artifact.viewUrl}`);
    expect(rendered.status()).toBe(200);
    expect(rendered.headers()["content-security-policy"]).toContain("default-src 'none'");
    expect(await rendered.text()).toContain("仅用于模拟训练与复盘");
    expect(errors).toEqual([]);
  });

  test("keeps scanner and replay controls usable on a narrow viewport", async ({ page }) => {
    const errors = collectRuntimeErrors(page);
    await page.setViewportSize({ width: 390, height: 844 });

    await page.goto(`${moduleOrigin}/mods/market-daily/?workspace=scanner`);
    await expect(page.getByRole("button", { name: "增加条件" })).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);

    await page.goto(`${moduleOrigin}/mods/market-daily/?workspace=trading-replay`);
    await expect(page.getByRole("button", { name: "沉淀回放" })).toBeVisible();
    await expect(page.getByRole("button", { name: "模拟买入" })).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    expect(errors).toEqual([]);
  });
});
