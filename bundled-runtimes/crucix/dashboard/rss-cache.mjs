import { readFile, mkdir, writeFile, rename, unlink } from 'node:fs/promises';
import { join } from 'node:path';
import { randomUUID } from 'node:crypto';
import { fetchNewsSource } from './rss.mjs';

const usable = result => ['ok', 'partial'].includes(result?.status) && Array.isArray(result.items);
const keyFor = ([url, source]) => JSON.stringify([url, source]);

// Attempt status and usable data have separate clocks. A failed attempt must
// never advance the collection time of retained articles.
export async function collectNewsSources(feeds, { cacheDir = null, refresh = true } = {}) {
  let entries = {};
  let cache = { status: cacheDir ? 'missing' : 'disabled', reason: '' };
  const file = cacheDir ? join(cacheDir, 'rss-cache.json') : null;
  if (file) {
    try {
      const saved = JSON.parse(await readFile(file, 'utf8'));
      if (saved.version !== 1 || !saved.entries || Array.isArray(saved.entries)
          || typeof saved.entries !== 'object') throw new Error('Invalid cache');
      for (const entry of Object.values(saved.entries)) {
        if (!entry?.attempt || !['ok', 'partial', 'error'].includes(entry.attempt.status)
            || !Number.isFinite(Date.parse(entry.attempt.asOf))
            || (entry.data && (!usable(entry.data) || !Number.isFinite(Date.parse(entry.data.asOf))
              || !entry.data.items.every(item => typeof item.title === 'string' && typeof item.source === 'string')))) {
          throw new Error('Invalid cache');
        }
      }
      entries = saved.entries;
      cache = { status: 'ok', reason: '' };
    } catch (error) {
      cache = error.code === 'ENOENT' ? { status: 'missing', reason: '尚无 RSS 缓存' }
        : { status: 'error', reason: 'RSS 缓存无法读取，未使用损坏内容' };
    }
  }

  const fetched = refresh ? await Promise.all(feeds.map(([url, source]) => fetchNewsSource(url, source))) : [];
  const next = {};
  const results = feeds.flatMap((feed, index) => {
    const key = keyFor(feed);
    const previous = entries[key];
    const current = fetched[index];
    if (!current && !previous) return [];
    const attempt = current || previous.attempt;
    const data = usable(current) ? current : previous?.data || null;
    const { items: ignored, ...summary } = attempt;
    // The dashboard displays at most 50 records; bound each persisted feed too.
    next[key] = { attempt: summary, data: data ? { ...data, items: data.items.slice(0, 500) } : null };
    return [{ ...summary, url: feed[0], cached: Boolean(data && (!refresh || !usable(current))),
      dataAsOf: data?.asOf || null, availableCount: data?.items.length ?? null,
      dataStatus: data?.status || null, items: data?.items || null }];
  });

  if (file && refresh) {
    const temporary = file + '.' + randomUUID() + '.tmp';
    try {
      await mkdir(cacheDir, { recursive: true });
      await writeFile(temporary, JSON.stringify({ version: 1, entries: next }), { flag: 'wx', mode: 0o600 });
      await rename(temporary, file);
      // Preserve a read error for this response even if the new cache repaired it.
      if (cache.status !== 'error') cache = { status: 'ok', reason: '' };
    } catch {
      cache = { status: 'error', reason: 'RSS 缓存保存失败，本次有效结果仍可查看，重启后可能丢失' };
      try { await unlink(temporary); } catch (error) { if (!['ENOENT', 'ENOTDIR'].includes(error.code)) console.error('RSS temporary cache cleanup failed'); }
    }
  }
  return { results, cache, mode: refresh ? 'refresh' : 'cache' };
}
