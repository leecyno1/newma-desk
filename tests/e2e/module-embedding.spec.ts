import { expect, test } from "@playwright/test";

import {
  demoModuleUrl,
  shellModuleUrl,
  shellOrigin,
} from "./runtime-config";

const requiredSandboxFlags = [
  "allow-scripts",
  "allow-forms",
  "allow-downloads",
  "allow-popups",
  "allow-same-origin",
];

test("demo Mod runs directly in standalone mode", async ({ page }) => {
  await page.goto(demoModuleUrl);

  await expect(
    page.getByRole("heading", { name: "Demo Mod" }),
  ).toBeVisible();
  await expect(page.getByText("Mode: standalone", { exact: true })).toBeVisible();
});

test("Newma-Desk embeds the demo Mod with its isolation contract", async ({
  page,
}) => {
  await page.goto(shellModuleUrl);

  await expect(
    page.getByRole("button", { name: "Demo Mod", exact: true }),
  ).toBeVisible();

  const frameElement = page.locator('iframe[title="Demo Mod"]');
  const frame = page.frameLocator('iframe[title="Demo Mod"]');

  await expect(
    frame.getByRole("heading", { name: "Demo Mod" }),
  ).toBeVisible();
  await expect(frame.getByText("Mode: embedded", { exact: true })).toBeVisible();

  const standaloneHref = await page
    .getByRole("link", { name: "独立打开" })
    .getAttribute("href");
  expect(standaloneHref).toBeTruthy();
  const standaloneUrl = new URL(standaloneHref!);
  const expectedDemoUrl = new URL(demoModuleUrl);
  expect(`${standaloneUrl.origin}${standaloneUrl.pathname}`).toBe(
    `${expectedDemoUrl.origin}${expectedDemoUrl.pathname}`,
  );
  expect(standaloneUrl.searchParams.get("__newma_mod_version")).toBe("0.1.0");

  const sandbox =
    (await frameElement.getAttribute("sandbox"))?.split(/\s+/) ?? [];
  expect(sandbox).toEqual(expect.arrayContaining(requiredSandboxFlags));
});

test("embedded market pages remain scrollable when the host narrows them", async ({
  page,
}) => {
  const deskUrl = new URL(shellOrigin);
  deskUrl.searchParams.set("mod", "market-daily");
  deskUrl.searchParams.set("host", "newma");
  deskUrl.searchParams.set("project", "market-surface");
  deskUrl.searchParams.set("workspace", "newma-mod-market-surface-e2e");
  deskUrl.searchParams.set("parentOrigin", "file:///");

  await page.setViewportSize({ width: 1100, height: 850 });
  await page.setContent(
    `<iframe id="newma-host" title="Newma host" style="display:block;width:426px;height:758px;border:0" src="${deskUrl}"></iframe>`,
  );

  const host = page.frameLocator("#newma-host");
  const frame = host.locator(
    '.module-frame[data-vibedesk-embedded="true"]',
  );
  await expect(host.getByText("贵州茅台", { exact: true }).first()).toBeVisible();

  const scrollState = await frame.evaluate((element) => ({
    clientHeight: element.clientHeight,
    scrollHeight: element.scrollHeight,
    overflowY: getComputedStyle(element).overflowY,
  }));
  expect(["auto", "scroll"]).toContain(scrollState.overflowY);
  expect(scrollState.scrollHeight).toBeGreaterThan(scrollState.clientHeight);

  await frame.evaluate((element) => {
    element.scrollTop = element.scrollHeight;
  });
  await expect
    .poll(() => frame.evaluate((element) => element.scrollTop))
    .toBeGreaterThan(0);
});

test("embedded market pages return their current context to the Newma host", async ({
  page,
}) => {
  const deskUrl = new URL(shellOrigin);
  deskUrl.searchParams.set("mod", "market-daily");
  deskUrl.searchParams.set("host", "newma");
  deskUrl.searchParams.set("project", "market-surface");
  deskUrl.searchParams.set("workspace", "newma-mod-market-surface-context");
  deskUrl.searchParams.set("parentOrigin", "file:///");

  await page.setContent(
    `<iframe id="newma-host" title="Newma host" style="display:block;width:960px;height:720px;border:0" src="${deskUrl}"></iframe>`,
  );
  const host = page.frameLocator("#newma-host");
  await expect(host.getByText("贵州茅台", { exact: true }).first()).toBeVisible();

  const context = await page.evaluate(async ({ targetOrigin }) => {
    const frame = document.querySelector<HTMLIFrameElement>("#newma-host");
    if (!frame?.contentWindow) throw new Error("Newma host frame is unavailable");
    const requestId = `context-${Date.now()}`;
    return await new Promise<Record<string, unknown>>((resolve, reject) => {
      const timer = window.setTimeout(() => {
        window.removeEventListener("message", handleMessage);
        reject(new Error("Mod context response timed out"));
      }, 5_000);
      const handleMessage = (event: MessageEvent) => {
        if (
          event.source !== frame.contentWindow ||
          event.origin !== targetOrigin ||
          !event.data ||
          event.data.type !== "newma:mod-context" ||
          event.data.requestId !== requestId
        ) {
          return;
        }
        window.clearTimeout(timer);
        window.removeEventListener("message", handleMessage);
        resolve(event.data as Record<string, unknown>);
      };
      window.addEventListener("message", handleMessage);
      frame.contentWindow.postMessage(
        {
          type: "newma:mod-context-request",
          protocol: "newma:mod-host:v1",
          requestId,
          projectId: "market-surface",
          modId: "market-daily",
          workspaceId: "newma-mod-market-surface-context",
          reason: "agent",
        },
        targetOrigin,
      );
    });
  }, { targetOrigin: shellOrigin });

  expect(context).toMatchObject({
    projectId: "market-surface",
    modId: "market-daily",
    workspaceId: "newma-mod-market-surface-context",
    context: {
      view: { id: "market-daily", title: "行情" },
      selection: { symbol: "600519", name: "贵州茅台", market: "CN" },
      filters: { timeframe: "1d", primaryIndicator: "MA", secondaryIndicator: "VOL" },
    },
  });
});
