// Vibe-Research 后端 API 客户端。/api → vite 代理到本地 FastAPI（默认 8900）。
// 后端未启动或数据源异常时抛 ApiError，页面据此优雅降级。

export class ApiError extends Error {
  constructor(message: string, readonly status: number) {
    super(message);
  }
}

// 后端访问密钥（对应后端部署时的 VR_API_KEY，公网部署防蹭用）。只存本地浏览器。
const ACCESS_KEY = "vr-access-key";
const API_BASE = (
  (import.meta.env.VITE_API_BASE as string | undefined)?.replace(/\/$/, "") ||
  "/api"
);

export function researchApiUrl(path: string): string {
  return `${API_BASE}${path.startsWith("/") ? path : `/${path}`}`;
}

export function loadAccessKey(): string {
  try {
    return localStorage.getItem(ACCESS_KEY) || "";
  } catch {
    return "";
  }
}

export function saveAccessKey(key: string) {
  try {
    if (key) localStorage.setItem(ACCESS_KEY, key);
    else localStorage.removeItem(ACCESS_KEY);
  } catch {
    /* 隐私模式等场景 localStorage 不可用 */
  }
}

export function authHeaders(): Record<string, string> {
  const k = loadAccessKey();
  return k ? { Authorization: `Bearer ${k}` } : {};
}

export interface MyReport {
  id: string; name: string; industry: string; size: number; ext: string; ts: number;
}

// 下载/预览研报：带鉴权头 fetch → blob → 触发浏览器下载（<a download> 无法带 Authorization，故走 blob）。
export async function downloadReport(id: string, name: string): Promise<void> {
  const resp = await fetch(researchApiUrl(`/myreports/file/${id}`), { headers: authHeaders() });
  if (!resp.ok) throw new ApiError(`下载失败 HTTP ${resp.status}`, resp.status);
  const blob = await resp.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

async function request<T>(path: string, method: "GET" | "POST" | "DELETE" = "GET", body?: unknown): Promise<T> {
  let resp: Response;
  const headers: Record<string, string> = { ...authHeaders() };
  const opts: RequestInit = { method };
  if (body !== undefined) {
    headers["Content-Type"] = "application/json";
    opts.body = JSON.stringify(body);
  }
  if (Object.keys(headers).length > 0) opts.headers = headers;
  try {
    resp = await fetch(researchApiUrl(path), opts);
  } catch {
    throw new ApiError("连接不到 VibeDesk Research 领域 API", 0);
  }
  let payload: any = null;
  try {
    payload = await resp.json();
  } catch {
    /* 非 JSON 响应 */
  }
  if (!resp.ok) {
    if (resp.status === 401) {
      throw new ApiError("后端开启了访问鉴权（VR_API_KEY）：请在「接入 AI」页底部填写后端访问密钥", 401);
    }
    throw new ApiError(payload?.detail || `HTTP ${resp.status}`, resp.status);
  }
  return (payload?.data ?? payload) as T;
}

const get = <T>(path: string) => request<T>(path, "GET");

export interface Quote {
  name: string; price: number; last_close: number; change_pct: number;
  pe_ttm: number; pb: number; mcap_yi: number; turnover_pct: number;
  limit_up: number; limit_down: number;
}

export interface Valuation {
  name: string; code: string; price: number; mcap_yi: number;
  pe_ttm: number; pb: number;
  eps_26e: number | null; eps_27e: number | null; pe_26e: number | null;
  cagr_pct: number | null; peg: number | null; digest_years: number | null;
  analyst_count: number; forecast_note?: string;
}

export interface Report {
  title: string; publishDate: string; orgSName: string;
  emRatingName?: string; indvInduName?: string; pdfUrl?: string | null;
}

export interface ValMetric {
  current: number; percentile: number; min: number; max: number;
  p20: number; p50: number; p80: number; n: number;
}
export interface ValPercentile {
  period: string; metrics: { pe_ttm?: ValMetric; pb?: ValMetric };
}

export interface Announcement {
  date: string; title: string; type: string; url: string;
}

export type CatalystType =
  | "earnings"
  | "corporate"
  | "industry"
  | "macro"
  | "regulatory"
  | "lockup"
  | "announcement"
  | "news"
  | "research"
  | "custom";

export type CatalystStatus =
  | "upcoming"
  | "monitoring"
  | "confirmed"
  | "invalidated"
  | "expired";

export interface CatalystEvent {
  id: string;
  type: CatalystType;
  date?: string;
  windowStart?: string;
  windowEnd?: string;
  timePrecision: "date" | "window";
  dateBasis?: "official" | "announcement-derived" | "model-window" | "aggregated-calendar" | "signal-window" | "user";
  urgency?: "high" | "medium" | "low";
  dateConfidence?: "high" | "medium" | "low";
  dateChange?: {
    originalDate: string;
    currentDate: string;
    changeCount: number;
    direction: "unchanged" | "advanced" | "delayed" | "actual";
  };
  status: CatalystStatus;
  title: string;
  summary: string;
  source: { id: string; label: string; url?: string };
  evidenceIds: string[];
  asOf: string;
  freshness: { status: "live" | "fresh" | "stale" | "unknown"; ageDays?: number };
  confidence: { level: "high" | "medium" | "low"; score?: number; rationale: string };
  impactedAssets: Array<{ market: "CN" | "HK" | "US"; symbol: string; name?: string }>;
  expectedDirection: "positive" | "negative" | "mixed" | "unknown";
  nextAction?: string;
  confirmationConditions: string[];
  invalidationConditions: string[];
  importance: "high" | "medium" | "low";
  cycleContext?: Record<string, unknown>;
}

export interface CatalystFeed {
  schemaVersion: "newma-desk.catalyst-calendar.v1";
  generatedAt: string;
  horizon: { start: string; end: string; days: number };
  coverage: { markets: string[]; symbols: string[]; concepts?: string[]; includeMacro?: boolean };
  items: CatalystEvent[];
  sources: Array<{
    id: string;
    label: string;
    status: "ok" | "partial" | "empty" | "unavailable" | "unsupported";
    count: number;
    asOf: string;
    error?: string;
  }>;
  gaps: Array<{ capability: string; reason: string }>;
  disclaimer: string;
}

export interface MacroIndicator {
  id: string;
  name: string;
  region: string;
  category: "growth" | "inflation" | "liquidity" | "labour" | "trade" | "rates";
  unit: string;
  period: string;
  releaseDate: string | null;
  dateBasis?: "release" | "source-update" | "period";
  nextReleaseDate?: string;
  value: number;
  forecast: number | null;
  previous: number | null;
  change: number | null;
  direction: "higher" | "lower" | "flat";
  source: { id: string; label: string; url: string };
  evidenceId: string;
  asOf: string;
  freshness: { status: "fresh" | "stale" | "unknown"; ageDays?: number };
  confidence: { level: "high" | "medium" | "low"; score: number; rationale: string };
  history: Array<{ period: string; value: number }>;
}

export interface MacroCalendarEvent {
  id: string;
  date: string;
  time: string | null;
  region: string;
  currency: string | null;
  title: string;
  importance: "high" | "medium" | "low";
  status: "scheduled" | "released";
  actual: number | null;
  forecast: number | null;
  previous: number | null;
  source: { id: string; label: string; url: string };
  evidenceId: string;
  asOf: string;
}

export interface MacroMonitorFeed {
  schemaVersion: "newma-desk.macro-monitor.v1";
  generatedAt: string;
  horizon: { start: string; end: string; days: number };
  regime: {
    overall: { label: string; summary: string; signals: string[]; evidenceIds: string[] };
    growth: MacroRegimeDimension;
    inflation: MacroRegimeDimension;
    liquidity: MacroRegimeDimension;
    confidence: { level: "high" | "medium" | "low"; score: number; rationale: string };
    transmission: Array<{ id: string; title: string; signal: MacroRegimeDimension["signal"]; summary: string; assets: string[]; evidenceIds: string[] }>;
    scenarios: Array<{ id: string; label: string; probability: string; summary: string; triggers: string[]; evidenceIds: string[] }>;
  };
  liquidity?: MacroLiquidityMonitor;
  indicators: MacroIndicator[];
  events: MacroCalendarEvent[];
  sources: Array<{
    id: string;
    label: string;
    status: "ok" | "partial" | "empty" | "unavailable" | "unsupported";
    count: number;
    asOf: string;
    coverage?: Record<string, unknown>;
    error?: string;
  }>;
  gaps: Array<{ capability: string; reason: string }>;
  disclaimer: string;
}

export interface MacroLiquidityIndicator {
  id: string;
  name: string;
  unit: string;
  value: number;
  previous: number | null;
  change: number | null;
  direction: "higher" | "lower" | "flat";
  effect: "supportive" | "supportive_inverse" | "restrictive" | "restrictive_inverse" | string;
  period: string;
  asOf: string;
  source: { id: string; label: string; url: string };
  freshness: { status: "fresh" | "stale" | "unknown"; ageDays?: number };
  history: Array<{ period: string; value: number }>;
}

export interface MacroLiquidityMonitor {
  groups: Array<{
    id: "quantity" | "price" | "transmission" | string;
    label: string;
    indicators: MacroLiquidityIndicator[];
  }>;
  indicators: MacroLiquidityIndicator[];
  forecast: {
    horizonDays: number;
    signal: "supportive" | "restrictive" | "mixed";
    direction: "higher" | "lower" | "mixed";
    confidence: number;
    method: string;
    items: Array<{
      id: string;
      name: string;
      direction: "higher" | "lower" | "flat";
      latest: number;
      forecast: number;
      slope: number;
    }>;
  };
  coverage: { available: number; total: number; asOf: string | null };
  source: string;
  note: string;
}

export interface MacroRegimeDimension {
  label: string;
  signal: "positive" | "neutral" | "negative" | "mixed" | "unknown";
  summary: string;
  evidenceIds: string[];
}

export interface Financials {
  period: string | null;
  revenue: string | null; revenue_yoy: string | null;
  net_profit: string | null; net_profit_yoy: string | null;
  eps: string | null; bvps: string | null; roe: string | null;
  gross_margin: string | null; net_margin: string | null; op_cf_ps: string | null;
}

export interface NewsItem {
  新闻标题?: string; 新闻内容?: string; 发布时间?: string; 文章来源?: string; 新闻链接?: string;
}

export interface IndexQuote {
  name: string; price: number; change_pct: number; change_amt: number;
}

export interface MarketSentiment {
  up: number; down: number; flat: number; zt: number; zt_real: number; dt: number; dt_real: number;
  active: string; breadth: string; speculation: string; date: string;
}
export interface SectorFlow {
  name: string; pct: number; net: number; inflow: number; outflow: number; firms: number;
}
export interface MarketOverview {
  sentiment: MarketSentiment; sectors: SectorFlow[]; updated: string;
}

// 短线情绪：连板梯队 / 最高连板 / 炸板率 / 封板率 / 晋级率 / 涨跌停家数 + 连板股清单（客观公开榜单）
export interface EmotionTier { boards: number; count: number; plus: boolean }
export interface LianbanStock {
  code: string; name: string; boards: number;
  price: number; pct: number; amount: number | null; float_cap: number | null; industry: string;
}
export interface ShortTermEmotion {
  date: string;
  zt_count: number; dt_count: number; zb_count: number;
  max_boards: number; lianban_count: number;
  ladder: EmotionTier[];
  lianban_stocks: LianbanStock[];
  seal_rate: number | null; break_rate: number | null; promotion_rate: number | null;
  yzt_count: number;
}

// 全市场成交额榜（客观公开榜单）
export interface TurnoverStock {
  code: string; name: string;
  price: number | null; pct: number | null;
  amount: number | null; mcap: number | null; float_cap: number | null; industry: string;
}
export interface TurnoverTop { stocks: TurnoverStock[]; updated: string }

export interface RadarItem {
  id?: string; title: string; url: string; time: string; ts?: number; source: string; summary?: string; zh?: string;
  industry_key?: string; industry_name?: string; language?: string;
  sentiment?: NewsSentiment; sentiment_score?: number;
  source_group?: string; source_group_label?: string;
  verification_status?: string; verification_label?: string; verification_flags?: string[];
  signal?: NewsSignal; published_at?: string | null;
}
export interface Industry {
  key: string; name: string; accent: string; total: number; items: RadarItem[];
}
export type NewsSentiment = "positive" | "negative" | "neutral" | "mixed";
export type NewsSignal = "risk" | "opportunity" | "mixed" | "watch";
export type NewsVelocityState = "rising" | "falling" | "flat" | "new";
export interface NewsSentimentCounts {
  positive: number; negative: number; neutral: number; mixed: number;
  positive_pct?: number; negative_pct?: number; neutral_pct?: number; mixed_pct?: number;
  net_score?: number;
}
export interface NewsSourceFrame {
  group: string; label: string; count: number;
  positive: number; negative: number; neutral: number; mixed: number;
  dominant_sentiment: NewsSentiment; dominant_label: string; sources: string[];
}
export interface NewsMonitorTopic {
  id: string; label: string; headline: string; summary?: string;
  industry_key: string; industry_name: string;
  mention_count: number; current_mentions: number; previous_mentions: number;
  heat_velocity_pct: number | null; velocity_state: NewsVelocityState;
  heat_score: number; attention_score: number; attention_level: string;
  spread_score: number; spread_level: string;
  source_count: number; sources: string[];
  language_count: number; languages: string[]; cross_language: boolean;
  sentiment: NewsSentiment; sentiment_score: number;
  sentiment_counts: NewsSentimentCounts;
  source_frames: NewsSourceFrame[];
  framing_divergence: boolean; framing_divergence_score: number;
  verification_status: string; verification_label?: string; verification_flags: string[];
  signal: NewsSignal; signal_reasons: string[];
  latest_at: string | null; keywords: string[]; items: RadarItem[];
}
export interface NewsMonitor {
  summary: {
    analyzed_items: number; topic_count: number; source_count: number; language_count?: number;
    current_mentions?: number; previous_mentions?: number;
    heat_velocity_pct: number | null; velocity_state: NewsVelocityState; window_hours?: number;
    attention_topic_count: number; risk_topic_count: number; opportunity_topic_count: number;
    rising_topic_count?: number; flagged_topic_count: number; divergent_topic_count: number;
    cross_language_topic_count?: number; spread_score: number;
    sentiment: NewsSentimentCounts & { net_score: number };
  };
  topics: NewsMonitorTopic[];
  keywords: Array<{ keyword: string; count: number }>;
  source_frames: NewsSourceFrame[];
  method: string; caveat: string; timestamp: string;
}
export interface NewsSourceHealth {
  name: string; url: string; industry_key: string;
  status: "healthy" | "stale" | "failed" | string;
  item_count: number; fresh_item_count: number;
  error?: string | null; elapsed_ms?: number;
  checked_at?: string | null; last_success_at?: string | null;
}
export interface NewsTopicPage {
  items: NewsMonitorTopic[];
  total: number; offset: number; limit: number;
  industry_counts: Record<string, number>;
  generated_at_iso?: string | null;
}
export interface RadarData {
  generated_at: string | null; generated_at_iso?: string | null; recent_days: number; industries: Industry[];
  stats: {
    industries: number; total_sources: number;
    healthy_sources?: number; failed_sources?: number;
    stale_sources?: number; unavailable_sources?: number;
    source_health?: NewsSourceHealth[];
  };
  monitor?: NewsMonitor;
  monitor_schema_version?: number;
  refresh?: { refreshing: boolean; stale: boolean; interval_minutes: number };
}

export interface Holding {
  code: string; name: string; price: number; shares: number; cost: number;
  market_value: number; pnl: number; pnl_pct: number;
}
export interface ClosedPosition {
  code: string; name: string; date: string; price: number; shares: number; cost: number;
  pnl: number; pnl_pct: number;
}
export interface PortfolioData {
  holdings: Holding[];
  totals: { market_value: number; cost: number; pnl: number; pnl_pct: number };
  closed: ClosedPosition[];
  realized_pnl: number;
  updated: string; last_refresh: string | null;
}

// 资金面 / 筹码 / 信号（v3.3 并入，均为「用户查的那只股」的公开数据）
export interface MarginRow { date: string; rzye: number; rzmre: number; rzche: number; rqye: number; rqmcl: number; rzrqye: number }
export interface BlockTradeRow { date: string; price: number; close: number; premium_pct: number; vol: number; amount: number; buyer: string; seller: string }
export interface HolderRow { date: string; holder_num: number; change_ratio: number; avg_shares: number }
export interface DividendRow { date: string; bonus_rmb: number; transfer_ratio: number; bonus_ratio: number | null; plan: string }
export interface FundFlowRow { date: string; main_net: number; small_net: number; mid_net: number; large_net: number; super_net: number }
export interface DtSeat { name: string; buy_amt: number; sell_amt: number; net: number }
export interface DragonTiger {
  records: { date: string; reason: string; net_buy: number; turnover: number }[];
  seats: { buy: DtSeat[]; sell: DtSeat[] };
  institution: { buy_amt: number; sell_amt: number; net_amt: number };
}
export interface LockupRow { date: string; type: string; shares: number; able_shares: number; ratio: number }
export interface Lockup { history: LockupRow[]; upcoming: LockupRow[] }
export interface Board { name: string; code: string; change_pct: number | string; lead_stock: string }
export interface Blocks { total: number; boards: Board[]; concept_tags: string[] }
export interface HotConcept { concept: string; bk: string; hit: number }
export interface QaRow { company: string; question: string; answer: string | null; answerer: string; ask_time: string }
export interface IndustryRow { rank: number; name: string; change_pct: number; code: string; up_count: number; down_count: number }
export interface IndustryData { top: IndustryRow[]; bottom: IndustryRow[]; total: number }

// 全球市场（美股 / 港股，按 global-stock-data Skill 路由）
export interface GlobalIndex {
  key: string; name: string; region: string;
  price: number | null; change_pct: number | null;
}
export interface GlobalQuote {
  code: string; name: string;
  price: number | null; open: number | null; high: number | null; low: number | null;
  prev_close: number | null; volume?: number | null; amount: number | null;
  turnover_rate?: number | null; mcap: number | null; change_pct: number | null;
  pe?: number | null; pb?: number | null; source?: string | null; sources?: string[];
}
export interface GlobalMetrics {
  report_date: string;
  revenue: number | null; revenue_yoy: number | null; net_profit: number | null;
  eps: number | null; roe: number | null; gross_margin: number | null;
  net_margin: number | null; debt_ratio: number | null;
}
export interface GlobalStock {
  code: string; name: string; market: string;
  quote: GlobalQuote; metrics: GlobalMetrics | null;
  data_sources?: string[];
}

export interface EquityResearchEvidence {
  id: string;
  dimension: string;
  label: string;
  value: string | number | boolean;
  source: string;
  sourceType: "structured" | "filing" | "derived" | string;
  field: string;
  asOf?: string | null;
  unit?: string | null;
  currency?: string | null;
  confidence: "high" | "medium" | "low" | string;
  url?: string | null;
  note?: string | null;
  dependsOn?: string[];
  method?: string | null;
}

export interface EquityResearchMetric {
  id: string;
  dimension: string;
  label: string;
  value: number;
  unit: string;
  dependsOn: string[];
  method: string;
  interpretation: string;
  asOf?: string | null;
  confidence: "high" | "medium" | "low" | string;
}

export interface EquityResearchAxisScore {
  id: "quality" | "growth" | "valuation" | "resilience" | string;
  title: string;
  score: number | null;
  status: "strong" | "balanced" | "watch" | "weak" | "unavailable" | string;
  summary: string;
  evidenceIds: string[];
  signalCount: number;
  method: string;
}

export type EquityResearchBlockStatus =
  | "available"
  | "missing"
  | "not_supported"
  | "fallback"
  | "stale"
  | "estimated"
  | "partial"
  | "fetch_failed"
  | string;

export interface EquityResearchHistoryItem {
  id: string;
  symbol: string;
  market: string;
  title: string;
  status: string;
  qualityScore: number;
  qualityLevel: string;
  coverageRatio: number;
  gapCount: number;
  createdAt: string;
}

export interface EquityResearchWorkflow {
  schemaVersion: string;
  task: {
    id: string;
    status: string;
    stage: string;
    progress: number;
    updatedAt: string;
  };
  stages: Array<{
    id: string;
    title: string;
    status: string;
    progress: number;
    durationMs: number;
  }>;
  blocks: Array<{
    id: string;
    title: string;
    status: EquityResearchBlockStatus;
    qualityScore: number;
    evidenceCount: number;
    sources: string[];
    asOf?: string | null;
    warnings: string[];
    gaps: string[];
  }>;
  dataQuality: {
    score: number;
    level: "good" | "usable" | "limited" | "poor" | string;
    blockScores: Record<string, number>;
    limitations: string[];
    warnings: string[];
  };
  sourceStatus: Array<{
    id: string;
    title: string;
    status: EquityResearchBlockStatus;
    source: string;
    blocks: string[];
    asOf?: string | null;
    message?: string | null;
  }>;
  diagnostics: {
    missingBlocks: string[];
    failedSources: string[];
    fallbackSources: string[];
    gapCount: number;
  };
  history: {
    mode: "desk-managed" | string;
    namespace: string;
    state: "pending" | "saved" | "current-only" | "unavailable" | string;
    lastGoodAt?: string | null;
  };
}

export interface EquityResearchSnapshot {
  schemaVersion: string;
  frameworkVersion: string;
  methodology: string[];
  identity: {
    symbol: string;
    name: string;
    market: string;
    currency: string;
  };
  coverage: {
    coveredDimensions: number;
    totalDimensions: number;
    ratio: number;
  };
  sections: {
    id: string;
    title: string;
    status: "covered" | "gap";
    evidenceIds: string[];
  }[];
  analytics?: {
    version: string;
    metrics: EquityResearchMetric[];
    limitations: string[];
  };
  scorecard?: EquityResearchAxisScore[];
  comparisonProfile?: EquityResearchComparisonProfile;
  derivedEvidence?: string[];
  workflow?: EquityResearchWorkflow;
  reportHistory?: EquityResearchHistoryItem[];
  evidenceLedger: EquityResearchEvidence[];
  sources: string[];
  gaps: string[];
  generatedAt: string;
}

export interface EquityResearchComparisonProfile {
  metrics: {
    pe: number | null;
    pb: number | null;
    valuationPercentile: number | null;
    revenueGrowthPct: number | null;
    netProfitGrowthPct: number | null;
    roePct: number | null;
    grossMarginPct: number | null;
    netMarginPct: number | null;
    cashConversionPct: number | null;
    debtRatioPct: number | null;
  };
  scores: Record<string, number | null>;
}

export interface EquityResearchComparison {
  schemaVersion: string;
  rows: Array<{
    identity: EquityResearchSnapshot["identity"];
    coverage: EquityResearchSnapshot["coverage"];
    metrics: EquityResearchComparisonProfile["metrics"];
    scores: EquityResearchComparisonProfile["scores"];
  }>;
  errors: Array<{ symbol: string; message: string }>;
  generatedAt: string;
}

export interface TerminalQuote {
  symbol: string;
  name: string;
  market: "CN" | "HK" | "US";
  exchange?: string;
  assetType?: "stock" | "etf" | "fund" | "index";
  securityType?: string;
  fundType?: string;
  fundCompany?: string;
  fundManager?: string;
  navDate?: string;
  cumulativeNav?: number | null;
  currency?: string;
  price: number | null;
  change: number | null;
  changePct: number | null;
  turnoverPct?: number | null;
  pe?: number | null;
  pb?: number | null;
  source?: string;
  asOf?: string;
}

export interface TerminalBar {
  timestamp: number;
  open: number;
  close: number;
  high: number;
  low: number;
  volume: number;
  turnover: number;
}

export interface TerminalOhlcv {
  symbol: string;
  market: "CN" | "HK" | "US";
  timeframe: string;
  adjust: string;
  items: TerminalBar[];
  source: string;
  asOf?: string;
  hasMore: boolean;
}

export const api = {
  health: () => get<{ ok: boolean }>("/health"),
  indices: () => get<IndexQuote[]>("/indices"),
  marketOverview: () => get<MarketOverview>("/market/overview"),
  emotion: () => get<ShortTermEmotion>("/market/emotion"),
  turnoverTop: () => get<TurnoverTop>("/market/turnover-top"),
  globalIndices: () => get<GlobalIndex[]>("/global/indices"),
  globalStock: (symbol: string) => get<GlobalStock>(`/global/stock?symbol=${encodeURIComponent(symbol)}`),
  equityResearch: (symbol: string) =>
    get<EquityResearchSnapshot>(
      `/equity-research/snapshot?symbol=${encodeURIComponent(symbol)}`,
    ),
  equityResearchComparison: (symbols: string[]) =>
    get<EquityResearchComparison>(
      `/equity-research/comparison?symbols=${encodeURIComponent(symbols.join(","))}`,
    ),
  terminalQuotes: (symbols: string) =>
    get<{ items: TerminalQuote[]; asOf?: string }>(
      `/market-terminal/quotes?symbols=${encodeURIComponent(symbols)}`,
    ),
  terminalQuote: (
    symbol: string,
    market: "CN" | "HK" | "US",
    assetType: "stock" | "etf" | "fund" | "index" = "stock",
  ) =>
    get<TerminalQuote>(
      `/market-terminal/quote?symbol=${encodeURIComponent(symbol)}&market=${market}&assetType=${assetType}`,
    ),
  terminalOhlcv: (
    symbol: string,
    market: "CN" | "HK" | "US",
    limit = 320,
    assetType: "stock" | "etf" | "fund" | "index" = "stock",
  ) =>
    get<TerminalOhlcv>(
      `/market-terminal/ohlcv?symbol=${encodeURIComponent(symbol)}&market=${market}&timeframe=1d&limit=${limit}&adjust=${market === "CN" && assetType !== "fund" ? "qfq" : "none"}&assetType=${assetType}`,
    ),
  radar: () => get<RadarData>("/radar"),
  radarTopics: (params: {
    query?: string; industry?: string; signal?: string; sort?: string; offset?: number; limit?: number;
  }) => {
    const query = new URLSearchParams({
      q: params.query || "",
      industry: params.industry || "all",
      signal: params.signal || "all",
      sort: params.sort || "attention",
      offset: String(params.offset || 0),
      limit: String(params.limit || 80),
    });
    return get<NewsTopicPage>(`/radar/topics?${query.toString()}`);
  },
  radarRefresh: () => request<RadarData>("/radar/refresh", "POST"),
  portfolio: () => get<PortfolioData>("/portfolio"),
  addHolding: (code: string, shares: number, cost: number) => request<PortfolioData>("/portfolio/holding", "POST", { code, shares, cost }),
  removeHolding: (code: string) => request<PortfolioData>(`/portfolio/holding?code=${code}`, "DELETE"),
  refreshPortfolio: () => request<PortfolioData>("/portfolio/refresh", "POST"),
  closePosition: (code: string, date: string, price: number, shares: number, cost: number) =>
    request<PortfolioData>("/portfolio/close", "POST", { code, date, price, shares, cost }),
  removeClosed: (index: number) => request<PortfolioData>(`/portfolio/close?index=${index}`, "DELETE"),
  valuation: (code: string) => get<Valuation>(`/valuation?code=${code}`),
  percentile: (code: string) => get<ValPercentile>(`/valuation/percentile?code=${code}`),
  financials: (code: string) => get<Financials>(`/financials?code=${code}`),
  announcements: (code: string) => get<Announcement[]>(`/announcements?code=${code}`),
  catalysts: (
    symbols: string[],
    days = 180,
    includeCycles = true,
    concepts: string[] = [],
    includeMacro = true,
  ) =>
    get<CatalystFeed>(
      `/catalysts?symbols=${encodeURIComponent(symbols.join(","))}&concepts=${encodeURIComponent(concepts.join(","))}&days=${days}&include_cycles=${includeCycles ? "true" : "false"}&include_macro=${includeMacro ? "true" : "false"}`,
    ),
  macroMonitor: (days = 7) => get<MacroMonitorFeed>(`/macro-monitor?days=${days}`),
  quote: (codes: string) => get<Record<string, Quote>>(`/quote?codes=${codes}`),
  reports: (code: string) => get<Report[]>(`/reports?code=${code}`),
  news: (code: string) => get<NewsItem[]>(`/news?code=${code}`),
  margin: (code: string) => get<MarginRow[]>(`/margin?code=${code}`),
  blockTrade: (code: string) => get<BlockTradeRow[]>(`/block-trade?code=${code}`),
  holders: (code: string) => get<HolderRow[]>(`/holders?code=${code}`),
  dividend: (code: string) => get<DividendRow[]>(`/dividend?code=${code}`),
  fundFlow: (code: string) => get<FundFlowRow[]>(`/fund-flow?code=${code}`),
  dragonTiger: (code: string) => get<DragonTiger>(`/dragon-tiger?code=${code}`),
  lockup: (code: string) => get<Lockup>(`/lockup?code=${code}`),
  blocks: (code: string) => get<Blocks>(`/blocks?code=${code}`),
  hotConcepts: (code: string) => get<HotConcept[]>(`/hot-concepts?code=${code}`),
  investorQa: (code: string) => get<QaRow[]>(`/investor-qa?code=${code}`),
  industry: (top = 20) => get<IndustryData>(`/industry?top=${top}`),
  myReports: () => get<MyReport[]>("/myreports"),
  uploadReport: (name: string, contentB64: string) =>
    request<MyReport>("/myreports", "POST", { name, content_b64: contentB64 }),
  deleteReport: (id: string) => request<{ ok: boolean }>(`/myreports/${id}`, "DELETE"),
};
