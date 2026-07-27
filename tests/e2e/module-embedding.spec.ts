import { expect, test } from "@playwright/test";

import { demoModuleUrl, shellModuleUrl } from "./runtime-config";

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

test("Newma-Dock embeds the demo Mod with its isolation contract", async ({
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

  await expect(page.getByRole("link", { name: "独立打开" })).toHaveAttribute(
    "href",
    demoModuleUrl,
  );

  const sandbox =
    (await frameElement.getAttribute("sandbox"))?.split(/\s+/) ?? [];
  expect(sandbox).toEqual(expect.arrayContaining(requiredSandboxFlags));
});
