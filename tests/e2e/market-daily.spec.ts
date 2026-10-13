import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { expect, test } from "@playwright/test";

import {
  apiOrigin,
  moduleOrigin,
  shellOrigin,
} from "./runtime-config";

const marketPackage = JSON.parse(
  readFileSync(resolve("mods/market-daily/mod.json"), "utf8"),
) as {
  id: string;
  name: string;
  version: string;
  runtime: { entry: Record<string, unknown> };
  manifest: Record<string, unknown>;
};
const marketManifest = {
  ...marketPackage.manifest,
  id: marketPackage.id,
  name: marketPackage.name,
  version: marketPackage.version,
  entry: marketPackage.runtime.entry,
};

test("Market quote workspace works directly, embedded, responsive, and publishes structured Context", async ({
  page,
  request,
}) => {
  const userId = "e2e-market-context-user";
  const workspaceId = `e2e-market-context-${Date.now()}`;
  const pageErrors: string[] = [];
  const consoleErrors: string[] = [];
  page.on("pageerror", (error) => pageErrors.push(error.message));
  page.on("console", (message) => {
    if (message.type() === "error") consoleErrors.push(message.text());
  });

  const draftResponse = await request.post(`${apiOrigin}/api/mods/drafts`, {
    data: marketManifest,
  });
  expect(draftResponse.status()).toBe(201);
  const draft = (await draftResponse.json()) as { revision: number };
  const publishResponse = await request.post(
    `${apiOrigin}/api/mods/market-daily/revisions/${draft.revision}/publish`,
  );
  expect(publishResponse.status()).toBe(200);

  const refreshInstanceId = "e2e-refresh-instance";
  const sessionResponse = await request.post(
    `${apiOrigin}/api/mods/market-daily/sessions`,
    {
      headers: { "X-User-Id": "e2e-refresh-user" },
      data: {
        instanceId: refreshInstanceId,
        workspaceId: "e2e-refresh-workspace",
      },
    },
  );
  expect(sessionResponse.status()).toBe(201);
  const session = (await sessionResponse.json()) as { accessToken: string };

  const refreshResponse = await request.post(
    `${apiOrigin}/api/mods/market-daily/actions/market.refresh`,
    {
      headers: {
        Authorization: `Bearer ${session.accessToken}`,
        "X-Newma-Desk-Instance-Id": refreshInstanceId,
      },
      data: {},
    },
  );
  expect(refreshResponse.status()).toBe(200);
  expect((await refreshResponse.json()).data.asOf).toBe(
    "2026-07-20T15:00:00+08:00",
  );

  await page.goto(`${moduleOrigin}/mods/market-daily/`);
  await expect(page.getByText("行情", { exact: true })).toBeVisible();
  await expect(page.getByText("1,488.00", { exact: true }).first()).toBeVisible();
  await expect(page.getByText("卖1", { exact: true })).toBeVisible();
  await expect(page.getByText("3120", { exact: true })).toBeVisible();
  await expect(page.locator(".kline-chart canvas").first()).toBeVisible();
  await expect(page.getByRole("button", { name: "解释行情" })).toHaveCount(0);

  await page.emulateMedia({ colorScheme: "dark" });
  await page.reload();
  await expect(page.getByText("行情", { exact: true })).toBeVisible();
  const darkBackground = await page.locator("body").evaluate(
    (element) => getComputedStyle(element).backgroundColor,
  );
  expect(darkBackground).not.toBe("rgb(255, 255, 255)");

  await page.setViewportSize({ width: 390, height: 844 });
  await page.reload();
  await expect(page.getByText("1,488.00", { exact: true }).first()).toBeVisible();
  const directMobileWidth = await page.evaluate(() => ({
    client: document.documentElement.clientWidth,
    scroll: document.documentElement.scrollWidth,
  }));
  expect(directMobileWidth.scroll).toBeLessThanOrEqual(directMobileWidth.client);

  await page.emulateMedia({ colorScheme: "light" });
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.addInitScript(({ user, workspace }) => {
    localStorage.setItem("vibedesk.userId.v1", user);
    localStorage.setItem("vibedesk.workspaceId.v1", workspace);
  }, { user: userId, workspace: workspaceId });
  await page.goto(`${shellOrigin}/?mod=market-daily`);
  await expect(
    page.getByRole("button", { name: "行情", exact: true }),
  ).toBeVisible();
  const market = page.locator('[data-vibedesk-mod-id="market-daily"]');
  await expect(market).toHaveAttribute("data-vibedesk-frame-state", "ready");
  await expect(market.getByText("1,488.00", { exact: true }).first()).toBeVisible();
  await expect(market.locator(".kline-chart canvas").first()).toBeVisible();

  await market.getByRole("textbox", { name: "搜索证券" }).fill("NVDA");
  await market.getByRole("button", { name: /NVIDIA/ }).click();
  await expect(market.getByText("186.50", { exact: true }).first()).toBeVisible();
  await expect(page.getByLabel("Mod 事件日志")).toContainText(
    "security.selected · NVDA",
  );
  // 独立运行时仍需保留本地 Copilot 入口；挂载 Newma 时由运行时接管 Agent。
  await expect(page.getByRole("button", { name: "问当前 Mod" })).toBeVisible();
  await expect.poll(async () => {
    const response = await request.get(`${apiOrigin}/api/mods/market-daily/context`, {
      headers: {
        "X-User-Id": userId,
        "X-Workspace-Id": workspaceId,
      },
    });
    if (response.status() === 404) return null;
    expect(response.status()).toBe(200);
    return (await response.json() as { context: Record<string, unknown> }).context;
  }).toMatchObject({
    selection: {
      symbol: "NVDA",
      name: "NVIDIA",
      market: "US",
    },
    filters: {
      timeframe: "1d",
      primaryIndicator: "MA",
    },
    data: {
      freshness: "live",
      summary: expect.objectContaining({ price: 186.5 }),
    },
  });

  await page.setViewportSize({ width: 390, height: 844 });
  const shellMobileWidth = await page.evaluate(() => ({
    client: document.documentElement.clientWidth,
    scroll: document.documentElement.scrollWidth,
  }));
  expect(shellMobileWidth.scroll).toBeLessThanOrEqual(shellMobileWidth.client);

  expect(pageErrors).toEqual([]);
  expect(consoleErrors).toEqual([]);
});
