import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import { once } from 'node:events';
import test from 'node:test';
import { safeFetch } from './fetch.mjs';
import { withSourceDeadline } from './source-request.mjs';

test('request timeout covers a body stalled after headers', { timeout: 3000 }, async (t) => {
  const server = createServer((_request, response) => {
    response.writeHead(200, { 'Content-Type': 'application/json' });
    response.write('{"value":');
  });
  server.listen(0, '127.0.0.1');
  await once(server, 'listening');
  t.after(() => { server.closeAllConnections(); server.close(); });
  let watchdog;
  try {
    const result = await Promise.race([
      safeFetch(`http://127.0.0.1:${server.address().port}/stalled`, { timeout: 50, retries: 0 }),
      new Promise((resolve) => { watchdog = setTimeout(() => resolve({ stalled: true }), 800); }),
    ]);
    assert.equal(result.stalled, undefined, 'headers must not clear the body deadline');
    assert.ok(result.error);
    assert.equal(result.errorCode, 'REQUEST_TIMEOUT');
  } finally {
    clearTimeout(watchdog);
  }
});

test('a fetch connection timeout keeps a safe typed reason despite a generic fetch error', async (t) => {
  t.mock.method(globalThis, 'fetch', async () => {
    throw new TypeError('fetch failed: private connection detail', { cause: { code: 'UND_ERR_CONNECT_TIMEOUT' } });
  });
  const result = await safeFetch('https://synthetic.invalid/', { retries: 0 });
  assert.equal(result.errorCode, 'REQUEST_TIMEOUT');
});

test('caller cancellation stops the request instead of returning data or retrying', async (t) => {
  const controller = new AbortController();
  let attempts = 0;
  t.mock.method(globalThis, 'fetch', async (_url, { signal }) => {
    attempts++;
    queueMicrotask(() => controller.abort(new Error('caller cancelled')));
    return new Promise((_resolve, reject) => {
      signal.addEventListener('abort', () => reject(signal.reason), { once: true });
    });
  });
  await assert.rejects(safeFetch('https://synthetic.invalid/', {
    signal: controller.signal, timeout: 50, retries: 0,
  }), /caller cancelled/);
  assert.equal(attempts, 1);
});

test('valid JSON and text responses keep the existing provider contract', async (t) => {
  const mock = t.mock.method(globalThis, 'fetch', async () => new Response('{"value":0}'));
  assert.deepEqual(await safeFetch('https://synthetic.invalid/'), { value: 0 });
  mock.mock.mockImplementation(async () => new Response('x'.repeat(800)));
  assert.deepEqual(await safeFetch('https://synthetic.invalid/'), { rawText: 'x'.repeat(500) });
});

test('permanent HTTP rejections return once without consuming the source deadline', async (t) => {
  const attempts = new Map();
  const server = createServer((request, response) => {
    const status = Number(request.url.slice(1));
    attempts.set(status, (attempts.get(status) || 0) + 1);
    response.writeHead(status, { 'Content-Type': 'text/plain' });
    // Rejection headers suffice, even when one provider never finishes its body.
    response.write('synthetic-private-provider-detail');
    if (status !== 403) response.end();
  });
  server.listen(0, '127.0.0.1');
  await once(server, 'listening');
  t.after(() => { server.closeAllConnections(); server.close(); });
  for (const status of [400, 401, 403, 404, 405, 422]) {
    const url = `http://127.0.0.1:${server.address().port}/${status}`;
    const result = await withSourceDeadline('rejection', () => safeFetch(url, { retries: 2 }), 500);
    assert.deepEqual(result, { error: `HTTP ${status}`, status, source: url });
    assert.equal(attempts.get(status), 1);
    assert.doesNotMatch(JSON.stringify(result), /private-provider-detail/);
  }
});

test('transient HTTP responses can recover while keeping their retry limit', async (t) => {
  const attempts = new Map();
  const server = createServer((request, response) => {
    const status = Number(request.url.slice(1));
    const attempt = (attempts.get(status) || 0) + 1;
    attempts.set(status, attempt);
    response.writeHead(attempt === 1 ? status : 200, { 'Content-Type': 'application/json' });
    response.end(attempt === 1 ? '{"error":"temporary"}' : '{"value":0}');
  });
  server.listen(0, '127.0.0.1');
  await once(server, 'listening');
  t.after(() => { server.closeAllConnections(); server.close(); });
  await Promise.all([408, 429, 500, 502, 503, 504].map(async (status) => {
    const result = await withSourceDeadline('transient', () => safeFetch(
      `http://127.0.0.1:${server.address().port}/${status}`,
    ), 5000);
    assert.deepEqual(result, { value: 0 });
    assert.equal(attempts.get(status), 2);
  }));
});

test('an exhausted HTTP failure keeps its status without leaking the response body', async (t) => {
  let attempts = 0;
  t.mock.method(globalThis, 'fetch', async () => {
    attempts++;
    return new Response('synthetic-private-provider-detail', { status: 503 });
  });
  const result = await safeFetch('https://synthetic.invalid/', { retries: 0 });
  assert.deepEqual(result, { error: 'HTTP 503', status: 503, source: 'https://synthetic.invalid/' });
  assert.equal(attempts, 1);
});
