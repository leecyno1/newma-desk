// Local signal eligibility, not a FRED publication-calendar or real-time guarantee.
// Keep historical observations readable; only dated, recent values drive current signals.
export const FRED_SIGNAL_SERIES = {
  VIXCLS: { key: 'vix', unit: 'index points', changeUnit: 'index points', maxAgeDays: 7 },
  BAMLH0A0HYM2: { key: 'hy_spread', unit: 'percentage points', changeUnit: 'percentage points', maxAgeDays: 7 },
  T10Y2Y: { key: '10y2y', unit: 'percentage points', changeUnit: 'percentage points', maxAgeDays: 7 },
  DFF: { key: 'fed_funds', unit: 'percent', changeUnit: 'percentage points', maxAgeDays: 7 },
  DGS10: { key: '10y_yield', unit: 'percent', changeUnit: 'percentage points', maxAgeDays: 7 },
  DGS2: { unit: 'percent', changeUnit: 'percentage points', maxAgeDays: 7 },
  DTWEXBGS: { key: 'usd_index', unit: 'index', changeUnit: 'index points', maxAgeDays: 7 },
  MORTGAGE30US: { key: 'mortgage', unit: 'percent', changeUnit: 'percentage points', maxAgeDays: 14 },
};

export function fredSignalObservation(row, { now = new Date(), maxAgeDays = FRED_SIGNAL_SERIES[row?.id]?.maxAgeDays ?? 7 } = {}) {
  if (!Number.isFinite(row?.value) || typeof row.date !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(row.date)) return null;
  const observed = Date.parse(row.date);
  if (!Number.isFinite(observed) || new Date(observed).toISOString().slice(0, 10) !== row.date) return null;
  const today = Date.parse(now.toISOString().slice(0, 10));
  const ageDays = (today - observed) / 86400000;
  return ageDays >= 0 && ageDays <= maxAgeDays ? row : null;
}
