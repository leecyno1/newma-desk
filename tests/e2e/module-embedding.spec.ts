import { expect, test } from "@playwright/test";

const moduleUrl = "http://127.0.0.1:5891/modules/demo/";
const shellUrl = "http://127.0.0.1:15888/?module=demo";
const requiredSandboxFlags = [
  "allow-scripts",
  "allow-forms",
  "allow-downloads",
  "allow-popups",
  "allow-same-origin",
];

test("demo module runs directly in standalone mode", async ({ page }) => {
  await page.goto(moduleUrl);

  await expect(
    page.getByRole("heading", { name: "Demo Module" }),
  ).toBeVisible();
  await expect(page.getByText("Mode: standalone", { exact: true })).toBeVisible();
});

test("Shell embeds the demo module with its isolation contract", async ({
  page,
}) => {
  await page.goto(shellUrl);

  const frameElement = page.locator('iframe[title="Demo Module"]');
  const frame = page.frameLocator('iframe[title="Demo Module"]');

  await expect(
    frame.getByRole("heading", { name: "Demo Module" }),
  ).toBeVisible();
  await expect(frame.getByText("Mode: embedded", { exact: true })).toBeVisible();

  await expect(page.getByRole("link", { name: "独立打开" })).toHaveAttribute(
    "href",
    moduleUrl,
  );

  const sandbox =
    (await frameElement.getAttribute("sandbox"))?.split(/\s+/) ?? [];
  expect(sandbox).toEqual(expect.arrayContaining(requiredSandboxFlags));
});
