// Delta Engine v2 — compares two synthesized sweep results and produces structured changes
// Improvements: count metric thresholds, semantic TG dedup, configurable thresholds, null-safety

import { createHash } from 'crypto';
import { FRED_SIGNAL_SERIES, fredSignalObservation } from '../../apis/utils/fred-signals.mjs';
import { BLS_SIGNAL_SERIES, blsSignalObservation, metalSignalObservation } from '../../apis/utils/economic-signals.mjs';
import { energySignalObservation, energyBasis, sameEnergyBasis, energyObservationDate } from '../../dashboard/energy.mjs';
import { COUNT_METRICS, countObservation, sameCountScope } from './count-observations.mjs';

// ─── Default Thresholds ──────────────────────────────────────────────────────
// Override via config.delta.thresholds in crucix.config.mjs

const DEFAULT_NUMERIC_THRESHOLDS = {
  vix: 5,            // % change to flag
  hy_spread: 5,
  '10y2y': 10,
  wti: 3,
  brent: 3,
  natgas: 5,
  gold: 2,
  silver: 3,
  unemployment: 2,
  fed_funds: 1,
  '10y_yield': 3,
  usd_index: 1,
  mortgage: 2,
};

const DEFAULT_COUNT_THRESHOLDS = {
  urgent_posts: 2,         // need ±2 to matter (was 0 — any change)
  thermal_total: 500,      // ±500 detections (was 0 — +1 was noise)
  air_total: 50,           // ±50 aircraft
  who_alerts: 1,           // any new WHO alert matters
  conflict_events: 5,      // ±5 ACLED events
  conflict_fatalities: 10,  // ±10 fatalities
  sdr_online: 3,           // ±3 receivers
  news_count: 5,           // ±5 news items
  sources_ok: 1,           // any source going down matters
};

// ─── Metric Definitions ──────────────────────────────────────────────────────

const NUMERIC_METRICS = [
  { key: 'vix', fred: 'VIXCLS', extract: d => d.fred?.find(f => f.id === 'VIXCLS')?.value, label: 'VIX' },
  { key: 'hy_spread', fred: 'BAMLH0A0HYM2', extract: d => d.fred?.find(f => f.id === 'BAMLH0A0HYM2')?.value, label: 'HY Spread' },
  { key: '10y2y', fred: 'T10Y2Y', extract: d => d.fred?.find(f => f.id === 'T10Y2Y')?.value, label: '10Y-2Y Spread' },
  { key: 'wti', energy: 'wti', extract: d => d.energy?.wti, label: 'WTI Crude' },
  { key: 'brent', energy: 'brent', extract: d => d.energy?.brent, label: 'Brent Crude' },
  { key: 'natgas', energy: 'naturalGas', extract: d => d.energy?.natgas, label: 'Natural Gas' },
  { key: 'gold', metal: 'gold', extract: d => d.metals?.gold, label: 'Gold' },
  { key: 'silver', metal: 'silver', extract: d => d.metals?.silver, label: 'Silver' },
  { key: 'unemployment', bls: 'LNS14000000', extract: d => d.bls?.find(b => b.id === 'LNS14000000')?.value, label: 'Unemployment' },
  { key: 'fed_funds', fred: 'DFF', extract: d => d.fred?.find(f => f.id === 'DFF')?.value, label: 'Fed Funds Rate' },
  { key: '10y_yield', fred: 'DGS10', extract: d => d.fred?.find(f => f.id === 'DGS10')?.value, label: '10Y Yield' },
  { key: 'usd_index', fred: 'DTWEXBGS', extract: d => d.fred?.find(f => f.id === 'DTWEXBGS')?.value, label: 'USD Index' },
  { key: 'mortgage', fred: 'MORTGAGE30US', extract: d => d.fred?.find(f => f.id === 'MORTGAGE30US')?.value, label: '30Y Mortgage' },
];

// Risk-sensitive keys: used for determining overall direction
// Collection/sample volume cannot establish geopolitical safety or risk appetite.
const RISK_KEYS = ['vix', 'hy_spread'];

// ─── Semantic Hashing for Telegram Posts ─────────────────────────────────────

/**
 * Produce a normalized semantic hash of a post's content.
 * This is intentionally lossy and is only safe as a fallback when a stable
 * post identity is unavailable.
 */
function contentHash(text) {
  if (!text) return '';
  const normalized = text
    .toLowerCase()
    .replace(/\d{1,2}:\d{2}(:\d{2})?/g, '')       // strip times
    .replace(/\d+/g, 'N')                           // normalize all numbers
    .replace(/[^\w\s]/g, '')                         // strip punctuation
    .replace(/\s+/g, ' ')
    .trim()
    .substring(0, 100);
  return createHash('sha256').update(normalized).digest('hex').substring(0, 12);
}

function stablePostKey(post) {
  if (!post) return '';

  const sourceId = post.postId || post.messageId || '';
  const channelId = post.channel || post.chat || '';
  const date = post.date || '';
  const text = (post.text || '').trim().substring(0, 200);

  if (sourceId) return `id:${sourceId}`;
  if (channelId && date) {
    return createHash('sha256')
      .update(`${channelId}|${date}|${text}`)
      .digest('hex')
      .substring(0, 16);
  }

  return `semantic:${contentHash(post.text)}`;
}

// ─── Core Delta Computation ──────────────────────────────────────────────────

/**
 * @param {object} current - current sweep's synthesized data
 * @param {object|null} previous - previous sweep's synthesized data (null on first run)
 * @param {object} [thresholdOverrides] - optional: { numeric: {...}, count: {...} }
 * @param {Array<object>} [priorRuns] - optional compacted prior runs for broader dedup
 */
export function computeDelta(current, previous, thresholdOverrides = {}, priorRuns = []) {
  if (!previous) return null;
  if (!current) return null;

  const numThresholds = { ...DEFAULT_NUMERIC_THRESHOLDS, ...(thresholdOverrides.numeric || {}) };
  const cntThresholds = { ...DEFAULT_COUNT_THRESHOLDS, ...(thresholdOverrides.count || {}) };

  const signals = { new: [], escalated: [], deescalated: [], unchanged: [] };
  const comparisonGaps = [];
  const now = new Date();
  let criticalChanges = 0;

  // ─── Numeric metrics: track % change ─────────────────────────────────

  for (const m of NUMERIC_METRICS) {
    let curr = m.extract(current);
    let prev = m.extract(previous);
    let observation = {};
    if (m.energy || m.metal) {
      const group = m.energy ? 'energy' : 'metals', id = m.energy || m.metal;
      const validate = m.energy ? energySignalObservation : metalSignalObservation;
      const currRow = current[group]?.observations?.find(row => row.id === id);
      const prevRow = previous[group]?.observations?.find(row => row.id === id);
      if (!currRow && !prevRow && curr == null && prev == null) continue;
      if (!validate(currRow, { now }) || !validate(prevRow, { now })
        || !sameEnergyBasis(energyBasis(currRow), energyBasis(prevRow))) {
        comparisonGaps.push({ key: m.key, reason: 'Missing, stale, unverified or changed commodity basis' });
        continue;
      }
      curr = currRow.value;
      prev = prevRow.value;
      const fromDate = energyObservationDate(prevRow), toDate = energyObservationDate(currRow);
      if (Date.parse(toDate) <= Date.parse(fromDate)) {
        if (Date.parse(toDate) === Date.parse(fromDate) && curr === prev) signals.unchanged.push(m.key);
        else comparisonGaps.push({ key: m.key, reason: Date.parse(toDate) === Date.parse(fromDate)
          ? 'Same-date revision, not a new commodity observation' : 'Commodity observation date regressed' });
        continue;
      }
      observation = { fromDate, toDate, unit: currRow.unit, changeUnit: currRow.unit,
        [m.energy ? 'energyBasis' : 'metalBasis']: energyBasis(currRow) };
    }
    if (m.fred || m.bls) {
      const source = m.fred ? 'FRED' : 'BLS';
      const id = m.fred || m.bls;
      const rows = data => m.fred ? data.fred : data.bls;
      const validate = m.fred ? fredSignalObservation : blsSignalObservation;
      const currRow = rows(current)?.find(row => row.id === id);
      const prevRow = rows(previous)?.find(row => row.id === id);
      if (!currRow && !prevRow) continue;
      const currentValid = validate(currRow, { now });
      const previousValid = validate(prevRow, { now });
      if (!currentValid || !previousValid) {
        comparisonGaps.push({ key: m.key, reason: `Missing, stale, invalid or undated ${source} observation` });
        continue;
      }
      if (currRow.date <= prevRow.date) {
        if (currRow.date === prevRow.date && curr === prev) signals.unchanged.push(m.key);
        else comparisonGaps.push({ key: m.key, reason: currRow.date === prevRow.date ? 'Same-date revision, not a new observation' : 'Observation date regressed' });
        continue;
      }
      const policy = m.fred ? FRED_SIGNAL_SERIES[id] : BLS_SIGNAL_SERIES[id];
      observation = { seriesId: id, fromDate: prevRow.date, toDate: currRow.date,
        unit: policy.unit, changeUnit: policy.changeUnit };
    }
    if (!Number.isFinite(curr) || !Number.isFinite(prev)) continue;

    const threshold = numThresholds[m.key] ?? 5;
    const diff = curr - prev;
    if (!Number.isFinite(diff)) continue;
    const pctChange = prev !== 0 && (!(m.energy || m.metal) || prev > 0 && curr >= 0) ? (diff / Math.abs(prev)) * 100 : null;

    if ((pctChange === null && diff !== 0) || (Number.isFinite(pctChange) && Math.abs(pctChange) > threshold)) {
      const entry = {
        key: m.key, label: m.label, from: prev, to: curr,
        change: diff, pctChange: pctChange === null ? null : parseFloat(pctChange.toFixed(2)),
        direction: diff > 0 ? 'up' : 'down',
        severity: Math.abs(pctChange) > threshold * 3 ? 'critical' : Math.abs(pctChange) > threshold * 2 ? 'high' : 'moderate',
        ...observation,
      };
      if (diff > 0) signals.escalated.push(entry);
      else signals.deescalated.push(entry);
      if (Math.abs(pctChange) > 10) criticalChanges++;
    } else {
      signals.unchanged.push(m.key);
    }
  }

  // ─── Count metrics: track absolute change (with minimum thresholds) ──

  for (const m of COUNT_METRICS) {
    if (current[m.field] == null && previous[m.field] == null) continue;
    const currSample = countObservation(current, m.key, now);
    const prevSample = countObservation(previous, m.key, now);
    if (!currSample || !prevSample || !sameCountScope(currSample, prevSample)) {
      comparisonGaps.push({ key: m.key, reason: 'Missing, partial, stale or different-scope collection samples; not evidence of safety improvement' });
      continue;
    }
    const curr = currSample.value, prev = prevSample.value;
    if (Date.parse(currSample.asOf) <= Date.parse(prevSample.asOf)) {
      if (currSample.asOf === prevSample.asOf && curr === prev) signals.unchanged.push(m.key);
      else comparisonGaps.push({ key: m.key, reason: 'Collection time regressed or same-time sample revised' });
      continue;
    }
    const diff = curr - prev;
    const threshold = cntThresholds[m.key] ?? 1;

    if (Math.abs(diff) >= threshold) {
      const pctChange = prev !== 0 ? ((diff / Math.abs(prev)) * 100) : null;
      const entry = {
        key: m.key, label: m.label, from: prev, to: curr,
        change: diff, direction: diff > 0 ? 'up' : 'down',
        pctChange: pctChange === null ? null : parseFloat(pctChange.toFixed(1)),
        severity: 'informational',
        fromDate: prevSample.asOf, toDate: currSample.asOf,
        unit: currSample.unit, changeUnit: currSample.unit,
        countBasis: currSample.basis, countScope: currSample.scope,
        note: 'Collection sample change, not incident onset, population total or safety improvement',
      };
      if (diff > 0) signals.escalated.push(entry);
      else signals.deescalated.push(entry);
      // Magnitude within a collection sample is not a critical-risk judgement.
    } else {
      signals.unchanged.push(m.key);
    }
  }

  // ─── New urgent Telegram posts (semantic dedup) ──────────────────────

  // Dedup against all recent runs (not just the last one) to catch posts that
  // drop out of one sweep but reappear in a later one. Use stable post identity
  // where possible so updated posts are not collapsed into earlier alerts just
  // because their text is semantically similar.
  const currTg = countObservation(current, 'urgent_posts', now);
  const prevTg = countObservation(previous, 'urgent_posts', now);
  const tgComparable = currTg && prevTg && sameCountScope(currTg, prevTg)
    && Date.parse(currTg.asOf) > Date.parse(prevTg.asOf);
  const sources = [previous, ...priorRuns].filter(run => {
    const sample = countObservation(run, 'urgent_posts', now);
    return currTg && sample && sameCountScope(currTg, sample) && Date.parse(sample.asOf) < Date.parse(currTg.asOf);
  });
  const prevHashes = new Set(
    sources.flatMap(run => (run?.tg?.urgent || []).map(stablePostKey)).filter(Boolean)
  );

  for (const post of (tgComparable ? current.tg.urgent : [])) {
    const hash = stablePostKey(post);
    if (hash && !prevHashes.has(hash)) {
      signals.new.push({
        key: `tg_urgent:${hash}`,
        text: post.text,
        item: post,
        reason: 'Newly present in shown OSINT samples; publication and incident onset not verified',
        fromDate: prevTg.asOf, toDate: currTg.asOf,
        countBasis: currTg.basis, countScope: currTg.scope,
      });
    }
  }

  // ─── Nuclear anomaly state change ────────────────────────────────────

  const currAnom = current.nuke?.some(n => n.anom) || false;
  const prevAnom = previous.nuke?.some(n => n.anom) || false;
  if (currAnom && !prevAnom) {
    signals.new.push({ key: 'nuke_anomaly', reason: 'Nuclear anomaly detected', severity: 'critical' });
    criticalChanges += 5;
  } else if (!currAnom && prevAnom && current.nuke?.length && current.nuke.every(n => n.anom === false)) {
    signals.deescalated.push({ key: 'nuke_anomaly', label: 'Nuclear Anomaly', direction: 'resolved', severity: 'high' });
  }

  // ─── Source health degradation ───────────────────────────────────────

  // sources_ok above already compares complete, same-source health checks.
  // Missing health is not zero failures and must not generate a second unverified alert.

  // ─── Overall direction ───────────────────────────────────────────────

  let direction = 'mixed';
  const riskUp = signals.escalated.filter(s => RISK_KEYS.includes(s.key)).length;
  const riskDown = signals.deescalated.filter(s => RISK_KEYS.includes(s.key)).length;
  if (riskUp > riskDown + 1) direction = 'risk-off';
  else if (riskDown > riskUp + 1) direction = 'risk-on';
  if (comparisonGaps.length) direction = 'unverified';

  return {
    timestamp: current.meta?.timestamp || new Date().toISOString(),
    previous: previous.meta?.timestamp || null,
    signals,
    comparisonGaps,
    summary: {
      totalChanges: signals.new.length + signals.escalated.length + signals.deescalated.length,
      criticalChanges,
      direction,
      signalBreakdown: {
        new: signals.new.length,
        escalated: signals.escalated.length,
        deescalated: signals.deescalated.length,
        unchanged: signals.unchanged.length,
      },
    },
  };
}

// Export thresholds for external config
export { DEFAULT_NUMERIC_THRESHOLDS, DEFAULT_COUNT_THRESHOLDS };
