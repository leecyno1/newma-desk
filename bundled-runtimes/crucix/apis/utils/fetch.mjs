// Shared fetch utility with timeout, retries, and error handling
import { sourceDelay, sourceFetch, sourceSignal } from './source-request.mjs';

export async function safeFetch(url, opts = {}) {
  const { timeout = 15000, retries = 1, headers = {} } = opts;
  const callerSignal = sourceSignal(opts.signal);
  let lastError;
  for (let i = 0; i <= retries; i++) {
    callerSignal?.throwIfAborted();
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(new DOMException('Request timed out', 'TimeoutError')), timeout);
    try {
      const res = await sourceFetch(url, {
        signal: callerSignal ? AbortSignal.any([callerSignal, controller.signal]) : controller.signal,
        headers: { 'User-Agent': 'Crucix/1.0', ...headers },
      });
      if (!res.ok) {
        // Do not wait for an error body or copy its private details into snapshots.
        await res.body?.cancel().catch(() => {});
        const error = new Error(`HTTP ${res.status}`);
        error.status = res.status;
        throw error;
      }
      const text = await res.text();
      try { return JSON.parse(text); } catch { return { rawText: text.slice(0, 500) }; }
    } catch (e) {
      // A source/caller deadline ends the whole operation, not just this attempt.
      callerSignal?.throwIfAborted();
      lastError = controller.signal.reason?.name === 'TimeoutError' ? controller.signal.reason : e;
      // Retrying the same credentials/query cannot fix a permanent rejection.
      if (e.status >= 400 && e.status < 500 && ![408, 429].includes(e.status)) break;
    } finally {
      clearTimeout(timer); // includes failures and body consumption, not just headers
    }
    if (i < retries) await sourceDelay(2000 * (i + 1), callerSignal);
  }
  const code = lastError?.cause?.code || lastError?.code;
  const timedOut = lastError?.name === 'TimeoutError'
    || ['ETIMEDOUT', 'UND_ERR_CONNECT_TIMEOUT', 'UND_ERR_HEADERS_TIMEOUT', 'UND_ERR_BODY_TIMEOUT'].includes(code);
  return { error: lastError?.message || 'Unknown error',
    ...(timedOut ? { errorCode: 'REQUEST_TIMEOUT' } : {}),
    ...(lastError?.status ? { status: lastError.status } : {}), source: url };
}

export function ago(hours) {
  return new Date(Date.now() - hours * 3600000).toISOString();
}

export function today() {
  return new Date().toISOString().split('T')[0];
}

export function daysAgo(n) {
  const d = new Date();
  d.setDate(d.getDate() - n);
  return d.toISOString().split('T')[0];
}
