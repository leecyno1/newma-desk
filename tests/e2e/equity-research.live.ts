import { expect, test } from "@playwright/test";

const shellOrigin = process.env.NEWMA_DESK_E2E_ORIGIN ?? "http://127.0.0.1:5888";

test("equity research exposes workflow quality and persists report history", async ({
  page,
}) => {
  const workspaceId = `e2e-research-${Date.now()}`;
  const storageResponses: Array<{ method: string; status: number }> = [];
  page.on("response", (response) => {
    if (!response.url().includes("/storage/research-history/")) return;
    storageResponses.push({
      method: response.request().method(),
      status: response.status(),
    });
  });
  await page.addInitScript(({ workspace }) => {
    localStorage.setItem("vibedesk.userId.v1", "e2e-research-user");
    localStorage.setItem("vibedesk.workspaceId.v1", workspace);
  }, { workspace: workspaceId });

  await page.goto(`${shellOrigin}/?mod=stock-research`, {
    waitUntil: "domcontentloaded",
  });
  const research = page.frameLocator('iframe[title="个股研究"]');
  const input = research.getByPlaceholder(/A 股 6 位代码/);
  await expect(input).toBeVisible();
  await input.fill("600519");
  await research.getByRole("button", { name: "查询", exact: true }).click();

  await expect(research.getByText("研究流程与数据质量", { exact: true }))
    .toBeVisible({ timeout: 40_000 });
  await expect(research.getByText(/质量 \d+\/100/)).toBeVisible();
  await expect(research.getByText(/Desk 已保存 · 1 条/))
    .toBeVisible({ timeout: 10_000 });
  await expect(research.getByText("Evidence Ledger", { exact: false }))
    .toBeVisible();

  expect(storageResponses.some((item) => item.method === "GET" && [200, 404].includes(item.status)))
    .toBe(true);
  expect(storageResponses.some((item) => item.method === "PUT" && item.status === 200))
    .toBe(true);
});
