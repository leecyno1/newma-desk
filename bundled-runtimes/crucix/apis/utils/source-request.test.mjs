import assert from 'node:assert/strict';
import { setTimeout as sleep } from 'node:timers/promises';
import test from 'node:test';
import { safeFetch } from './fetch.mjs';
import { sourceDelay, sourceFetch, withSourceDeadline } from './source-request.mjs';
import { briefing as gdelt } from '../sources/gdelt.mjs';
import { briefing as bluesky } from '../sources/bluesky.mjs';
import { briefing as telegram } from '../sources/telegram.mjs';
import { getGSCPI } from '../sources/gscpi.mjs';

test('one source deadline aborts its requests without cancelling a healthy sibling', async (t) => {
  let aborted = 0;
  t.mock.method(globalThis, 'fetch', async (url, { signal }) => {
    if (url.endsWith('/slow')) return new Promise((_resolve, reject) => {
      signal.addEventListener('abort', () => { aborted++; reject(signal.reason); }, { once: true });
    });
    await sleep(60, undefined, { signal });
    return new Response('{"value":0}');
  });
  const results = await Promise.allSettled([
    withSourceDeadline('slow', () => safeFetch('https://synthetic.invalid/slow'), 30),
    withSourceDeadline('healthy', () => safeFetch('https://synthetic.invalid/healthy'), 500),
  ]);
  assert.equal(results[0].status, 'rejected');
  assert.equal(results[0].reason.name, 'TimeoutError');
  assert.deepEqual(results[1], { status: 'fulfilled', value: { value: 0 } });
  assert.equal(aborted, 1);
});

test('source timeout cancels retry backoff before another network attempt', async (t) => {
  let attempts = 0;
  let settled = false;
  t.mock.method(globalThis, 'fetch', async () => { attempts++; throw new Error('connection failed'); });
  await assert.rejects(withSourceDeadline('retry', async () => {
    try { return await safeFetch('https://synthetic.invalid/', { retries: 3 }); }
    finally { settled = true; }
  }, 30), { name: 'TimeoutError' });
  await sleep(10);
  assert.equal(attempts, 1);
  assert.equal(settled, true, 'the underlying source must settle, not only Promise.race');
});

test('a source cannot start fallback requests after its deadline', async (t) => {
  let attempts = 0;
  let operation;
  t.mock.method(globalThis, 'fetch', async () => { attempts++; return new Response('{}'); });
  await assert.rejects(withSourceDeadline('fallback', () => {
    operation = (async () => {
      try { await sourceDelay(1000); } catch {}
      return sourceFetch('https://synthetic.invalid/late');
    })();
    return operation;
  }, 30), { name: 'TimeoutError' });
  await assert.rejects(operation);
  assert.equal(attempts, 0);
  assert.deepEqual(await safeFetch('https://synthetic.invalid/outside'), {});
  assert.equal(attempts, 1, 'deadline context must not escape the source');
});

for (const [name, briefing] of [['GDELT', gdelt], ['Bluesky', bluesky]]) {
  test(`${name} stops its sequential rate-limit wait at the source deadline`, async (t) => {
    let attempts = 0;
    let operation;
    t.mock.method(globalThis, 'fetch', async () => {
      attempts++;
      return new Response('{"articles":[],"posts":[]}');
    });
    await assert.rejects(withSourceDeadline(name, () => {
      operation = briefing();
      return operation;
    }, 30), { name: 'TimeoutError' });
    await assert.rejects(operation);
    assert.equal(attempts, 1);
  });
}

test('Telegram cancels the current parallel batch and never starts the next one', async (t) => {
  const previous = process.env.TELEGRAM_BOT_TOKEN;
  process.env.TELEGRAM_BOT_TOKEN = '';
  t.after(() => {
    if (previous === undefined) delete process.env.TELEGRAM_BOT_TOKEN;
    else process.env.TELEGRAM_BOT_TOKEN = previous;
  });
  let attempts = 0;
  let aborted = 0;
  let operation;
  t.mock.method(globalThis, 'fetch', async (_url, { signal }) => {
    attempts++;
    return new Promise((_resolve, reject) => {
      signal.addEventListener('abort', () => { aborted++; reject(signal.reason); }, { once: true });
    });
  });
  await assert.rejects(withSourceDeadline('Telegram', () => {
    operation = telegram();
    return operation;
  }, 30), { name: 'TimeoutError' });
  await assert.rejects(operation);
  assert.equal(attempts, 3);
  assert.equal(aborted, 3);
});

test('raw CSV response bodies also remain within their source deadline', async (t) => {
  let aborted = false;
  let operation;
  t.mock.method(globalThis, 'fetch', async (_url, { signal }) => ({
    ok: true,
    text: () => new Promise((_resolve, reject) => {
      signal.addEventListener('abort', () => { aborted = true; reject(signal.reason); }, { once: true });
    }),
  }));
  await assert.rejects(withSourceDeadline('GSCPI', () => {
    operation = getGSCPI();
    return operation;
  }, 30), { name: 'TimeoutError' });
  const result = await operation;
  assert.ok(result.error);
  assert.deepEqual(result.data, []);
  assert.equal(aborted, true);
});

test('source deadlines preserve successful return values and immediate errors', async () => {
  assert.deepEqual(await withSourceDeadline('normal', () => ({ items: [], value: 0 })), { items: [], value: 0 });
  await assert.rejects(withSourceDeadline('failure', () => { throw new Error('provider failed'); }), /provider failed/);
});
