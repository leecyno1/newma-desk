// Yahoo Finance public chart quotes; availability and delay vary by market.
// A collection time is not the quote's observation time.

import { safeFetch } from '../utils/fetch.mjs';

const BASE = 'https://query1.finance.yahoo.com/v8/finance/chart';

// Symbols to track — covers broad market, rates, commodities, crypto, volatility
const SYMBOLS = {
  // Indexes / ETFs
  '^GSPC': 'S&P 500',
  '^IXIC': 'Nasdaq Composite',
  '^DJI': 'Dow Jones',
  '^RUT': 'Russell 2000',
  // Rates / Credit
  TLT: '20Y+ Treasury',
  HYG: 'High Yield Corp',
  LQD: 'IG Corporate',
  // Commodities
  'GC=F': 'Gold',
  'SI=F': 'Silver',
  'CL=F': 'WTI Crude',
  'BZ=F': 'Brent Crude',
  'NG=F': 'Natural Gas',
  // Crypto
  'BTC-USD': 'Bitcoin',
  'ETH-USD': 'Ethereum',
  // Volatility
  '^VIX': 'VIX',
};

const rounded = value => Number.isFinite(value) ? Math.round(value * 100) / 100 : null;
function observationTime(seconds) {
  const date = new Date(seconds * 1000);
  return Number.isFinite(seconds) && seconds > 0 && Number.isFinite(date.getTime()) ? date.toISOString() : null;
}
function sessionDate(seconds, timeZone) {
  if (!observationTime(seconds) || !timeZone) return null;
  try {
    return new Intl.DateTimeFormat('en-CA', { timeZone, year: 'numeric', month: '2-digit', day: '2-digit' }).format(new Date(seconds * 1000));
  } catch { return null; }
}
function failedQuote(symbol, errorCode, error, httpStatus) {
  return { symbol, name: SYMBOLS[symbol] || symbol, errorCode, error,
    ...(httpStatus ? { httpStatus } : {}) };
}

async function fetchQuote(symbol) {
  try {
    const url = `${BASE}/${encodeURIComponent(symbol)}?range=5d&interval=1d&includePrePost=false`;
    const data = await safeFetch(url, {
      timeout: 8000,
      headers: {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
      },
    });

    if (data?.error) {
      const status = Number.isInteger(data.status) && data.status >= 400 && data.status <= 599 ? data.status : null;
      return failedQuote(symbol, status ? 'HTTP_ERROR' : 'REQUEST_FAILED',
        status ? `行情请求被拒绝（HTTP ${status}）` : '行情请求失败或超时', status);
    }
    if (data?.chart?.error) return failedQuote(symbol, 'PROVIDER_ERROR', '来源返回行情错误');
    const result = data?.chart?.result?.[0];
    if (!result) return failedQuote(symbol, 'INVALID_RESPONSE', '未返回有效行情结构');

    const meta = result.meta || {};
    const quotes = result.indicators?.quote?.[0] || {};
    const closes = Array.isArray(quotes.close) ? quotes.close : [];
    const timestamps = Array.isArray(result.timestamp) ? result.timestamp : [];

    // Get current price and previous close
    // Do not silently promote an old daily bar to a current market quote.
    const price = meta.regularMarketPrice;
    if (!Number.isFinite(price)) return failedQuote(symbol, 'INVALID_PRICE', '缺少有效行情价格');
    const timeZone = meta.exchangeTimezoneName;
    const quoteDate = sessionDate(meta.regularMarketTime, timeZone);
    const currentIndex = quoteDate ? timestamps.findLastIndex(ts => sessionDate(ts, timeZone) === quoteDate) : -1;
    // chartPreviousClose is the close BEFORE the requested five-day range.
    // Only use the immediately preceding daily bar; never bridge missing bars.
    const priorIndex = currentIndex - 1;
    const priorDate = priorIndex >= 0 ? sessionDate(timestamps[priorIndex], timeZone) : null;
    const dailyPrevious = priorDate && priorDate < quoteDate && Number.isFinite(closes[priorIndex])
      ? closes[priorIndex] : null;
    const providerPrevious = Number.isFinite(meta.previousClose) ? meta.previousClose : null;
    const prevClose = providerPrevious ?? dailyPrevious;
    const change = prevClose !== null ? price - prevClose : null;
    const changePct = prevClose !== null && prevClose > 0 ? (change / prevClose) * 100 : null;

    // Build 5-day history
    const history = [];
    for (let i = 0; i < timestamps.length; i++) {
      const date = sessionDate(timestamps[i], timeZone);
      if (date && Number.isFinite(closes[i])) {
        history.push({
          date,
          close: rounded(closes[i]),
        });
      }
    }

    return {
      symbol,
      name: SYMBOLS[symbol] || meta.shortName || symbol,
      price: rounded(price),
      prevClose: rounded(prevClose),
      previousCloseBasis: providerPrevious !== null ? 'provider' : dailyPrevious !== null ? 'daily-bars' : null,
      change: rounded(change),
      changePct: rounded(changePct),
      currency: typeof meta.currency === 'string' ? meta.currency : null,
      exchange: meta.exchangeName || '',
      marketState: meta.marketState || 'UNKNOWN',
      observedAt: observationTime(meta.regularMarketTime),
      source: 'Yahoo Finance',
      history,
    };
  } catch (e) {
    return failedQuote(symbol, 'REQUEST_FAILED', '行情请求失败或超时');
  }
}

export async function briefing() {
  return collect();
}

export async function collect() {
  const symbols = Object.keys(SYMBOLS);
  const results = await Promise.allSettled(
    symbols.map(s => fetchQuote(s))
  );

  const quotes = {};
  let ok = 0;
  let failed = 0;

  for (const [index, r] of results.entries()) {
    const q = r.status === 'fulfilled' ? r.value : null;
    if (q && !q.error && Number.isFinite(q.price)) {
      quotes[q.symbol] = q;
      ok++;
    } else {
      failed++;
      const sym = symbols[index];
      quotes[sym] = q || { symbol: sym, error: 'fetch failed' };
    }
  }

  // Categorize for easy dashboard consumption
  return {
    quotes,
    summary: {
      totalSymbols: symbols.length,
      ok,
      failed,
      timestamp: new Date().toISOString(),
    },
    indexes: pickGroup(quotes, ['^GSPC', '^IXIC', '^DJI', '^RUT']),
    rates: pickGroup(quotes, ['TLT', 'HYG', 'LQD']),
    commodities: pickGroup(quotes, ['GC=F', 'SI=F', 'CL=F', 'BZ=F', 'NG=F']),
    crypto: pickGroup(quotes, ['BTC-USD', 'ETH-USD']),
    volatility: pickGroup(quotes, ['^VIX']),
  };
}

function pickGroup(quotes, symbols) {
  return symbols.map(s => quotes[s]).filter(row => row && !row.error && Number.isFinite(row.price));
}
