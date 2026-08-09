#!/usr/bin/env node

import { chromium } from "@playwright/test";

const DEFAULT_SHELL_ORIGIN = "http://127.0.0.1:5888";
const DEFAULT_API_ORIGIN = "http://127.0.0.1:8911";
const DEFAULT_TIMEOUT_MS = 20_000;
const DEFAULT_SETTLE_MS = 800;
const THEMES = ["light", "dark"];
const THEME_BG = {
  light: [244, 239, 227],
  dark: [15, 23, 20],
};

function usage() {
  return `Usage: npm run mods:theme:audit -- [options]

Options:
  --mod <id[,id...]>       Audit only selected Mods (repeatable)
  --shell-origin <origin>  Newma-Desk shell origin (default ${DEFAULT_SHELL_ORIGIN})
  --api-origin <origin>    Control-plane origin (default ${DEFAULT_API_ORIGIN})
  --timeout <ms>           Navigation/load timeout (default ${DEFAULT_TIMEOUT_MS})
  --settle <ms>            Post-load settle time (default ${DEFAULT_SETTLE_MS})
  --headed                 Show the browser
  --browser-channel <name> Playwright browser channel, for example chrome
  --help                    Show this help
`;
}

function parseArgs(argv) {
  const options = { mods: [], headed: false };
  const valueOptions = new Set([
    "mod", "shell-origin", "api-origin", "timeout", "settle", "browser-channel",
  ]);
  for (let index = 0; index < argv.length; index += 1) {
    const argument = argv[index];
    if (argument === "--headed") {
      options.headed = true;
      continue;
    }
    if (argument === "--help") {
      options.help = true;
      continue;
    }
    if (!argument.startsWith("--")) throw new Error(`Unexpected argument: ${argument}`);
    const equals = argument.indexOf("=");
    const name = argument.slice(2, equals < 0 ? undefined : equals);
    if (!valueOptions.has(name)) throw new Error(`Unknown option: --${name}`);
    const value = equals < 0 ? argv[++index] : argument.slice(equals + 1);
    if (!value || value.startsWith("--")) throw new Error(`--${name} requires a value`);
    if (name === "mod") options.mods.push(...value.split(","));
    else options[name.replaceAll("-", "_")] = value;
  }
  options.mods = options.mods.map((id) => id.trim()).filter(Boolean);
  return options;
}

function httpOrigin(value, label) {
  let url;
  try {
    url = new URL(value);
  } catch {
    throw new Error(`${label} must be an HTTP(S) origin`);
  }
  if (!["http:", "https:"].includes(url.protocol) || url.username || url.password ||
      (url.pathname !== "/" && url.pathname !== "") || url.search || url.hash) {
    throw new Error(`${label} must be an HTTP(S) origin`);
  }
  return url.origin;
}

function milliseconds(value, fallback, label, minimum, maximum) {
  const parsed = value === undefined ? fallback : Number(value);
  if (!Number.isFinite(parsed) || parsed < minimum || parsed > maximum) {
    throw new Error(`${label} must be between ${minimum} and ${maximum} milliseconds`);
  }
  return Math.round(parsed);
}

async function loadMods(apiOrigin, requestedIds, timeoutMs) {
  const response = await fetch(`${apiOrigin}/api/mods`, {
    signal: AbortSignal.timeout(timeoutMs),
  });
  if (!response.ok) throw new Error(`/api/mods returned HTTP ${response.status}`);
  const rows = await response.json();
  if (!Array.isArray(rows)) throw new Error("/api/mods returned malformed data");
  const mods = rows.map((row) => ({
    id: row?.moduleId,
    name: row?.manifest?.name,
  })).filter(({ id, name }) => typeof id === "string" && typeof name === "string");
  if (mods.length !== rows.length) throw new Error("/api/mods returned malformed data");
  const requested = new Set(requestedIds);
  const selected = requested.size === 0 ? mods : mods.filter(({ id }) => requested.has(id));
  const missing = [...requested].filter((id) => !mods.some((mod) => mod.id === id));
  if (missing.length) throw new Error(`Unknown Mod IDs: ${missing.join(", ")}`);
  if (!selected.length) throw new Error("No installed Mods selected for audit");
  return selected;
}

async function launchBrowser({ headed, browserChannel }) {
  if (browserChannel) {
    return chromium.launch({ headless: !headed, channel: browserChannel });
  }
  try {
    return await chromium.launch({ headless: !headed });
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    if (!/executable.*(?:doesn(?:'|’)t exist|not found)/i.test(message)) throw error;
    process.stdout.write("BROWSER Playwright Chromium unavailable; falling back to Google Chrome\n");
    return chromium.launch({ headless: !headed, channel: "chrome" });
  }
}

async function findModFrame(page, mod, timeoutMs) {
  await page.waitForFunction(
    (id) => [...document.querySelectorAll(".module-frame")]
      .some((node) => node.getAttribute("data-vibedesk-mod-id") === id),
    mod.id,
    { timeout: timeoutMs },
  );
  const sections = page.locator(".module-frame");
  for (let index = 0; index < await sections.count(); index += 1) {
    const section = sections.nth(index);
    if (await section.getAttribute("data-vibedesk-mod-id") === mod.id) {
      return section;
    }
  }
  throw new Error("Desk did not render the selected Mod frame");
}

async function inspectTheme(frame, expectedTheme) {
  return frame.evaluate(({ theme, expectedBg }) => {
    const root = document.documentElement;
    const rootStyle = getComputedStyle(root);
    const issues = [];
    const themeMarkers = [root.dataset.theme, root.dataset.vibedeskTheme].filter(Boolean);
    if (!themeMarkers.includes(theme) || themeMarkers.some((value) => value !== theme)) {
      issues.push(`root theme marker is ${themeMarkers.join("/") || "missing"}; expected ${theme}`);
    }
    const colorScheme = rootStyle.colorScheme.trim();
    if (colorScheme !== theme) {
      issues.push(`color-scheme is ${colorScheme || "missing"}; expected ${theme}`);
    }

    const colorTuples = (value) => {
      const colors = [];
      const pattern = /rgba?\(([^)]+)\)|#([\da-f]{3,8})\b/gi;
      for (const match of value.matchAll(pattern)) {
        if (match[1]) {
          const parts = match[1].replaceAll(",", " ").split(/[\s/]+/).filter(Boolean);
          if (parts.length < 3) continue;
          const channel = (part) => part.endsWith("%")
            ? Math.round(Number.parseFloat(part) * 2.55)
            : Number.parseFloat(part);
          const alpha = parts[3] === undefined ? 1 : parts[3].endsWith("%")
            ? Number.parseFloat(parts[3]) / 100
            : Number.parseFloat(parts[3]);
          const tuple = [channel(parts[0]), channel(parts[1]), channel(parts[2]), alpha];
          if (tuple.every(Number.isFinite)) colors.push(tuple);
          continue;
        }
        const hex = match[2];
        const expanded = hex.length <= 4
          ? [...hex].map((digit) => `${digit}${digit}`).join("")
          : hex;
        const tuple = [0, 2, 4].map((offset) => Number.parseInt(expanded.slice(offset, offset + 2), 16));
        tuple.push(expanded.length === 8 ? Number.parseInt(expanded.slice(6, 8), 16) / 255 : 1);
        colors.push(tuple);
      }
      return colors;
    };
    const vibeBg = rootStyle.getPropertyValue("--vibe-bg").trim();
    const vibeBgColor = colorTuples(vibeBg)[0];
    if (!vibeBgColor || expectedBg.some((value, index) => Math.abs(value - vibeBgColor[index]) > 1)) {
      issues.push(`--vibe-bg is ${vibeBg || "missing"}; expected rgb(${expectedBg.join(", ")})`);
    }

    const isBlue = ([red, green, blue, alpha]) => {
      if (alpha < 0.2) return false;
      const max = Math.max(red, green, blue);
      const min = Math.min(red, green, blue);
      const chroma = max - min;
      if (chroma < 18) return false;
      const lightness = (max + min) / 510;
      const saturation = chroma / (255 * (1 - Math.abs(2 * lightness - 1)) || 1);
      let hue = max === red
        ? 60 * (((green - blue) / chroma) % 6)
        : max === green
          ? 60 * ((blue - red) / chroma + 2)
          : 60 * ((red - green) / chroma + 4);
      if (hue < 0) hue += 360;
      return hue >= 185 && hue <= 260 && saturation >= 0.22 && lightness >= 0.08 && lightness <= 0.94;
    };
    const isNeutralWhite = ([red, green, blue, alpha]) =>
      alpha >= 0.8 && Math.min(red, green, blue) >= 246 &&
      Math.max(red, green, blue) - Math.min(red, green, blue) <= 5;
    const hasBlue = (value) => colorTuples(value).some(isBlue);
    const targetName = (element) => {
      const tag = element.tagName.toLowerCase();
      const id = element.id ? `#${element.id}` : "";
      const classes = [...element.classList].slice(0, 2).map((name) => `.${name}`).join("");
      const role = element.getAttribute("role");
      const label = element.getAttribute("aria-label") || element.getAttribute("title") ||
        element.textContent?.replace(/\s+/g, " ").trim().slice(0, 40);
      return `${tag}${id}${classes}${role ? `[role=${role}]` : ""}${label ? ` “${label}”` : ""}`;
    };
    const allowed = (element) => {
      let current = element;
      while (current) {
        if (current.matches?.("[data-newma-theme-allow], .newma-theme-allow")) return true;
        const parent = current.parentElement;
        current = parent || current.getRootNode?.().host || null;
      }
      return false;
    };
    const roots = [document];
    const elements = [];
    while (roots.length) {
      const currentRoot = roots.shift();
      for (const element of currentRoot.querySelectorAll("*")) {
        elements.push(element);
        if (element.shadowRoot) roots.push(element.shadowRoot);
      }
    }
    const viewportArea = Math.max(1, innerWidth * innerHeight);
    const largeArea = Math.max(12_000, viewportArea * 0.025);
    const findings = [];
    const findingElements = new Map();
    const addFinding = (kind, element, detail, area) => {
      const ancestors = findingElements.get(kind) || [];
      if (ancestors.some((ancestor) => ancestor.contains?.(element))) return;
      ancestors.push(element);
      findingElements.set(kind, ancestors);
      if (findings.length < 20) {
        findings.push({ kind, target: targetName(element), detail, area: Math.round(area) });
      }
    };
    const controlSelector = [
      "a", "button", "input", "select", "textarea", "[role=button]", "[role=link]",
      "[role=tab]", "[role=menuitem]", "[role=switch]", "[role=checkbox]", "[role=radio]",
    ].join(",");

    for (const element of elements) {
      if (allowed(element)) continue;
      const style = getComputedStyle(element);
      const rect = element.getBoundingClientRect();
      const width = Math.max(0, Math.min(innerWidth, rect.right) - Math.max(0, rect.left));
      const height = Math.max(0, Math.min(innerHeight, rect.bottom) - Math.max(0, rect.top));
      const area = width * height;
      if (!area || style.display === "none" || style.visibility !== "visible" ||
          Number.parseFloat(style.opacity || "1") <= 0.05 ||
          element.checkVisibility?.({ checkOpacity: true, checkVisibilityCSS: true }) === false) continue;

      const background = style.backgroundColor;
      const gradient = style.backgroundImage === "none" ? "" : style.backgroundImage;
      if (area >= largeArea && (hasBlue(background) || hasBlue(gradient))) {
        addFinding("large-blue-background", element, `${background}${gradient ? `; ${gradient}` : ""}`, area);
      }
      if (area >= largeArea && colorTuples(background).some(isNeutralWhite)) {
        addFinding("large-neutral-white-block", element, background, area);
      }
      if (!element.matches(controlSelector)) continue;
      if (hasBlue(background) || hasBlue(gradient)) {
        addFinding("blue-control-background", element, `${background}${gradient ? `; ${gradient}` : ""}`, area);
      }
      if (hasBlue(style.color)) addFinding("blue-control-text", element, style.color, area);
      for (const side of ["Top", "Right", "Bottom", "Left"]) {
        if (Number.parseFloat(style[`border${side}Width`]) > 0 &&
            style[`border${side}Style`] !== "none" && hasBlue(style[`border${side}Color`])) {
          addFinding("blue-control-border", element, style[`border${side}Color`], area);
          break;
        }
      }
    }
    return { issues, findings };
  }, { theme: expectedTheme, expectedBg: THEME_BG[expectedTheme] });
}

async function auditMod(page, mod, theme, shellOrigin, timeoutMs, settleMs) {
  const response = await page.goto(`${shellOrigin}/?mod=${encodeURIComponent(mod.id)}`, {
    waitUntil: "domcontentloaded",
    timeout: timeoutMs,
  });
  if (!response?.ok()) throw new Error(`Desk navigation returned HTTP ${response?.status() ?? "unknown"}`);
  const section = await findModFrame(page, mod, timeoutMs);
  const iframe = section.locator("iframe");
  await iframe.waitFor({ state: "visible", timeout: timeoutMs });
  await section.waitFor({ state: "visible", timeout: timeoutMs });
  await page.waitForFunction(
    (id) => [...document.querySelectorAll(".module-frame")].find(
      (node) => node.getAttribute("data-vibedesk-mod-id") === id,
    )?.getAttribute("data-vibedesk-frame-state") === "ready",
    mod.id,
    { timeout: timeoutMs },
  );
  const iframeHandle = await iframe.elementHandle();
  const frame = await iframeHandle?.contentFrame();
  if (!frame || frame.url().startsWith("chrome-error://")) throw new Error("Mod iframe is unreadable");
  await frame.locator("body").waitFor({ state: "attached", timeout: timeoutMs });
  await frame.waitForFunction(
    (expected) => [document.documentElement.dataset.theme, document.documentElement.dataset.vibedeskTheme]
      .includes(expected),
    theme,
    { timeout: Math.min(timeoutMs, 4_000) },
  ).catch(() => {});
  if (settleMs) await page.waitForTimeout(settleMs);
  const inspectedFrames = [
    { label: "Mod", frame },
    ...frame.childFrames()
      .filter((child) => new URL(child.url()).searchParams.get("newmaTheme") === "1")
      .map((child) => ({ label: `nested artifact ${child.url()}`, frame: child })),
  ];
  const issues = [];
  for (const inspected of inspectedFrames) {
    const result = await inspectTheme(inspected.frame, theme);
    issues.push(
      ...result.issues.map((issue) => `${inspected.label}: ${issue}`),
      ...result.findings.map(({ kind, target, detail, area }) =>
        `${inspected.label}: ${kind} at ${target}: ${detail} (${area}px²)`,
      ),
    );
  }
  return issues;
}

async function main() {
  const options = parseArgs(process.argv.slice(2));
  if (options.help) {
    process.stdout.write(usage());
    return;
  }
  const shellOrigin = httpOrigin(
    options.shell_origin || process.env.NEWMA_DESK_SHELL_ORIGIN ||
      process.env.NEWMA_DOCK_SHELL_ORIGIN || process.env.VIBEDESK_SHELL_ORIGIN ||
      DEFAULT_SHELL_ORIGIN,
    "shell origin",
  );
  const apiOrigin = httpOrigin(
    options.api_origin || process.env.NEWMA_DESK_API_ORIGIN ||
      process.env.NEWMA_DOCK_API_ORIGIN || process.env.VIBEDESK_API_ORIGIN ||
      DEFAULT_API_ORIGIN,
    "api origin",
  );
  const timeoutMs = milliseconds(options.timeout, DEFAULT_TIMEOUT_MS, "timeout", 1_000, 120_000);
  const settleMs = milliseconds(options.settle, DEFAULT_SETTLE_MS, "settle", 0, 30_000);
  const mods = await loadMods(apiOrigin, options.mods, timeoutMs);
  process.stdout.write(`AUDIT ${mods.length} installed Mod(s) from ${apiOrigin}\n`);
  const browser = await launchBrowser({
    headed: options.headed,
    browserChannel: options.browser_channel,
  });
  const failures = [];
  let passed = 0;
  try {
    for (const theme of THEMES) {
      const systemTheme = theme === "light" ? "dark" : "light";
      process.stdout.write(`THEME ${theme} (browser system=${systemTheme})\n`);
      const context = await browser.newContext({
        viewport: { width: 1440, height: 900 },
        colorScheme: systemTheme,
      });
      await context.addInitScript(({ origin, mode }) => {
        if (location.origin === origin) localStorage.setItem("vibedesk.themeMode", mode);
      }, { origin: shellOrigin, mode: theme });
      const openPage = async () => {
        const page = await context.newPage();
        page.on("dialog", (dialog) => dialog.dismiss().catch(() => {}));
        return page;
      };
      let page = await openPage();
      try {
        for (const mod of mods) {
          let issues;
          try {
            issues = await auditMod(page, mod, theme, shellOrigin, timeoutMs, settleMs);
          } catch (error) {
            const firstFailure = error instanceof Error ? error.message : String(error);
            process.stdout.write(`RETRY ${theme} ${mod.id} after ${firstFailure.split("\n", 1)[0]}\n`);
            await page.close().catch(() => {});
            page = await openPage();
            try {
              issues = await auditMod(page, mod, theme, shellOrigin, timeoutMs, settleMs);
            } catch (retryError) {
              const retryFailure = retryError instanceof Error
                ? retryError.message
                : String(retryError);
              issues = [retryFailure];
            }
          }
          if (issues.length === 0) {
            passed += 1;
            process.stdout.write(`PASS ${theme} ${mod.id} — ${mod.name}\n`);
          } else {
            failures.push({ theme, mod, issues });
            process.stdout.write(`FAIL ${theme} ${mod.id} — ${mod.name} (${issues.length})\n`);
          }
        }
      } finally {
        await page.close().catch(() => {});
        await context.close();
      }
    }
  } finally {
    await browser.close();
  }

  const total = mods.length * THEMES.length;
  process.stdout.write(`\nSUMMARY ${passed}/${total} passed; ${failures.length} failed\n`);
  if (failures.length) {
    process.stdout.write("FAILURES\n");
    for (const { theme, mod, issues } of failures) {
      process.stdout.write(`- ${theme} ${mod.id} — ${mod.name}\n`);
      for (const issue of issues) process.stdout.write(`    ${issue}\n`);
    }
    process.exitCode = 1;
  }
}

main().catch((error) => {
  process.stderr.write(`ERROR ${error instanceof Error ? error.message : String(error)}\n`);
  process.exitCode = 1;
});
