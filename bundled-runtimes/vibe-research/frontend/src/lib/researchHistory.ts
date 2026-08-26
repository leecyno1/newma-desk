import type {
  EquityResearchHistoryItem,
  EquityResearchSnapshot,
} from "@/lib/api";
import { waitForVibeDeskConfig, type VibeDeskConfig } from "@/lib/vibedesk";

const NAMESPACE = "research-history";
const MAX_HISTORY_ITEMS = 20;

interface StorageDocument {
  revision: number;
  value: unknown;
}

interface StoredResearchHistory {
  schemaVersion: 1;
  symbol: string;
  items: EquityResearchHistoryItem[];
}

function documentKey(symbol: string) {
  return `equity.${symbol.toUpperCase().replace(/[^A-Z0-9.-]/g, "-")}`;
}

function canReadStorage(config: VibeDeskConfig | null): config is VibeDeskConfig & {
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

function canUseStorage(config: VibeDeskConfig | null): config is VibeDeskConfig & {
  accessToken: string;
  instanceId: string;
  storageGateway: string;
} {
  return canReadStorage(config) && Boolean(config.permissions?.includes("storage.write"));
}

function headers(config: VibeDeskConfig, json = false) {
  return {
    Authorization: `Bearer ${config.accessToken}`,
    "X-Newma-Desk-Instance-Id": config.instanceId || "",
    ...(json ? { "Content-Type": "application/json" } : {}),
  };
}

function endpoint(config: VibeDeskConfig, symbol: string) {
  return `${config.storageGateway}/${NAMESPACE}/${encodeURIComponent(documentKey(symbol))}`;
}

function currentRecord(snapshot: EquityResearchSnapshot): EquityResearchHistoryItem {
  return {
    id: `${snapshot.identity.market}:${snapshot.identity.symbol}:${snapshot.generatedAt}`,
    symbol: snapshot.identity.symbol,
    market: snapshot.identity.market,
    title: `${snapshot.identity.name} · ${snapshot.identity.symbol}`,
    status: snapshot.workflow?.task.status || "completed",
    qualityScore: snapshot.workflow?.dataQuality.score || 0,
    qualityLevel: snapshot.workflow?.dataQuality.level || "unknown",
    coverageRatio: snapshot.coverage.ratio,
    gapCount: snapshot.gaps.length,
    createdAt: snapshot.generatedAt,
  };
}

function normalizeHistory(value: unknown, symbol: string): StoredResearchHistory {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return { schemaVersion: 1, symbol, items: [] };
  }
  const raw = value as Partial<StoredResearchHistory>;
  const items = Array.isArray(raw.items)
    ? raw.items.filter((item): item is EquityResearchHistoryItem => Boolean(
        item &&
        typeof item === "object" &&
        typeof item.id === "string" &&
        typeof item.createdAt === "string",
      )).slice(0, MAX_HISTORY_ITEMS)
    : [];
  return { schemaVersion: 1, symbol, items };
}

async function readHistory(
  config: VibeDeskConfig,
  symbol: string,
): Promise<{ revision: number; history: StoredResearchHistory }> {
  const response = await fetch(endpoint(config, symbol), {
    headers: headers(config),
  });
  if (response.status === 404) {
    return {
      revision: 0,
      history: { schemaVersion: 1, symbol, items: [] },
    };
  }
  if (!response.ok) throw new Error(`research history read failed: ${response.status}`);
  const document = await response.json() as StorageDocument;
  return {
    revision: Number(document.revision) || 0,
    history: normalizeHistory(document.value, symbol),
  };
}

async function writeHistory(
  config: VibeDeskConfig,
  symbol: string,
  record: EquityResearchHistoryItem,
) {
  for (let attempt = 0; attempt < 2; attempt += 1) {
    const { revision, history } = await readHistory(config, symbol);
    const items = [
      record,
      ...history.items.filter((item) => item.id !== record.id),
    ].slice(0, MAX_HISTORY_ITEMS);
    const response = await fetch(endpoint(config, symbol), {
      method: "PUT",
      headers: headers(config, true),
      body: JSON.stringify({
        expectedRevision: revision,
        value: { schemaVersion: 1, symbol, items },
      }),
    });
    if (response.status === 409 && attempt === 0) continue;
    if (!response.ok) throw new Error(`research history write failed: ${response.status}`);
    return items;
  }
  throw new Error("research history revision conflict");
}

function withHistory(
  snapshot: EquityResearchSnapshot,
  items: EquityResearchHistoryItem[],
  state: "saved" | "current-only" | "unavailable",
): EquityResearchSnapshot {
  const lastGoodAt = items.find((item) =>
    ["good", "usable"].includes(item.qualityLevel) &&
    ["completed", "partial"].includes(item.status)
  )?.createdAt || null;
  return {
    ...snapshot,
    reportHistory: items,
    ...(snapshot.workflow
      ? {
          workflow: {
            ...snapshot.workflow,
            history: {
              ...snapshot.workflow.history,
              state,
              lastGoodAt,
            },
          },
        }
      : {}),
  };
}

export async function persistEquityResearchHistory(
  snapshot: EquityResearchSnapshot,
): Promise<EquityResearchSnapshot> {
  const record = currentRecord(snapshot);
  const config = await waitForVibeDeskConfig();
  if (!canUseStorage(config)) {
    return withHistory(snapshot, [record], "current-only");
  }
  try {
    const items = await writeHistory(config, snapshot.identity.symbol, record);
    return withHistory(snapshot, items, "saved");
  } catch {
    return withHistory(snapshot, [record], "unavailable");
  }
}

export async function loadEquityResearchHistory(symbol: string) {
  const config = await waitForVibeDeskConfig();
  if (!canReadStorage(config)) return [];
  try {
    return (await readHistory(config, symbol)).history.items;
  } catch {
    return [];
  }
}
