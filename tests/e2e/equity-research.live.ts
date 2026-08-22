import { expect, test } from "@playwright/test";

const shellOrigin = process.env.NEWMA_DESK_E2E_ORIGIN ?? "http://127.0.0.1:5888";

test("company archive generates an evidence-backed research dossier", async ({
  page,
}) => {
  await page.goto(`${shellOrigin}/?mod=instock-stock-research`, {
    waitUntil: "domcontentloaded",
  });
  const research = page.frameLocator('iframe[title="公司档案"]');
  const input = research.locator("#dossier-symbol");
  await expect(input).toBeVisible();
  await input.fill("600519");
  await research.getByRole("button", { name: "生成档案", exact: true }).click();

  await expect(research.locator("#dossier-name")).toContainText("600519", {
    timeout: 40_000,
  });
  await expect(research.getByRole("heading", { name: /综合判断/ })).toBeVisible();
  await expect(research.getByRole("heading", { name: /财务与估值/ })).toBeVisible();
  await expect(research.getByRole("heading", { name: /K 线结构/ })).toBeVisible();
  await expect(research.locator("#dossier-state")).toHaveText("完整");
});
