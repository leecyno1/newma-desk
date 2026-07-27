import type { ModPageContext } from "@newma-dock/contracts";

export type MarketWorkspaceKind =
  | "scanner"
  | "multi-timeframe"
  | "relative-strength"
  | "event-timeline"
  | "trading-replay";

export interface MarketWorkspaceConfig {
  kind: MarketWorkspaceKind;
  modId: string;
  title: string;
  description: string;
  accent: string;
  blocks: ModPageContext["visibleBlocks"];
}

export const MARKET_WORKSPACES: Record<MarketWorkspaceKind, MarketWorkspaceConfig> = {
  scanner: {
    kind: "scanner",
    modId: "market-scanner",
    title: "市场扫描器",
    description: "从共享自选与成交额榜中筛选量价、趋势和估值候选。",
    accent: "#2563eb",
    blocks: [
      { id: "scanner-filters", type: "market-filter", title: "扫描条件" },
      { id: "scanner-results", type: "security-table", title: "候选标的" },
    ],
  },
  "multi-timeframe": {
    kind: "multi-timeframe",
    modId: "multi-timeframe",
    title: "多周期看盘",
    description: "日线、60 分钟、15 分钟与 5 分钟图表联动。",
    accent: "#4f46e5",
    blocks: [
      { id: "multi-chart-grid", type: "klinechart-grid", title: "多周期 K 线" },
      { id: "multi-inspector", type: "market-inspector", title: "行情检查器" },
    ],
  },
  "relative-strength": {
    kind: "relative-strength",
    modId: "relative-strength",
    title: "相对强弱地图",
    description: "比较自选标的的归一化收益、趋势和阶段排名。",
    accent: "#7c3aed",
    blocks: [
      { id: "relative-chart", type: "relative-strength-chart", title: "归一化走势" },
      { id: "relative-ranking", type: "security-ranking", title: "阶段排名" },
    ],
  },
  "event-timeline": {
    kind: "event-timeline",
    modId: "event-timeline",
    title: "事件时间轴",
    description: "将价格异动、成交量变化和阶段突破叠加到行情时间线上。",
    accent: "#d97706",
    blocks: [
      { id: "event-chart", type: "klinechart", title: "事件行情" },
      { id: "event-list", type: "event-timeline", title: "市场事件" },
    ],
  },
  "trading-replay": {
    kind: "trading-replay",
    modId: "trading-replay",
    title: "交易回放室",
    description: "隐藏未来行情，逐根播放 K 线并记录模拟决策。",
    accent: "#0f766e",
    blocks: [
      { id: "replay-chart", type: "klinechart-replay", title: "历史回放" },
      { id: "replay-ledger", type: "trade-ledger", title: "模拟交易记录" },
    ],
  },
};

export function marketWorkspaceFromSearch(search: string): MarketWorkspaceConfig | undefined {
  const kind = new URLSearchParams(search).get("workspace") as MarketWorkspaceKind | null;
  return kind ? MARKET_WORKSPACES[kind] : undefined;
}
