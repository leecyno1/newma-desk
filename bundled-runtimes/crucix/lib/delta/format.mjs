import { FRED_SIGNAL_SERIES, fredSignalObservation } from '../../apis/utils/fred-signals.mjs';
import { BLS_SIGNAL_SERIES, blsSignalObservation, METAL_SIGNAL_SERIES, metalSignalObservation } from '../../apis/utils/economic-signals.mjs';
import { energySignalObservation, energyBasis, sameEnergyBasis, energyObservationDate } from '../../dashboard/energy.mjs';
import { COUNT_METRICS, countObservation, sameCountScope } from './count-observations.mjs';

// Old saved deltas remain readable, but cannot override current verified economic observations.
export function currentDeltaSignal(signal, data, now = new Date()) {
  const tgPost = signal.key?.startsWith('tg_urgent:');
  if (tgPost || COUNT_METRICS.some(metric => metric.key === signal.key)) {
    const current = countObservation(data, tgPost ? 'urgent_posts' : signal.key, now);
    const fromTime = Date.parse(signal.fromDate), toTime = Date.parse(signal.toDate);
    if (!current || !sameCountScope(current, { basis: signal.countBasis, unit: tgPost ? current.unit : signal.unit, scope: signal.countScope })
      || current.asOf !== signal.toDate || !Number.isFinite(fromTime) || fromTime >= toTime
      || now.getTime() - fromTime > 2 * 3600000) return false;
    if (tgPost) return Boolean(signal.item && data.tg.urgent.some(post => post.text === signal.item.text
      && post.channel === signal.item.channel && post.date === signal.item.date));
    const diff = signal.to - signal.from;
    const pct = signal.from === 0 ? null : Number((diff / signal.from * 100).toFixed(1));
    return Number.isSafeInteger(signal.from) && signal.from >= 0 && current.value === signal.to
      && signal.changeUnit === current.unit && signal.change === diff && signal.pctChange === pct
      && signal.direction === (diff > 0 ? 'up' : 'down');
  }
  if (signal.key === 'source_degradation') return false; // Legacy health inference lacks scope evidence.
  const energyId = { wti: 'wti', brent: 'brent', natgas: 'naturalGas' }[signal.key];
  const metalId = METAL_SIGNAL_SERIES[signal.key] ? signal.key : null;
  if (energyId || metalId) {
    const validate = energyId ? energySignalObservation : metalSignalObservation;
    const current = validate(data[energyId ? 'energy' : 'metals']?.observations?.find(row => row.id === (energyId || metalId)), { now });
    if (!current || signal.unit !== current.unit || signal.changeUnit !== current.unit
      || !sameEnergyBasis(energyId ? signal.energyBasis : signal.metalBasis, energyBasis(current))) return false;
    const observation = (value, date) => validate({ ...current, value,
      ...(current.kind === 'futures' ? { observedAt: date } : { period: date }) }, { now });
    const from = observation(signal.from, signal.fromDate), to = observation(signal.to, signal.toDate);
    return Boolean(from && to && Date.parse(signal.fromDate) < Date.parse(signal.toDate)
      && Date.parse(energyObservationDate(current)) === Date.parse(signal.toDate) && current.value === signal.to);
  }
  const fred = Object.entries(FRED_SIGNAL_SERIES).find(([, policy]) => policy.key && policy.key === signal.key);
  const bls = Object.entries(BLS_SIGNAL_SERIES).find(([, policy]) => policy.key && policy.key === signal.key);
  const series = fred || bls;
  if (!series) return true;
  const [id] = series;
  const validate = fred ? fredSignalObservation : blsSignalObservation;
  const rows = fred ? data.fred : data.bls;
  const basis = fred ? {} : { ...BLS_SIGNAL_SERIES[id], frequency: 'monthly' };
  if (bls && (signal.unit !== basis.unit || signal.changeUnit !== basis.changeUnit)) return false;
  const current = validate(rows?.find(row => row.id === id), { now });
  const from = validate({ ...basis, id, value: signal.from, date: signal.fromDate }, { now });
  const to = validate({ ...basis, id, value: signal.to, date: signal.toDate }, { now });
  return Boolean(current && from && to && from.date < to.date
    && current.date === to.date && current.value === to.value);
}

export function deltaSignalText(signal) {
  const label = signal.label || signal.key || 'Signal';
  if (!Number.isFinite(signal.from) || !Number.isFinite(signal.to)) {
    return `${label}: ${signal.reason || signal.text || signal.direction || 'comparison unavailable'}`;
  }
  const signed = value => `${value > 0 ? '+' : ''}${Number(value.toFixed(6))}`;
  const absolute = signal.to - signal.from;
  const commodity = signal.energyBasis || signal.metalBasis;
  const relative = signal.from !== 0 && (!commodity || signal.from > 0 && signal.to >= 0)
    ? absolute / Math.abs(signal.from) * 100 : null;
  const percent = Number.isFinite(relative) ? `${relative > 0 ? '+' : ''}${relative.toFixed(1)}%`
    : `relative unavailable (${signal.from === 0 ? 'zero baseline' : 'nonpositive commodity price'})`;
  const dates = signal.fromDate && signal.toDate ? ` [${signal.fromDate} → ${signal.toDate}]` : '';
  const basis = commodity ? ` [${commodity.kind}, ${commodity.sourceId}/${commodity.seriesId}${commodity.kind === 'futures' ? '; continuous futures may roll' : ''}]`
    : signal.countBasis ? ` [sample scope ${JSON.stringify(signal.countScope)}; collection sample change, not safety improvement]` : '';
  return `${label}: ${signal.from} → ${signal.to}${signal.unit ? ` ${signal.unit}` : ''} (change ${signed(absolute)}${signal.changeUnit ? ` ${signal.changeUnit}` : ''}; ${percent})${dates}${basis}`;
}
