#!/usr/bin/env node

import { registerDefaultMods } from "./lib/mod-store.mjs";

function option(name) {
  const prefix = `--${name}=`;
  return process.argv.slice(2).find((argument) => argument.startsWith(prefix))?.slice(prefix.length);
}

const dryRun = process.argv.includes("--dry-run");
const apiUrl =
  option("api-url") ||
  process.env.NEWMA_DESK_CONTROL_PLANE_URL ||
  process.env.NEWMA_DOCK_CONTROL_PLANE_URL ||
  process.env.VIBEDESK_CONTROL_PLANE_URL ||
  "http://127.0.0.1:8911";

try {
  const result = await registerDefaultMods({ apiUrl, dryRun });
  const defaults = result.store.mods.filter((mod) => mod.defaultInstall);
  if (dryRun) {
    console.log(`已验证商店全部 ${result.store.mods.length} 个 Mod，准备注册其中 ${defaults.length} 个内置默认 Mod。`);
  } else {
    console.log(`默认 Mod 注册完成：发布 ${result.created.length} 个，保持 ${result.skipped.length} 个，下架 ${result.disabled.length} 个。`);
  }
  for (const mod of defaults) console.log(`- ${mod.manifest.name} (${mod.id})`);
} catch (error) {
  console.error(error instanceof Error ? error.message : String(error));
  process.exitCode = 1;
}
