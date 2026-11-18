#!/usr/bin/env node
// Crucix Dashboard Data Synthesizer
// Reads runs/latest.json, fetches RSS news, generates signal-based ideas,
// and injects everything into dashboard/public/jarvis.html
//
// Exports synthesize(), generateIdeas(), fetchAllNews() for use by server.mjs

import { existsSync, readFileSync, readdirSync, writeFileSync } from 'fs';
import { dirname, join } from 'path';
import { fileURLToPath } from 'url';
import { exec } from 'child_process';
import config from '../crucix.config.mjs';
import { createLLMProvider } from '../lib/llm/index.mjs';
import { generateLLMIdeas } from '../lib/llm/ideas.mjs';
import { energySnapshot, energySignalObservation, energySpotChange, energyObservationDate } from './energy.mjs';
import { collectNewsSources } from './rss-cache.mjs';
import { sourceHealth, sourceOutcome } from '../apis/utils/source-health.mjs';
import { fredSignalObservation } from '../apis/utils/fred-signals.mjs';
import { countObservation } from '../lib/delta/count-observations.mjs';
import { blsSignalObservation, blsMonthlyChange, METAL_SIGNAL_SERIES, gscpiSignalObservation } from '../apis/utils/economic-signals.mjs';

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = join(__dirname, '..');

// === Helpers ===
const cyrillic = /[\u0400-\u04FF]/;
function isEnglish(text) {
  if (!text) return false;
  return !cyrillic.test(text.substring(0, 80));
}

// === Geo-tagging keyword map ===
const geoKeywords = {
  'Ukraine':[49,32],'Russia':[56,38],'Moscow':[55.7,37.6],'Kyiv':[50.4,30.5],
  'China':[35,105],'Beijing':[39.9,116.4],'Iran':[32,53],'Tehran':[35.7,51.4],
  'Israel':[31.5,35],'Gaza':[31.4,34.4],'Palestine':[31.9,35.2],
  'Syria':[35,38],'Iraq':[33,44],'Saudi':[24,45],'Yemen':[15,48],'Lebanon':[34,36],
  'India':[20,78],'Japan':[36,138],'Korea':[37,127],'Pyongyang':[39,125.7],
  'Taiwan':[23.5,121],'Philippines':[13,122],'Myanmar':[20,96],
  'Canada':[56,-96],'Mexico':[23,-102],'Brazil':[-14,-51],'Argentina':[-38,-63],
  'Colombia':[4,-74],'Venezuela':[7,-66],'Cuba':[22,-80],'Chile':[-35,-71],
  'Germany':[51,10],'France':[46,2],'UK':[54,-2],'Britain':[54,-2],'London':[51.5,-0.1],
  'Spain':[40,-4],'Italy':[42,12],'Poland':[52,20],'NATO':[50,4],'EU':[50,4],
  'Turkey':[39,35],'Greece':[39,22],'Romania':[46,25],'Finland':[64,26],'Sweden':[62,15],
  'Africa':[0,20],'Nigeria':[10,8],'South Africa':[-30,25],'Kenya':[-1,38],
  'Egypt':[27,30],'Libya':[27,17],'Sudan':[13,30],'Ethiopia':[9,38],
  'Somalia':[5,46],'Congo':[-4,22],'Uganda':[1,32],'Morocco':[32,-6],
  'Pakistan':[30,70],'Afghanistan':[33,65],'Bangladesh':[24,90],
  'Australia':[-25,134],'Indonesia':[-2,118],'Thailand':[15,100],
  'US':[39,-98],'America':[39,-98],'Washington':[38.9,-77],'Pentagon':[38.9,-77],
  'Trump':[38.9,-77],'White House':[38.9,-77],
  'Wall Street':[40.7,-74],'New York':[40.7,-74],'California':[37,-120],
  'Nepal':[28,84],'Cambodia':[12.5,105],'Malawi':[-13.5,34],'Burundi':[-3.4,29.9],
  'Oman':[21,57],'Netherlands':[52.1,5.3],'Gabon':[-0.8,11.6],
  'Peru':[-10,-76],'Ecuador':[-2,-78],'Bolivia':[-17,-65],
  'Singapore':[1.35,103.8],'Malaysia':[4.2,101.9],'Vietnam':[16,108],
  'Algeria':[28,3],'Tunisia':[34,9],'Zimbabwe':[-20,30],'Mozambique':[-18,35],
  // Americas expansion
  'Texas':[31,-100],'Florida':[28,-82],'Chicago':[41.9,-87.6],'Los Angeles':[34,-118],
  'San Francisco':[37.8,-122.4],'Seattle':[47.6,-122.3],'Miami':[25.8,-80.2],
  'Toronto':[43.7,-79.4],'Ottawa':[45.4,-75.7],'Vancouver':[49.3,-123.1],
  'São Paulo':[-23.5,-46.6],'Rio':[-22.9,-43.2],'Buenos Aires':[-34.6,-58.4],
  'Bogotá':[4.7,-74.1],'Lima':[-12,-77],'Santiago':[-33.4,-70.7],
  'Caracas':[10.5,-66.9],'Havana':[23.1,-82.4],'Panama':[9,-79.5],
  'Guatemala':[14.6,-90.5],'Honduras':[14.1,-87.2],'El Salvador':[13.7,-89.2],
  'Costa Rica':[10,-84],'Jamaica':[18.1,-77.3],'Haiti':[19,-72],
  'Dominican':[18.5,-70],'Puerto Rico':[18.2,-66.5],
  // More Asia-Pacific
  'Sri Lanka':[7,80],'Hong Kong':[22.3,114.2],'Taipei':[25,121.5],
  'Seoul':[37.6,127],'Osaka':[34.7,135.5],'Mumbai':[19.1,72.9],
  'Delhi':[28.6,77.2],'Shanghai':[31.2,121.5],'Shenzhen':[22.5,114.1],
  'Auckland':[-36.8,174.8],'Papua New Guinea':[-6.3,147],
  // More Europe
  'Berlin':[52.5,13.4],'Paris':[48.9,2.3],'Madrid':[40.4,-3.7],
  'Rome':[41.9,12.5],'Warsaw':[52.2,21],'Prague':[50.1,14.4],
  'Vienna':[48.2,16.4],'Budapest':[47.5,19.1],'Bucharest':[44.4,26.1],
  'Kyiv':[50.4,30.5],'Oslo':[59.9,10.7],'Copenhagen':[55.7,12.6],
  'Brussels':[50.8,4.4],'Zurich':[47.4,8.5],'Dublin':[53.3,-6.3],
  'Lisbon':[38.7,-9.1],'Athens':[37.9,23.7],'Minsk':[53.9,27.6],
  // More Africa
  'Nairobi':[-1.3,36.8],'Lagos':[6.5,3.4],'Accra':[5.6,-0.2],
  'Addis Ababa':[9,38.7],'Cape Town':[-33.9,18.4],'Johannesburg':[-26.2,28],
  'Kinshasa':[-4.3,15.3],'Khartoum':[15.6,32.5],'Mogadishu':[2.1,45.3],
  'Dakar':[14.7,-17.5],'Abuja':[9.1,7.5],
  // Tech/Economy keywords with US locations
  'Fed':[38.9,-77],'Congress':[38.9,-77],'Senate':[38.9,-77],
  'Silicon Valley':[37.4,-122],'NASA':[28.6,-80.6],'Pentagon':[38.9,-77],
  'IMF':[38.9,-77],'World Bank':[38.9,-77],'UN':[40.7,-74],
};

function geoTagText(text) {
  if (!text) return null;
  // Longest phrase first (South Africa before Africa); never match US inside
  // BUSINESS or UN inside FUNDING. This is a topic hint, not geolocation.
  for (const [keyword, [lat, lon]] of Object.entries(geoKeywords).sort((a, b) => b[0].length - a[0].length)) {
    const flags = /^[A-Z]+$/.test(keyword) ? 'u' : 'iu';
    const pattern = new RegExp(`(?<![\\p{L}\\p{N}])${keyword}(?![\\p{L}\\p{N}])`, flags);
    if (pattern.test(text)) {
      return { lat, lon, region: keyword };
    }
  }
  return null;
}

function sanitizeExternalUrl(raw) {
  if (!raw) return undefined;
  try {
    const url = new URL(raw);
    return url.protocol === 'http:' || url.protocol === 'https:' ? url.toString() : undefined;
  } catch {
    return undefined;
  }
}

function sumAirHotspots(hotspots = []) {
  return hotspots.reduce((sum, hotspot) => sum + (hotspot.totalAircraft || 0), 0);
}

function summarizeAirHotspots(hotspots = []) {
  return hotspots.map(h => ({
    key: h.key || null,
    region: h.region,
    status: h.status || (h.error ? 'error' : 'unknown'),
    total: !h.error && Number.isFinite(h.totalAircraft) ? h.totalAircraft : null,
    noCallsign: !h.error && Number.isFinite(h.noCallsign) ? h.noCallsign : null,
    highAlt: !h.error && Number.isFinite(h.highAltitude) ? h.highAltitude : null,
    observedAt: h.observedAt || null,
    ...referenceLocation(h, 'query-bounds-center'),
    top: Object.entries(h.byCountry || {}).sort((a, b) => b[1] - a[1]).slice(0, 5),
  }));
}

function referenceLocation(row, basis) {
  const valid = row.geoBasis === basis && Number.isFinite(row.latitude) && Math.abs(row.latitude) <= 90
    && Number.isFinite(row.longitude) && Math.abs(row.longitude) <= 180;
  return { lat: valid ? row.latitude : null, lon: valid ? row.longitude : null, geoBasis: valid ? basis : 'unlocated' };
}

function loadOpenSkyFallback(currentTimestamp) {
  const runsDir = config.runsDir;
  if (!existsSync(runsDir)) return null;

  const currentMs = currentTimestamp ? new Date(currentTimestamp).getTime() : NaN;
  const files = readdirSync(runsDir)
    .filter(name => /^briefing_.*\.json$/.test(name))
    .sort()
    .reverse();

  for (const file of files) {
    const filePath = join(runsDir, file);
    try {
      const prior = JSON.parse(readFileSync(filePath, 'utf8'));
      const priorTimestamp = prior.sources?.OpenSky?.timestamp || prior.crucix?.timestamp || null;
      if (priorTimestamp && Number.isFinite(currentMs) && new Date(priorTimestamp).getTime() >= currentMs) continue;

      const hotspots = prior.sources?.OpenSky?.hotspots || [];
      if (sumAirHotspots(hotspots) > 0) {
        return { file, timestamp: priorTimestamp, hotspots };
      }
    } catch {
      // Ignore unreadable historical runs and continue searching backward.
    }
  }

  return null;
}


const REGIONAL_NEWS_SOURCES = ['MercoPress', 'Indian Express', 'The Hindu', 'SBS Australia'];

export const DEFAULT_NEWS_FEEDS = [
    // Global
    ['http://feeds.bbci.co.uk/news/world/rss.xml', 'BBC'],
    ['https://rss.nytimes.com/services/xml/rss/nyt/World.xml', 'NYT'],
    ['https://www.aljazeera.com/xml/rss/all.xml', 'Al Jazeera'],
    // USA
    ['https://feeds.npr.org/1001/rss.xml', 'NPR'],
    ['https://feeds.bbci.co.uk/news/technology/rss.xml', 'BBC Tech'],
    ['http://feeds.bbci.co.uk/news/science_and_environment/rss.xml', 'BBC Science'],
    ['https://rss.nytimes.com/services/xml/rss/nyt/Americas.xml', 'NYT Americas'],
    // Europe
    ['https://rss.dw.com/rdf/rss-en-all', 'DW'],
    ['https://www.france24.com/en/rss', 'France 24'],
    ['https://www.euronews.com/rss?format=mrss', 'Euronews'],
    // Africa & Cameroon region
    ['https://rss.dw.com/rdf/rss-en-africa', 'DW Africa'],
    ['https://www.rfi.fr/en/rss', 'RFI'],
    ['https://www.africanews.com/feed/rss', 'Africa News'],
    ['https://rss.nytimes.com/services/xml/rss/nyt/Africa.xml', 'NYT Africa'],
    // Asia-Pacific
    ['https://rss.nytimes.com/services/xml/rss/nyt/AsiaPacific.xml', 'NYT Asia'],
    ['https://www.sbs.com.au/news/topic/australia/feed', 'SBS Australia'],
    // India
    ['https://indianexpress.com/section/india/feed/', 'Indian Express'],
    ['https://www.thehindu.com/news/national/feeder/default.rss', 'The Hindu'],
    // South America
    ['https://en.mercopress.com/rss/latin-america', 'MercoPress'],
  ];

export async function fetchNewsResult(feeds = DEFAULT_NEWS_FEEDS, options = {}) {
  const { results, cache, mode } = await collectNewsSources(feeds, options);
  const allNews = results.flatMap(r => (r.items || []).map(item => ({ ...item,
    collectedAt: r.dataAsOf, cached: r.cached, sourceStatus: r.status })));

  // De-duplicate and geo-tag
  const seen = new Set();
  const geoNews = [];
  const keyFor = item => JSON.stringify([item.source, item.url || item.title, item.date]);
  for (const item of allNews) {
    const key = keyFor(item);
    if (seen.has(key)) continue;
    seen.add(key);
    const geo = geoTagText(item.title);
    geoNews.push({
      title: item.title,
      source: item.source,
      date: item.date,
      url: item.url,
      collectedAt: item.collectedAt,
      cached: item.cached,
      sourceStatus: item.sourceStatus,
      lat: geo?.lat ?? null,
      lon: geo?.lon ?? null,
      region: geo?.region ?? 'Global',
      geoBasis: geo ? 'headline-keyword' : 'unlocated'
    });
  }

  const cutoff = new Date(Date.now() - 30 * 24 * 60 * 60 * 1000);
  const filtered = geoNews.filter(n => !n.date || new Date(n.date) >= cutoff);
  filtered.sort((a, b) => new Date(b.date || 0) - new Date(a.date || 0));

  const selected = [];
  const selectedKeys = new Set();
  const pushUnique = item => {
    const key = keyFor(item);
    if (selectedKeys.has(key)) return;
    selected.push(item);
    selectedKeys.add(key);
  };

  // Reserve a little space so newly-added regional feeds are not crowded out by larger globals.
  for (const source of REGIONAL_NEWS_SOURCES) {
    filtered.filter(item => item.source === source).slice(0, 2).forEach(pushUnique);
  }
  filtered.forEach(pushUnique);
  const news = selected.slice(0, 50).map(item => ({ ...item, title: item.title.slice(0, 300) }));
  const coverage = {
    requested: results.length,
    succeeded: results.filter(r => r.status === 'ok').length,
    partial: results.filter(r => r.status === 'partial').length,
    failed: results.filter(r => r.status === 'error').length,
  };
  const cachedSources = results.filter(r => r.cached).length;
  const status = !results.length ? 'unknown' : coverage.succeeded === results.length && !cachedSources && cache.status !== 'error' ? 'ok'
    : coverage.succeeded + coverage.partial + cachedSources > 0 ? 'partial' : 'error';
  const asOf = results.map(r => r.asOf).filter(Boolean).sort().at(-1) || null;
  return { news, meta: { status, asOf, coverage, cachedSources, cache, mode,
    selection: 'regional-reserve-30d-url-v2',
    displayedCount: news.length, eligibleCount: filtered.length, limit: 50,
    items: results.map(({ items, ...summary }) => summary) } };
}

// Existing callers retain the array API; synthesis uses the coverage-aware result.
export async function fetchAllNews() {
  return (await fetchNewsResult()).news;
}

// === Leverageable Ideas from Signals ===
export function generateIdeas(V2, { now = new Date() } = {}) {
  const ideas = [];
  const signal = id => fredSignalObservation(V2.fred.find(f => f.id === id), { now });
  const vix = signal('VIXCLS');
  const hy = signal('BAMLH0A0HYM2');
  const spread = signal('T10Y2Y');

  const wti = energySignalObservation(V2.energy?.observations?.find(row => row.id === 'wti'), { now });
  const urgentSample = countObservation(V2, 'urgent_posts', now);
  if (urgentSample?.value > 3 && wti && wti.value > 68) {
    ideas.push({
      title: 'Conflict-Energy Nexus Active',
      text: `${V2.tg.urgent.length} urgent OSINT samples and WTI ${wti.kind} at ${wti.value} ${wti.unit} (${energyObservationDate(wti)}, ${wti.source.id}/${wti.source.seriesId}). Co-occurrence does not establish causality, a risk premium or a directional trade.`,
      type: 'watch', confidence: 'Medium', horizon: 'swing'
    });
  }
  if (vix && vix.value > 20) {
    ideas.push({
      title: 'Elevated Volatility Regime',
      text: `${vix.date}: VIX at ${vix.value} — elevated volatility observation, not a forecast or proof of capped equity upside.`,
      type: 'hedge', confidence: vix.value > 25 ? 'High' : 'Medium', horizon: 'tactical'
    });
  }
  if (vix && vix.value > 20 && hy && hy.value > 3 && vix.date === hy.date) {
    ideas.push({
      title: 'Volatility and Credit Stress',
      text: `${vix.date}: VIX ${vix.value} + HY spread ${hy.value}% — joint stress observation; safe-haven demand and future outperformance are not established.`,
      type: 'hedge', confidence: 'Medium', horizon: 'tactical'
    });
  }
  const oilChange = energySpotChange(wti, { now });
  if (oilChange && Number.isFinite(oilChange.pctChange)) {
    const pct = oilChange.pctChange;
    if (Math.abs(pct) > 3) {
      ideas.push({
        title: pct > 0 ? 'Oil Momentum Building' : 'Oil Under Pressure',
        text: `${oilChange.fromDate} → ${oilChange.toDate}: WTI spot moved ${pct > 0 ? '+' : ''}${pct.toFixed(1)}% from ${oilChange.from} to ${oilChange.to} ${wti.unit} (${wti.source.id}/${wti.source.seriesId}). This dated sample does not establish demand, supply or future returns.`,
        type: 'watch', confidence: 'Medium', horizon: 'swing'
      });
    }
  }
  if (spread) {
    ideas.push({
      title: spread.value > 0 ? 'Positive Yield Spread' : spread.value < 0 ? 'Yield Curve Inverted' : 'Flat Yield Curve',
      text: `${spread.date}: 10Y-2Y spread at ${spread.value.toFixed(2)} percentage points. A single observation establishes the sign, not normalization, persistence or a recession forecast.`,
      type: 'watch', confidence: 'Medium', horizon: 'strategic'
    });
  }
  // A nominal debt level alone cannot justify a directional hard-asset trade.
  const thermalSample = countObservation(V2, 'thermal_total', now);
  if (thermalSample?.value > 30000 && urgentSample?.value > 2) {
    ideas.push({
      title: 'Thermal and OSINT Sample Review',
      text: `${thermalSample.value.toLocaleString()} thermal query-region samples (overlapping) + ${urgentSample.value} shown urgent OSINT samples. Neither confirms conflict intensity, thermal cause or defense procurement; independently verify locations and reports.`,
      type: 'watch', confidence: 'Medium', horizon: 'swing'
    });
  }

  // Yield Curve + Labor Interaction
  const unemployment = blsSignalObservation(V2.bls.find(b => b.id === 'LNS14000000'), { now });
  const payrolls = blsSignalObservation(V2.bls.find(b => b.id === 'CES0000000001'), { now });
  if (spread && unemployment && payrolls && unemployment.date === payrolls.date) {
    const payrollChange = blsMonthlyChange(payrolls, { now });
    const weakLabor = unemployment.value > 4.3 || (payrollChange && payrollChange.value < -50);
    if (spread.value > 0.3 && weakLabor) {
      ideas.push({
        title: 'Positive Spread with Weak Labor',
        text: `${spread.date}: 10Y-2Y at ${spread.value.toFixed(2)} percentage points + ${unemployment.date} UE ${unemployment.value}%. These different frequencies warrant review, not proof of curve steepening, recession or a hedge recommendation.`,
        type: 'watch', confidence: 'Medium', horizon: 'tactical'
      });
    }
  }

  // Bounded conflict samples do not establish an energy/defense trade or a causal transmission.

  // HY Spread + VIX Divergence
  if (hy && vix && hy.date === vix.date) {
    const hyWide = hy.value > 3.5;
    const vixLow = vix.value < 18;
    const hyTight = hy.value < 2.5;
    const vixHigh = vix.value > 25;
    if (hyWide && vixLow) {
      ideas.push({
        title: 'Credit Stress Ignored by Equity Vol',
        text: `${vix.date}: HY spread ${hy.value.toFixed(1)}% (wide) but VIX ${vix.value.toFixed(0)} (low). Different risk measures; possible divergence, not proof of equity mispricing.`,
        type: 'watch', confidence: 'Medium', horizon: 'tactical'
      });
    } else if (hyTight && vixHigh) {
      ideas.push({
        title: 'Equity Fear Exceeds Credit Stress',
        text: `${vix.date}: VIX at ${vix.value.toFixed(0)} but HY spread ${hy.value.toFixed(1)}%. Different risk measures; possible divergence, not proof of equity overshooting.`,
        type: 'watch', confidence: 'Medium', horizon: 'tactical'
      });
    }
  }

  // Supply Chain + Inflation Pipeline
  const ppi = blsSignalObservation(V2.bls.find(b => b.id === 'WPUFD49104'), { now });
  const cpi = blsSignalObservation(V2.bls.find(b => b.id === 'CUUR0000SA0'), { now });
  const supply = gscpiSignalObservation(V2.gscpi, { now });
  const ppiChange = blsMonthlyChange(ppi, { now });
  if (ppiChange && cpi && supply && ppi.date === cpi.date && ppi.date === supply.date) {
    const supplyPressure = supply.value > 0.5;
    const ppiRising = ppiChange.relative > 0.3;
    if (supplyPressure && ppiRising) {
      ideas.push({
        title: 'Supply Chain and Inflation Review',
        text: `${supply.date}: GSCPI ${supply.value.toFixed(2)} standard deviations (vintage ${supply.vintage}) and PPI adjacent change +${ppiChange.relative.toFixed(1)}% (NSA). Aligned observation periods do not establish release simultaneity, seasonally-adjusted momentum or causal pass-through to CPI.`,
        type: 'watch', confidence: 'Medium', horizon: 'strategic'
      });
    }
  }

  return ideas.slice(0, 8);
}

// === Synthesize raw sweep data into dashboard format ===
export async function synthesize(data, { refreshNews = true, newsCacheDir = null } = {}) {
  const liveAirHotspots = data.sources.OpenSky?.hotspots || [];
  const airFallback = liveAirHotspots.some(h => !h.error && Number.isFinite(h.totalAircraft))
    ? null
    : loadOpenSkyFallback(data.sources.OpenSky?.timestamp || data.crucix?.timestamp);
  const effectiveAirHotspots = airFallback?.hotspots || liveAirHotspots;
  const air = summarizeAirHotspots(effectiveAirHotspots);
  const thermal = (data.sources.FIRMS?.hotspots || []).map(h => ({
    region: h.region, det: h.error ? null : h.totalDetections ?? null, night: h.error ? null : h.nightDetections ?? null,
    hc: h.error ? null : h.highConfidence ?? null, status: h.error ? 'error' : h.status || 'unknown',
    error: h.error || null,
    fires: (h.highIntensity || []).slice(0, 8).map(f => ({ lat: f.lat, lon: f.lon, frp: f.frp || 0 }))
  }));
  const firmsData = data.sources.FIRMS;
  const thermalMeta = { status: firmsData ? sourceOutcome('FIRMS', firmsData).status : 'unknown',
    collectedAt: firmsData?.timestamp || null, scope: firmsData?.scope || null };
  const tSignals = data.sources.FIRMS?.signals || [];
  const chokepoints = Object.values(data.sources.Maritime?.chokepoints || {}).map(c => ({
    label: c.label || c.name, note: c.note || '', lat: c.lat || 0, lon: c.lon || 0
  }));
  const nuke = (data.sources.Safecast?.sites || []).map(s => ({
    site: s.site, key: s.key || null, anom: null,
    status: s.status || 'unknown', reason: s.reason || 'Legacy sample; radiation safety unassessed',
    cpm: s.deviceId != null && Number.isFinite(s.avgCPM) ? s.avgCPM : null,
    n: Number.isFinite(s.recentReadings) ? s.recentReadings : null,
    sampleReadings: Number.isFinite(s.sampleReadings) ? s.sampleReadings : null,
    deviceId: s.deviceId ?? null, observedAt: s.lastReading || null,
    windowStart: s.windowStart || null, windowEnd: s.windowEnd || null, sampleLimit: s.sampleLimit ?? null,
    radiusKm: s.radiusKm ?? null, measurements: s.measurements || [],
    ...referenceLocation(s, 'query-radius-center'),
  }));
  const nukeSignals = (data.sources.Safecast?.signals || []).filter(s => s);
  const sdrData = data.sources.KiwiSDR || {};
  const sdrNet = sdrData.network || {};
  const sdrConflict = sdrData.conflictZones || {};
  const sdrZones = Object.values(sdrConflict).map(z => ({
    region: z.region, count: z.count ?? null,
    receivers: (z.receivers || []).slice(0, 5).map(r => ({ name: r.name || '', lat: r.lat || 0, lon: r.lon || 0 }))
  }));
  const tgData = data.sources.Telegram || {};
  const tgWeb = ['web_scrape', 'bot_api_empty_fallback_scrape'].includes(tgData.status);
  const tgComplete = tgWeb && tgData.channels?.length > 0
    && tgData.channels.length === tgData.channelsMonitored && tgData.channelsMonitored === tgData.channelsReachable
    && tgData.channels.every(channel => channel.reachable === true);
  const tgScope = tgWeb && tgData.channels?.length ? { source: 'Telegram-web-preview',
    channels: tgData.channels.map(channel => channel.channel).sort(), limit: 15,
    selection: 'significance-order-exclude-cyrillic-v1' } : null;
  const tgUrgent = (tgData.urgentPosts || []).filter(p => isEnglish(p.text)).map(p => ({
    channel: p.channel, text: p.text?.substring(0, 200), views: p.views, date: p.date, urgentFlags: p.urgentFlags || []
  }));
  const tgTop = (tgData.topPosts || []).filter(p => isEnglish(p.text)).map(p => ({
    channel: p.channel, text: p.text?.substring(0, 200), views: p.views, date: p.date, urgentFlags: []
  }));
  const who = (data.sources.WHO?.diseaseOutbreakNews || []).slice(0, 10).map(w => ({
    title: w.title?.substring(0, 120), date: w.date, url: w.url, summary: w.summary?.substring(0, 150)
  }));
  const whoData = data.sources.WHO;
  const whoMeta = { status: whoData ? sourceOutcome('WHO', whoData).status : 'unknown',
    count: Number.isFinite(whoData?.outbreakCount) ? whoData.outbreakCount : null,
    collectedAt: whoData?.timestamp || null,
    window: whoData?.window || null, gaps: whoData?.gaps || {}, displayedCount: who.length };
  const fred = (data.sources.FRED?.indicators || []).map(f => ({
    id: f.id, label: f.label, value: f.value, date: f.date,
    recent: f.recent || [],
    momChange: f.momChange, momChangePct: f.momChangePct
  }));
  const energyData = data.sources.EIA || {};
  const energy = energySnapshot(energyData, data.sources.YFinance?.quotes);
  const bls = data.sources.BLS?.indicators || [];
  const treasuryData = data.sources.Treasury || {};
  const debtArr = treasuryData.debt || [];
  const treasury = { totalDebt: debtArr[0]?.totalDebt ?? null, date: debtArr[0]?.date || null,
    status: treasuryData.status || 'unknown', collectedAt: treasuryData.timestamp || null,
    debt: debtArr, interestRates: treasuryData.interestRates || [], coverage: treasuryData.coverage || null,
    debtUrl: treasuryData.debtUrl || null, ratesUrl: treasuryData.ratesUrl || null,
    note: treasuryData.note || null, signals: treasuryData.signals || [] };
  const gscpiData = data.sources.GSCPI;
  const gscpi = gscpiData ? { ...gscpiData.latest,
    status: gscpiData.error ? 'error' : gscpiData.status || 'unknown',
    vintage: gscpiData.latest?.vintage ?? gscpiData.vintage ?? null,
    collectedAt: gscpiData.timestamp ?? null,
    rejected: gscpiData.rejected ?? null, missing: gscpiData.missing ?? null,
    history: Array.isArray(gscpiData.history) ? gscpiData.history : [] } : null;
  const defense = (data.sources.USAspending?.recentDefenseContracts || []).slice(0, 5).map(c => ({
    recipient: c.recipient?.substring(0, 40), amount: c.amount, desc: c.description?.substring(0, 80)
  }));
  const weather = data.sources.NOAA || {};
  const noaa = {
    status: weather.status || (weather.error ? 'error' : 'unknown'),
    totalAlerts: Number.isFinite(weather.totalSevereAlerts) ? weather.totalSevereAlerts : null,
    collectedAt: weather.timestamp || null, updatedAt: weather.updatedAt || null,
    coverage: weather.coverage || null, error: weather.error || null,
    errorCode: weather.errorCode || null, httpStatus: weather.httpStatus || null,
    alerts: (weather.topAlerts || []).slice(0, 50).map(a => ({
      id: a.id, url: a.url, event: a.event, severity: a.severity, headline: a.headline?.substring(0, 300),
      areas: a.areas, sent: a.sent, effective: a.effective, onset: a.onset, expires: a.expires,
      lat: a.lat, lon: a.lon, geoBasis: a.geoBasis
    }))
  };

  // EPA RadNet — pass through geo-tagged readings
  const epaData = data.sources.EPA || {};
  const epaStations = [];
  const seenEpa = new Set();
  for (const r of (epaData.readings || [])) {
    if (r.lat == null || r.lon == null) continue;
    const key = `${r.lat},${r.lon}`;
    if (seenEpa.has(key)) continue;
    seenEpa.add(key);
    epaStations.push({ location: r.location, state: r.state, lat: r.lat, lon: r.lon, analyte: r.analyte, result: r.result, unit: r.unit });
  }
  const epa = { totalReadings: epaData.totalReadings || 0, stations: epaStations.slice(0, 10) };

  // Space/CelesTrak satellite data
  const spaceData = data.sources.Space || {};
  // Approximate subsatellite position from TLE orbital elements
  function estimateSatPosition(sat) {
    if (!sat?.inclination || !sat?.epoch) return null;
    const epoch = new Date(sat.epoch);
    const now = new Date();
    const elapsed = (now - epoch) / 1000;
    const period = (sat.period || 92.7) * 60; // minutes to seconds
    const orbits = elapsed / period;
    const frac = orbits % 1;
    const lat = sat.inclination * Math.sin(frac * 2 * Math.PI);
    const lonShift = (elapsed / 86400) * 360;
    const orbitLon = frac * 360;
    const lon = ((orbitLon - lonShift) % 360 + 540) % 360 - 180;
    return { lat: +lat.toFixed(2), lon: +lon.toFixed(2), name: sat.name };
  }
  const issPos = estimateSatPosition(spaceData.iss);
  const spaceStations = (spaceData.spaceStations || []).map(s => estimateSatPosition(s)).filter(Boolean);
  const space = {
    totalNewObjects: spaceData.totalNewObjects || 0,
    militarySats: spaceData.militarySatellites || 0,
    militaryByCountry: spaceData.militaryByCountry || {},
    constellations: spaceData.constellations || {},
    iss: spaceData.iss || null,
    issPosition: issPos,
    stationPositions: spaceStations.slice(0, 5),
    recentLaunches: (spaceData.recentLaunches || []).slice(0, 10).map(l => ({
      name: l.name, country: l.country, epoch: l.epoch,
      apogee: l.apogee, perigee: l.perigee, type: l.objectType
    })),
    launchByCountry: spaceData.launchByCountry || {},
    signals: spaceData.signals || [],
  };

  // ACLED conflict events
  const acledData = data.sources.ACLED || {};
  const acledKnown = ['ok', 'partial'].includes(acledData.status) && acledData.basis === 'bounded-event-sample';
  const acled = {
    status: acledData.status || 'unknown', basis: acledData.basis || null,
    period: acledData.period || null, collectedAt: acledData.timestamp || null,
    sampleLimit: acledData.sampleLimit ?? null,
    coverage: acledData.coverage || null, errorCode: acledData.errorCode || null, httpStatus: acledData.httpStatus || null,
    totalEvents: acledKnown ? acledData.totalEvents ?? null : null,
    totalFatalities: acledKnown ? acledData.totalFatalities ?? null : null,
    byRegion: acledKnown ? acledData.byRegion || {} : {},
    byType: acledKnown ? acledData.byType || {} : {},
    deadliestEvents: acledKnown ? (acledData.deadliestEvents || []).slice(0, 15).map(e => ({
      id: e.id, date: e.date, type: e.type, country: e.country, location: e.location,
      fatalities: e.fatalities ?? null, lat: e.lat ?? null, lon: e.lon ?? null
    })) : [],
  };

  // GDELT news articles + geo events
  const gdeltData = data.sources.GDELT || {};
  const articlesKnown = Number.isFinite(gdeltData.totalArticles);
  const gdelt = {
    totalArticles: articlesKnown ? gdeltData.totalArticles : null,
    conflicts: articlesKnown ? (gdeltData.conflicts || []).length : null,
    economy: articlesKnown ? (gdeltData.economy || []).length : null,
    health: articlesKnown ? (gdeltData.health || []).length : null,
    crisis: articlesKnown ? (gdeltData.crisis || []).length : null,
    coverage: gdeltData.coverage || null,
    gaps: gdeltData.gaps || {},
    topTitles: (gdeltData.allArticles || []).slice(0, 5).map(a => a.title?.substring(0, 80)),
    geoPoints: (gdeltData.geoPoints || []).slice(0, 20).map(p => ({
      lat: p.lat, lon: p.lon, name: (p.name || '').substring(0, 80), count: p.count ?? null
    }))
  };

  const { health, counts } = sourceHealth(data);

  // === Yahoo Finance quotes (observation time is distinct from collection time) ===
  const yfData = data.sources.YFinance || {};
  const yfQuotes = yfData.quotes || {};
  const marketQuote = q => ({
    symbol: q.symbol, name: q.name, price: q.price,
    change: q.change ?? null, changePct: q.changePct ?? null,
    currency: q.currency ?? null, observedAt: q.observedAt ?? null,
    prevClose: q.prevClose ?? null, previousCloseBasis: q.previousCloseBasis ?? null,
    history: q.history || [],
  });
  const markets = {
    indexes: (yfData.indexes || []).map(marketQuote),
    rates: (yfData.rates || []).map(marketQuote),
    commodities: (yfData.commodities || []).map(marketQuote),
    crypto: (yfData.crypto || []).map(marketQuote),
    vix: !yfQuotes['^VIX']?.error && Number.isFinite(yfQuotes['^VIX']?.price) ? {
      value: yfQuotes['^VIX'].price,
      change: yfQuotes['^VIX'].change,
      changePct: yfQuotes['^VIX'].changePct,
      observedAt: yfQuotes['^VIX'].observedAt ?? null,
    } : null,
    timestamp: yfData.summary?.timestamp || null,
  };

  const yfGold = yfQuotes['GC=F'];
  const yfSilver = yfQuotes['SI=F'];
  const metals = {
    gold: yfGold?.price,
    goldChange: yfGold?.change,
    goldChangePct: yfGold?.changePct,
    goldRecent: yfGold?.history?.map(h => h.close) || [],
    silver: yfSilver?.price,
    silverChange: yfSilver?.change,
    silverChangePct: yfSilver?.changePct,
    silverRecent: yfSilver?.history?.map(h => h.close) || [],
    observations: Object.entries(METAL_SIGNAL_SERIES).map(([id, symbol]) => {
      const quote = yfQuotes[symbol];
      return { id, value: !quote?.error && Number.isFinite(quote?.price) ? quote.price : null,
        kind: 'futures', frequency: 'quote', unit: quote?.currency === 'USD' ? 'USD/troy-ounce' : null,
        prevClose: Number.isFinite(quote?.prevClose) ? quote.prevClose : null,
        previousCloseBasis: quote?.previousCloseBasis || null,
        observedAt: quote?.observedAt || null, source: { id: 'YFinance', seriesId: symbol,
          url: `https://finance.yahoo.com/quote/${encodeURIComponent(symbol)}/` },
        note: 'Continuous futures quote, not spot or physical metal; may be delayed and may roll.' };
    }),
  };

  // Fetch RSS
  const rss = await fetchNewsResult(DEFAULT_NEWS_FEEDS, { refresh: refreshNews, cacheDir: newsCacheDir });
  const news = rss.news;

  const ofacData = data.sources.OFAC;
  const ofacList = ofacData?.sdnList || {};
  const ofacOutcome = sourceOutcome('OFAC', ofacData);
  // List metadata only: file-order examples are not new designation events.
  const ofac = ofacData ? {
    ...ofacOutcome, collectedAt: ofacData.timestamp || null,
    reason: ofacList.reason ? ofacList.reason + (ofacList.httpStatus ? `（HTTP ${ofacList.httpStatus}）` : '') : ofacOutcome.reason,
    sdnList: Object.fromEntries(['publishDate', 'entryCount', 'recordCount', 'countBasis',
      'complete', 'dataAvailable'].map(key => [key, ofacList[key] ?? null])),
  } : null;

  const V2 = {
    meta: { ...data.crucix, ...counts }, air, thermal, thermalMeta, tSignals, chokepoints, nuke, nukeSignals,
    airMeta: {
      fallback: Boolean(airFallback),
      liveTotal: liveAirHotspots.length && liveAirHotspots.every(h => !h.error && Number.isFinite(h.totalAircraft))
        ? sumAirHotspots(liveAirHotspots) : null,
      countBasis: 'overlapping-query-regions',
      timestamp: airFallback?.timestamp || data.sources.OpenSky?.timestamp || null,
      source: airFallback ? 'OpenSky fallback' : 'OpenSky',
      scope: liveAirHotspots.length && liveAirHotspots.every(row => row.bounds) ? {
        source: 'OpenSky', regions: liveAirHotspots.map(row => ({ region: row.region, bounds: row.bounds })) } : null,
      ...(airFallback ? { fallbackFile: airFallback.file } : {}),
      ...(data.sources.OpenSky?.error ? { error: data.sources.OpenSky.error } : {}),
    },
    sdr: { total: sdrNet.totalReceivers ?? null, online: null, basis: 'directory-only',
      collectedAt: sdrData.timestamp || null, zones: sdrZones },
    tg: { posts: tgData.totalPosts ?? tgData.totalMessages ?? null, urgent: tgUrgent, topPosts: tgTop,
      status: tgComplete ? 'ok' : tgWeb ? 'partial' : 'unknown', collectedAt: tgData.timestamp || null, scope: tgScope },
    who, whoMeta, fred, energy, metals, bls, treasury, gscpi, defense, noaa, epa, acled, gdelt, space, health, news, ofac,
    newsMeta: rss.meta,
    markets, // Live Yahoo Finance market data
    ideas: [], ideasSource: 'disabled',
    // Official bulletins retain publication dates; HDX datasets are not news reports.
    newsFeed: buildNewsFeed(news, gdeltData, tgUrgent, tgTop, [
      ...(whoData?.diseaseOutbreakNews || []).map(item => ({ ...item, source: 'WHO', type: 'who' })),
      ...(data.sources.ReliefWeb?.latestReports || []).map(item => ({ ...item, source: 'ReliefWeb', type: 'reliefweb' })),
    ]),
  };

  return V2;
}

// === Unified News Feed for Ticker ===
export function buildNewsFeed(rssNews, gdeltData, tgUrgent, tgTop, officialNews = []) {
  const feed = [];

  // RSS news
  for (const n of rssNews) {
    feed.push({
      headline: n.title, source: n.source, type: 'rss',
      timestamp: n.date, region: n.region, urgent: false, url: n.url,
      collectedAt: n.collectedAt, cached: n.cached, sourceStatus: n.sourceStatus
    });
  }

  for (const item of officialNews) {
    const published = Date.parse(item.date);
    if (!item.title || !Number.isFinite(published) || published > Date.now()) continue;
    feed.push({ headline: item.title.substring(0, 100), source: item.source, type: item.type,
      timestamp: new Date(published).toISOString(), timestampBasis: 'published',
      region: 'Global', urgent: false, url: sanitizeExternalUrl(item.url) });
  }

  // GDELT top articles
  for (const a of (gdeltData.allArticles || []).slice(0, 10)) {
    if (a.title) {
      const geo = geoTagText(a.title);
      // GDELT seendate is an indexing time, not the article's publication date.
      const date = typeof a.date === 'string' ? a.date.replace(/^(\d{4})(\d{2})(\d{2})T(\d{2})(\d{2})(\d{2})Z$/, '$1-$2-$3T$4:$5:$6Z') : '';
      const indexedAt = Date.parse(date);
      feed.push({
        headline: a.title.substring(0, 100), source: 'GDELT', type: 'gdelt',
        timestamp: Number.isFinite(indexedAt) ? new Date(indexedAt).toISOString() : null,
        timestampBasis: Number.isFinite(indexedAt) ? 'indexed' : 'unknown',
        region: geo?.region || 'Global', urgent: false, url: sanitizeExternalUrl(a.url)
      });
    }
  }

  // Telegram urgent
  for (const p of tgUrgent.slice(0, 10)) {
    const text = (p.text || '').replace(/[\u{1F1E0}-\u{1F1FF}]/gu, '').trim();
    feed.push({
      headline: text.substring(0, 100), source: p.channel?.toUpperCase() || 'TELEGRAM',
      type: 'telegram', timestamp: p.date, region: 'OSINT', urgent: true
    });
  }

  // Telegram top (non-urgent)
  for (const p of tgTop.slice(0, 5)) {
    const text = (p.text || '').replace(/[\u{1F1E0}-\u{1F1FF}]/gu, '').trim();
    feed.push({
      headline: text.substring(0, 100), source: p.channel?.toUpperCase() || 'TELEGRAM',
      type: 'telegram', timestamp: p.date, region: 'OSINT', urgent: false
    });
  }

  // Filter to last 30 days, sort by timestamp descending, limit to 50
  const cutoff = new Date(Date.now() - 30 * 24 * 60 * 60 * 1000);
  const recent = feed.filter(item => !item.timestamp || new Date(item.timestamp) >= cutoff);
  recent.sort((a, b) => new Date(b.timestamp || 0) - new Date(a.timestamp || 0));

  const selected = [];
  const selectedKeys = new Set();
  const keyFor = item => JSON.stringify([item.type, item.source, item.url || item.headline, item.timestamp]);
  const pushUnique = item => {
    const key = keyFor(item);
    if (selectedKeys.has(key)) return;
    selected.push(item);
    selectedKeys.add(key);
  };

  for (const source of REGIONAL_NEWS_SOURCES) {
    recent.filter(item => item.source === source).slice(0, 2).forEach(pushUnique);
  }
  recent.forEach(pushUnique);
  return selected.slice(0, 50);
}

// === CLI Mode: inject into HTML file ===
function getCliArg(flag) {
  const idx = process.argv.indexOf(flag);
  return idx >= 0 ? process.argv[idx + 1] : null;
}

async function cliInject() {
  const data = JSON.parse(readFileSync(join(config.runsDir, 'latest.json'), 'utf8'));
  const htmlOverride = getCliArg('--html');
  const shouldOpen = !process.argv.includes('--no-open');

  console.log('Fetching RSS news feeds...');
  const V2 = await synthesize(data, { newsCacheDir: config.runsDir });
  const llmProvider = createLLMProvider(config.llm);

  if (llmProvider?.isConfigured) {
    try {
      console.log(`[LLM] Generating ideas via ${llmProvider.name}...`);
      const llmIdeas = await generateLLMIdeas(llmProvider, V2, null, []);
      if (llmIdeas?.length) {
        V2.ideas = llmIdeas;
        V2.ideasSource = 'llm';
        console.log(`[LLM] Generated ${llmIdeas.length} ideas`);
      } else {
        V2.ideas = [];
        V2.ideasSource = 'llm-failed';
        console.log('[LLM] No ideas returned');
      }
    } catch (err) {
      V2.ideas = [];
      V2.ideasSource = 'llm-failed';
      console.log('[LLM] Idea generation failed:', err.message);
    }
  } else {
    V2.ideas = [];
    V2.ideasSource = 'disabled';
  }
  console.log(`Generated ${V2.ideas.length} leverageable ideas`);

  const json = JSON.stringify(V2);
  console.log('\n--- Synthesis ---');
  console.log('Size:', json.length, 'bytes | Air:', V2.air.length, '| Thermal:', V2.thermal.length,
    '| News:', V2.news.length, '| Ideas:', V2.ideas.length, '| Sources:', V2.health.length);

  const htmlPath = htmlOverride || join(ROOT, 'dashboard/public/jarvis.html');
  let html = readFileSync(htmlPath, 'utf8');
  // Use a replacer function so JSON is inserted literally even if it contains `$`.
  html = html.replace(/^(let|const) D = .*;\s*$/m, () => 'let D = ' + json + ';');
  writeFileSync(htmlPath, html);
  console.log('Data injected into jarvis.html!');

  if (!shouldOpen) return;

  // Auto-open dashboard in default browser
  // NOTE: On Windows, `start` in PowerShell is an alias for Start-Service, not cmd's start.
  // We must use `cmd /c start ""` to ensure it works in both cmd.exe and PowerShell.
  const openCmd = process.platform === 'win32' ? 'cmd /c start ""' :
                  process.platform === 'darwin' ? 'open' : 'xdg-open';
  const dashUrl = htmlPath.replace(/\\/g, '/');
  exec(`${openCmd} "${dashUrl}"`, (err) => {
    if (err) console.log('Could not auto-open browser:', err.message);
    else console.log('Dashboard opened in browser!');
  });
}

// Run CLI if invoked directly
const isMain = process.argv[1]
  && fileURLToPath(import.meta.url).replace(/\\/g, '/') === process.argv[1].replace(/\\/g, '/');
if (isMain) {
  await cliInject();
}
