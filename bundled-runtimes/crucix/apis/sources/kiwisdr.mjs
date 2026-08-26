// KiwiSDR Network — Global software-defined radio receiver network
// No auth required. ~900 public HF receivers worldwide (0-30 MHz).
// Useful for SIGINT awareness: HF band activity, receiver distribution,
// detecting unusual radio configurations in conflict zones.
// Data source: receiverbook.de (embeds full receiver list as JS variable)

import { safeFetch } from '../utils/fetch.mjs';

const RECEIVERBOOK_URL = 'https://www.receiverbook.de/map?type=kiwisdr';

// Fetch the full list of public KiwiSDR receivers from receiverbook.de
export async function getAllReceivers() {
  try {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 20000);
    const res = await fetch(RECEIVERBOOK_URL, {
      headers: { 'User-Agent': 'Crucix/1.0' },
      signal: controller.signal,
    });
    clearTimeout(timer);
    if (!res.ok) return { error: `HTTP ${res.status}` };
    const html = await res.text();
    // Extract embedded JS: var receivers = [...];
    const match = html.match(/var\s+receivers\s*=\s*(\[[\s\S]*?\]);/);
    if (!match) return { error: 'Could not parse receiver data from page' };
    const sites = JSON.parse(match[1]);
    // Flatten: each site has a .receivers[] array of individual SDRs
    const flat = [];
    for (const site of sites) {
      const [lon, lat] = site.location?.coordinates || [NaN, NaN];
      const country = site.label?.split(',').pop()?.trim() || '';
      for (const rx of (site.receivers || [site])) {
        flat.push({
          name: rx.label || site.label || '',
          location: site.label || '',
          lat, lon,
          country,
          url: rx.url || site.url || '',
          version: rx.version || '',
          antenna: '',
          users: 0, usersMax: 0,
          offline: false,
          snr: NaN,
          tdoa: null,
          bands: '',
        });
      }
    }
    return flat;
  } catch (e) {
    return { error: e.message };
  }
}

// Regions of intelligence interest with bounding boxes
const REGIONS_OF_INTEREST = {
  middleEast:     { lamin: 12, lomin: 30, lamax: 42, lomax: 65, label: 'Middle East' },
  ukraine:        { lamin: 44, lomin: 22, lamax: 53, lomax: 41, label: 'Ukraine / Eastern Europe' },
  taiwan:         { lamin: 20, lomin: 115, lamax: 28, lomax: 125, label: 'Taiwan Strait' },
  baltics:        { lamin: 53, lomin: 19, lamax: 60, lomax: 29, label: 'Baltic Region' },
  southChinaSea:  { lamin: 5, lomin: 105, lamax: 23, lomax: 122, label: 'South China Sea' },
  koreanPeninsula:{ lamin: 33, lomin: 124, lamax: 43, lomax: 132, label: 'Korean Peninsula' },
  iran:           { lamin: 25, lomin: 44, lamax: 40, lomax: 63, label: 'Iran' },
  sahel:          { lamin: 10, lomin: -17, lamax: 20, lomax: 25, label: 'Sahel / West Africa' },
};

// HF band classifications for intelligence relevance
const HF_BANDS = {
  vlf:       { min: 0,     max: 0.3,  label: 'VLF (submarine/military comms)' },
  lf:        { min: 0.3,   max: 0.5,  label: 'LF (navigation/time signals)' },
  mf:        { min: 0.5,   max: 1.8,  label: 'MF (AM broadcast/maritime)' },
  hf160m:    { min: 1.8,   max: 2.0,  label: '160m amateur' },
  hf80m:     { min: 3.5,   max: 4.0,  label: '80m amateur' },
  hf60m:     { min: 5.3,   max: 5.4,  label: '60m amateur/utility' },
  hf49m:     { min: 5.9,   max: 6.2,  label: '49m shortwave broadcast' },
  hf40m:     { min: 7.0,   max: 7.3,  label: '40m amateur' },
  hf31m:     { min: 9.4,   max: 9.9,  label: '31m shortwave broadcast' },
  hf30m:     { min: 10.1,  max: 10.15,label: '30m amateur' },
  hf25m:     { min: 11.6,  max: 12.1, label: '25m shortwave broadcast' },
  hf20m:     { min: 14.0,  max: 14.35,label: '20m amateur' },
  hf17m:     { min: 18.068,max: 18.168,label: '17m amateur' },
  hf15m:     { min: 21.0,  max: 21.45,label: '15m amateur' },
  hf11m:     { min: 25.67, max: 26.1, label: '11m broadcast/CB' },
  hfMilitary:{ min: 2.0,   max: 30.0, label: 'HF military/utility (general)' },
};

// Check if a receiver falls within a bounding box
function inBounds(rx, box) {
  if (isNaN(rx.lat) || isNaN(rx.lon)) return false;
  return rx.lat >= box.lamin && rx.lat <= box.lamax && rx.lon >= box.lomin && rx.lon <= box.lomax;
}

// Map a receiver to a continent based on coordinates
function getContinent(lat, lon) {
  if (isNaN(lat) || isNaN(lon)) return 'Unknown';
  if (lat >= 15 && lat <= 72 && lon >= -170 && lon <= -50) return 'North America';
  if (lat >= -60 && lat < 15 && lon >= -90 && lon <= -30) return 'South America';
  if (lat >= 35 && lat <= 72 && lon >= -25 && lon <= 45) return 'Europe';
  if (lat >= -35 && lat <= 37 && lon >= -25 && lon <= 55) return 'Africa';
  if (lat >= 0 && lat <= 72 && lon >= 45 && lon <= 180) return 'Asia';
  if (lat >= -50 && lat <= 0 && lon >= 95 && lon <= 180) return 'Oceania';
  if (lat >= 35 && lat < 45 && lon >= 25 && lon <= 45) return 'Middle East';
  return 'Other';
}

// Classify the frequency range of a receiver
function classifyFrequency(rx) {
  // KiwiSDR receivers typically cover 0-30 MHz
  // Some entries have frequency info in various fields
  const maxFreq = parseFloat(rx.max_freq ?? rx.sdr_hu?.max_freq ?? 30);
  const minFreq = parseFloat(rx.min_freq ?? rx.sdr_hu?.min_freq ?? 0);
  return { minFreq, maxFreq };
}

// Normalize receiver data (already flat from getAllReceivers)
function normalizeReceiver(rx, idx) {
  return {
    name: (rx.name || `Receiver-${idx}`).slice(0, 100),
    location: (rx.location || '').slice(0, 80),
    lat: parseFloat(rx.lat) || NaN,
    lon: parseFloat(rx.lon) || NaN,
    users: parseInt(rx.users ?? 0, 10),
    usersMax: parseInt(rx.usersMax ?? 0, 10),
    antenna: (rx.antenna || '').slice(0, 80),
    bands: (rx.bands || '').slice(0, 60),
    offline: rx.offline === true,
    snr: parseFloat(rx.snr ?? NaN),
    tdoa: rx.tdoa ?? null,
    country: rx.country || '',
  };
}

// Briefing — analyze the global KiwiSDR network
export async function briefing() {
  const raw = await getAllReceivers();

  // Handle errors
  if (raw?.error) {
    return {
      source: 'KiwiSDR',
      timestamp: new Date().toISOString(),
      status: 'error',
      message: raw.error,
    };
  }

  // The API may return an array directly or an object with a receivers list
  let rxList;
  if (Array.isArray(raw)) {
    rxList = raw;
  } else if (raw && typeof raw === 'object') {
    // Try common keys
    rxList = raw.receivers || raw.rx || raw.sdrs || raw.data || Object.values(raw);
    // If the object values are receiver objects, flatten
    if (!Array.isArray(rxList)) {
      rxList = Object.values(raw).filter(v => v && typeof v === 'object' && !Array.isArray(v));
    }
  } else {
    return {
      source: 'KiwiSDR',
      timestamp: new Date().toISOString(),
      status: 'error',
      message: 'Unexpected data format from KiwiSDR API',
    };
  }

  // Normalize all receivers
  const allRx = rxList.map((rx, i) => normalizeReceiver(rx, i));
  const onlineRx = allRx.filter(r => !r.offline);
  const offlineRx = allRx.filter(r => r.offline);

  // --- Geographic distribution by country ---
  const byCountry = {};
  for (const rx of onlineRx) {
    const c = rx.country || 'Unknown';
    byCountry[c] = (byCountry[c] || 0) + 1;
  }
  // Sort by count descending, take top 20
  const topCountries = Object.entries(byCountry)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 20)
    .map(([country, count]) => ({ country, count }));

  // --- Continental distribution ---
  const byContinent = {};
  for (const rx of onlineRx) {
    const continent = getContinent(rx.lat, rx.lon);
    byContinent[continent] = (byContinent[continent] || 0) + 1;
  }

  // --- Receivers in regions of interest ---
  const conflictZoneReceivers = {};
  for (const [key, box] of Object.entries(REGIONS_OF_INTEREST)) {
    const rxInRegion = onlineRx.filter(rx => inBounds(rx, box));
    conflictZoneReceivers[key] = {
      region: box.label,
      count: rxInRegion.length,
      receivers: rxInRegion.slice(0, 10).map(rx => ({
        name: rx.name,
        location: rx.location,
        lat: rx.lat,
        lon: rx.lon,
        users: rx.users,
        antenna: rx.antenna,
        country: rx.country,
      })),
    };
  }

  // --- Activity analysis (users connected) ---
  const activeRx = onlineRx
    .filter(r => r.users > 0)
    .sort((a, b) => b.users - a.users);

  const totalUsers = onlineRx.reduce((sum, r) => sum + r.users, 0);
  const totalCapacity = onlineRx.reduce((sum, r) => sum + r.usersMax, 0);

  const topActive = activeRx.slice(0, 15).map(rx => ({
    name: rx.name,
    location: rx.location,
    country: rx.country,
    users: rx.users,
    usersMax: rx.usersMax,
    lat: rx.lat,
    lon: rx.lon,
    antenna: rx.antenna,
  }));

  // --- TDOA-capable receivers (direction finding / geolocation) ---
  const tdoaCapable = onlineRx.filter(r => r.tdoa !== null && r.tdoa > 0);

  // --- Antenna analysis (identify unusual/specialized setups) ---
  const antennaTypes = {};
  for (const rx of onlineRx) {
    if (rx.antenna) {
      const key = rx.antenna.toLowerCase().trim();
      antennaTypes[key] = (antennaTypes[key] || 0) + 1;
    }
  }

  // --- Utilization metrics ---
  const utilizationPct = totalCapacity > 0
    ? ((totalUsers / totalCapacity) * 100).toFixed(1)
    : '0.0';

  const highUtilization = onlineRx
    .filter(r => r.usersMax > 0 && (r.users / r.usersMax) >= 0.8)
    .map(rx => ({
      name: rx.name,
      location: rx.location,
      country: rx.country,
      users: rx.users,
      usersMax: rx.usersMax,
    }));

  // --- Generate signals ---
  const signals = [];

  // High user count (unusual listening activity)
  if (totalUsers > onlineRx.length * 0.5) {
    signals.push(`HIGH LISTENER ACTIVITY: ${totalUsers} total users across ${onlineRx.length} receivers (${utilizationPct}% utilization)`);
  }

  // Conflict zone coverage
  for (const [key, info] of Object.entries(conflictZoneReceivers)) {
    if (info.count > 0) {
      const activeInZone = info.receivers.filter(r => r.users > 0);
      if (activeInZone.length > 0) {
        signals.push(`ACTIVE LISTENING in ${info.region}: ${activeInZone.length}/${info.count} receivers have users connected`);
      }
    }
  }

  // High utilization receivers
  if (highUtilization.length > 5) {
    signals.push(`${highUtilization.length} receivers at >80% capacity — elevated HF monitoring demand`);
  }

  return {
    source: 'KiwiSDR',
    timestamp: new Date().toISOString(),
    status: 'active',
    network: {
      totalReceivers: allRx.length,
      online: onlineRx.length,
      offline: offlineRx.length,
      totalUsers,
      totalCapacity,
      utilizationPct: parseFloat(utilizationPct),
      tdoaCapable: tdoaCapable.length,
    },
    geographic: {
      byContinent,
      topCountries,
    },
    conflictZones: conflictZoneReceivers,
    topActive,
    highUtilization: highUtilization.slice(0, 10),
    signals,
  };
}

if (process.argv[1]?.endsWith('kiwisdr.mjs')) {
  const data = await briefing();
  console.log(JSON.stringify(data, null, 2));
}
