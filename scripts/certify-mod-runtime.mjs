#!/usr/bin/env node

import { writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";

import { chromium } from "@playwright/test";

import { checkModManifest } from "./check-mod-compatibility.mjs";
import { loadModStore } from "./lib/mod-store.mjs";
import {
  createRuntimeCertification,
  requiredRuntimeChecks,
  summarizeRuntimeCertifications,
} from "./lib/mod-runtime-certification.mjs";

const DEFAULT_SHELL_ORIGIN = "http://127.0.0.1:5888";
const DEFAULT_TIMEOUT_MS = 20_000;

function optionValue(args, name) {
  const prefix = `--${name}=`;
  const inline = args.find((argument) => argument.startsWith(prefix));
  if (inline) return inline.slice(prefix.length);
  const index = args.indexOf(`--${name}`);
  return index >= 0 ? args[index + 1] : undefined;
}

function exactHttpOrigin(value, label) {
  let parsed;
  try {
    parsed = new URL(value);
  } catch {
    throw new Error(`${label} must be an HTTP(S) origin`);
  }
  if (!["http:", "https:"].includes(parsed.protocol) || parsed.origin !== value) {
    throw new Error(`${label} must be an HTTP(S) origin`);
  }
  return value;
}

async function captured(operation) {
  try {
    const detail = await operation();
    return { status: "passed", ...(detail ? { detail } : {}) };
  } catch (error) {
    return {
      status: "failed",
      detail: error instanceof Error ? error.message : String(error),
    };
  }
}

async function waitForContextPersistence(request, shellOrigin, id, identity, timeoutMs) {
  const deadline = Date.now() + timeoutMs;
  let lastStatus = 0;
  while (Date.now() < deadline) {
    const response = await request.get(
      `${shellOrigin}/api/mods/${encodeURIComponent(id)}/context`,
      {
        timeout: 2_000,
        headers: {
          "X-User-Id": identity.userId,
          "X-Workspace-Id": identity.workspaceId,
        },
      },
    );
    lastStatus = response.status();
    if (response.ok()) return;
    await new Promise((resolve) => setTimeout(resolve, 200));
  }
  throw new Error(`Agent Context was not persisted (last HTTP ${lastStatus || "unavailable"})`);
}

async function certifyMod({ browser, mod, shellOrigin, timeoutMs }) {
  const manifest = mod.manifest;
  const declaredLevel = manifest.compatibility.level;
  const contract = checkModManifest(manifest);
  const required = requiredRuntimeChecks(declaredLevel);
  if (contract.contractStatus !== "passed") {
    return createRuntimeCertification({
      id: mod.id,
      declaredLevel,
      shellOrigin,
      checks: Object.fromEntries(required.map((name) => [name, {
        status: "failed",
        detail: `Static contract failed: ${contract.errors.join("; ")}`,
      }])),
    });
  }

  const identity = {
    userId: `cert-${mod.id}`,
    workspaceId: "runtime-certification",
  };
  const context = await browser.newContext({
    viewport: { width: 1440, height: 900 },
  });
  const page = await context.newPage();
  await page.addInitScript(({ userId, workspaceId }) => {
    localStorage.setItem("vibedesk.userId.v1", userId);
    localStorage.setItem("vibedesk.workspaceId.v1", workspaceId);
  }, identity);

  let entryUrl;
  let inlineEmbedded = false;
  const checks = {};
  checks.embed = await captured(async () => {
    const navigationUrl = `${shellOrigin}/?mod=${encodeURIComponent(mod.id)}`;
    const response = await page.goto(
      navigationUrl,
      { waitUntil: "domcontentloaded", timeout: timeoutMs },
    );
    if (!response?.ok()) {
      throw new Error(`Desk navigation returned HTTP ${response?.status() ?? "unavailable"}`);
    }
    const boundary = page.locator(
      `.module-frame[data-vibedesk-mod-id="${mod.id}"]`,
    );
    await boundary.waitFor({ state: "visible", timeout: timeoutMs });
    const iframe = page.getByTitle(manifest.name, { exact: true });
    if (await iframe.count() === 0) {
      await page.waitForFunction(
        (id) => {
          const element = document.querySelector(
            `.module-frame[data-vibedesk-mod-id="${id}"]`,
          );
          return element?.getAttribute("data-vibedesk-frame-state") === "ready"
            && Boolean(element.textContent?.trim());
        },
        mod.id,
        { timeout: timeoutMs },
      );
      inlineEmbedded = true;
      entryUrl = navigationUrl;
      return "inline Desk runtime";
    }
    await iframe.waitFor({ state: "visible", timeout: timeoutMs });
    const src = await iframe.getAttribute("src");
    if (!src) throw new Error("embedded iframe has no src");
    entryUrl = new URL(src, shellOrigin).toString();
    const handle = await iframe.elementHandle();
    const frame = await handle?.contentFrame();
    if (!frame || frame.url().startsWith("chrome-error://")) {
      throw new Error("embedded frame did not create a readable document");
    }
    await frame.locator("body").waitFor({ state: "attached", timeout: timeoutMs });
    return entryUrl;
  });

  checks.health = await captured(async () => {
    if (!entryUrl) throw new Error("entry URL is unavailable because embedding failed");
    const response = await context.request.get(entryUrl, { timeout: timeoutMs });
    if (!response.ok()) throw new Error(`entry health returned HTTP ${response.status()}`);
    const contentType = response.headers()["content-type"] || "";
    if (!contentType.includes("text/html")) {
      throw new Error(`entry health returned ${contentType || "an unknown content type"}`);
    }
    return `HTTP ${response.status()}`;
  });

  checks.bridge = await captured(async () => {
    await page.waitForFunction(
      (id) => document.querySelector(
        `.module-frame[data-vibedesk-mod-id="${id}"]`,
      )?.getAttribute("data-vibedesk-bridge-state") === "acknowledged",
      mod.id,
      { timeout: timeoutMs },
    );
    return "hello → init → ack";
  });

  checks.responsive = await captured(async () => {
    if (!entryUrl) throw new Error("entry URL is unavailable because embedding failed");
    const responsivePage = await context.newPage();
    try {
      await responsivePage.setViewportSize({ width: 320, height: 800 });
      const response = await responsivePage.goto(entryUrl, {
        waitUntil: "domcontentloaded",
        timeout: timeoutMs,
      });
      if (!response?.ok()) {
        throw new Error(`narrow entry returned HTTP ${response?.status() ?? "unavailable"}`);
      }
      if (inlineEmbedded) {
        await responsivePage.waitForFunction(
          (id) => document.querySelector(
            `.module-frame[data-vibedesk-mod-id="${id}"]`,
          )?.getAttribute("data-vibedesk-frame-state") === "ready",
          mod.id,
          { timeout: timeoutMs },
        );
      }
      await responsivePage.locator("body").waitFor({ state: "visible", timeout: timeoutMs });
      const overflow = await responsivePage.evaluate(() =>
        document.documentElement.scrollWidth
          - Math.max(document.documentElement.clientWidth, window.innerWidth),
      );
      if (overflow > 1) throw new Error(`document overflows the 320px viewport by ${overflow}px`);
      return "320px viewport";
    } finally {
      await responsivePage.close();
    }
  });

  if (declaredLevel === 3) {
    checks.agentContext = await captured(async () => {
      await page.waitForFunction(
        (id) => document.querySelector(
          `.module-frame[data-vibedesk-mod-id="${id}"]`,
        )?.getAttribute("data-vibedesk-context-state") === "received",
        mod.id,
        { timeout: timeoutMs },
      );
      await waitForContextPersistence(
        context.request,
        shellOrigin,
        mod.id,
        identity,
        timeoutMs,
      );
      return "structured context received and persisted";
    });
  }

  await context.close();
  return createRuntimeCertification({
    id: mod.id,
    declaredLevel,
    shellOrigin,
    checks,
  });
}

async function launchCertificationBrowser({ headed, browserChannel }) {
  if (browserChannel) {
    return chromium.launch({ headless: !headed, channel: browserChannel });
  }
  try {
    return await chromium.launch({ headless: !headed });
  } catch (error) {
    if (!(error instanceof Error) || !error.message.includes("Executable doesn't exist")) {
      throw error;
    }
    process.stdout.write("BROWSER Playwright Chromium unavailable; falling back to Google Chrome\n");
    return chromium.launch({ headless: !headed, channel: "chrome" });
  }
}

async function main() {
  const args = process.argv.slice(2);
  const shellOrigin = exactHttpOrigin(
    optionValue(args, "shell-origin") ||
      process.env.NEWMA_DESK_SHELL_ORIGIN ||
      process.env.NEWMA_DOCK_SHELL_ORIGIN ||
      process.env.VIBEDESK_SHELL_ORIGIN ||
      DEFAULT_SHELL_ORIGIN,
    "shell origin",
  );
  const timeoutMs = Number(optionValue(args, "timeout") || DEFAULT_TIMEOUT_MS);
  if (!Number.isFinite(timeoutMs) || timeoutMs < 1_000 || timeoutMs > 120_000) {
    throw new Error("timeout must be between 1000 and 120000 milliseconds");
  }
  const requestedIds = new Set(
    (optionValue(args, "mod") || "")
      .split(",")
      .map((id) => id.trim())
      .filter(Boolean),
  );
  const store = await loadModStore();
  const mods = store.mods.filter(({ manifest, id }) =>
    manifest.schemaVersion === "1.1" &&
    (requestedIds.size === 0 || requestedIds.has(id)),
  );
  if (requestedIds.size > 0) {
    const missing = [...requestedIds].filter((id) => !mods.some((mod) => mod.id === id));
    if (missing.length > 0) throw new Error(`Unknown or legacy Mod IDs: ${missing.join(", ")}`);
  }
  if (mods.length === 0) throw new Error("No Manifest 1.1 Mods selected for certification");

  const browser = await launchCertificationBrowser({
    headed: args.includes("--headed"),
    browserChannel: optionValue(args, "browser-channel"),
  });
  const results = [];
  try {
    for (const mod of mods) {
      process.stdout.write(`CERTIFY ${mod.id} declared=level-${mod.manifest.compatibility.level}\n`);
      const result = await certifyMod({ browser, mod, shellOrigin, timeoutMs });
      results.push(result);
      process.stdout.write(
        `${result.status === "certified" ? "CERTIFIED" : "FAILED"} ${mod.id}` +
          (result.certifiedLevel ? ` level=${result.certifiedLevel}` : "") +
          (result.failedChecks.length ? ` failed=${result.failedChecks.join(",")}` : "") +
          "\n",
      );
    }
  } finally {
    await browser.close();
  }

  const generatedAt = new Date().toISOString();
  const report = {
    schemaVersion: "1.0",
    generatedAt,
    shellOrigin,
    summary: summarizeRuntimeCertifications(results),
    results,
  };
  const output = optionValue(args, "output") || path.join(
    os.tmpdir(),
    `newma-desk-mod-certification-${generatedAt.replaceAll(":", "-")}.json`,
  );
  await writeFile(output, `${JSON.stringify(report, null, 2)}\n`, "utf8");
  process.stdout.write(`REPORT ${output}\n`);
  if (report.summary.failed > 0) process.exitCode = 1;
}

await main();
