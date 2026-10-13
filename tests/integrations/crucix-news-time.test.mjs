import assert from 'node:assert/strict';
import test from 'node:test';
import { buildNewsFeed } from '../../bundled-runtimes/crucix/dashboard/inject.mjs';

test('GDELT indexing time survives refresh instead of becoming a new publication', () => {
  const indexed = new Date(Date.now() - 3_600_000).toISOString().replace(/\.\d{3}Z$/, 'Z');
  const input = { allArticles: [{ title: 'Indexed story', date: indexed.replace(/[-:]/g, ''), url: 'https://example.com/story' }] };
  const first = buildNewsFeed([], input, [], []);
  const second = buildNewsFeed([], input, [], []);
  assert.equal(first[0].timestamp, new Date(indexed).toISOString());
  assert.equal(first[0].timestampBasis, 'indexed');
  assert.equal(first[0].timestamp, second[0].timestamp);
});

test('GDELT without a source date remains undated', () => {
  const [item] = buildNewsFeed([], { allArticles: [{ title: 'Undated story' }] }, [], []);
  assert.equal(item.timestamp, null);
  assert.equal(item.timestampBasis, 'unknown');
});
