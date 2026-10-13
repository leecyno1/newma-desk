#!/usr/bin/env node

import { randomUUID } from "node:crypto";
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
// Dev-mode Next runtimes may compile the first requested route on demand.
const DEFAULT_TIMEOUT_MS = 30_000;
const CERTIFICATION_MESSAGES_KEY = "__newmaDeskRuntimeCertificationMessages";
const PNG_DATA_URL_PREFIX = "data:image/png;base64,";

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

function sleep(milliseconds) {
  return new Promise((resolve) => setTimeout(resolve, milliseconds));
}

function contextFallbackReason(context) {
  const source = context?.data?.source;
  const contextSource = context?.data?.summary?.contextSource;
  if (contextSource === "dom-html-fallback") return "DOM/HTML fallback";
  if (contextSource === "server-playwright-dom") return "server visual fallback";
  if (
    typeof source === "string" &&
    [
      "newma-desk-same-origin-dom",
      "newma-desk-server-playwright",
      "seven-cycle-rendered-dom",
      "vibe-research-rendered-dom",
      "vibe-research-rendered-page",
    ].includes(source)
  ) {
    return source;
  }
  return undefined;
}

function assertStructuredContext(context) {
  if (!context || typeof context !== "object") {
    throw new Error("Agent Context response is missing");
  }
  if (!context.view || typeof context.view.id !== "string" || typeof context.view.title !== "string") {
    throw new Error("Agent Context view is malformed");
  }
  if (!context.data || typeof context.data !== "object") {
    throw new Error("Agent Context data is missing");
  }
  const fallbackReason = contextFallbackReason(context);
  if (fallbackReason) {
    throw new Error(`Mod returned ${fallbackReason} instead of structured Agent Context`);
  }
  if (typeof context.data.source !== "string" || !context.data.source.trim()) {
    throw new Error("Structured Agent Context does not declare its data source");
  }
  if (!["live", "fresh", "stale", "unknown"].includes(context.data.freshness)) {
    throw new Error("Structured Agent Context does not declare data freshness");
  }
}

function localPathLeak(value) {
  const serialized = JSON.stringify(value);
  if (/"(?:path|filePath|localPath|outputPath)"\s*:/.test(serialized)) return true;
  return /(?:\/(?:Users|Volumes|home|opt|private|tmp)\/|\/var\/folders\/|[A-Za-z]:\\Users\\)/.test(serialized);
}

function validateVisualArtifact(payload, expectedSource) {
  if (!payload || typeof payload !== "object" || payload.status !== "ready") {
    throw new Error("visual evidence response is not ready");
  }
  if (payload.source !== expectedSource) {
    throw new Error(`visual evidence returned ${payload.source || "an unknown source"}`);
  }
  const expectedMode = expectedSource === "browser-mod-bridge"
    ? "current-frame"
    : "reopened-module";
  if (payload.captureMode !== expectedMode) {
    throw new Error(`visual evidence did not declare ${expectedMode} capture mode`);
  }
  const image = payload.image;
  if (
    !image ||
    typeof image.artifactId !== "string" ||
    !/^[0-9a-f]{32}$/.test(image.artifactId) ||
    image.mimeType !== "image/png" ||
    !Number.isInteger(image.width) || image.width < 1 ||
    !Number.isInteger(image.height) || image.height < 1 ||
    !Number.isInteger(image.bytes) || image.bytes < 8
  ) {
    throw new Error("visual evidence did not return a usable PNG Artifact");
  }
  if (
    payload.delivery?.mode !== "artifact-reference" ||
    payload.delivery?.adapterReadable !== true
  ) {
    throw new Error("visual Artifact cannot be resolved by Agent adapters");
  }
  if (localPathLeak(payload)) {
    throw new Error("visual evidence response leaks a local filesystem path");
  }
  return image.artifactId;
}

async function waitForContextPersistence(
  request,
  shellOrigin,
  id,
  identity,
  timeoutMs,
  expectedInstanceId,
) {
  const deadline = Date.now() + timeoutMs;
  let lastStatus = 0;
  let lastDetail = "context not found";
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
    if (response.ok()) {
      const body = await response.json();
      try {
        assertStructuredContext(body?.context);
        if (expectedInstanceId && body.instanceId !== expectedInstanceId) {
          lastDetail = `received context from instance ${body.instanceId || "unknown"}`;
        } else {
          return body;
        }
      } catch (error) {
        lastDetail = error instanceof Error ? error.message : String(error);
      }
    }
    await sleep(200);
  }
  throw new Error(
    `Structured Agent Context was not persisted from the current frame (last HTTP ${lastStatus || "unavailable"}; ${lastDetail})`,
  );
}

async function frameInitMessage(frame, modId, timeoutMs) {
  await frame.waitForFunction(
    ({ key, id }) => Array.isArray(globalThis[key]) && globalThis[key].some(
      (message) => message?.type === "vibedesk:init" && message?.modId === id,
    ),
    { key: CERTIFICATION_MESSAGES_KEY, id: modId },
    { timeout: timeoutMs },
  );
  return frame.evaluate(
    ({ key, id }) => globalThis[key].findLast(
      (message) => message?.type === "vibedesk:init" && message?.modId === id,
    ),
    { key: CERTIFICATION_MESSAGES_KEY, id: modId },
  );
}

async function bridgeHelloMessage(page, modId, timeoutMs) {
  await page.waitForFunction(
    ({ key, id }) => Array.isArray(globalThis[key]) && globalThis[key].some(
      (message) => message?.type === "vibedesk:hello" && message?.modId === id,
    ),
    { key: CERTIFICATION_MESSAGES_KEY, id: modId },
    { timeout: timeoutMs },
  );
  return page.evaluate(
    ({ key, id }) => globalThis[key].findLast(
      (message) => message?.type === "vibedesk:hello" && message?.modId === id,
    ),
    { key: CERTIFICATION_MESSAGES_KEY, id: modId },
  );
}

async function requestBridgeResponse({
  page,
  modId,
  targetOrigin,
  request,
  responseType,
  timeoutMs,
}) {
  return page.evaluate(
    ({ id, origin, payload, expectedType, timeout }) => new Promise((resolve, reject) => {
      const boundary = document.querySelector(
        `.module-frame[data-vibedesk-mod-id="${CSS.escape(id)}"]`,
      );
      const iframe = boundary?.querySelector("iframe");
      if (!iframe?.contentWindow) {
        reject(new Error("embedded iframe is unavailable"));
        return;
      }
      const timer = window.setTimeout(() => {
        window.removeEventListener("message", onMessage);
        reject(new Error(`${expectedType} response timed out`));
      }, timeout);
      const onMessage = (event) => {
        const data = event.data;
        if (
          event.source !== iframe.contentWindow ||
          event.origin !== origin ||
          !data || typeof data !== "object" ||
          data.type !== expectedType ||
          data.requestId !== payload.requestId ||
          data.instanceId !== payload.instanceId ||
          data.modId !== id
        ) return;
        window.clearTimeout(timer);
        window.removeEventListener("message", onMessage);
        resolve(data);
      };
      window.addEventListener("message", onMessage);
      iframe.contentWindow.postMessage(payload, origin);
    }),
    {
      id: modId,
      origin: targetOrigin,
      payload: request,
      expectedType: responseType,
      timeout: Math.min(timeoutMs, 8_000),
    },
  );
}

async function requestStructuredContext({ page, modId, entryUrl, init, timeoutMs }) {
  const deadline = Date.now() + timeoutMs;
  let lastDetail = "context response not received";
  while (Date.now() < deadline) {
    const requestId = randomUUID();
    try {
      const response = await requestBridgeResponse({
        page,
        modId,
        targetOrigin: new URL(entryUrl).origin,
        request: {
          type: "vibedesk:context-request",
          requestId,
          instanceId: init.instanceId,
          modId,
          reason: "agent",
        },
        responseType: "vibedesk:context",
        timeoutMs,
      });
      assertStructuredContext(response.context);
      return response.context;
    } catch (error) {
      lastDetail = error instanceof Error ? error.message : String(error);
      await sleep(200);
    }
  }
  throw new Error(`current frame did not provide structured Agent Context: ${lastDetail}`);
}

function sessionFromInit(init) {
  if (
    !init || typeof init.instanceId !== "string" ||
    !init.session || typeof init.session.accessToken !== "string"
  ) {
    throw new Error("Desk init did not provide a scoped Mod session");
  }
  return {
    instanceId: init.instanceId,
    accessToken: init.session.accessToken,
  };
}

async function issueCertificationSession(request, shellOrigin, modId, identity) {
  const instanceId = `cert-evidence-${randomUUID()}`;
  const response = await request.post(
    `${shellOrigin}/api/mods/${encodeURIComponent(modId)}/sessions`,
    {
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
        "X-User-Id": identity.userId,
      },
      data: { instanceId, workspaceId: identity.workspaceId },
    },
  );
  if (!response.ok()) {
    throw new Error(`Mod session returned HTTP ${response.status()}`);
  }
  const body = await response.json();
  if (body.instanceId !== instanceId || typeof body.accessToken !== "string") {
    throw new Error("Mod session response is malformed");
  }
  return { instanceId, accessToken: body.accessToken };
}

function sessionHeaders(session, contentType) {
  return {
    Accept: "application/json",
    Authorization: `Bearer ${session.accessToken}`,
    "X-Newma-Desk-Instance-Id": session.instanceId,
    ...(contentType ? { "Content-Type": contentType } : {}),
  };
}

async function persistStructuredContext(
  request,
  shellOrigin,
  modId,
  identity,
  session,
  pageContext,
  timeoutMs,
) {
  const response = await request.put(
    `${shellOrigin}/api/mods/${encodeURIComponent(modId)}/context`,
    {
      headers: sessionHeaders(session, "application/json"),
      data: { context: pageContext },
      timeout: timeoutMs,
    },
  );
  if (!response.ok()) {
    throw new Error(`structured context persistence returned HTTP ${response.status()}`);
  }
  return waitForContextPersistence(
    request,
    shellOrigin,
    modId,
    identity,
    timeoutMs,
    session.instanceId,
  );
}

async function renderedDomEvidence(frame, boundary) {
  const locator = frame ? frame.locator("body") : boundary;
  return locator.evaluate((root) => {
    const text = (root.innerText || root.textContent || "")
      .replace(/[ \t]+\n/g, "\n")
      .replace(/\n{3,}/g, "\n\n")
      .trim();
    const clone = root.cloneNode(true);
    for (const node of clone.querySelectorAll(
      "script,style,noscript,template,svg,canvas,video,audio,input[type=password],input[type=hidden]",
    )) node.remove();
    const html = clone.outerHTML.replace(/>\s+</g, "><").trim();
    return {
      textChars: text.length,
      htmlChars: html.length,
      visualElementCount: root.querySelectorAll(
        "canvas,svg,img,video,[role=img],[data-visual-context]",
      ).length,
    };
  });
}

async function waitForRenderedDomEvidence(frame, boundary, timeoutMs) {
  const deadline = Date.now() + timeoutMs;
  let evidence = await renderedDomEvidence(frame, boundary);
  while (evidence.textChars < 20 && Date.now() < deadline) {
    await sleep(200);
    evidence = await renderedDomEvidence(frame, boundary);
  }
  return evidence;
}

async function uploadBrowserVisual(
  request,
  shellOrigin,
  modId,
  session,
  capture,
  timeoutMs,
) {
  if (
    !capture || typeof capture.dataUrl !== "string" ||
    !capture.dataUrl.startsWith(PNG_DATA_URL_PREFIX)
  ) {
    throw new Error("visual-context capability did not return a PNG data URL");
  }
  const image = Buffer.from(capture.dataUrl.slice(PNG_DATA_URL_PREFIX.length), "base64");
  if (image.length < 8 || !image.subarray(0, 8).equals(Buffer.from("89504e470d0a1a0a", "hex"))) {
    throw new Error("visual-context capability returned invalid PNG bytes");
  }
  const query = new URLSearchParams({
    width: String(capture.width),
    height: String(capture.height),
  });
  const response = await request.post(
    `${shellOrigin}/api/mods/${encodeURIComponent(modId)}/visual-context?${query}`,
    {
      headers: sessionHeaders(session, "image/png"),
      data: image,
      timeout: timeoutMs,
    },
  );
  if (!response.ok()) {
    throw new Error(`current-frame visual upload returned HTTP ${response.status()}`);
  }
  const payload = await response.json();
  validateVisualArtifact(payload, "browser-mod-bridge");
  return payload;
}

async function captureServerVisual(
  request,
  shellOrigin,
  modId,
  session,
  timeoutMs,
) {
  const response = await request.post(
    `${shellOrigin}/api/mods/${encodeURIComponent(modId)}/visual-context/capture`,
    {
      headers: {
        ...sessionHeaders(session),
        Origin: shellOrigin,
      },
      timeout: Math.max(timeoutMs, 35_000),
    },
  );
  if (!response.ok()) {
    const detail = await response.text();
    throw new Error(
      `server visual fallback returned HTTP ${response.status()}: ${detail.slice(0, 240)}`,
    );
  }
  const payload = await response.json();
  validateVisualArtifact(payload, "server-playwright");
  if (!payload.dom || (!payload.dom.text?.trim() && !payload.dom.html?.trim())) {
    throw new Error("server visual fallback did not return rendered DOM evidence");
  }
  return payload;
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
    userId: `cert-${mod.id}-${randomUUID().slice(0, 8)}`,
    workspaceId: `runtime-certification-${randomUUID()}`,
  };
  const context = await browser.newContext({
    viewport: { width: 1440, height: 900 },
  });
  const page = await context.newPage();
  await page.addInitScript(({ userId, workspaceId, messageKey }) => {
    try {
      localStorage.setItem("vibedesk.userId.v1", userId);
      localStorage.setItem("vibedesk.workspaceId.v1", workspaceId);
    } catch {
      // Third-party iframe storage can be blocked; the parent still owns identity.
    }
    const messages = [];
    Object.defineProperty(globalThis, messageKey, {
      configurable: false,
      enumerable: false,
      value: messages,
      writable: false,
    });
    window.addEventListener("message", (event) => {
      const data = event.data;
      if (
        !data || typeof data !== "object" ||
        !["vibedesk:hello", "vibedesk:init", "vibedesk:ack"].includes(data.type)
      ) return;
      messages.push(data);
      if (messages.length > 50) messages.shift();
    });
  }, { ...identity, messageKey: CERTIFICATION_MESSAGES_KEY });

  let entryUrl;
  let inlineEmbedded = false;
  let embeddedFrame;
  let boundary;
  let activeSession;
  let activeInit;
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
    boundary = page.locator(
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
    embeddedFrame = await handle?.contentFrame();
    if (!embeddedFrame || embeddedFrame.url().startsWith("chrome-error://")) {
      throw new Error("embedded frame did not create a readable document");
    }
    await embeddedFrame.locator("body").waitFor({ state: "attached", timeout: timeoutMs });
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
      if (!embeddedFrame || !entryUrl) {
        const persisted = await waitForContextPersistence(
          context.request,
          shellOrigin,
          mod.id,
          identity,
          timeoutMs,
        );
        return `structured inline context received and persisted (${persisted.context.data.source})`;
      }
      activeInit = await frameInitMessage(embeddedFrame, mod.id, timeoutMs);
      activeSession = sessionFromInit(activeInit);
      const currentPageContext = await requestStructuredContext({
        page,
        modId: mod.id,
        entryUrl,
        init: activeInit,
        timeoutMs,
      });
      const persisted = await persistStructuredContext(
        context.request,
        shellOrigin,
        mod.id,
        identity,
        activeSession,
        currentPageContext,
        timeoutMs,
      );
      return `current structured context persisted (${persisted.context.data.source}; ${persisted.context.data.freshness})`;
    });

    checks.agentEvidence = await captured(async () => {
      if (!boundary) throw new Error("Mod boundary is unavailable");
      const dom = await waitForRenderedDomEvidence(
        embeddedFrame,
        boundary,
        timeoutMs,
      );
      if (dom.textChars < 20 || dom.htmlChars < 20) {
        throw new Error("current page does not expose enough rendered DOM evidence");
      }
      const session = activeSession ?? await issueCertificationSession(
        context.request,
        shellOrigin,
        mod.id,
        identity,
      );
      let currentFrameArtifact = false;
      if (embeddedFrame && entryUrl) {
        activeInit ??= await frameInitMessage(embeddedFrame, mod.id, timeoutMs);
        const hello = await bridgeHelloMessage(page, mod.id, timeoutMs);
        if (Array.isArray(hello.capabilities) && hello.capabilities.includes("visual-context")) {
          const visualResponse = await requestBridgeResponse({
            page,
            modId: mod.id,
            targetOrigin: new URL(entryUrl).origin,
            request: {
              type: "vibedesk:visual-context-request",
              requestId: randomUUID(),
              instanceId: activeInit.instanceId,
              modId: mod.id,
              reason: "agent",
              maxBytes: 5 * 1024 * 1024,
              mediaTypes: ["image/png"],
            },
            responseType: "vibedesk:visual-context",
            timeoutMs,
          });
          if (visualResponse.ok !== true) {
            throw new Error(
              `visual-context was declared but failed: ${visualResponse.error?.message || "unknown error"}`,
            );
          }
          await uploadBrowserVisual(
            context.request,
            shellOrigin,
            mod.id,
            session,
            visualResponse.capture,
            timeoutMs,
          );
          currentFrameArtifact = true;
        }
      }
      const serverVisual = await captureServerVisual(
        context.request,
        shellOrigin,
        mod.id,
        session,
        timeoutMs,
      );
      return [
        `DOM ${dom.textChars} chars`,
        currentFrameArtifact ? "current-frame visual Artifact" : "no visual-context declaration",
        `server fallback ${serverVisual.image.width}x${serverVisual.image.height}`,
        "adapter-readable Artifact; no path leak",
      ].join("; ");
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
