export const ENERGY_SERIES = {
  wti: { eia: 'RWTC', fred: 'DCOILWTICO', symbol: 'CL=F', unit: '美元/桶' },
  brent: { eia: 'RBRTE', fred: 'DCOILBRENTEU', symbol: 'BZ=F', unit: '美元/桶' },
  naturalGas: { eia: 'RNGWHHD', fred: 'DHHNGSP', symbol: 'NG=F', unit: '美元/百万英热单位' },
  crudeStocks: { eia: 'WCESTUS1', unit: '千桶' },
};

function dayTime(value) {
  if (typeof value !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return null;
  const time = Date.parse(value);
  return Number.isFinite(time) && new Date(time).toISOString().slice(0, 10) === value ? time : null;
}

// Local conservative age windows, not a publication calendar or real-time certification.
export function energySignalObservation(row, { now = new Date() } = {}) {
  const policy = ENERGY_SERIES[row?.id];
  if (!policy || !Number.isFinite(row.value) || row.unit !== policy.unit) return null;
  const source = row.source;
  if (!source) return null;
  if (row.kind === 'futures') {
    if (!policy.symbol || source.id !== 'YFinance' || source.seriesId !== policy.symbol
      || row.frequency !== 'quote' || typeof row.observedAt !== 'string'
      || !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$/.test(row.observedAt)
      || dayTime(row.observedAt.slice(0, 10)) === null) return null;
    const age = (now.getTime() - Date.parse(row.observedAt)) / 86400000;
    return Number.isFinite(age) && age >= 0 && age <= 7 ? row : null;
  }
  const inventory = row.id === 'crudeStocks';
  if (row.kind !== (inventory ? 'inventory' : 'spot') || row.frequency !== (inventory ? 'weekly' : 'daily')
    || inventory && row.value < 0) return null;
  const sameSeries = source.id === 'EIA' && source.seriesId === policy.eia
    || policy.fred && source.id === 'FRED-public' && source.seriesId === policy.fred
      && source.originalSeriesId === policy.eia;
  const time = dayTime(row.period);
  if (!sameSeries || time === null) return null;
  const age = (Date.parse(now.toISOString().slice(0, 10)) - time) / 86400000;
  return age >= 0 && age <= (inventory ? 14 : 7) ? row : null;
}

export function energyBasis(row) {
  return { id: row.id, kind: row.kind, frequency: row.frequency, unit: row.unit,
    sourceId: row.source.id, seriesId: row.source.seriesId };
}

export function sameEnergyBasis(a, b) {
  return ['id', 'kind', 'frequency', 'unit', 'sourceId', 'seriesId'].every(key => a?.[key] === b?.[key]);
}

export function energyObservationDate(row) {
  return row.kind === 'futures' ? row.observedAt : row.period;
}

// Compare dated EIA spot history only. Yahoo daily closes are not intraday futures quotes.
export function energySpotChange(row, options) {
  if (!energySignalObservation(row, options) || row.kind !== 'spot' || !Array.isArray(row.history)) return null;
  const points = new Map();
  const end = dayTime(row.period);
  for (const point of row.history) {
    const time = dayTime(point.period);
    if (time === null || !Number.isFinite(point.value) || time > end || end - time > 30 * 86400000) return null;
    if (points.has(point.period) && points.get(point.period) !== point.value) return null;
    points.set(point.period, point.value);
  }
  const dates = [...points.keys()].sort();
  const fromDate = dates[0], toDate = dates.at(-1);
  if (dates.length < 2 || toDate !== row.period || points.get(toDate) !== row.value) return null;
  const from = points.get(fromDate), to = row.value;
  return { from, to, fromDate, toDate, change: to - from,
    pctChange: from > 0 && to >= 0 ? (to - from) / from * 100 : null };
}

// Keep the selected value and its provenance together. Yahoo futures are not EIA spot prices.
export function energySnapshot(eia = {}, quotes = {}) {
  const definitions = [
    ['wti', 'WTI', eia.oilPrices?.wti, 'RWTC', 'CL=F', '美元/桶', 'daily'],
    ['brent', 'Brent', eia.oilPrices?.brent, 'RBRTE', 'BZ=F', '美元/桶', 'daily'],
    ['naturalGas', 'Henry Hub 天然气', eia.gasPrice, 'RNGWHHD', 'NG=F', '美元/百万英热单位', 'daily'],
    ['crudeStocks', '美国商业原油库存（不含战略储备）', eia.inventories?.crudeStocks, 'WCESTUS1', null, '千桶', 'weekly'],
  ];
  const observations = definitions.map(([id, label, row, seriesId, symbol, unit, frequency]) => {
    const quote = symbol ? quotes[symbol] : null;
    if (quote && Number.isFinite(quote.price)) {
      return {
        id, label: `${label}期货`, value: quote.price, kind: 'futures', frequency: 'quote',
        unit: quote.currency === 'USD' ? unit : null,
        period: null, observedAt: quote.observedAt || null, history: [],
        source: { id: 'YFinance', label: 'Yahoo Finance', seriesId: symbol,
          url: `https://finance.yahoo.com/quote/${encodeURIComponent(symbol)}/` },
        note: '期货公开报价，可能延迟；不能当作 EIA 现货价，历史连续报价可能换月。',
      };
    }
    const available = Number.isFinite(row?.value);
    return {
      id, label: symbol ? `${label}现货` : label, value: available ? row.value : null,
      kind: symbol ? 'spot' : 'inventory', frequency, unit,
      period: available ? row.period || null : null, observedAt: null,
      history: available && Array.isArray(row.recent) ? row.recent : [],
      source: row?.source || { id: 'EIA', label: '美国能源信息署 EIA', seriesId,
        url: `https://www.eia.gov/dnav/${id === 'naturalGas' ? 'ng' : 'pet'}/hist/LeafHandler.ashx?n=${id === 'naturalGas' ? 'NG' : 'PET'}&s=${seriesId}&f=${frequency === 'weekly' ? 'W' : 'D'}` },
      note: available ? row.note || '保留来源统计期；不是采集时间或已核实的发布日期。'
        : eia.gaps?.[id] || '来源未返回数据，不以零值代替。',
    };
  });
  const values = Object.fromEntries(observations.map(item => [item.id, item.value]));
  const wti = observations[0];
  const history = wti.kind === 'futures' ? quotes['CL=F']?.history : wti.history;
  const dated = (history || []).map(point => ({ date: point.date || point.period,
    value: wti.kind === 'futures' ? point.close : point.value }));
  const dates = new Map();
  const cutoff = dayTime((energyObservationDate(wti) || '').slice(0, 10));
  const validHistory = cutoff !== null && dated.every(point => {
    const time = dayTime(point.date);
    if (time === null || time > cutoff || !Number.isFinite(point.value)
      || dates.has(point.date) && dates.get(point.date) !== point.value) return false;
    dates.set(point.date, point.value);
    return true;
  });
  return {
    // Preserve the upstream dashboard's scalar API; Desk consumes observations.
    wti: values.wti, brent: values.brent, natgas: values.naturalGas, crudeStocks: values.crudeStocks,
    // Rendering only: oldest to newest, never mix spot values with futures closes.
    wtiRecent: validHistory ? [...dates.entries()].sort(([a], [b]) => a.localeCompare(b)).map(([, value]) => value) : [],
    observations, signals: eia.signals || [],
  };
}
