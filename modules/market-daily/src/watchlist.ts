import { createStorageRequest, StorageAccessError, type StorageClientOptions } from "./storageAccess";

import type { SecurityRef, WatchGroup } from "./types";

const STORAGE_KEY = "vibedesk.market-terminal.watch-groups.v1";

const SAMPLE_SYMBOLS: SecurityRef[] = [
  { symbol: "600519", name: "贵州茅台", market: "CN", exchange: "SH", currency: "CNY" },
  { symbol: "688981", name: "中芯国际", market: "CN", exchange: "SH", currency: "CNY" },
  { symbol: "300308", name: "中际旭创", market: "CN", exchange: "SZ", currency: "CNY" },
  { symbol: "002463", name: "沪电股份", market: "CN", exchange: "SZ", currency: "CNY" },
  { symbol: "300750", name: "宁德时代", market: "CN", exchange: "SZ", currency: "CNY" },
  { symbol: "600406", name: "国电南瑞", market: "CN", exchange: "SH", currency: "CNY" },
  { symbol: "00700", name: "腾讯控股", market: "HK", exchange: "HKEX", currency: "HKD" },
  { symbol: "AAPL", name: "Apple", market: "US", exchange: "NASDAQ", currency: "USD" },
  { symbol: "NVDA", name: "NVIDIA", market: "US", exchange: "NASDAQ", currency: "USD" },
  { symbol: "TSLA", name: "Tesla", market: "US", exchange: "NASDAQ", currency: "USD" },
];

export function defaultWatchGroups(): WatchGroup[] {
  return [{ id: "sample", name: "示例组合", symbols: SAMPLE_SYMBOLS }];
}

function validSecurity(value: unknown): value is SecurityRef {
  if (typeof value !== "object" || value === null) return false;
  const row = value as Record<string, unknown>;
  return (
    typeof row.symbol === "string" &&
    typeof row.name === "string" &&
    (row.market === "CN" || row.market === "HK" || row.market === "US")
  );
}

export function readLocalWatchGroups(): {
  groups: WatchGroup[];
  hasStoredValue: boolean;
} {
  try {
    const stored = window.localStorage.getItem(STORAGE_KEY);
    const value = JSON.parse(stored || "null");
    if (!Array.isArray(value)) {
      return { groups: defaultWatchGroups(), hasStoredValue: false };
    }
    const groups = value.flatMap((item): WatchGroup[] => {
      if (typeof item !== "object" || item === null) return [];
      const row = item as Record<string, unknown>;
      if (typeof row.id !== "string" || typeof row.name !== "string" || !Array.isArray(row.symbols)) {
        return [];
      }
      return [{ id: row.id, name: row.name, symbols: row.symbols.filter(validSecurity) }];
    });
    return {
      groups: groups.length ? groups : defaultWatchGroups(),
      hasStoredValue: stored !== null,
    };
  } catch {
    return { groups: defaultWatchGroups(), hasStoredValue: false };
  }
}

export function loadWatchGroups(): WatchGroup[] {
  return readLocalWatchGroups().groups;
}

export function saveWatchGroups(groups: WatchGroup[]) {
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(groups));
  } catch {
    // Private browsing may disable persistence; the in-memory terminal remains usable.
  }
}

export interface WatchlistSnapshot {
  userId: string;
  workspaceId: string;
  revision: number;
  groups: WatchGroup[];
  updatedAt?: string | null;
}

export interface WatchlistClient {
  load(): Promise<WatchlistSnapshot>;
  replace(revision: number, groups: WatchGroup[]): Promise<WatchlistSnapshot>;
  createGroup(group: Pick<WatchGroup, "id" | "name">): Promise<WatchlistSnapshot>;
  renameGroup(groupId: string, name: string): Promise<WatchlistSnapshot>;
  deleteGroup(groupId: string): Promise<WatchlistSnapshot>;
  addSecurity(groupId: string, security: SecurityRef): Promise<WatchlistSnapshot>;
  removeSecurity(groupId: string, security: SecurityRef): Promise<WatchlistSnapshot>;
}

export class WatchlistRequestError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = "WatchlistRequestError";
  }
}

export function createWatchlistClient(input: StorageClientOptions): WatchlistClient {
  const send = createStorageRequest(input);
  const request = async (
    method: "GET" | "POST" | "PUT" | "PATCH" | "DELETE",
    path: string,
    body?: unknown,
  ): Promise<WatchlistSnapshot> => {
    try {
      return await send<WatchlistSnapshot>(method, path, body);
    } catch (error) {
      if (error instanceof StorageAccessError) throw new WatchlistRequestError(error.status, error.message);
      throw error;
    }
  };
  const groupPath = (groupId: string) =>
    `/api/watchlists/groups/${encodeURIComponent(groupId)}`;
  const securityPath = (groupId: string, security: SecurityRef) =>
    `${groupPath(groupId)}/securities/${security.market}/${encodeURIComponent(security.symbol)}`;
  return {
    load: () => request("GET", "/api/watchlists"),
    replace: (revision, groups) =>
      request("PUT", "/api/watchlists", { revision, groups }),
    createGroup: (group) =>
      request("POST", "/api/watchlists/groups", group),
    renameGroup: (groupId, name) =>
      request("PATCH", groupPath(groupId), { name }),
    deleteGroup: (groupId) => request("DELETE", groupPath(groupId)),
    addSecurity: (groupId, security) =>
      request("PUT", securityPath(groupId, security), security),
    removeSecurity: (groupId, security) =>
      request("DELETE", securityPath(groupId, security)),
  };
}
