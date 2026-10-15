export type DimensionStatus = "ready" | "degraded" | "on-demand" | "planned";

export interface EvidenceCoverage {
  status: string; reason: string; usingSaved: boolean; receivedAt: string | null;
}
export interface MarginComparison {
  status: "agree" | "conflict" | "partial";
  fields: Array<{ field: string; tushareYuan: number; referenceYuan: number | null; differenceYuan: number | null }>;
  referenceResidualYuan: number | null;
  available?: number; matched?: number; total?: number;
}
export interface BoardDisclosure {
  reason: string; reasonKey: string;
  window: { label: string; sessions: number | null; start: string | null; end: string };
  buyYuan: number | null; sellYuan: number | null; netYuan: number | null; amountConflict: boolean;
  records: Array<Record<string, unknown>>;
  seats: Array<{ name: string; sides: string[]; buyYuan: number | null; sellYuan: number | null; netYuan: number | null;
    ambiguousIdentity: boolean; possibleRepeat: boolean; disclosureCount: number; residualYuan: number | null; raw: Record<string, unknown> }>;
  rawSeatCount: number; repeatedNamedRows: number; ambiguousSeatRows: number; aggregateSafe: boolean;
}
export interface MarginCase {
  date: string; previousDate: string; previousBalanceYuan: number; balanceYuan: number; buyYuan: number; repayYuan: number;
  expectedBalanceYuan: number; residualYuan: number; size: "small" | "review";
  raw: Record<string, unknown>; previousRaw: Record<string, unknown>; mirrorComparison: MarginComparison;
}
export interface SecurityEvidenceData {
  schemaVersion: string; code: string; symbol: string; generatedAt: string;
  board: { date: string; dates: string[]; calendarStatus: string; groups: BoardDisclosure[];
    recordsCoverage: EvidenceCoverage; seatsCoverage: EvidenceCoverage; unmatchedSeats: number; aggregateSafe: boolean; notes: string[] };
  audit: { expectedDate: string | null; start: string; end: string; checked: number; expected: number;
    cases: MarginCase[]; dates?: string[]; smallDifferences: number; reviewDifferences: number; coverage: EvidenceCoverage;
    calendarStatus: string; confirmedInputs: boolean; mirror: EvidenceCoverage;
    official: { date: string | null; previousDate?: string; status: string; reason: string; comparison: MarginComparison | null;
      sourceName?: string; sourceUrl?: string; missingFields?: string[];
      current?: EvidenceCoverage & { rows: Array<Record<string, unknown>> }; previous?: EvidenceCoverage & { rows: Array<Record<string, unknown>> } };
    notes: string[] };
}

export interface SecurityResearchPoint {
  date: string; net: number | null; largeYi: number | null; extraYi: number | null;
  amountYi: number | null; netSharePct: number | null; sourceSharePct: number | null;
  close: number | null; adjFactor: number | null; adjustedValue: number | null; adjustedPct: number | null; factorChanged: boolean;
  balanceYi: number | null; marginBuyYi: number | null; marginRepayYi: number | null; marginNetYi: number | null;
  balanceChangeYi: number | null; marginResidualYuan: number | null;
}
export interface SecurityResearchData {
  schemaVersion: string; code: string; symbol: string; generatedAt: string; expectedDate: string | null;
  currency: string; unit: string; source: string; fallbackReason: string;
  calendar: { status: string; reason: string; dates: string[] };
  feeds: Record<"orders" | "daily" | "factors" | "margin", { api: string; status: string; reason: string; usingSaved: boolean; receivedAt: string; asOf: string | null; count: number }>;
  points: SecurityResearchPoint[];
  order: { net1dYi: number | null; net5dYi: number | null; net20dYi: number | null;
    share1dPct: number | null; share5dPct: number | null; share20dPct: number | null;
    streak: { direction: string; days: number }; baseline: ResearchBaseline };
  leverage: { net1dYi: number | null; net5dYi: number | null; net20dYi: number | null;
    balanceChange5dYi: number | null; balanceChange20dYi: number | null; buyShare5dPct: number | null;
    baseline: ResearchBaseline; reconciliationChecked: number; reconciliationConflicts: number };
  price: { change5dPct: number | null; change20dPct: number | null; method: string; factorChanges20d: number };
  observations: Array<{ id: string; title: string; detail: string }>;
  notes: string[];
}

export type SupplyKind = "repurchase" | "stk_holdertrade" | "share_float";
export interface SupplyEvent {
  id: string; kind: SupplyKind; label: string; stage: string; progress: string;
  annDate: string | null; eventDate: string | null; holder: string | null;
  beginDate: string | null; endDate: string | null; expiryDate: string | null;
  amountYi: number | null; sharesWan: number | null; ratioPct: number | null;
  superseded: boolean; note: string; raw: Record<string, unknown>;
  capacityDaysAt5Pct?: number | null;
}
export interface SupplyDocument {
  id: string; title: string; date: string; url: string; pdfUrl: string;
  text: string; status: string; note: string;
  textTruncated?: boolean;
  parsed: { planDate: string | null; planSignature: string | null; signatureBasis: string; purpose: string | null;
    cumulativeAmountYi: number | null; cumulativeSharesWan: number | null; cumulativeAsOf: string | null; stage: string; quotes: string[] } | null;
}
export interface SupplyVerificationData {
  code: string; kind: SupplyKind; annDate: string; status: string; reason: string; source: string;
  usingSaved?: boolean; truncated?: boolean; items: SupplyDocument[]; previousDocument: SupplyDocument | null;
  comparison: Array<{ field: string; sourceValue: string | number | null; documentValue: string | number | null; status: string }>;
  delta: { status: string; amountYi: number | null; sharesWan: number | null; fromExclusive?: string; toInclusive?: string; note: string };
}
export interface CapitalSupplyData {
  schemaVersion: string; code: string; symbol: string; generatedAt: string; asOf: string;
  window: { start: string; announcementEnd: string; unlockEnd: string };
  feeds: Array<{ id: SupplyKind; label: string; source: string; sourceUrl: string;
    status: string; reason: string; receivedAt: string; usingSaved: boolean;
    asOf: string | null; items: SupplyEvent[]; count: number; duplicatesRemoved: number }>;
  notes: string[]; aggregateSafe: boolean;
  capacity?: { status: string; expectedDate: string | null; samples: number; expected: number;
    averageVolumeWan: number | null; averageTurnoverYi: number | null; participationPct: number; source: string; note: string; reason: string };
}

export interface SectorFlow {
  code?: string; category?: string; aggregateSafe?: boolean;
  level?: SectorLevel; reportedLevel?: string | null; classificationDate?: string | null;
  name?: string; sector?: string; industry?: string;
  inflow?: number; outflow?: number; net?: number; pct?: number; firms?: number;
  netSharePct?: number; asOf?: string | null; metric?: string; source?: string;
}

export type SectorCategory = "industry" | "concept" | "region";
export type SectorLevel = "all" | "L1" | "L2" | "L3" | "unknown";
export interface SectorClassification {
  source: string; url: string; status: string; reason: string; current: boolean; usingSaved: boolean;
  asOf: string | null; total: number; matched: number; counts: Record<string, number>; conflicts: number;
  constituentsVerified: boolean; note: string; selectedLevel: SectorLevel; selectedCount: number;
}
export interface SectorResearchPoint {
  date: string; net: number | null; pct: number | null; close: number | null;
  netSharePct: number | null; superNetYi: number | null; largeNetYi: number | null;
}
export interface SectorResearchData {
  schemaVersion: string; generatedAt: string; source: string;
  category: SectorCategory; categoryLabel: string; expectedDate: string | null; asOf: string | null;
  boards: SectorFlow[];
  level?: SectorLevel; classification?: SectorClassification | null;
  selected: { code: string; name: string; asOf: string | null; points: SectorResearchPoint[];
    status: string; fetchStatus: string; sourceNote: string; usingSaved: boolean;
    summary: { net1dYi: number | null; net5dYi: number | null; net20dYi: number | null;
      price5dPct: number | null; price20dPct: number | null;
      streak: { direction: string; days: number }; baseline: ResearchBaseline } } | null;
  calendar: { status: string; reason: string; dates: string[] };
  coverage: { status: string; reason: string; usingSaved: boolean; duplicatesRemoved: number;
    classified: number; aggregateSafe: boolean; hierarchyVerified: boolean; selectedNotFound: boolean };
  notes: string[];
}

export interface TurnoverLeader {
  code?: string; name?: string; price?: number | null; pct?: number | null; amount?: number; industry?: string;
}

export interface TurnoverSnapshot {
  schemaVersion: string; generatedAt: string; asOf: string | null; expectedDate: string | null;
  status: string; current: boolean; usingSaved: boolean; cached: boolean; reason: string;
  source: string; unit: string; rawUnit: string; note: string; calendarStatus: string; nameNote: string;
  coverage: { received: number; sampleCount: number; rejected: number; invalid: number; duplicates: number;
    conflicts: number; namesMatched: number; universeVerified: boolean; valid: boolean } | null;
  summary: { sampleTurnoverYi: number | null; top20TurnoverYi: number | null; top20SharePct: number | null };
  exchanges: Array<{ id: string; name: string; count: number; turnoverYi: number | null }>;
  leaders: TurnoverLeader[];
}

export interface TurnoverHistoryData {
  days: 20 | 60; asOf: string | null; start: string | null; current: boolean;
  completed: number; expected: number; remaining: number; commonCount: number;
  latestSampleCount: number; excludedLatest: number | null; note: string;
  summary: { latestTurnoverYi: number | null; meanTurnoverYi: number | null; relativeVolume: number | null;
    percentilePct: number | null; top20SharePct: number | null; meanTop20SharePct: number | null; concentrationChangePp: number | null };
  points: Array<{ date: string; status: string; reason: string; sampleCount: number; turnoverYi: number | null; top20SharePct: number | null }>;
  generatedAt: string; source: string; unit: string; calendarStatus: string; failedDates: string[];
  fetchedDays: number; canContinue: boolean; reason: string;
}

export interface CapitalFlowDimension {
  id: string; name: string; status: DimensionStatus; frequency: string;
  lag: string; source: string; note?: string; metric?: string; asOf?: string | null;
}

export type CapitalDriverSignal = "supportive" | "restrained" | "mixed" | "observed" | "unavailable";

export interface CapitalRiskDriver {
  id: string;
  name: string;
  signal: CapitalDriverSignal;
  value?: string | null;
  detail: string;
  source: string;
  asOf?: string | null;
}

export interface ConnectSummary {
  market?: string; turnoverYi?: number | null; buyYi?: number | null;
  sellYi?: number | null; netBuyYi?: number | null; etfTurnoverYi?: number | null;
  currency?: "CNY" | "HKD"; unit?: string;
}

export interface SecuritySearchItem {
  symbol: string;
  name: string;
  market: "CN";
  exchange?: string;
  industry?: string;
  securityType?: string;
}

export interface FundFlowRow {
  date?: string;
  close?: number;
  change_pct?: number;
  main_net?: number;
  large_net?: number;
  super_net?: number;
  net_amount?: number;
  source?: string;
}

export interface MarginRow {
  date?: string;
  rzye?: number;
  rzmre?: number;
  rzche?: number;
  rqye?: number;
  rqmcl?: number;
  rzrqye?: number;
}

export interface DragonTigerSeat {
  name?: string;
  buy_amt?: number;
  sell_amt?: number;
  net?: number;
}

export interface DragonTigerData {
  records?: Array<{ date?: string; reason?: string; net_buy?: number; turnover?: number }>;
  seats?: { buy?: DragonTigerSeat[]; sell?: DragonTigerSeat[] };
  institution?: { buy_amt?: number; sell_amt?: number; net_amt?: number };
  source?: string;
}

export interface SecurityCoverage {
  status: "ready" | "empty" | "unavailable";
  count: number; source: string; asOf: string | null; note: string;
}

export interface NorthboundHistoryPoint {
  date: string;
  sseTurnoverYi?: number | null;
  szseTurnoverYi?: number | null;
  northTurnoverYi?: number | null;
}

export interface ConnectMomentumPeriod {
  start: string | null; end: string | null; available: number; current: boolean;
  turnoverYi: number | null; netBuyYi: number | null; netIntensityPct: number | null;
}
export interface ConnectMomentum {
  days: number; current: boolean; recent: ConnectMomentumPeriod; previous: ConnectMomentumPeriod;
  missingDates: string[]; netChangeYi: number | null; intensityChangePp: number | null; turnoverRatio: number | null;
}
export interface ConnectResearchWindow {
  direction: string; days: number; currency: string; unit: string; current: boolean;
  asOf: string | null; start: string | null; available: number; closedDays: string[]; missingDates: string[];
  momentum?: ConnectMomentum;
  points: Array<{ date: string; status: string; usingSaved?: boolean; reason?: string; turnoverYi?: number | null;
    buyYi?: number | null; sellYi?: number | null; netBuyYi?: number | null }>;
  summary: { turnoverYi: number | null; buyYi: number | null; sellYi: number | null; netBuyYi: number | null;
    positiveDays: number | null; streakDays: number | null; streakDirection: string; streakCensored: boolean;
    prior20MeanTurnoverYi: number | null; latestVsPrior20: number | null };
}
export interface ConnectResearchData {
  generatedAt: string; cutoff: string; source: string; completed: number; expected: number; remaining: number;
  failedDates: string[]; canContinue: boolean; notes: string[];
  windows: Record<"5" | "20", { northbound: ConnectResearchWindow; southbound: ConnectResearchWindow }>;
}

export interface NorthboundHistory {
  points?: NorthboundHistoryPoint[];
  status?: string;
  metric?: string;
  currency?: "CNY";
  unit?: string;
  source?: string;
  reason?: string;
  validation?: {
    status?: string;
    date?: string;
    officialDate?: string;
    historyDate?: string;
    officialTurnoverYi?: number;
    historyTurnoverYi?: number;
    differenceYi?: number;
    differencePct?: number;
    thresholdPct?: number;
  };
}

export interface CapitalFlowDashboard {
  schemaVersion: string; generatedAt: string; marketDate: string | null;
  summary: {
    sectorNetYi: number | null; sectorInflowYi: number | null; sectorOutflowYi: number | null;
    top20TurnoverYi: number | null; active: number | string | null;
  };
  sectors: SectorFlow[];
  turnoverLeaders: TurnoverLeader[];
  turnover?: TurnoverSnapshot;
  security: { code: string; fundFlow: FundFlowRow[]; margin: MarginRow[]; dragonTiger?: DragonTigerData; coverage?: Record<"fundFlow" | "margin" | "dragonTiger", SecurityCoverage> } | null;
  crossBorder?: {
    northbound: { sse: ConnectSummary; szse: ConnectSummary; history?: NorthboundHistory; source?: string; date?: string | null; currency?: "CNY"; unit?: string };
    southbound: { sse: ConnectSummary; szse: ConnectSummary; source?: string; date?: string | null; currency?: "HKD"; unit?: string };
  };
  liquidity?: {
    indicators: Array<Record<string, unknown>>;
    groups?: Array<{ id: string; label: string; indicators: Array<Record<string, unknown>> }>;
    regime?: Record<string, unknown> | null;
    forecast?: { horizonDays?: number; signal?: string; direction?: string; confidence?: number; method?: string; items?: Array<Record<string, unknown>> };
    coverage?: { available?: number; total?: number; asOf?: string | null };
    note?: string;
    source: string;
  };
  riskAppetite?: {
    drivers: CapitalRiskDriver[];
    available: number;
    total: number;
  };
  dimensions: CapitalFlowDimension[];
  sources: Array<{ name: string; url: string }>;
  upstream: { status: "ready" | "degraded"; base: string };
}

export interface ResearchBaseline {
  samples: number; expected: number; percentile: number | null; mean: number | null;
}

export interface AppetiteRelation {
  id: string; inputs: string[]; status: "incomplete" | "flat" | "aligned" | "divergent";
  title: string; watch: string;
}
export interface AppetiteWindow {
  days: number; start: string | null; end: string | null;
  evidence: Array<{ id: string; name: string; value: number | null; unit: string; current: boolean;
    asOf: string | null; scope: string; source: string; note: string }>;
  etfs: Array<{ code: string; name: string; value: number | null; current: boolean; asOf: string | null; note: string }>;
  relationships: AppetiteRelation[]; conditions: AppetiteRelation; verifiedRelationships: number; divergences: number;
}
export interface AppetiteResearchData {
  schemaVersion: string; generatedAt: string; expectedDate: string | null;
  market: { code: string; name: string; asOf: string | null; current: boolean;
    points: Array<{ date: string; close: number | null; pct: number | null }>;
    return5dPct: number | null; return20dPct: number | null; volatility20dPct: number | null;
    maxDrawdown60dPct: number | null; volatilitySamples: number; drawdownSamples: number; source: string; note: string };
  breadth: { asOf: string | null; total: number; comparable: number; current: boolean; source: string; note: string;
    scope?: string; classification?: SectorClassification | null;
    buckets: Array<{ id: string; name: string; count: number; examples: Array<{ code: string; name: string }> }> };
  windows: Record<"5" | "20", AppetiteWindow>;
  sectorSnapshot?: SectorResearchData;
  leverage: CapitalResearch["leverage"];
  credit: Pick<LiquidityResearchData["credit"], "money" | "social"> & { transmission: LiquidityResearchData["transmission"] };
  sources: { calendar: CapitalResearch["calendar"]; benchmark: { status: string; reason: string; usingSaved: boolean };
    leverage: Pick<CapitalResearch["leverage"], "status" | "fetchStatus" | "usingSaved" | "sourceNote" | "asOf">;
    sectors: { status: string; usingSaved?: boolean; reason?: string }; liquidity: LiquidityResearchData["feeds"] };
  notes: string[];
}

export interface LiquidityRatePoint {
  date: string; dr007: number | null; r007: number | null;
  shibor1w: number | null; shibor3m: number | null; spreadBp: number | null;
}

export interface LiquidityMonthPoint {
  month: string; m1Yoy: number | null; m2Yoy: number | null; m2M1GapPp: number | null;
  socialFlowYi: number | null; socialPriorYearYi: number | null; socialYoYDiffYi: number | null;
  socialStockWanYi: number | null; socialStockYoy: number | null;
}

export interface LiquidityResearchData {
  schemaVersion: string; generatedAt: string;
  query: { dailyStart: string; dailyEnd: string; monthlyStart: string; monthlyEnd: string };
  daily: {
    asOf: string | null; note: string; points: LiquidityRatePoint[];
    series: Array<{ id: keyof Omit<LiquidityRatePoint, "date">; name: string; definition: string; unit: string;
      value: number | null; asOf: string | null; ageDays: number | null; current: boolean;
      change1Bp: number | null; change5Bp: number | null; change20Bp: number | null;
      baselineSamples: number; baselineExpected: number; percentile: number | null }>;
  };
  credit: {
    note: string; points: LiquidityMonthPoint[];
    money: Partial<LiquidityMonthPoint> & { current: boolean; m1ChangePp: number | null; m2ChangePp: number | null; gapChangePp: number | null };
    social: Partial<LiquidityMonthPoint> & { current: boolean; stockYoyChangePp: number | null;
      flow3mYi: number | null; flow3mPriorYearYi: number | null; flow3mYoYDiffYi: number | null };
  };
  transmission: Array<{ id: string; name: string; signal: "higher" | "lower" | "flat" | "mixed" | "unknown";
    evidence: string; implication: string; watch: string }>;
  feeds: Array<{ id: string; name: string; url: string; status: string; reason: string;
    receivedAt: string; cached: boolean; usingSaved: boolean; count: number; asOf: string | null }>;
  operations: { status: string; grossYi: number | null; maturitiesYi: number | null; netYi: number | null; url: string; note: string };
  notes: string[];
}

export interface ETFResearchPoint {
  date: string; sharesWan: number | null; nav: number | null; navAnnDate?: string | null;
  shareChangeWan: number | null; shareChangePct: number | null; flowYi: number | null;
  navChangePct: number | null; suspectedSplit: boolean;
}

export interface ETFResearch {
  code: string; name: string; category: string; currency: string;
  source: string; sourceNote: string; receivedAt: string; fetchStatus: string; usingSaved: boolean;
  status: string; asOf: string | null; expectedDate: string | null; note: string;
  latest: Partial<ETFResearchPoint>; points: ETFResearchPoint[];
  summary: { flow1dYi: number | null; flow5dYi: number | null; flow20dYi: number | null; baseline: ResearchBaseline };
}

export interface MarketLeveragePoint {
  date: string; exchanges: string[]; complete: boolean;
  balanceYi: number | null; buyYi: number | null; repayYi: number | null; netYi: number | null;
  byExchange: Array<{ exchange: string; name: string; balanceYi: number | null }>;
}

export interface CapitalResearch {
  schemaVersion: string; generatedAt: string; expectedDate: string | null;
  calendar: { status: string; sessions: number; dates: string[]; reason: string };
  coverage: { etfAvailable: number; etfTotal: number; sampleOnly: boolean; primaryStatus: string; primaryReason: string };
  etfs: ETFResearch[];
  groups: Array<{ category: string; count: number; available: number; flow1dYi: number | null; flow5dYi: number | null; flow20dYi: number | null }>;
  leverage: {
    status: string; source: string; sourceNote: string; fetchStatus: string; receivedAt: string; usingSaved: boolean;
    currency: string; unit: string; scope: string[]; asOf: string | null; expectedDate: string | null;
    latest: Partial<MarketLeveragePoint>; points: MarketLeveragePoint[]; note: string;
    summary: { net1dYi: number | null; net5dYi: number | null; net20dYi: number | null; baseline: ResearchBaseline };
  };
  notes: string[];
}
