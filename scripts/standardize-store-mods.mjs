#!/usr/bin/env node

import { standardizeStoreMods } from "./lib/mod-store.mjs";

function option(name) {
  const prefix = `--${name}=`;
  return process.argv.slice(2).find((argument) => argument.startsWith(prefix))?.slice(prefix.length);
}

const apiUrl = option("api-url") || process.env.NEWMA_DOCK_CONTROL_PLANE_URL || "http://127.0.0.1:8911";

try {
  const result = await standardizeStoreMods({ apiUrl });
  console.log(
    `标准配置完成：新增 ${result.created.length} 个商店 Mod，保留 ${result.skipped.length} 个，下架 ${result.disabled.length} 个已退休官方 Mod，第三方 Mod 保持不变。`,
  );
} catch (error) {
  console.error(error instanceof Error ? error.message : String(error));
  process.exitCode = 1;
}
