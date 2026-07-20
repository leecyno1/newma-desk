import type { ModuleManifest } from "@vibe-visualization/contracts";

const DEFAULT_MODULE_ORIGIN = "http://127.0.0.1:5891";

export function resolveModuleUrl(
  entry: ModuleManifest["entry"],
  configuredOrigin = import.meta.env.VITE_MODULE_ORIGIN as string | undefined,
  shellOrigin = window.location.origin,
): string {
  const resolved =
    entry.type === "external"
      ? new URL(entry.url)
      : new URL(
          entry.url,
          `${new URL(configuredOrigin || DEFAULT_MODULE_ORIGIN).origin}/`,
        );

  if (resolved.origin === shellOrigin) {
    throw new Error(
      entry.type === "external"
        ? "模块页面必须使用与 Web Shell 不同的 origin。"
        : "模块服务必须使用与 Web Shell 不同的 origin，请检查 VITE_MODULE_ORIGIN。",
    );
  }

  return resolved.toString();
}
