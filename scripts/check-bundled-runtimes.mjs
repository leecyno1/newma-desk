#!/usr/bin/env node

import { existsSync, readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const repoRoot = fileURLToPath(new URL("../", import.meta.url));
const manifestPath = path.join(repoRoot, "config", "bundled-runtime-sources.json");
const manifest = JSON.parse(readFileSync(manifestPath, "utf8"));

if (manifest.schemaVersion !== "1.0" || !Array.isArray(manifest.runtimes)) {
  throw new Error("bundled runtime source manifest is invalid");
}

let failed = false;
for (const runtime of manifest.runtimes) {
  const workspace = path.join(repoRoot, runtime.path);
  const missing = runtime.requiredFiles.filter(
    (file) => !existsSync(path.join(workspace, file)),
  );
  const nestedGit = existsSync(path.join(workspace, ".git"));
  const ok = existsSync(workspace) && missing.length === 0 && !nestedGit;
  failed ||= !ok;
  console.log(`${ok ? "OK  " : "FAIL"} ${runtime.id}`);
  if (!existsSync(workspace)) console.log(`     缺少目录：${runtime.path}`);
  for (const file of missing) console.log(`     缺少文件：${file}`);
  if (nestedGit) console.log("     快照中不应包含嵌套 .git");
}

if (failed) process.exitCode = 1;
