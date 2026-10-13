#!/usr/bin/env node

import { mkdir } from "node:fs/promises";
import path from "node:path";

import { chromium } from "@playwright/test";

const MAX_TEXT_CHARS = 24_000;
const MAX_HTML_CHARS = 24_000;

function redactLocalPaths(value) {
  return value.replace(
    /(?:\/(?:Users|Volumes|home|opt|private|tmp)\/|\/var\/folders\/)[^<>"'\n\r]*/g,
    "[local-path]",
  ).replace(
    /[A-Za-z]:\\Users\\[^<>"'\n\r]*/g,
    "[local-path]",
  );
}

function optionValue(args, name) {
  const prefix = `--${name}=`;
  const inline = args.find((argument) => argument.startsWith(prefix));
  if (inline) return inline.slice(prefix.length);
  const index = args.indexOf(`--${name}`);
  return index >= 0 ? args[index + 1] : undefined;
}

function exactHttpOrigin(value) {
  const parsed = new URL(value);
  if (
    !["http:", "https:"].includes(parsed.protocol) ||
    parsed.username ||
    parsed.password ||
    parsed.origin !== value
  ) {
    throw new Error("shell origin must be an exact HTTP(S) origin");
  }
  return parsed.origin;
}

async function launchBrowser() {
  try {
    return await chromium.launch({ headless: true });
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    if (!/executable.*(?:doesn(?:'|’)t exist|not found)/i.test(message)) throw error;
    return chromium.launch({ headless: true, channel: "chrome" });
  }
}

async function renderedContext(frame) {
  const rendered = await frame.locator("body").evaluate((body) => {
    const text = (body.innerText || body.textContent || "")
      .replace(/[ \t]+\n/g, "\n")
      .replace(/\n{3,}/g, "\n\n")
      .trim();
    const clone = body.cloneNode(true);
    for (const node of clone.querySelectorAll(
      "script,style,noscript,template,svg,canvas,video,audio,input[type=password],input[type=hidden]",
    )) {
      node.remove();
    }
    for (const element of clone.querySelectorAll("*")) {
      for (const attribute of [...element.attributes]) {
        if (
          attribute.name === "style" ||
          attribute.name.startsWith("on") ||
          attribute.name === "srcset"
        ) {
          element.removeAttribute(attribute.name);
        }
      }
    }
    const html = clone.outerHTML.replace(/>\s+</g, "><").trim();
    return { text, html };
  });
  const text = redactLocalPaths(rendered.text);
  const html = redactLocalPaths(rendered.html);
  return {
    text: text.slice(0, MAX_TEXT_CHARS),
    html: html.slice(0, MAX_HTML_CHARS),
    textTruncated: text.length > MAX_TEXT_CHARS,
    htmlTruncated: html.length > MAX_HTML_CHARS,
  };
}

async function main() {
  const args = process.argv.slice(2);
  const moduleId = optionValue(args, "mod") || "";
  if (!/^[a-z][a-z0-9-]{2,63}$/.test(moduleId)) {
    throw new Error("mod must be a valid Mod ID");
  }
  const workspaceId = optionValue(args, "workspace") || "";
  if (workspaceId && !/^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/.test(workspaceId)) {
    throw new Error("workspace must be a valid workspace ID");
  }
  const shellOrigin = exactHttpOrigin(optionValue(args, "shell-origin") || "");
  const output = path.resolve(optionValue(args, "output") || "");
  if (!output.endsWith(".png")) throw new Error("output must be a PNG path");
  const timeoutMs = Number(optionValue(args, "timeout") || 30_000);
  if (!Number.isFinite(timeoutMs) || timeoutMs < 1_000 || timeoutMs > 60_000) {
    throw new Error("timeout must be between 1000 and 60000 milliseconds");
  }

  await mkdir(path.dirname(output), { recursive: true });
  const browser = await launchBrowser();
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
    const target = new URL("/", shellOrigin);
    target.searchParams.set("mod", moduleId);
    target.searchParams.set("standalone", "1");
    if (workspaceId) target.searchParams.set("workspace", workspaceId);
    const pageUrl = target.toString();
    const response = await page.goto(pageUrl, {
      waitUntil: "domcontentloaded",
      timeout: timeoutMs,
    });
    if (!response?.ok()) {
      throw new Error(`Desk returned HTTP ${response?.status() ?? "unavailable"}`);
    }
    const boundary = page.locator(
      `.module-frame[data-vibedesk-mod-id="${moduleId}"]`,
    );
    await boundary.waitFor({ state: "visible", timeout: timeoutMs });
    const iframe = boundary.locator("iframe").first();
    let contentFrame = page.mainFrame();
    let screenshotTarget = boundary;
    if (await iframe.count()) {
      await iframe.waitFor({ state: "visible", timeout: timeoutMs });
      const handle = await iframe.elementHandle();
      contentFrame = (await handle?.contentFrame()) ?? page.mainFrame();
      screenshotTarget = iframe;
    }
    await contentFrame.locator("body").waitFor({ state: "attached", timeout: timeoutMs });
    await contentFrame.waitForFunction(
      () => (document.body?.innerText || document.body?.textContent || "").trim().length >= 20,
      undefined,
      { timeout: Math.min(timeoutMs, 15_000) },
    ).catch(() => undefined);
    await page.waitForTimeout(300);
    const dom = await renderedContext(contentFrame);
    await screenshotTarget.screenshot({ path: output, type: "png" });
    const box = await screenshotTarget.boundingBox();
    process.stdout.write(JSON.stringify({
      status: "ready",
      source: "server-playwright",
      capturedAt: new Date().toISOString(),
      pageUrl,
      renderedUrl: contentFrame.url(),
      dom,
      image: {
        path: output,
        mimeType: "image/png",
        width: Math.round(box?.width ?? 0),
        height: Math.round(box?.height ?? 0),
      },
    }));
  } finally {
    await browser.close();
  }
}

await main();
