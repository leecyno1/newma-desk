import { useCallback, useEffect, useMemo, useRef, useSyncExternalStore } from "react";
import type { GatewayFetch, ModHostConnection } from "@newma-desk/mod-sdk";

type EmbeddedHost = Extract<ModHostConnection, { embedded: true }>;

function scopeKey(host: EmbeddedHost) {
  const c = host.config;
  return JSON.stringify([c.modId, c.instanceId, c.user.id, c.workspace.id,
    c.gateways.storage, c.gateways.data, c.session?.accessToken, c.session?.expiresAt,
    [...c.grants.permissions].sort()]);
}

export interface StorageSession {
  config: EmbeddedHost["config"];
  isCurrent(): boolean;
}

export function useStorageSession(host?: EmbeddedHost): StorageSession | undefined {
  const latest = useRef(host);
  latest.current = host;
  const subscribe = useCallback((changed: () => void) => host?.subscribe(changed) ?? (() => {}), [host]);
  const snapshot = useCallback(() => host ? scopeKey(host) : "", [host]);
  const key = useSyncExternalStore(subscribe, snapshot);
  const session = useMemo(() => {
    if (!host) return undefined;
    const state = { active: true };
    return {
      state,
      config: host.config,
      isCurrent: () => state.active && latest.current === host && key === scopeKey(host),
    };
  }, [host, key]);
  useEffect(() => {
    if (!session) return;
    session.state.active = true;
    return () => { session.state.active = false; };
  }, [session]);
  return session;
}

export interface StorageClientOptions {
  baseUrl: string;
  userId: string;
  workspaceId: string;
  fetch?: GatewayFetch;
  session?: StorageSession;
  validateResponse?: (payload: unknown) => void;
}

export class StorageAccessError extends Error {
  constructor(readonly status: number, message: string) { super(message); }
}

export function createStorageRequest(input: StorageClientOptions) {
  const fetcher = input.fetch ?? globalThis.fetch.bind(globalThis);
  const session = input.session;
  const baseUrl = session
    ? new URL(session.config.gateways.storage ?? session.config.gateways.data).origin
    : input.baseUrl.replace(/\/$/, "");
  const assertCurrent = () => {
    if (session && !session.isCurrent()) throw new StorageAccessError(409, "账户或页面授权已切换，请重新操作");
  };
  return async <T>(method: string, path: string, body?: unknown, format: "json" | "html" = "json"): Promise<T> => {
    assertCurrent();
    const permission = method === "GET" ? "storage.read" : "storage.write";
    const headers: Record<string, string> = { Accept: "application/json", "Content-Type": "application/json" };
    if (session) {
      const c = session.config;
      if (!c.session?.accessToken || !(Date.parse(c.session.expiresAt) > Date.now())) {
        throw new StorageAccessError(401, "页面会话已失效，请重新打开页面");
      }
      if (!c.grants.permissions.includes(permission)) throw new StorageAccessError(403, "当前页面没有所需的存储权限");
      headers.Authorization = `Bearer ${c.session.accessToken}`;
      headers["X-Newma-Desk-Instance-Id"] = c.instanceId;
    } else {
      headers["X-User-Id"] = input.userId;
      headers["X-Workspace-Id"] = input.workspaceId;
    }
    try {
      const response = await fetcher(`${baseUrl}${path}`, {
        method, headers, credentials: "omit", redirect: "error", cache: "no-store",
        signal: AbortSignal.timeout(15_000),
        ...(body === undefined ? {} : { body: JSON.stringify(body) }),
      });
      const payload: unknown = format === "html" ? await response.text() : await response.json().catch(() => undefined);
      assertCurrent();
      if (!response.ok) {
        const messages: Record<number, string> = {
          401: "页面会话已失效，请重新打开页面", 403: "当前页面没有所需的存储权限",
          404: "记录或存储接口不存在，请刷新核验", 409: "数据版本已变化，请刷新后重试",
          422: "提交的存储内容不符合要求",
        };
        throw new StorageAccessError(response.status, messages[response.status] ?? "共享存储暂时不可用");
      }
      if (format === "html") {
        if (!response.headers.get("content-type")?.includes("text/html") || typeof payload !== "string") {
          throw new StorageAccessError(502, "归档视图响应无效");
        }
        return payload as T;
      }
      if (!payload || typeof payload !== "object") throw new StorageAccessError(502, "共享存储响应无效");
      if (input.validateResponse) {
        input.validateResponse(payload);
        return payload as T;
      }
      const checkOwner = (record: unknown) => {
        if (!record || typeof record !== "object") throw new StorageAccessError(502, "共享存储响应无效");
        const row = record as Record<string, unknown>;
        const expected = session?.config;
        if (row.userId !== (expected?.user.id ?? input.userId)
            || row.workspaceId !== (expected?.workspace.id ?? input.workspaceId)) {
          throw new StorageAccessError(403, "存储响应与当前账户不匹配");
        }
      };
      if (method !== "DELETE" || path.startsWith("/api/watchlists")) {
        if (path.startsWith("/api/artifacts/replays") && Array.isArray(payload)) {
          payload.forEach(checkOwner);
        } else if (path.startsWith("/api/market-alerts") && method === "GET") {
          const items = (payload as { items?: unknown }).items;
          if (!Array.isArray(items)) throw new StorageAccessError(502, "共享存储响应无效");
          items.forEach(checkOwner);
        } else checkOwner(payload);
      }
      return payload as T;
    } catch (error) {
      assertCurrent();
      if (error instanceof StorageAccessError) throw error;
      throw new StorageAccessError(503, "共享存储请求未确认，请刷新核验；未自动重试");
    }
  };
}
