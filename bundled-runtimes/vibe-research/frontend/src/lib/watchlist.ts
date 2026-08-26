import { getVibeDeskConfig, waitForVibeDeskConfig } from "@/lib/vibedesk";

const LEGACY_KEY = "vr-watchlist";
const SAMPLE_SEED_KEY = "vr-watchlist-sample-v1";
const GROUPS_KEY = "vibedesk.research.watch-groups.v1";

export type SecurityMarket = "CN" | "HK" | "US";

export interface SecurityRef {
  symbol: string;
  name: string;
  market: SecurityMarket;
  exchange?: string;
  currency?: string;
  timezone?: string;
  assetType?: string;
}

export interface WatchGroup {
  id: string;
  name: string;
  symbols: SecurityRef[];
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

// 首次打开时提供一组可直接使用的研究样本，覆盖半导体、光模块、PCB、
// 电力设备与消费。共享服务还会补充港股、美股样本。
export const SAMPLE_WATCHLIST = [
  "002371", // 北方华创
  "688981", // 中芯国际
  "300308", // 中际旭创
  "300394", // 天孚通信
  "002463", // 沪电股份
  "300476", // 胜宏科技
  "300750", // 宁德时代
  "600406", // 国电南瑞
  "600519", // 贵州茅台
  "000858", // 五粮液
] as const;

const SAMPLE_NAMES: Record<string, string> = {
  "002371": "北方华创",
  "688981": "中芯国际",
  "300308": "中际旭创",
  "300394": "天孚通信",
  "002463": "沪电股份",
  "300476": "胜宏科技",
  "300750": "宁德时代",
  "600406": "国电南瑞",
  "600519": "贵州茅台",
  "000858": "五粮液",
};

function cnSecurity(symbol: string, name = SAMPLE_NAMES[symbol] || symbol): SecurityRef {
  return {
    symbol,
    name,
    market: "CN",
    exchange: symbol.startsWith("6") ? "SH" : "SZ",
    currency: "CNY",
  };
}

export function defaultWatchGroups(): WatchGroup[] {
  return [{
    id: "sample",
    name: "示例组合",
    symbols: SAMPLE_WATCHLIST.map((symbol) => cnSecurity(symbol)),
  }];
}

function validSecurity(value: unknown): value is SecurityRef {
  if (!value || typeof value !== "object") return false;
  const row = value as Record<string, unknown>;
  return (
    typeof row.symbol === "string" &&
    typeof row.name === "string" &&
    (row.market === "CN" || row.market === "HK" || row.market === "US")
  );
}

function parsedGroups(value: unknown): WatchGroup[] {
  if (!Array.isArray(value)) return [];
  return value.flatMap((item): WatchGroup[] => {
    if (!item || typeof item !== "object") return [];
    const row = item as Record<string, unknown>;
    if (
      typeof row.id !== "string" ||
      typeof row.name !== "string" ||
      !Array.isArray(row.symbols)
    ) return [];
    return [{
      id: row.id,
      name: row.name,
      symbols: row.symbols.filter(validSecurity),
    }];
  });
}

function legacyCodes(): { codes: string[]; stored: boolean } {
  try {
    const raw = localStorage.getItem(LEGACY_KEY);
    const value = JSON.parse(raw || "[]");
    const codes = Array.isArray(value)
      ? value.filter((code): code is string =>
          typeof code === "string" && /^\d{6}$/.test(code))
      : [];
    return { codes, stored: raw !== null };
  } catch {
    return { codes: [], stored: false };
  }
}

export function loadLocalWatchGroups(): {
  groups: WatchGroup[];
  hasStoredValue: boolean;
} {
  try {
    const raw = localStorage.getItem(GROUPS_KEY);
    const groups = parsedGroups(JSON.parse(raw || "null"));
    if (groups.length) return { groups, hasStoredValue: true };
  } catch {
    // Fall through to the legacy flat A-share list.
  }
  const legacy = legacyCodes();
  if (legacy.codes.length) {
    return {
      groups: [{
        id: "sample",
        name: "自选组合",
        symbols: legacy.codes.map((symbol) => cnSecurity(symbol)),
      }],
      hasStoredValue: legacy.stored,
    };
  }
  return { groups: defaultWatchGroups(), hasStoredValue: false };
}

export function saveLocalWatchGroups(groups: WatchGroup[]) {
  try {
    localStorage.setItem(GROUPS_KEY, JSON.stringify(groups));
    const codes = Array.from(new Set(
      groups.flatMap((group) => group.symbols)
        .filter((security) => security.market === "CN" && /^\d{6}$/.test(security.symbol))
        .map((security) => security.symbol),
    ));
    localStorage.setItem(LEGACY_KEY, JSON.stringify(codes));
    localStorage.setItem(SAMPLE_SEED_KEY, "1");
  } catch {
    // Private browsing may disable persistence; the in-memory page remains usable.
  }
}

export function loadWatch(): string[] {
  const codes = loadLocalWatchGroups().groups
    .flatMap((group) => group.symbols)
    .filter((security) => security.market === "CN" && /^\d{6}$/.test(security.symbol))
    .map((security) => security.symbol);
  return Array.from(new Set(codes));
}

export function saveWatch(codes: string[]) {
  const cleanCodes = Array.from(new Set(codes.filter((code) => /^\d{6}$/.test(code))));
  const current = loadLocalWatchGroups().groups;
  const allowed = new Set(cleanCodes);
  const known = new Map(
    current.flatMap((group) => group.symbols)
      .filter((security) => security.market === "CN")
      .map((security) => [security.symbol, security]),
  );
  const next = current.map((group) => ({
    ...group,
    symbols: group.symbols.filter((security) =>
      security.market !== "CN" || allowed.has(security.symbol)),
  }));
  const present = new Set(
    next.flatMap((group) => group.symbols)
      .filter((security) => security.market === "CN")
      .map((security) => security.symbol),
  );
  const first = next[0] || { id: "sample", name: "自选组合", symbols: [] };
  first.symbols = [
    ...first.symbols,
    ...cleanCodes
      .filter((symbol) => !present.has(symbol))
      .map((symbol) => known.get(symbol) || cnSecurity(symbol)),
  ];
  if (!next.length) next.push(first);
  saveLocalWatchGroups(next);
}

// 从任意文本里抽取 6 位 A 股代码（逗号 / 空格 / 换行 / 顿号分隔都行）。
export function parseCodes(raw: string): string[] {
  const tokens = raw.split(/[^\d]+/).filter(Boolean);
  return Array.from(new Set(tokens.filter((token) => /^\d{6}$/.test(token))));
}

export function addCodes(
  existing: string[],
  raw: string,
): { next: string[]; added: number } {
  const incoming = parseCodes(raw).filter((code) => !existing.includes(code));
  return { next: [...existing, ...incoming], added: incoming.length };
}

export function createGroupId(name: string, existingIds: string[]) {
  const normalized = name
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 48);
  const base = /^[a-z]/.test(normalized) ? normalized : `group-${Date.now()}`;
  if (!existingIds.includes(base)) return base;
  let suffix = 2;
  while (existingIds.includes(`${base}-${suffix}`)) suffix += 1;
  return `${base}-${suffix}`;
}

export class WatchlistRequestError extends Error {
  constructor(readonly status: number, message: string) {
    super(message);
    this.name = "WatchlistRequestError";
  }
}

function errorMessage(body: unknown, fallback: string) {
  if (
    body &&
    typeof body === "object" &&
    "detail" in body &&
    typeof body.detail === "string"
  ) return body.detail;
  return fallback;
}

export function createWatchlistClient(input: {
  baseUrl: string;
  userId: string;
  workspaceId: string;
  fetch?: typeof globalThis.fetch;
}): WatchlistClient {
  const fetcher = input.fetch ?? globalThis.fetch.bind(globalThis);
  const baseUrl = input.baseUrl.replace(/\/$/, "");
  const identityHeaders = {
    Accept: "application/json",
    "X-User-Id": input.userId,
    "X-Workspace-Id": input.workspaceId,
  };
  const request = async (
    method: "GET" | "POST" | "PUT" | "PATCH" | "DELETE",
    path: string,
    body?: unknown,
  ) => {
    const response = await fetcher(`${baseUrl}${path}`, {
      method,
      credentials: "omit",
      headers: {
        ...identityHeaders,
        ...(body === undefined ? {} : { "Content-Type": "application/json" }),
      },
      ...(body === undefined ? {} : { body: JSON.stringify(body) }),
    });
    let payload: unknown;
    try {
      payload = await response.json();
    } catch {
      payload = undefined;
    }
    if (!response.ok) {
      throw new WatchlistRequestError(
        response.status,
        errorMessage(payload, `Watchlist API returned ${response.status}`),
      );
    }
    return payload as WatchlistSnapshot;
  };
  const groupPath = (groupId: string) =>
    `/api/watchlists/groups/${encodeURIComponent(groupId)}`;
  const securityPath = (groupId: string, security: SecurityRef) =>
    `${groupPath(groupId)}/securities/${security.market}/${encodeURIComponent(security.symbol)}`;
  return {
    load: () => request("GET", "/api/watchlists"),
    replace: (revision, groups) =>
      request("PUT", "/api/watchlists", { revision, groups }),
    createGroup: (group) => request("POST", "/api/watchlists/groups", group),
    renameGroup: (groupId, name) =>
      request("PATCH", groupPath(groupId), { name }),
    deleteGroup: (groupId) => request("DELETE", groupPath(groupId)),
    addSecurity: (groupId, security) =>
      request("PUT", securityPath(groupId, security), security),
    removeSecurity: (groupId, security) =>
      request("DELETE", securityPath(groupId, security)),
  };
}

export async function connectWorkspaceWatchlist() {
  const config = getVibeDeskConfig() || await waitForVibeDeskConfig();
  return createWatchlistClient({
    baseUrl: config?.apiOrigin || window.location.origin,
    userId: config?.userId || "local-user",
    workspaceId: config?.workspaceId || "local-workspace",
  });
}
