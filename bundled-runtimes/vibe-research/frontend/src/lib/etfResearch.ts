import type { TerminalBar, TerminalQuote } from "@/lib/api";

export type EtfMarket = "CN" | "HK" | "US";
export type FundInstrumentType = "etf" | "fund";

export interface EtfSecurity {
  market: EtfMarket;
  symbol: string;
  assetType: FundInstrumentType;
  name?: string;
}

export interface EtfMetrics {
  security: EtfSecurity;
  quote?: TerminalQuote;
  bars: TerminalBar[];
  source: string;
  return20d: number | null;
  return60d: number | null;
  return252d: number | null;
  annualizedReturn: number | null;
  annualizedVolatility: number | null;
  maxDrawdown: number | null;
  returnVolatilityRatio: number | null;
  positiveDayRatio: number | null;
  riskBand: "稳健" | "均衡" | "进取" | "数据不足";
}

export const etfKey = (security: Pick<EtfSecurity, "market" | "symbol" | "assetType">) =>
  `${security.assetType}:${security.market}:${security.symbol}`;

export function parseEtfSecurity(
  value: string,
  fallbackMarket: EtfMarket,
  assetType: FundInstrumentType = "etf",
): EtfSecurity | null {
  const clean = value.trim().toUpperCase();
  if (!clean) return null;
  if (assetType === "fund" && fallbackMarket !== "CN") return null;
  const explicit = clean.match(/^(CN|HK|US):([A-Z0-9.-]{1,24})$/);
  if (explicit) {
    const market = explicit[1] as EtfMarket;
    if (assetType === "fund" && market !== "CN") return null;
    return { market, symbol: explicit[2], assetType };
  }
  if (/^\d{6}$/.test(clean)) return { market: "CN", symbol: clean, assetType };
  if (/^\d{1,5}$/.test(clean) && fallbackMarket === "HK") {
    return { market: "HK", symbol: clean.padStart(5, "0"), assetType };
  }
  if (/^[A-Z][A-Z0-9.-]{0,9}$/.test(clean)) {
    return { market: fallbackMarket, symbol: clean, assetType };
  }
  return null;
}

const periodReturn = (closes: number[], periods: number) => {
  if (closes.length <= periods) return null;
  const start = closes[closes.length - 1 - periods];
  const end = closes[closes.length - 1];
  if (!start || end == null) return null;
  return ((end / start) - 1) * 100;
};

const dailyReturns = (bars: TerminalBar[]) => bars.slice(1).flatMap((bar, index) => {
  const previous = bars[index]?.close;
  if (!previous || !Number.isFinite(previous) || !Number.isFinite(bar.close)) return [];
  return [(bar.close / previous) - 1];
});

const standardDeviation = (values: number[]) => {
  if (values.length < 2) return null;
  const mean = values.reduce((sum, value) => sum + value, 0) / values.length;
  const variance = values.reduce((sum, value) => sum + ((value - mean) ** 2), 0) /
    (values.length - 1);
  return Math.sqrt(variance);
};

function riskBand(volatility: number | null, drawdown: number | null): EtfMetrics["riskBand"] {
  if (volatility == null || drawdown == null) return "数据不足";
  const stress = Math.max(volatility, Math.abs(drawdown));
  if (stress < 15) return "稳健";
  if (stress < 28) return "均衡";
  return "进取";
}

export function calculateEtfMetrics(
  security: EtfSecurity,
  bars: TerminalBar[],
  source: string,
  quote?: TerminalQuote,
): EtfMetrics {
  const cleanBars = bars
    .filter((bar) => Number.isFinite(bar.close) && bar.close > 0)
    .sort((left, right) => left.timestamp - right.timestamp);
  const closes = cleanBars.map((bar) => bar.close);
  const returns = dailyReturns(cleanBars);
  const volatility = standardDeviation(returns);
  const annualizedVolatility = volatility == null ? null : volatility * Math.sqrt(252) * 100;
  let peak = -Infinity;
  let maxDrawdown = 0;
  for (const close of closes) {
    peak = Math.max(peak, close);
    if (peak > 0) maxDrawdown = Math.min(maxDrawdown, (close / peak) - 1);
  }
  const elapsed = Math.max(cleanBars.length - 1, 0);
  const start = closes[0];
  const end = closes[closes.length - 1];
  const annualizedReturn = elapsed >= 20 && start && end
    ? (((end / start) ** (252 / elapsed)) - 1) * 100
    : null;
  const drawdownPct = cleanBars.length ? maxDrawdown * 100 : null;
  const ratio = annualizedReturn != null && annualizedVolatility
    ? annualizedReturn / annualizedVolatility
    : null;
  return {
    security: { ...security, name: quote?.name || security.name },
    quote,
    bars: cleanBars,
    source,
    return20d: periodReturn(closes, 20),
    return60d: periodReturn(closes, 60),
    return252d: periodReturn(closes, 252),
    annualizedReturn,
    annualizedVolatility,
    maxDrawdown: drawdownPct,
    returnVolatilityRatio: ratio,
    positiveDayRatio: returns.length
      ? (returns.filter((value) => value > 0).length / returns.length) * 100
      : null,
    riskBand: riskBand(annualizedVolatility, drawdownPct),
  };
}

function returnMap(metrics: EtfMetrics) {
  const map = new Map<number, number>();
  for (let index = 1; index < metrics.bars.length; index += 1) {
    const current = metrics.bars[index];
    const previous = metrics.bars[index - 1];
    if (previous.close > 0) map.set(current.timestamp, (current.close / previous.close) - 1);
  }
  return map;
}

export function correlation(left: EtfMetrics, right: EtfMetrics): number | null {
  if (etfKey(left.security) === etfKey(right.security)) return 1;
  const leftReturns = returnMap(left);
  const rightReturns = returnMap(right);
  const pairs = [...leftReturns.entries()].flatMap(([timestamp, value]) => {
    const other = rightReturns.get(timestamp);
    return other == null ? [] : [[value, other] as const];
  });
  if (pairs.length < 20) return null;
  const leftMean = pairs.reduce((sum, pair) => sum + pair[0], 0) / pairs.length;
  const rightMean = pairs.reduce((sum, pair) => sum + pair[1], 0) / pairs.length;
  let covariance = 0;
  let leftVariance = 0;
  let rightVariance = 0;
  for (const [leftValue, rightValue] of pairs) {
    const leftDelta = leftValue - leftMean;
    const rightDelta = rightValue - rightMean;
    covariance += leftDelta * rightDelta;
    leftVariance += leftDelta ** 2;
    rightVariance += rightDelta ** 2;
  }
  const denominator = Math.sqrt(leftVariance * rightVariance);
  return denominator ? covariance / denominator : null;
}

export function normalizedSeries(metrics: EtfMetrics, limit = 120) {
  const bars = metrics.bars.slice(-limit);
  const base = bars[0]?.close;
  if (!base) return [];
  return bars.map((bar) => ({
    timestamp: bar.timestamp,
    value: ((bar.close / base) - 1) * 100,
  }));
}
