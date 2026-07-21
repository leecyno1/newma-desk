#!/usr/bin/env node

import { registerDefaultMods } from "./lib/mod-store.mjs";

function option(name) {
  const prefix = `--${name}=`;
  return process.argv.slice(2).find((argument) => argument.startsWith(prefix))?.slice(prefix.length);
}

const dryRun = process.argv.includes("--dry-run");
const apiUrl = option("api-url") || process.env.VIBEDESK_CONTROL_PLANE_URL || "http://127.0.0.1:8901";

try {
  const result = await registerDefaultMods({ apiUrl, dryRun });
  const defaults = result.store.mods.filter((mod) => mod.defaultInstall);
  if (dryRun) {
    console.log(`已验证商店 ${result.store.mods.length} 个 Mod，其中 ${defaults.length} 个为默认示例。`);
  } else {
    console.log(`默认示例注册完成：发布 ${result.created.length} 个，保持 ${result.skipped.length} 个。`);
  }
  for (const mod of defaults) console.log(`- ${mod.manifest.name} (${mod.id})`);
} catch (error) {
  console.error(error instanceof Error ? error.message : String(error));
  process.exitCode = 1;
}
