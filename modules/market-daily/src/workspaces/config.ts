import type { ModPageContext } from "@newma-desk/contracts";

export type MarketWorkspaceKind =
  | "scanner"
  | "sentiment"
  | "technical"
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
    title: "选股扫描",
    description: "从共享自选与成交额榜中筛选量价、趋势和估值候选。",
    accent: "var(--vibe-accent)",
    blocks: [
      { id: "scanner-filters", type: "market-filter", title: "扫描条件" },
      { id: "scanner-results", type: "security-table", title: "候选标的" },
    ],
  },
  sentiment: {
    kind: "sentiment",
    modId: "market-sentiment",
    title: "情绪分析",
    description: "用市场宽度、涨跌停、行业扩散和成交活跃度观察交易情绪。",
    accent: "var(--vibe-accent)",
    blocks: [
      { id: "sentiment-score", type: "market-sentiment", title: "情绪温度" },
      { id: "sentiment-breadth", type: "market-breadth", title: "市场宽度" },
      { id: "sentiment-sectors", type: "sector-diffusion", title: "行业扩散" },
    ],
  },
  technical: {
    kind: "technical",
    modId: "market-technical",
    title: "技术分析",
    description: "从真实 OHLCV 计算趋势、波动、量价确认、回撤和支撑阻力。",
    accent: "var(--vibe-accent)",
    blocks: [
      { id: "technical-regime", type: "trend-regime", title: "趋势状态" },
      { id: "technical-metrics", type: "technical-metrics", title: "技术指标" },
      { id: "technical-levels", type: "support-resistance", title: "支撑阻力" },
    ],
  },
  "multi-timeframe": {
    kind: "multi-timeframe",
    modId: "multi-timeframe",
    title: "多周期分析",
    description: "日线、60 分钟、15 分钟与 5 分钟图表联动。",
    accent: "var(--vibe-accent)",
    blocks: [
      { id: "multi-chart-grid", type: "klinechart-grid", title: "多周期 K 线" },
      { id: "multi-inspector", type: "market-inspector", title: "行情检查器" },
    ],
  },
  "relative-strength": {
    kind: "relative-strength",
    modId: "relative-strength",
    title: "强弱对比",
    description: "比较自选标的的归一化收益、趋势和阶段排名。",
    accent: "var(--vibe-accent)",
    blocks: [
      { id: "relative-chart", type: "relative-strength-chart", title: "归一化走势" },
      { id: "relative-ranking", type: "security-ranking", title: "阶段排名" },
    ],
  },
  "event-timeline": {
    kind: "event-timeline",
    modId: "event-timeline",
    title: "日线时间轴",
    description: "将股票、ETF 与开放式基金的日线和公开事件按交易日对齐。",
    accent: "var(--vibe-accent)",
    blocks: [
      { id: "event-chart", type: "klinechart", title: "日线事件图层" },
      { id: "event-list", type: "event-timeline", title: "日线事件" },
    ],
  },
  "trading-replay": {
    kind: "trading-replay",
    modId: "trading-replay",
    title: "复盘回放",
    description: "隐藏未来行情，逐根播放 K 线并记录模拟决策。",
    accent: "var(--vibe-accent)",
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
