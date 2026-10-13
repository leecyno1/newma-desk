import type { ModManifest } from "@newma-desk/contracts";

const DEFAULT_MODULE_ORIGIN = "http://127.0.0.1:5891";

function isLocalOrigin(origin: string): boolean {
  const url = new URL(origin);
  return url.protocol === "file:" || url.hostname === "localhost" ||
    url.hostname.endsWith(".localhost") || url.hostname === "[::1]" ||
    /^127\./.test(url.hostname);
}

export function resolveModUrl(
  entry: ModManifest["entry"],
  configuredOrigin = (import.meta.env.VITE_MOD_ORIGIN ||
    import.meta.env.VITE_MODULE_ORIGIN) as string | undefined,
  deskOrigin = window.location.origin,
): string {
  if (entry.type !== "external" && !configuredOrigin && !isLocalOrigin(deskOrigin)) {
    throw new Error("远程 Mod 地址尚未配置，请设置 VITE_MOD_ORIGIN 后重新构建 Newma-Desk。");
  }
  const resolved =
    entry.type === "external"
      ? new URL(entry.url)
      : new URL(
          entry.url,
          `${new URL(configuredOrigin || DEFAULT_MODULE_ORIGIN).origin}/`,
        );

  if (!isLocalOrigin(deskOrigin) && isLocalOrigin(resolved.origin)) {
    throw new Error("远程 Mod 不能使用本机地址，请配置服务器的独立 HTTPS Mod 地址。");
  }

  if (resolved.origin === deskOrigin) {
    throw new Error(
      entry.type === "external"
        ? "Mod 页面必须使用与 Newma-Desk 不同的 origin。"
        : "Mod 服务必须使用与 Newma-Desk 不同的 origin，请检查 VITE_MOD_ORIGIN。",
    );
  }

  return resolved.toString();
}

export const resolveModuleUrl = resolveModUrl;
