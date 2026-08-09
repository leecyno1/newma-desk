export type MarketId = "CN" | "HK" | "US";
export type MarketFilter = MarketId | "ALL";
export type Timeframe = "1m" | "5m" | "15m" | "30m" | "60m" | "1d" | "1w" | "1M";
export type Adjustment = "none" | "qfq" | "hfq";
export type PrimaryIndicator = "MA" | "EMA" | "BOLL";
export type SecondaryIndicator = "VOL" | "MACD" | "RSI" | "KDJ";
export type MarketScanSort =
  | "changePct"
  | "amount"
  | "turnoverPct"
  | "volumeRatio"
  | "marketCap"
  | "pe"
  | "pb";
export type MarketScanOrder = "asc" | "desc";

export interface SecurityRef {
  symbol: string;
  name: string;
  market: MarketId;
  exchange?: string;
  currency?: string;
  timezone?: string;
  assetType?: string;
}

export interface SearchResult extends SecurityRef {
  source?: string;
  quoteId?: string;
  securityType?: string;
}

export interface OrderLevel {
  price: number;
  volume: number;
}

export interface Quote extends SecurityRef {
  price?: number | null;
  change?: number | null;
  changePct?: number | null;
  prevClose?: number | null;
  open?: number | null;
  high?: number | null;
  low?: number | null;
  volume?: number | null;
  amount?: number | null;
  turnoverPct?: number | null;
  marketCap?: number | null;
  floatMarketCap?: number | null;
  pe?: number | null;
  pb?: number | null;
  amplitudePct?: number | null;
  volumeRatio?: number | null;
  limitUp?: number | null;
  limitDown?: number | null;
  orderBook?: { bids: OrderLevel[]; asks: OrderLevel[] };
  source?: string;
  sources?: string[];
  asOf?: string;
  industry?: string;
}

export interface MarketScanResult {
  items: Quote[];
  market: MarketId;
  sort: MarketScanSort;
  order: MarketScanOrder;
  source: string;
  asOf: string;
  coverage: {
    requested: number;
    returned: number;
  };
}

export interface Bar {
  timestamp: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume?: number;
  turnover?: number;
}

export interface OhlcvResult {
  symbol: string;
  market: MarketId;
  timeframe: Timeframe;
  adjust: Adjustment;
  items: Bar[];
  source: string;
  asOf: string;
  hasMore: boolean;
}

export interface MarketOverview {
  sentiment?: {
    up?: number;
    down?: number;
    flat?: number;
    zt?: number;
    dt?: number;
    breadth?: string;
    speculation?: string;
  };
  sectors?: Array<{
    name: string;
    pct?: number;
    net?: number;
  }>;
  updated?: string;
}

export interface TurnoverStock {
  code?: string;
  symbol?: string;
  name?: string;
  price?: number;
  pct?: number;
  change_pct?: number;
  amount?: number;
}

export type MarketEvidenceEventType =
  | "announcement"
  | "earnings"
  | "news"
  | "research";

export interface MarketEvidenceEvent {
  id: string;
  timestamp: number;
  type: MarketEvidenceEventType;
  title: string;
  detail: string;
  source: string;
  url?: string;
  evidenceId: string;
}

export interface MarketEventSourceStatus {
  id: "announcements" | "reports" | "news";
  label: string;
  status: "ok" | "empty" | "unavailable" | "unsupported";
  count: number;
  error?: string;
}

export interface MarketEventFeed {
  items: MarketEvidenceEvent[];
  sources: MarketEventSourceStatus[];
  asOf: string;
}

export interface WatchGroup {
  id: string;
  name: string;
  symbols: SecurityRef[];
}

export interface MarketDataSource {
  search(query: string, market: MarketFilter): Promise<SearchResult[]>;
  quotes(symbols: SecurityRef[]): Promise<Quote[]>;
  quote(security: SecurityRef): Promise<Quote>;
  scan(
    market: MarketId,
    sort: MarketScanSort,
    order?: MarketScanOrder,
    limit?: number,
  ): Promise<MarketScanResult>;
  ohlcv(
    security: SecurityRef,
    timeframe: Timeframe,
    adjustment: Adjustment,
  ): Promise<OhlcvResult>;
  overview(): Promise<MarketOverview>;
  indices(): Promise<Array<Record<string, unknown>>>;
  globalIndices(): Promise<Array<Record<string, unknown>>>;
  turnoverTop(): Promise<TurnoverStock[]>;
  events(security: SecurityRef): Promise<MarketEventFeed>;
}
