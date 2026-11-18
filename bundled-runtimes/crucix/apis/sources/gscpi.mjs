import { sourceFetch as fetch } from '../utils/source-request.mjs';
import { adjacentMonthPeriods, gscpiSignalObservation } from '../utils/economic-signals.mjs';

// GSCPI — NY Fed Global Supply Chain Pressure Index
// Measures global supply chain stress (standard deviations from historical average).
// Values above 0 = above average pressure. Above 1.0 = elevated. Below -1.0 = unusually loose.
// Data fetched directly from NY Fed — no API key required.

const GSCPI_CSV_URL = 'https://www.newyorkfed.org/medialibrary/research/interactives/data/gscpi/gscpi_interactive_data.csv';

// Fetch and parse the GSCPI CSV from the NY Fed
// The CSV is wide-format: each column is a revision vintage, last column is latest estimate.
// Uses raw fetch instead of safeFetch because safeFetch truncates non-JSON to 500 chars.
export async function getGSCPI(months = 12) {
  try {
    const signal = AbortSignal.timeout(20000);
    const res = await fetch(GSCPI_CSV_URL, {
      signal,
      headers: { 'User-Agent': 'Crucix/1.0' },
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const text = await res.text();
    return parseCSV(text, months);
  } catch (e) {
    return { error: e.message || 'Failed to fetch GSCPI data', data: [] };
  }
}

// Parse the wide-format CSV, extracting the latest vintage value for each date
function parseCSV(text, months) {
  const lines = text.trim().split('\n').filter(l => l.trim() && !l.startsWith(','));
  if (lines.length < 2) return { data: [], vintage: null, rejected: 0, missing: 0 };
  const header = lines[0].trim().replace(/^\uFEFF/, '').split(',').map(value => value.trim());
  const column = header.findLastIndex(value => value !== '');
  if (header[0] !== 'Date' || column < 1) return { data: [], vintage: null, rejected: 0, missing: 0 };
  const vintage = header[column], points = new Map();
  let rejected = 0, missing = 0;

  for (let i = 1; i < lines.length; i++) {
    const cols = lines[i].split(',');
    const dateStr = cols[0]?.trim();
    if (!dateStr) continue;

    // One common vintage for the entire history; never borrow an older column for a missing cell.
    const raw = cols[column]?.trim();
    if (!raw || raw === '#N/A') { missing++; continue; }
    const value = /^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:e[+-]?\d+)?$/i.test(raw) ? Number(raw) : null;

    // Parse date from "31-Jan-2026" format to "2026-01"
    const date = parseNYFedDate(dateStr);
    if (!date || !Number.isFinite(value) || date >= new Date().toISOString().slice(0, 7)) { rejected++; continue; }
    if (points.has(date) && points.get(date) !== value) { points.set(date, null); rejected++; }
    else if (!points.has(date)) points.set(date, value);
  }

  // Sort newest first
  const results = [...points].filter(([, value]) => value !== null).map(([date, value]) => ({ date, value, vintage }));
  results.sort((a, b) => b.date.localeCompare(a.date));
  return { data: results.slice(0, months), vintage, rejected, missing };
}

// Parse "31-Jan-2026" -> "2026-01"
function parseNYFedDate(str) {
  const months = {
    Jan: '01', Feb: '02', Mar: '03', Apr: '04', May: '05', Jun: '06',
    Jul: '07', Aug: '08', Sep: '09', Oct: '10', Nov: '11', Dec: '12',
  };
  const parts = str.split('-');
  if (parts.length !== 3) return null;
  const mon = months[parts[1]];
  const year = parts[2];
  if (!mon || !/^\d{4}$/.test(year) || !/^\d{1,2}$/.test(parts[0])) return null;
  const day = `${year}-${mon}-${parts[0].padStart(2, '0')}`, time = Date.parse(day);
  return Number.isFinite(time) && new Date(time).toISOString().slice(0, 10) === day ? `${year}-${mon}` : null;
}

// Detect trend from an array of {date, value} sorted newest-first
function detectTrend(history) {
  if (history.length < 3) return 'insufficient data';

  // Compare recent 3 months direction
  const recent = history.slice(0, 3);
  if (!adjacentMonthPeriods(recent[0].date, recent[1].date)
    || !adjacentMonthPeriods(recent[1].date, recent[2].date)) return 'insufficient data';
  let rising = 0;
  let falling = 0;

  for (let i = 0; i < recent.length - 1; i++) {
    // history is newest-first, so recent[0] is latest
    if (recent[i].value > recent[i + 1].value) rising++;
    else if (recent[i].value < recent[i + 1].value) falling++;
  }

  if (rising > falling) return 'rising';
  if (falling > rising) return 'falling';
  return 'stable';
}

// Briefing — latest GSCPI, trend, and signals
export async function briefing() {
  const result = await getGSCPI(12);

  if (result.error) {
    return {
      source: 'NY Fed GSCPI',
      error: result.error,
      timestamp: new Date().toISOString(),
    };
  }

  const history = result.data;
  const trend = detectTrend(history);
  const signals = [];

  const latest = history.length > 0 ? { ...history[0], unit: 'standard-deviations', frequency: 'monthly',
    source: { id: 'GSCPI', seriesId: 'GSCPI', url: GSCPI_CSV_URL } } : null;

  if (gscpiSignalObservation(latest)) {
    if (latest.value > 2.0) {
      signals.push(`GSCPI extremely elevated at ${latest.value.toFixed(2)} — severe supply chain stress`);
    } else if (latest.value > 1.0) {
      signals.push(`GSCPI elevated at ${latest.value.toFixed(2)} — above-normal supply chain pressure`);
    } else if (latest.value < -1.0) {
      signals.push(`GSCPI at ${latest.value.toFixed(2)} — unusually loose supply chains`);
    }

    if (trend === 'rising' && latest.value > 0) {
      signals.push('Supply chain pressure trending higher');
    }
    if (trend === 'falling' && latest.value > 1.0) {
      signals.push('Supply chain pressure elevated but improving');
    }
  }

  // Check month-over-month change
  if (gscpiSignalObservation(latest) && history.length >= 2 && adjacentMonthPeriods(history[0].date, history[1].date)) {
    const mom = history[0].value - history[1].value;
    if (Math.abs(mom) > 0.5) {
      const dir = mom > 0 ? 'surged' : 'dropped';
      signals.push(`GSCPI ${dir} ${Math.abs(mom).toFixed(2)} points month-over-month`);
    }
  }

  return {
    source: 'NY Fed GSCPI',
    status: !latest ? 'no_data' : result.rejected || result.missing ? 'partial' : 'ok',
    vintage: result.vintage, rejected: result.rejected, missing: result.missing,
    timestamp: new Date().toISOString(),
    latest: latest ? {
      ...latest,
      interpretation: latest.value > 1.0 ? 'elevated' :
                      latest.value > 0 ? 'above average' :
                      latest.value === 0 ? 'historical average' :
                      latest.value > -1.0 ? 'below average' : 'unusually loose',
    } : null,
    trend,
    history,
    signals,
  };
}

if (process.argv[1]?.endsWith('gscpi.mjs')) {
  const data = await briefing();
  console.log(JSON.stringify(data, null, 2));
}
