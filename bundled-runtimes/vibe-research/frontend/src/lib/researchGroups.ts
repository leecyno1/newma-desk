import type { PortfolioData } from "@/lib/api";
import {
  type SecurityRef,
  type WatchGroup,
  parseCodes,
} from "@/lib/watchlist";
import { getVibeDeskConfig, waitForVibeDeskConfig } from "@/lib/vibedesk";

const STORAGE_KEY = "vibedesk.research.catalyst-groups.v1";

export type CatalystResearchGroupSource =
  | "watchlist"
  | "workspace-portfolio"
  | "local-portfolio"
  | "custom"
  | "system";

export interface CatalystResearchGroup {
  id: string;
  name: string;
  source: CatalystResearchGroupSource;
  sourceLabel: string;
  symbols: SecurityRef[];
  concepts: string[];
  includeMacro: boolean;
  editable?: boolean;
}

interface WorkspacePortfolioDashboard {
  accounts?: Array<{ id: string; name: string }>;
  positions?: Array<{
    accountId: string;
    market: "CN" | "HK" | "US";
    symbol: string;
    name: string;
  }>;
}

function uniqueSecurities(items: SecurityRef[]) {
  return Array.from(new Map(
    items.map((security) => [`${security.market}:${security.symbol}`, security]),
  ).values());
}

export function parseResearchConcepts(raw: string) {
  return Array.from(new Set(
    raw.split(/[,，、\n]+/)
      .map((item) => item.trim())
      .filter(Boolean)
      .map((item) => item.slice(0, 40)),
  )).slice(0, 5);
}

export function parseResearchSecurities(raw: string): SecurityRef[] {
  return parseCodes(raw).slice(0, 30).map((symbol) => ({
    symbol,
    name: symbol,
    market: "CN",
    exchange: symbol.startsWith("6") ? "SH" : "SZ",
    currency: "CNY",
  }));
}

function validGroup(value: unknown): value is CatalystResearchGroup {
  if (!value || typeof value !== "object") return false;
  const group = value as Record<string, unknown>;
  return (
    typeof group.id === "string" &&
    typeof group.name === "string" &&
    group.source === "custom" &&
    Array.isArray(group.symbols) &&
    Array.isArray(group.concepts) &&
    typeof group.includeMacro === "boolean"
  );
}

export function loadLocalCatalystResearchGroups(): CatalystResearchGroup[] {
  try {
    const value = JSON.parse(localStorage.getItem(STORAGE_KEY) || "[]");
    if (!Array.isArray(value)) return [];
    return value.filter(validGroup).map((group) => ({
      ...group,
      source: "custom",
      sourceLabel: "用户自定义",
      editable: true,
      symbols: uniqueSecurities(group.symbols),
      concepts: group.concepts.slice(0, 5),
    }));
  } catch {
    return [];
  }
}

export function saveLocalCatalystResearchGroups(groups: CatalystResearchGroup[]) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(
    groups.filter((group) => group.source === "custom").map((group) => ({
      ...group,
      sourceLabel: "用户自定义",
      editable: true,
    })),
  ));
}

export function createCatalystResearchGroup(input: {
  name: string;
  codes: string;
  concepts: string;
  includeMacro: boolean;
}): CatalystResearchGroup | null {
  const name = input.name.trim();
  const symbols = parseResearchSecurities(input.codes);
  const concepts = parseResearchConcepts(input.concepts);
  if (!name || (!symbols.length && !concepts.length && !input.includeMacro)) return null;
  return {
    id: `custom:${Date.now()}`,
    name,
    source: "custom",
    sourceLabel: "用户自定义",
    symbols,
    concepts,
    includeMacro: input.includeMacro,
    editable: true,
  };
}

function watchlistGroups(groups: WatchGroup[]): CatalystResearchGroup[] {
  return groups.map((group) => ({
    id: `watchlist:${group.id}`,
    name: group.name,
    source: "watchlist",
    sourceLabel: "自选分组",
    symbols: group.symbols,
    concepts: [],
    includeMacro: true,
  }));
}

function localPortfolioGroups(portfolio?: PortfolioData | null): CatalystResearchGroup[] {
  if (!portfolio?.holdings.length) return [];
  return [{
    id: "local-portfolio:current",
    name: "本模块持仓",
    source: "local-portfolio",
    sourceLabel: "研究模块持仓",
    symbols: portfolio.holdings.map((holding) => ({
      symbol: holding.code,
      name: holding.name || holding.code,
      market: "CN",
      exchange: holding.code.startsWith("6") ? "SH" : "SZ",
      currency: "CNY",
    })),
    concepts: [],
    includeMacro: true,
  }];
}

export function composeCatalystResearchGroups(input: {
  watchGroups: WatchGroup[];
  customGroups: CatalystResearchGroup[];
  localPortfolio?: PortfolioData | null;
  workspacePortfolioGroups?: CatalystResearchGroup[];
}) {
  const groups = [
    ...watchlistGroups(input.watchGroups),
    ...(input.workspacePortfolioGroups || []),
    ...localPortfolioGroups(input.localPortfolio),
    ...input.customGroups,
    {
      id: "system:macro-geopolitics",
      name: "宏观与地缘",
      source: "system" as const,
      sourceLabel: "宏观日历与主题雷达",
      symbols: [],
      concepts: ["地缘政治", "制裁", "战争"],
      includeMacro: true,
    },
  ];
  return Array.from(new Map(groups.map((group) => [group.id, {
    ...group,
    symbols: uniqueSecurities(group.symbols),
  }])).values());
}

export async function loadWorkspacePortfolioResearchGroups(): Promise<CatalystResearchGroup[]> {
  const config = getVibeDeskConfig() || await waitForVibeDeskConfig();
  if (!config) return [];
  const response = await fetch(`${config.apiOrigin.replace(/\/$/, "")}/api/portfolio-center?includeQuotes=false`, {
    credentials: "omit",
    headers: {
      Accept: "application/json",
      "X-User-Id": config.userId,
      "X-Workspace-Id": config.workspaceId,
    },
  });
  if (!response.ok) return [];
  const dashboard = await response.json() as WorkspacePortfolioDashboard;
  const positions = dashboard.positions || [];
  if (!positions.length) return [];
  const accountNames = new Map((dashboard.accounts || []).map((account) => [account.id, account.name]));
  const byAccount = new Map<string, SecurityRef[]>();
  for (const position of positions) {
    const securities = byAccount.get(position.accountId) || [];
    securities.push({
      symbol: position.symbol,
      name: position.name || position.symbol,
      market: position.market,
    });
    byAccount.set(position.accountId, securities);
  }
  const groups: CatalystResearchGroup[] = Array.from(byAccount, ([accountId, symbols]) => ({
    id: `workspace-portfolio:${accountId}`,
    name: accountNames.get(accountId) || accountId,
    source: "workspace-portfolio",
    sourceLabel: "组合中心账户",
    symbols: uniqueSecurities(symbols),
    concepts: [],
    includeMacro: true,
  }));
  if (groups.length > 1) {
    groups.unshift({
      id: "workspace-portfolio:all",
      name: "组合中心 · 全部持仓",
      source: "workspace-portfolio",
      sourceLabel: "组合中心",
      symbols: uniqueSecurities(groups.flatMap((group) => group.symbols)),
      concepts: [],
      includeMacro: true,
    });
  }
  return groups;
}
