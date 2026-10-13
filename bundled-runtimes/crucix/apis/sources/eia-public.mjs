// Keyless fallbacks for the same EIA spot/inventory series, not futures or inventory changes.
const FRED_SERIES = { RWTC: 'DCOILWTICO', RBRTE: 'DCOILBRENTEU', RNGWHHD: 'DHHNGSP' };
const STOCKS_URL = 'https://ir.eia.gov/wpsr/table4.csv';

export function energyNumber(value) {
  if (value == null || String(value).trim() === '') return null;
  const number = Number(String(value).replaceAll(',', ''));
  return Number.isFinite(number) ? number : null;
}

export function energyPeriod(value) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value || '')) return null;
  const time = Date.parse(value);
  return Number.isFinite(time) && new Date(time).toISOString().slice(0, 10) === value ? value : null;
}

function csvRows(text) {
  return text.trim().split(/\r?\n/).map(line =>
    Array.from(line.matchAll(/(?:^|,)(?:"((?:[^"]|"")*)"|([^,]*))/g),
      match => (match[1]?.replaceAll('""', '"') ?? match[2]).trim()));
}

export function parseSpotCsv(text, seriesId) {
  const [header, ...rows] = csvRows(text);
  const column = header.indexOf(seriesId);
  if (column < 1 || !['observation_date', 'DATE'].includes(header[0])) return [];
  return rows.map(row => ({ period: energyPeriod(row[0]), value: energyNumber(row[column]) }))
    .filter(row => row.period && row.value !== null)
    .sort((a, b) => b.period.localeCompare(a.period)).slice(0, 5);
}

export function parseStocksCsv(text) {
  const [header, ...rows] = csvRows(text);
  const stocks = rows.find(row => row[0] === 'Commercial (Excluding SPR)');
  if (!stocks) return [];
  // WPSR Table 4 is in million barrels. Use current/previous week only, not difference or year-ago columns.
  return [1, 2].map(column => {
    const date = header[column]?.match(/^(\d{1,2})\/(\d{1,2})\/(\d{2}|\d{4})$/);
    const period = date ? energyPeriod(`${date[3].length === 2 ? '20' : ''}${date[3]}-${date[1].padStart(2, '0')}-${date[2].padStart(2, '0')}`) : null;
    const millions = energyNumber(stocks[column]);
    return { period, value: millions !== null && millions >= 0 ? Math.round(millions * 1000) : null };
  }).filter(row => row.period && row.value !== null).sort((a, b) => b.period.localeCompare(a.period));
}

export async function fetchPublicSeries(seriesId, fallbackReason) {
  const fredId = FRED_SERIES[seriesId];
  const isStocks = seriesId === 'WCESTUS1';
  if (!fredId && !isStocks) throw new Error('不支持的能源公开序列');
  const url = new URL(isStocks ? STOCKS_URL : 'https://fred.stlouisfed.org/graph/fredgraph.csv');
  if (fredId) {
    url.searchParams.set('id', fredId);
    url.searchParams.set('cosd', new Date(Date.now() - 60 * 86400000).toISOString().slice(0, 10));
    url.searchParams.set('coed', new Date().toISOString().slice(0, 10));
  }
  const response = await fetch(url, { signal: AbortSignal.timeout(10000), headers: { 'User-Agent': 'Crucix/1.0' } });
  if (!response.ok) throw new Error(`公开数据请求失败（HTTP ${response.status}）`);
  const csv = await response.text();
  const recent = isStocks ? parseStocksCsv(csv) : parseSpotCsv(csv, fredId);
  if (!recent.length) throw new Error('公开数据未返回有效日期与数值');
  return {
    ...recent[0], recent, unit: isStocks ? 'thousand barrels' : seriesId === 'RNGWHHD' ? '$/MMBtu' : '$/bbl',
    source: {
      id: isStocks ? 'EIA' : 'FRED-public', label: isStocks ? 'EIA 公开周报' : 'FRED · EIA',
      collectorId: 'EIA', seriesId: fredId || seriesId,
      url: isStocks ? STOCKS_URL : `https://fred.stlouisfed.org/series/${fredId}`,
      originalSource: '美国能源信息署 EIA', originalSeriesId: seriesId,
      originalUrl: isStocks ? 'https://www.eia.gov/petroleum/supply/weekly/'
        : seriesId === 'RNGWHHD' ? 'https://www.eia.gov/dnav/ng/hist/rngwhhdD.htm' : 'https://www.eia.gov/dnav/pet/pet_pri_spt_s1_d.htm',
      fallbackReason,
    },
    note: isStocks
      ? 'EIA 周报表 4：商业原油库存总量，不含战略储备；百万桶 × 1000 转为千桶。日期为周末统计期，不是发布日期。'
      : 'FRED 转发 EIA 日度现货统计，不是独立报价或期货。保留原始数据期，不代表实时价格。',
  };
}
