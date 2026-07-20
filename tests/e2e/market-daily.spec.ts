import { expect, test } from "@playwright/test";

import {
  apiOrigin,
  fakeOrigin,
  moduleOrigin,
  shellOrigin,
} from "./runtime-config";


const marketManifest = {
  schemaVersion: "1.0",
  id: "market-daily",
  name: "每日股票行情",
  version: "0.1.0",
  category: "market",
  entry: { type: "structured", url: "/modules/market-daily/" },
  permissions: ["market.read"],
  dataServices: ["market-data"],
  agentCapabilities: ["market.refresh", "market.explain"],
  events: {
    emits: ["security.selected"],
    accepts: ["date.changed", "security.selected"],
  },
  refresh: { mode: "schedule", cron: "0 18 * * 1-5" },
};

test("daily market module works directly, embedded, and through the Agent Gateway", async ({
  page,
  request,
}) => {
  expect(fakeOrigin).toMatch(/^http:\/\/127\.0\.0\.1:/);
  const draftResponse = await request.post(`${apiOrigin}/api/modules/drafts`, {
    data: marketManifest,
  });
  expect(draftResponse.status()).toBe(201);
  const draft = (await draftResponse.json()) as { revision: number };
  const publishResponse = await request.post(
    `${apiOrigin}/api/modules/market-daily/revisions/${draft.revision}/publish`,
  );
  expect(publishResponse.status()).toBe(200);

  const refreshResponse = await request.post(
    `${apiOrigin}/api/modules/market-daily/actions/market.refresh`,
    { data: {} },
  );
  expect(refreshResponse.status()).toBe(200);
  expect((await refreshResponse.json()).data.asOf).toBe(
    "2026-07-20T15:00:00+08:00",
  );

  await page.goto(`${moduleOrigin}/modules/market-daily/`);
  await expect(
    page.getByRole("heading", { name: "每日股票行情" }),
  ).toBeVisible();
  await expect(page.getByText("3,120")).toBeVisible();
  await expect(page.getByRole("row", { name: /600519 贵州茅台/ })).toBeVisible();
  await expect(page.locator(".vv-chart-block canvas")).toBeVisible();

  await page.setViewportSize({ width: 390, height: 844 });
  await page.reload();
  await expect(page.getByText("3,120")).toBeVisible();
  const mobileWidth = await page.evaluate(() => ({
    client: document.documentElement.clientWidth,
    scroll: document.documentElement.scrollWidth,
  }));
  expect(mobileWidth.scroll).toBeLessThanOrEqual(mobileWidth.client);

  await page.setViewportSize({ width: 1280, height: 720 });
  await page.goto(`${shellOrigin}/?module=market-daily`);
  await expect(
    page.getByRole("button", { name: "每日股票行情" }),
  ).toBeVisible();
  const frame = page.frameLocator('iframe[title="每日股票行情"]');
  await expect(frame.getByText("3,120")).toBeVisible();
  await expect(frame.locator(".vv-chart-block canvas")).toBeVisible();

  await page.setViewportSize({ width: 390, height: 844 });
  await page.reload();
  const embeddedMobileFrame = page.frameLocator(
    'iframe[title="每日股票行情"]',
  );
  await expect(embeddedMobileFrame.getByText("3,120")).toBeVisible();
  const embeddedMobileWidth = await embeddedMobileFrame.locator("html").evaluate(
    (element) => ({
      client: element.clientWidth,
      scroll: element.scrollWidth,
    }),
  );
  expect(embeddedMobileWidth.scroll).toBeLessThanOrEqual(
    embeddedMobileWidth.client,
  );

  await page.setViewportSize({ width: 1280, height: 720 });
  await page.reload();
  const restoredFrame = page.frameLocator('iframe[title="每日股票行情"]');

  await restoredFrame.getByRole("row", { name: /600519 贵州茅台/ }).click();
  await expect(page.getByLabel("模块事件日志")).toContainText(
    "security.selected · 600519",
  );

  await restoredFrame.getByRole("button", { name: "解释行情" }).click();
  await expect(
    restoredFrame.getByText("E2E 行情解释完成", { exact: false }),
  ).toBeVisible();
});
