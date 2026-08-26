import type { CatalystEvent, CatalystStatus } from "@/lib/api";
import { waitForVibeDeskConfig, type VibeDeskConfig } from "@/lib/vibedesk";

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
  const response = await fetch(endpoint(config), { headers: headers(config) });
  if (response.status === 404) return { revision: 0, state: EMPTY_STATE };
  if (!response.ok) throw new Error(`catalyst tracker read failed: ${response.status}`);
  const document = await response.json() as StorageDocument;
  return { revision: Number(document.revision) || 0, state: normalize(document.value) };
}

export async function hydrateCatalystTracker() {
  const local = loadLocalCatalystTracker();
  const config = await waitForVibeDeskConfig();
  if (!canRead(config)) return local;
  try {
    const remote = await readRemote(config);
    const hasRemote = remote.state.trackedIds.length || remote.state.customEvents.length || Object.keys(remote.state.outcomes).length;
    return hasRemote ? remote.state : local;
  } catch {
    return local;
  }
}

export async function persistCatalystTracker(state: CatalystTrackerState) {
  const normalized = normalize(state);
  try {
    localStorage.setItem(LOCAL_KEY, JSON.stringify(normalized));
  } catch {
    // Keep the in-memory tracker usable when local persistence is disabled.
  }
  const config = await waitForVibeDeskConfig();
  if (!canWrite(config)) return;
  for (let attempt = 0; attempt < 2; attempt += 1) {
    try {
      const current = await readRemote(config);
      const response = await fetch(endpoint(config), {
        method: "PUT",
        headers: headers(config, true),
        body: JSON.stringify({ expectedRevision: current.revision, value: normalized }),
      });
      if (response.status === 409 && attempt === 0) continue;
      if (!response.ok) throw new Error(`catalyst tracker write failed: ${response.status}`);
      return;
    } catch {
      return;
    }
  }
}
