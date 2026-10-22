import type { CatalystEvent, CatalystStatus } from "@/lib/api";
import { getVibeDeskConfig, isVibeDeskEmbedded, subscribeVibeDeskConfig, type VibeDeskConfig } from "@/lib/vibedesk";

const LOCAL_KEY = "newma-desk.catalyst-tracker.v1";
const NAMESPACE = "catalyst-calendar";
const DOCUMENT_KEY = "tracker";

export interface CatalystOutcome {
  status: Extract<CatalystStatus, "confirmed" | "invalidated">;
  updatedAt: string;
}

export interface CatalystTrackerState {
  schemaVersion: 1;
  trackedIds: string[];
  customEvents: CatalystEvent[];
  outcomes: Record<string, CatalystOutcome>;
}

interface StorageDocument {
  revision: number;
  value: unknown;
}

const EMPTY_STATE: CatalystTrackerState = {
  schemaVersion: 1,
  trackedIds: [],
  customEvents: [],
  outcomes: {},
};

function normalize(value: unknown): CatalystTrackerState {
  if (!value || typeof value !== "object" || Array.isArray(value)) return EMPTY_STATE;
  const raw = value as Partial<CatalystTrackerState>;
  const trackedIds = Array.isArray(raw.trackedIds)
    ? raw.trackedIds.filter((item): item is string => typeof item === "string").slice(0, 500)
    : [];
  const customEvents = Array.isArray(raw.customEvents)
    ? raw.customEvents.filter((item): item is CatalystEvent => Boolean(
        item && typeof item === "object" && typeof item.id === "string" && item.type === "custom",
      )).slice(0, 200)
    : [];
  const outcomes = raw.outcomes && typeof raw.outcomes === "object" && !Array.isArray(raw.outcomes)
    ? Object.fromEntries(Object.entries(raw.outcomes).flatMap(([id, outcome]) => {
        if (!outcome || typeof outcome !== "object") return [];
        const row = outcome as Partial<CatalystOutcome>;
        if ((row.status !== "confirmed" && row.status !== "invalidated") || typeof row.updatedAt !== "string") return [];
        return [[id, { status: row.status, updatedAt: row.updatedAt } satisfies CatalystOutcome]];
      }))
    : {};
  return { schemaVersion: 1, trackedIds, customEvents, outcomes };
}

export function loadLocalCatalystTracker() {
  if (getVibeDeskConfig() || isVibeDeskEmbedded || import.meta.env.VITE_NEWMA_DESK_INTEGRATED === "1") return EMPTY_STATE;
  try {
    return normalize(JSON.parse(localStorage.getItem(LOCAL_KEY) || "null"));
  } catch {
    return EMPTY_STATE;
  }
}

function canRead(config: VibeDeskConfig | null): config is VibeDeskConfig & {
  accessToken: string;
  instanceId: string;
  storageGateway: string;
} {
  return Boolean(
    config?.accessToken &&
    config.instanceId &&
    config.storageGateway &&
    config.permissions?.includes("storage.read"),
  );
}

function canWrite(config: VibeDeskConfig | null): config is VibeDeskConfig & {
  accessToken: string;
  instanceId: string;
  storageGateway: string;
} {
  return canRead(config) && Boolean(config.permissions?.includes("storage.write"));
}

function endpoint(config: VibeDeskConfig) {
  return `${config.storageGateway}/${NAMESPACE}/${DOCUMENT_KEY}`;
}

function headers(config: VibeDeskConfig, json = false) {
  return {
    Authorization: `Bearer ${config.accessToken}`,
    "X-Newma-Desk-Instance-Id": config.instanceId || "",
    ...(json ? { "Content-Type": "application/json" } : {}),
  };
}

async function readRemote(config: VibeDeskConfig) {
  const response = await fetch(endpoint(config), { headers: headers(config), credentials: "omit", redirect: "error", cache: "no-store", signal: AbortSignal.timeout(15000) });
  if (response.status === 404) return { revision: 0, state: EMPTY_STATE };
  if (!response.ok) throw new Error("催化剂跟踪读取失败，请核验当前工作区授权");
  const document = await response.json() as StorageDocument;
  if (!Number.isInteger(document.revision) || document.revision < 1) throw new Error("催化剂跟踪响应无效");
  return { revision: Number(document.revision) || 0, state: normalize(document.value) };
}

function scope(config: VibeDeskConfig | null) {
  return JSON.stringify(config && [config.apiOrigin, config.storageGateway, config.moduleId, config.userId, config.workspaceId, config.instanceId, config.accessToken, config.permissions]);
}
let loaded: { scope: string; revision: number } | undefined;

async function inScope<T>(config: VibeDeskConfig, operation: (assertCurrent: () => void) => Promise<T>): Promise<T> {
  const initial = scope(config);
  let active = true;
  const unsubscribe = subscribeVibeDeskConfig(next => { if (scope(next) !== initial) active = false; });
  const assertCurrent = () => { if (!active || scope(getVibeDeskConfig()) !== initial) throw new Error("工作区已切换，未应用旧跟踪结果"); };
  try {
    assertCurrent();
    const value = await operation(assertCurrent);
    assertCurrent();
    return value;
  } finally { unsubscribe(); }
}

export async function hydrateCatalystTracker() {
  const config = getVibeDeskConfig();
  if (!config && !isVibeDeskEmbedded && import.meta.env.VITE_NEWMA_DESK_INTEGRATED !== "1") return loadLocalCatalystTracker();
  if (!canRead(config) || config.moduleId !== "catalyst-calendar") throw new Error("催化剂跟踪读取未获授权");
  return inScope(config, async assertCurrent => {
    const remote = await readRemote(config);
    assertCurrent();
    loaded = { scope: scope(config), revision: remote.revision };
    return remote.state;
  });
}

export async function persistCatalystTracker(state: CatalystTrackerState) {
  const normalized = normalize(state);
  const config = getVibeDeskConfig();
  if (!config && !isVibeDeskEmbedded && import.meta.env.VITE_NEWMA_DESK_INTEGRATED !== "1") {
    localStorage.setItem(LOCAL_KEY, JSON.stringify(normalized));
    return;
  }
  if (!canWrite(config) || config.moduleId !== "catalyst-calendar") throw new Error("催化剂跟踪保存未获授权");
  if (!loaded || loaded.scope !== scope(config)) throw new Error("请先读取当前工作区跟踪记录，再保存");
  const revision = loaded.revision;
  return inScope(config, async assertCurrent => {
    const response = await fetch(endpoint(config), {
      method: "PUT", headers: headers(config, true), credentials: "omit", redirect: "error", cache: "no-store", signal: AbortSignal.timeout(15000),
      body: JSON.stringify({ expectedRevision: revision, value: normalized }),
    });
    assertCurrent();
    if (response.status === 409) throw new Error("跟踪记录已更新，请重新打开页面读取；本次未覆盖");
    if (!response.ok) throw new Error("跟踪保存未确认，请核验权限；未自动重试");
    const document = await response.json() as StorageDocument;
    assertCurrent();
    if (document.revision !== revision + 1) throw new Error("跟踪保存响应无效，请重新核验");
    loaded = { scope: scope(config), revision: document.revision };
  });
}
