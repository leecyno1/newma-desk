import { SaxesParser } from 'saxes';
import { sourceFetch, sourceSignal } from '../apis/utils/source-request.mjs';

const unavailable = (reason, errorCode = 'RSS_INVALID_FEED') => ({ status: 'error', reason, errorCode, items: null, count: null });

function networkFailure(error, timedOut) {
  const code = error?.cause?.code || error?.code;
  if (timedOut || ['ETIMEDOUT', 'UND_ERR_CONNECT_TIMEOUT', 'UND_ERR_HEADERS_TIMEOUT', 'UND_ERR_BODY_TIMEOUT'].includes(code)) {
    return unavailable('来源请求超时，未确认订阅内容', 'RSS_TIMEOUT');
  }
  if (['ENOTFOUND', 'EAI_AGAIN'].includes(code)) return unavailable('来源域名解析失败，未收到订阅内容', 'RSS_DNS_ERROR');
  if (['CERT_HAS_EXPIRED', 'ERR_TLS_CERT_ALTNAME_INVALID', 'DEPTH_ZERO_SELF_SIGNED_CERT', 'UNABLE_TO_VERIFY_LEAF_SIGNATURE', 'ERR_SSL_TLSV1_ALERT_INTERNAL_ERROR'].includes(code)) {
    return unavailable('来源安全连接校验失败，未读取订阅内容', 'RSS_TLS_ERROR');
  }
  if (code === 'ECONNREFUSED') return unavailable('来源连接被拒绝，未收到 HTTP 响应', 'RSS_CONNECTION_REFUSED');
  return unavailable('来源连接或响应读取失败', 'RSS_NETWORK_ERROR');
}

function publicUrl(value) {
  try {
    const url = new URL(value);
    return ['https:', 'http:'].includes(url.protocol) && !url.username && !url.password ? url.href : undefined;
  } catch { return undefined; }
}

export function parseNewsFeed(xml, source) {
  const parser = new SaxesParser({ xmlns: true });
  const stack = [];
  const items = [];
  let root, hasChannel = false, record = null, field = null, invalid = 0;
  const reject = () => { throw new Error('Invalid feed'); };
  parser.on('error', reject);
  parser.on('doctype', reject);
  parser.on('opentag', tag => {
    const name = tag.local;
    const parent = stack.at(-1);
    stack.push(name);
    if (stack.length === 1) {
      root = name;
      if (!['rss', 'RDF', 'feed'].includes(root)) reject();
    }
    if (root === 'rss' && stack.length === 2 && name === 'channel') hasChannel = true;
    const isEntry = (root === 'feed' && stack.length === 2 && name === 'entry')
      || (root === 'RDF' && stack.length === 2 && name === 'item')
      || (root === 'rss' && stack.length === 3 && parent === 'channel' && name === 'item');
    if (isEntry) record = { depth: stack.length, title: '', link: '', date: '' };
    if (!record || stack.length !== record.depth + 1) return;
    field = name === 'title' ? 'title' : ['pubDate', 'published', 'date'].includes(name) ? 'date' : name === 'link' ? 'link' : null;
    if (root === 'feed' && name === 'link') {
      const attrs = Object.fromEntries(Object.values(tag.attributes).map(a => [a.local, a.value]));
      if (attrs.href && (!attrs.rel || attrs.rel === 'alternate')) record.link = attrs.href;
      field = null;
    }
  });
  const append = value => { if (record && field) record[field] += value; };
  parser.on('text', append);
  parser.on('cdata', append);
  parser.on('closetag', () => {
    if (record && stack.length === record.depth + 1) field = null;
    if (record && stack.length === record.depth) {
      const title = record.title.trim();
      const rawDate = record.date.trim();
      const time = rawDate ? Date.parse(rawDate) : NaN;
      if (!title || (Number.isFinite(time) && time > Date.now())) invalid++;
      else {
        if (rawDate && !Number.isFinite(time)) invalid++;
        items.push({ title, date: Number.isFinite(time) ? new Date(time).toISOString() : null,
          source, url: publicUrl(record.link.trim()) });
      }
      record = null;
      field = null;
    }
    stack.pop();
  });
  try {
    parser.write(xml).close();
    if (!root || (root === 'rss' && !hasChannel)) reject();
  } catch { return unavailable('返回内容不是有效 RSS/RDF/Atom'); }
  if (invalid && !items.length) return unavailable('订阅记录缺少有效标题或日期不合理');
  return { status: invalid ? 'partial' : 'ok',
    reason: invalid ? '保留 ' + items.length + ' 条，' + invalid + ' 条字段不完整或无效' : items.length ? '取得 ' + items.length + ' 条记录' : '订阅有效，当前无记录',
    items, count: items.length };
}

export async function fetchNewsSource(url, source) {
  const caller = sourceSignal();
  caller?.throwIfAborted();
  const timeout = AbortSignal.timeout(8000);
  const signal = caller ? AbortSignal.any([caller, timeout]) : timeout;
  let result;
  try {
    const response = await sourceFetch(url, { signal, headers: { 'User-Agent': 'Crucix/1.0', Accept: 'application/rss+xml, application/atom+xml, application/xml, text/xml' } });
    if (!response.ok) {
      await response.body?.cancel().catch(() => {});
      result = { ...unavailable('HTTP ' + response.status, 'RSS_HTTP_ERROR'), httpStatus: response.status };
    } else result = parseNewsFeed(await response.text(), source);
  } catch (error) {
    caller?.throwIfAborted();
    result = networkFailure(error, timeout.aborted);
  }
  return { source, ...result, asOf: new Date().toISOString() };
}

