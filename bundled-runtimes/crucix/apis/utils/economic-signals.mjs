// Current-context eligibility, not a publication calendar or point-in-time certification.
export const BLS_SIGNAL_SERIES = {
  CUUR0000SA0: { unit: 'index', changeUnit: 'index-points', seasonalAdjustment: 'not-seasonally-adjusted' },
  CUUR0000SA0L1E: { unit: 'index', changeUnit: 'index-points', seasonalAdjustment: 'not-seasonally-adjusted' },
  LNS14000000: { key: 'unemployment', unit: 'percent', changeUnit: 'percentage-points', seasonalAdjustment: 'seasonally-adjusted' },
  CES0000000001: { unit: 'thousands-of-persons', changeUnit: 'thousands-of-persons', seasonalAdjustment: 'seasonally-adjusted' },
  WPUFD49104: { unit: 'index', changeUnit: 'index-points', seasonalAdjustment: 'not-seasonally-adjusted' },
};

function monthOrdinal(date) {
  const match = typeof date === 'string' && date.match(/^(\d{4})-(0[1-9]|1[0-2])$/);
  return match ? Number(match[1]) * 12 + Number(match[2]) - 1 : null;
}

export function adjacentMonthPeriods(current, previous) {
  const currentMonth = monthOrdinal(current), previousMonth = monthOrdinal(previous);
  return currentMonth !== null && previousMonth !== null && currentMonth === previousMonth + 1;
}

export const METAL_SIGNAL_SERIES = { gold: 'GC=F', silver: 'SI=F' };

export function metalSignalObservation(row, { now = new Date() } = {}) {
  if (!METAL_SIGNAL_SERIES[row?.id] || !Number.isFinite(row.value) || row.unit !== 'USD/troy-ounce'
    || row.kind !== 'futures' || row.frequency !== 'quote' || row.source?.id !== 'YFinance'
    || row.source.seriesId !== METAL_SIGNAL_SERIES[row.id] || typeof row.observedAt !== 'string'
    || !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$/.test(row.observedAt)) return null;
  const date = row.observedAt.slice(0, 10), time = Date.parse(row.observedAt), day = Date.parse(date);
  if (!Number.isFinite(day) || new Date(day).toISOString().slice(0, 10) !== date) return null;
  const age = (now.getTime() - time) / 86400000;
  return Number.isFinite(age) && age >= 0 && age <= 7 ? row : null;
}

export function metalSessionChange(row, options) {
  if (!metalSignalObservation(row, options) || !Number.isFinite(row.prevClose) || row.prevClose <= 0
    || !['provider', 'daily-bars'].includes(row.previousCloseBasis)) return null;
  return { value: row.value - row.prevClose, pct: (row.value - row.prevClose) / row.prevClose * 100,
    basis: row.previousCloseBasis };
}

export function gscpiSignalObservation(row, { now = new Date() } = {}) {
  const month = monthOrdinal(row?.date);
  if (month === null || !Number.isFinite(row.value) || row.unit !== 'standard-deviations'
    || row.frequency !== 'monthly' || row.source?.id !== 'GSCPI' || row.source.seriesId !== 'GSCPI'
    || typeof row.vintage !== 'string' || !row.vintage) return null;
  const age = now.getUTCFullYear() * 12 + now.getUTCMonth() - month;
  return age >= 1 && age <= 2 ? row : null;
}

export function gscpiMonthlyChange(row, options) {
  if (!gscpiSignalObservation(row, options)) return null;
  const current = row.history?.find(point => point.date === row.date);
  const previous = row.history?.find(point => adjacentMonthPeriods(row.date, point.date));
  if (!current || current.value !== row.value || current.vintage !== row.vintage
    || !Number.isFinite(previous?.value) || previous.vintage !== row.vintage) return null;
  return { value: row.value - previous.value, unit: 'standard-deviations',
    fromDate: previous.date, toDate: row.date };
}

export function blsSignalObservation(row, { now = new Date() } = {}) {
  const policy = BLS_SIGNAL_SERIES[row?.id];
  const ordinal = monthOrdinal(row?.date);
  if (!policy || ordinal === null || !Number.isFinite(row.value) || row.frequency !== 'monthly'
    || row.unit !== policy.unit || row.seasonalAdjustment !== policy.seasonalAdjustment) return null;
  const ageMonths = now.getUTCFullYear() * 12 + now.getUTCMonth() - ordinal;
  // Only the last two completed months; an incomplete current month is not a BLS release.
  return ageMonths >= 1 && ageMonths <= 2 ? row : null;
}

export function blsMonthlyChange(row, options) {
  if (!blsSignalObservation(row, options) || !Number.isFinite(row.momChange)) return null;
  if (monthOrdinal(row.momPreviousPeriod) !== monthOrdinal(row.date) - 1) return null;
  return { value: row.momChange, relative: Number.isFinite(row.momChangePct) ? row.momChangePct : null,
    fromDate: row.momPreviousPeriod, toDate: row.date, unit: BLS_SIGNAL_SERIES[row.id].changeUnit };
}

export function treasuryDebtObservation(treasury, { now = new Date() } = {}) {
  const status = treasury?.coverage?.debt?.status;
  if (status !== 'ok' && status !== 'partial') return null;
  const row = treasury.debt?.find(item => item.date === treasury.date && item.totalDebt === treasury.totalDebt);
  if (!row || row.unit !== 'USD' || row.frequency !== 'daily') return null;
  const value = row.totalDebt;
  if (!(typeof value === 'string' && /^\d+(?:\.\d+)?$/.test(value) || typeof value === 'number')
    || !Number.isFinite(Number(value)) || Number(value) < 0) return null;
  if (typeof row.date !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(row.date)) return null;
  const observed = Date.parse(row.date);
  if (!Number.isFinite(observed) || new Date(observed).toISOString().slice(0, 10) !== row.date) return null;
  const ageDays = (Date.parse(now.toISOString().slice(0, 10)) - observed) / 86400000;
  return ageDays >= 0 && ageDays <= 7 ? { value, date: row.date, unit: 'USD', status } : null;
}
