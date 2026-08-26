import {
  getVibeDeskModSession,
  isVibeDeskEmbedded,
  waitForVibeDeskModSession,
} from "@/lib/vibedesk";

const STORAGE_KEY = "vibe_trading_api_auth_key";

export function getApiAuthKey(): string {
  return window.localStorage.getItem(STORAGE_KEY) || "";
}

export function setApiAuthKey(value: string): void {
  const trimmed = value.trim();
  if (trimmed) {
    window.localStorage.setItem(STORAGE_KEY, trimmed);
  } else {
    window.localStorage.removeItem(STORAGE_KEY);
  }
}

export function authHeaders(): Record<string, string> {
  if (isVibeDeskEmbedded) {
    const session = getVibeDeskModSession();
    return session
      ? {
          "X-Newma-Desk-Mod-Session": session.accessToken,
          "X-Newma-Desk-Instance-Id": session.instanceId,
        }
      : {};
  }
  const key = getApiAuthKey();
  return key ? { Authorization: `Bearer ${key}` } : {};
}

export async function requestAuthHeaders(): Promise<Record<string, string>> {
  if (isVibeDeskEmbedded && !getVibeDeskModSession()) {
    await waitForVibeDeskModSession();
  }
  return authHeaders();
}

export function authQuerySuffix(): string {
  if (isVibeDeskEmbedded) return "";
  const key = getApiAuthKey();
  return key ? `api_key=${encodeURIComponent(key)}` : "";
}

export function withAuthQuery(url: string): string {
  const suffix = authQuerySuffix();
  if (!suffix) return url;
  return `${url}${url.includes("?") ? "&" : "?"}${suffix}`;
}
