import assert from "node:assert/strict";
import { mkdtemp, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";

import { runThemeCheck, scanThemeSources } from "../../scripts/check-mod-theme.mjs";

test("theme scanner rejects default blue/slate palettes without flagging semantic variables", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "newma-theme-"));
  try {
    await writeFile(
      path.join(root, "good.css"),
      ":root { --blue: var(--vibe-accent); color: var(--vibe-text); }\n",
    );
    await writeFile(
      path.join(root, "bad.tsx"),
      [
        '<button className="bg-blue-500 text-slate-100">Open</button>',
        '<div style={{ background: "rgba(59, 130, 246, 0.10)" }}>Legacy</div>',
        '<a style={{ color: "#007aff" }}>Link</a>',
        "",
      ].join("\n"),
    );
    await writeFile(
      path.join(root, "bad.html"),
      '<meta name="theme-color" content="#ffffff">\n',
    );

    const findings = await scanThemeSources([root]);
    assert.deepEqual(
      findings.map((finding) => finding.rule).sort(),
      [
        "legacy-blue-rgb",
        "legacy-blue-slate-hex",
        "tailwind-default-blue",
        "tailwind-default-blue",
        "white-browser-theme",
      ],
    );
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

test("theme scanner accepts a template-compliant Mod wrapper", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "newma-theme-pass-"));
  try {
    await writeFile(
      path.join(root, "index.html"),
      [
        "<!doctype html>",
        '<html lang="zh-CN">',
        "  <head>",
        '    <meta name="theme-color" content="#f4efe3">',
        "  </head>",
        "  <body>",
        '    <div id="root"></div>',
        "  </body>",
        "</html>",
        "",
      ].join("\n"),
    );
    await writeFile(
      path.join(root, "main.tsx"),
      [
        'import "@newma-desk/desk-ui/mod-theme.css";',
        'export function App() {',
        '  return <main className="newma-mod-surface" style={{ color: "var(--vibe-text)" }}>Desk Mod</main>;',
        "}",
        "",
      ].join("\n"),
    );

    const result = await runThemeCheck([root, "--no-import-check"]);
    assert.deepEqual(result.findings, []);
    assert.deepEqual(result.missingImports, []);
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

test("theme scanner exceptions are scoped to one reviewed rule", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "newma-theme-allow-"));
  try {
    await writeFile(
      path.join(root, "reviewed.tsx"),
      [
        '<div className="bg-blue-500" style={{ color: "#007aff" }}>Reviewed</div> // newma-theme-allow:legacy-blue-slate-hex',
        '<div style={{ color: "#007aff" }}>Reviewed link</div> // newma-theme-allow:legacy-blue-slate-hex',
        "",
      ].join("\n"),
    );

    const findings = await scanThemeSources([root]);

    assert.deepEqual(findings.map((finding) => finding.rule), ["tailwind-default-blue"]);
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});
