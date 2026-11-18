import { AsyncLocalStorage } from 'node:async_hooks';
import { setTimeout as sleep } from 'node:timers/promises';

// Each source owns its deadline, including its nested requests and rate-limit waits.
// Keep provider entry points usable on their own, without changing their API arguments.
const sourceScope = new AsyncLocalStorage();

export function sourceSignal(signal) {
  const parent = sourceScope.getStore();
  return parent && signal ? AbortSignal.any([parent, signal]) : parent || signal;
}

export function sourceFetch(url, options = {}) {
  const signal = sourceSignal(options.signal || AbortSignal.timeout(15000));
  signal.throwIfAborted();
  return globalThis.fetch(url, { ...options, signal });
}

export function sourceDelay(ms, signal) {
  return sleep(ms, undefined, { signal: sourceSignal(signal) });
}

export async function withSourceDeadline(name, operation, timeoutMs = 30000) {
  const controller = new AbortController();
  let timer;
  const deadline = new Promise((_, reject) => {
    timer = setTimeout(() => {
      const error = new DOMException(`Source ${name} timed out after ${timeoutMs / 1000}s`, 'TimeoutError');
      reject(error);
      controller.abort(error);
    }, timeoutMs);
  });
  try {
    return await sourceScope.run(controller.signal, () => Promise.race([
      Promise.resolve().then(operation), deadline,
    ]));
  } finally {
    clearTimeout(timer);
  }
}
