export type MarketId = "CN" | "HK" | "US";
export type Timeframe = "1m" | "5m" | "15m" | "30m" | "60m" | "1d" | "1w" | "1M";
export type Adjustment = "none" | "qfq" | "hfq";
export type PrimaryIndicator = "MA" | "EMA" | "BOLL";
export type SecondaryIndicator = "VOL" | "MACD" | "RSI" | "KDJ";

export interface SecurityRef {
  symbol: string;
  name: string;
  market: MarketId;
  exchange?: string;
  currency?: string;
  timezone?: string;
  assetType?: string;
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

export interface ChartAnnotation {
  id: string;
  timestamp: number;
  value: number;
  label: string;
  tone?: "info" | "positive" | "negative" | "warning";
}

export interface RelativeStrengthPoint {
  timestamp: number;
  value: number;
}

export interface RelativeStrengthSeries {
  id: string;
  label: string;
  color: string;
  points: RelativeStrengthPoint[];
}
