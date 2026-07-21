#!/usr/bin/env node

import { standardizeDefaultMods } from "./lib/mod-store.mjs";

function option(name) {
  const prefix = `--${name}=`;
  return process.argv.slice(2).find((argument) => argument.startsWith(prefix))?.slice(prefix.length);
}

const apiUrl = option("api-url") || process.env.VIBEDESK_CONTROL_PLANE_URL || "http://127.0.0.1:8901";

try {
  const result = await standardizeDefaultMods({ apiUrl });
  console.log(
    `标准配置完成：新增 ${result.created.length} 个示例，保留 ${result.skipped.length} 个，移回商店 ${result.disabled.length} 个。`,
  );
  for (const modId of result.disabled) console.log(`- 已从默认导航移除 ${modId}`);
} catch (error) {
  console.error(error instanceof Error ? error.message : String(error));
  process.exitCode = 1;
}
