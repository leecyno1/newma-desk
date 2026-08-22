export type DimensionStatus = "ready" | "degraded" | "on-demand" | "planned";

export interface SectorFlow {
  name?: string; sector?: string; industry?: string;
  inflow?: number; outflow?: number; net?: number; pct?: number; firms?: number;
}

export interface TurnoverLeader {
  code?: string; name?: string; price?: number; pct?: number; amount?: number; industry?: string;
}

export interface CapitalFlowDimension {
  id: string; name: string; status: DimensionStatus; frequency: string;
  lag: string; source: string; note?: string;
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

export interface NorthboundHistoryPoint {
  date: string;
  sseTurnoverYi?: number | null;
  szseTurnoverYi?: number | null;
  northTurnoverYi?: number | null;
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
    sectorNetYi: number; sectorInflowYi: number; sectorOutflowYi: number;
    top20TurnoverYi: number; active: number | string | null;
  };
  sectors: SectorFlow[];
  turnoverLeaders: TurnoverLeader[];
  security: { code: string; fundFlow: FundFlowRow[]; margin: MarginRow[]; dragonTiger?: DragonTigerData } | null;
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
