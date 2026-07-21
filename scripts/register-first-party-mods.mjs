#!/usr/bin/env node

import { registerFirstPartyMods } from "./lib/first-party-mods.mjs";

function option(name) {
  const prefix = `--${name}=`;
  const value = process.argv.slice(2).find((argument) => argument.startsWith(prefix));
  return value?.slice(prefix.length);
}

const dryRun = process.argv.includes("--dry-run");
const apiUrl =
  option("api-url") ||
  process.env.VIBEDESK_CONTROL_PLANE_URL ||
  "http://127.0.0.1:8901";

try {
  const result = await registerFirstPartyMods({ apiUrl, dryRun });
  const count = result.integrations.reduce(
    (total, integration) => total + integration.manifests.length,
    0,
  );
  if (dryRun) {
    console.log(`已验证 ${result.integrations.length} 个原生集成、${count} 个 Mod。`);
  } else {
    console.log(
      `第一批 Mod 注册完成：发布 ${result.created.length} 个，保持 ${result.skipped.length} 个。`,
    );
  }
  for (const integration of result.integrations) {
    console.log(
      `- ${integration.name}: ${integration.manifests.length} 个 Mod -> ${integration.baseUrl}`,
    );
  }
} catch (error) {
  console.error(error instanceof Error ? error.message : String(error));
  process.exitCode = 1;
}
