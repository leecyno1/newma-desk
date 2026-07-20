import type { ModuleManifest } from "@vibe-visualization/contracts";

const DEFAULT_MODULE_ORIGIN = "http://127.0.0.1:5891";

export function resolveModuleUrl(
  entry: ModuleManifest["entry"],
  configuredOrigin = import.meta.env.VITE_MODULE_ORIGIN as string | undefined,
  shellOrigin = window.location.origin,
): string {
  if (entry.type === "external") return entry.url;

  const moduleOrigin = new URL(configuredOrigin || DEFAULT_MODULE_ORIGIN);
  if (moduleOrigin.origin === shellOrigin) {
    throw new Error(
      "模块服务必须使用与 Web Shell 不同的 origin，请检查 VITE_MODULE_ORIGIN。",
    );
  }

  return new URL(entry.url, `${moduleOrigin.origin}/`).toString();
}
