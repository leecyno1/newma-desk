#!/usr/bin/env node

import { readdir, readFile, stat } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

import { loadExternalModRuntimes } from "./lib/external-mod-runtimes.mjs";

const REPO_ROOT = fileURLToPath(new URL("../", import.meta.url));
const DEFAULT_ROOTS = [
  "apps/shell/src",
  "modules",
  "packages/chart-kit/src",
  "bundled-runtimes/vibe-research/frontend",
  "bundled-runtimes/vibe-trading/frontend",
];
const REQUIRED_TEMPLATE_IMPORTS = [
  "modules/global-intelligence/src/main.tsx",
  "modules/market-daily/src/main.tsx",
  "modules/portfolio-center/src/main.tsx",
  "modules/creator-studio/src/main.tsx",
  "modules/policy-analysis/src/main.tsx",
  "modules/capital-flow/src/main.tsx",
];
const EXTERNAL_THEME_ADAPTERS = [
  {
    runtime: "deepsee",
    workspace: "source",
    files: [
      { path: "static/modules/vibedesk-embed.css", markers: ["--vibe-bg", "vibedesk-embed"] },
    ],
  },
  {
    runtime: "seven-cycle",
    workspace: "source",
    files: [
      { path: "web/src/lib/vibedesk.ts", markers: ["vibedesk:init", "appearance"] },
    ],
  },
  {
    runtime: "instock",
    workspace: "source",
    files: [
      { path: "instock/web/static/js/vibedesk-bridge.js", markers: ["vibedesk:init", "cssVars"] },
      { path: "instock/web/static/css/vibedesk-theme.css", markers: ["--instock-bg", "#f4efe3"] },
    ],
  },
  {
    runtime: "orchestra",
    workspace: "frontend",
    files: [
      { path: "hooks/useVibeDeskBridge.ts", markers: ["vibedesk:init", "appearance"] },
      { path: "styles/orchestra.css", markers: ["--vibe-bg", "--vibe-accent"] },
    ],
  },
];
const SOURCE_EXTENSIONS = new Set([
  ".css",
  ".html",
  ".js",
  ".jsx",
  ".less",
  ".sass",
  ".scss",
  ".svelte",
  ".svg",
  ".ts",
  ".tsx",
  ".vue",
]);
const SKIPPED_DIRECTORIES = new Set([
  ".git",
  "__tests__",
  "build",
  "coverage",
  "dist",
  "node_modules",
  "output",
  "vendor",
]);

const RULES = [
  {
    id: "tailwind-default-blue",
    pattern:
      /\b(?:bg|text|border|ring|outline|shadow|from|via|to)-(?:blue|sky|indigo|slate)-(?:[1-9]\d{1,2})(?:\/\d{1,3})?\b/gi,
  },
  {
    id: "legacy-blue-slate-hex",
    pattern:
      /#(?:eff6ff|dbeafe|bfdbfe|93c5fd|60a5fa|3b82f6|2563eb|1d4ed8|1e40af|1e3a8a|f0f9ff|e0f2fe|bae6fd|7dd3fc|38bdf8|0ea5e9|0284c7|0369a1|075985|0c4a6e|007aff|0066d6|0a84ff|337ab7|428bca|f8fafc|f1f5f9|e2e8f0|cbd5e1|94a3b8|64748b|475569|334155|1e293b|0f172a)\b/gi,
  },
  {
    id: "legacy-blue-rgb",
    pattern:
      /rgba?\(\s*(?:0\s*,\s*122\s*,\s*255|20\s*,\s*38\s*,\s*79|37\s*,\s*99\s*,\s*235|51\s*,\s*122\s*,\s*183|59\s*,\s*130\s*,\s*246|66\s*,\s*139\s*,\s*202)(?:\s*[,/]\s*[\d.]+)?\s*\)/gi,
  },
  {
    id: "white-browser-theme",
    pattern:
      /<meta\s+[^>]*name=["']theme-color["'][^>]*content=["']#(?:fff|ffffff)["'][^>]*>/gi,
  },
];

function ignoredFile(filePath) {
  const base = path.basename(filePath);
  return (
    base.endsWith(".min.js") ||
    base.endsWith(".min.css") ||
    /\.(?:test|spec)\.[^.]+$/i.test(base)
  );
}

async function sourceFiles(root) {
  const result = [];
  const visit = async (current) => {
    const metadata = await stat(current);
    if (metadata.isFile()) {
      if (
        SOURCE_EXTENSIONS.has(path.extname(current).toLowerCase()) &&
        !ignoredFile(current)
      ) {
        result.push(current);
      }
      return;
    }
    if (!metadata.isDirectory()) return;
    const entries = await readdir(current, { withFileTypes: true });
    for (const entry of entries) {
      if (entry.isDirectory() && SKIPPED_DIRECTORIES.has(entry.name)) continue;
      await visit(path.join(current, entry.name));
    }
  };
  await visit(root);
  return result;
}

export async function scanThemeSources(roots) {
  const findings = [];
  for (const root of roots) {
    let files;
    try {
      files = await sourceFiles(root);
    } catch (error) {
      if (error && typeof error === "object" && error.code === "ENOENT") continue;
      throw error;
    }
    for (const file of files) {
      const lines = (await readFile(file, "utf8")).split(/\r?\n/);
      lines.forEach((line, index) => {
        const allowedRules = new Set(
          [...line.matchAll(/\bnewma-theme-allow(?::|\s+)([a-z0-9-]+)\b/gi)]
            .map((match) => match[1].toLowerCase()),
        );
        for (const rule of RULES) {
          if (allowedRules.has(rule.id)) continue;
          rule.pattern.lastIndex = 0;
          for (const match of line.matchAll(rule.pattern)) {
            findings.push({
              file,
              line: index + 1,
              column: (match.index ?? 0) + 1,
              rule: rule.id,
              value: match[0],
            });
          }
        }
      });
    }
  }
  return findings;
}

async function externalThemeAdapterState() {
  const catalog = await loadExternalModRuntimes();
  const roots = [];
  const missing = [];
  for (const adapter of EXTERNAL_THEME_ADAPTERS) {
    const workspace = catalog.byId[adapter.runtime]?.workspaces[adapter.workspace];
    if (!workspace?.path) continue;
    for (const descriptor of adapter.files) {
      const file = path.join(workspace.path, descriptor.path);
      let source;
      try {
        source = await readFile(file, "utf8");
      } catch (error) {
        if (error && typeof error === "object" && error.code === "ENOENT") {
          missing.push(`${adapter.runtime}: missing ${file}`);
          continue;
        }
        throw error;
      }
      const absent = descriptor.markers.filter((marker) => !source.includes(marker));
      if (absent.length) {
        missing.push(`${adapter.runtime}: ${file} missing ${absent.join(", ")}`);
      }
      roots.push(file);
    }
  }
  return { roots, missing };
}

async function missingTemplateImports() {
  const missing = [];
  for (const relativePath of REQUIRED_TEMPLATE_IMPORTS) {
    const file = path.join(REPO_ROOT, relativePath);
    const source = await readFile(file, "utf8");
    if (!source.includes('@newma-desk/desk-ui/mod-theme.css')) {
      missing.push(relativePath);
    }
  }
  return missing;
}

export async function runThemeCheck(arguments_ = process.argv.slice(2)) {
  const explicitRoots = arguments_.filter((value) => value !== "--no-import-check");
  const external = explicitRoots.length ? { roots: [], missing: [] } : await externalThemeAdapterState();
  const roots = [...(explicitRoots.length ? explicitRoots : DEFAULT_ROOTS), ...external.roots].map((value) =>
    path.resolve(REPO_ROOT, value),
  );
  const findings = await scanThemeSources(roots);
  const missingImports =
    explicitRoots.length || arguments_.includes("--no-import-check")
      ? []
      : await missingTemplateImports();
  return { findings, missingImports, missingAdapters: external.missing };
}

async function main() {
  const result = await runThemeCheck();
  for (const finding of result.findings) {
    const label = path.isAbsolute(finding.file)
      ? path.relative(REPO_ROOT, finding.file) || finding.file
      : finding.file;
    process.stderr.write(
      `${label}:${finding.line}:${finding.column} ${finding.rule} ${finding.value}\n`,
    );
  }
  for (const file of result.missingImports) {
    process.stderr.write(
      `${file}: missing @newma-desk/desk-ui/mod-theme.css import\n`,
    );
  }
  for (const issue of result.missingAdapters) process.stderr.write(`${issue}\n`);
  if (result.findings.length || result.missingImports.length || result.missingAdapters.length) {
    process.stderr.write(
      "Newma theme check failed. Map legacy brand colors to semantic --vibe-* variables; scope reviewed exceptions as newma-theme-allow:<rule-id>.\n",
    );
    process.exitCode = 1;
    return;
  }
  process.stdout.write(
    `Newma theme check passed (${rootsLabel(process.argv.slice(2))}).\n`,
  );
}

function rootsLabel(arguments_) {
  const roots = arguments_.filter((value) => !value.startsWith("--"));
  return roots.length ? roots.join(", ") : "default Mod sources";
}

if (
  process.argv[1] &&
  import.meta.url === pathToFileURL(process.argv[1]).href
) {
  await main();
}
