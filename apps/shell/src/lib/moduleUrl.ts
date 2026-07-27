import type { ModManifest } from "@newma-dock/contracts";

const DEFAULT_MODULE_ORIGIN = "http://127.0.0.1:5891";

export function resolveModUrl(
  entry: ModManifest["entry"],
  configuredOrigin = (import.meta.env.VITE_MOD_ORIGIN ||
    import.meta.env.VITE_MODULE_ORIGIN) as string | undefined,
  deskOrigin = window.location.origin,
): string {
  const resolved =
    entry.type === "external"
      ? new URL(entry.url)
      : new URL(
          entry.url,
          `${new URL(configuredOrigin || DEFAULT_MODULE_ORIGIN).origin}/`,
        );

  if (resolved.origin === deskOrigin) {
    throw new Error(
      entry.type === "external"
        ? "Mod 页面必须使用与 Newma-Dock 不同的 origin。"
        : "Mod 服务必须使用与 Newma-Dock 不同的 origin，请检查 VITE_MOD_ORIGIN。",
    );
  }

  return resolved.toString();
}

export const resolveModuleUrl = resolveModUrl;
