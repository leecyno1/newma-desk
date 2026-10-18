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
  securityType?: string;
}

export interface SearchResult extends SecurityRef {
  source?: string;
  quoteId?: string;
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
  fundType?: string;
  fundCompany?: string;
  fundManager?: string;
  navDate?: string;
  cumulativeNav?: number | null;
  subscribeStatus?: string;
  redeemStatus?: string;
  minimumPurchase?: number | null;
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
  cumulativeNav?: number | null;
  changePct?: number | null;
  navEvent?: string;
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
  sample?: { sampleCount: number; activeCount: number; validCount: number; inactiveCount: number; missingPctCount: number; medianPct: number | null; buckets: Array<{ label: string; count: number }>; note: string } | null;
  coverage?: { received: number; rejected: number; invalid: number; duplicates: number; conflicts: number; universeVerified: boolean } | null;
  session?: { expectedDate: string | null; current: boolean; calendarStatus: string; cached: boolean; usingSaved: boolean };
  sources?: Record<string, { status: string; reason: string; receivedAt: string | null }>;
  sentiment?: {
    up?: number | null;
    down?: number | null;
    flat?: number | null;
    zt?: number | null;
    dt?: number | null;
    breadth?: string | null;
    speculation?: string | null;
    date?: string;
    source?: string;
    scope?: string;
  };
  sectors?: Array<{
    name: string;
    pct?: number;
    net?: number;
    asOf?: string;
    metric?: string;
    source?: string;
  }>;
  updated?: string;
}

export interface LimitBoards {
  current: boolean; asOf: string | null; previousDate: string | null; status: string; reason: string;
  source: string; generatedAt: string; receivedAt: string | null; previousStatus: string; note: string;
  summary: { up: number | null; down: number | null; broken: number | null; attempts: number | null;
    sealRatePct: number | null; breakRatePct: number | null; knownMaxBoards: number | null;
    unknownBoards: number | null; reopenedUp: number | null; previousUp: number | null;
    retainedUp: number | null; retentionRatePct: number | null };
  ladder: Array<{ boards: number; count: number }>;
  tracking?: {
    ready: boolean; reason: string; note: string;
    summary: { total: number; U: number; Z: number; D: number; absent: number; mismatches: number } | null;
    tiers: Array<{ boards: number | null; total: number; U: number; Z: number; D: number; absent: number; retentionRatePct: number }>;
    rows: Array<{ code: string; name: string; industry: string; previousBoards: number | null; currentBoards: number | null;
      outcome: "U" | "Z" | "D" | "absent"; progression: "matched" | "mismatch" | "unknown" }>;
    unmatchedContinuations: Array<{ code: string; name: string; boards: number | null }>;
    quoteVerification?: {
      asOf: string; source: string; receivedAt: string; dailyStatus: string; limitsStatus: string; note: string;
      summary: { total: number; priced: number; returnCount: number; medianPct: number | null;
        belowLimit: number; atLimit: number; conflicts: number; unresolved: number };
      rows: Array<{ code: string; status: "unavailable" | "no_trade" | "conflict" | "traded" | "at_limit" | "below_limit";
        reason: string; close: number | null; pct: number | null; amountYi: number | null; upLimit: number | null; downLimit: number | null }>;
    };
  };
  items: Array<{ code: string; name: string; industry: string; kind: "U" | "D" | "Z"; boards: number | null;
    openTimes: number | null; firstTime: string | null; lastTime: string | null }>;
}

export interface SentimentHistory {
  days: number; asOf: string | null; start: string | null;
  current: boolean; calendarReady: boolean; completed: number; expected: number; remaining: number;
  commonCount: number; missingDates: string[]; failedDates: string[]; canContinue: boolean; fetchedDays: number;
  source: string; generatedAt: string; note: string; reason: string;
  summary: { latestUpRatioPct: number | null; latestChangePp: number | null; mean5Pct: number | null;
    previous5Pct: number | null; change5Pp: number | null; aboveHalfDays: number | null };
  points: Array<{ date: string; status: string; reason: string; sampleCount: number | null;
    excludedCount: number | null; upRatioPct: number | null; medianPct: number | null }>;
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
  sentiment(refresh?: boolean): Promise<MarketOverview>;
  sentimentHistory(refresh?: boolean): Promise<SentimentHistory>;
  limitBoards(refresh?: boolean): Promise<LimitBoards>;
  indices(): Promise<Array<Record<string, unknown>>>;
  globalIndices(): Promise<Array<Record<string, unknown>>>;
  turnoverTop(): Promise<TurnoverStock[]>;
  events(security: SecurityRef): Promise<MarketEventFeed>;
}
