import assert from "node:assert/strict";
import test from "node:test";

import {
  collectRuntimeStatus,
  createRuntimeStatusReport,
  formatRuntimeStatusLine,
  RUNTIME_STATUS_SCHEMA_VERSION,
} from "../../scripts/lib/runtime-status.mjs";
import {
  SERVICE_CRITICALITY,
  SERVICE_STATE,
} from "../../scripts/lib/runtime-supervisor.mjs";

function deferred() {
  let resolve;
  const promise = new Promise((settle) => {
    resolve = settle;
  });
  return { promise, resolve };
}

function service(id, overrides = {}) {
  return {
    id,
    label: `Service ${id}`,
    criticality: SERVICE_CRITICALITY.OPTIONAL,
    url: `http://127.0.0.1/${id}`,
    probe: async () => ({ state: SERVICE_STATE.READY }),
    ...overrides,
  };
}

test("probes all runtime services concurrently and preserves declaration order", async () => {
  const first = deferred();
  const second = deferred();
  const started = [];
  const collection = collectRuntimeStatus([
    service("first", {
      probe: async () => {
        started.push("first");
        return first.promise;
      },
    }),
    service("second", {
      probe: async () => {
        started.push("second");
        return second.promise;
      },
    }),
  ]);

  assert.deepEqual(started, ["first", "second"]);
  second.resolve({ state: SERVICE_STATE.DEGRADED, reason: "stale" });
  first.resolve({ state: SERVICE_STATE.READY });

  const results = await collection;
  assert.deepEqual(results.map(({ id }) => id), ["first", "second"]);
  assert.deepEqual(results.map(({ state }) => state), [
    SERVICE_STATE.READY,
    SERVICE_STATE.DEGRADED,
  ]);
});

test("records rounded probe latency", async () => {
  const timestamps = [100, 124.6];
  const [result] = await collectRuntimeStatus([service("timed")], {
    now: () => timestamps.shift(),
  });

  assert.equal(result.latencyMs, 25);
});

test("creates a stable runtime status report with core and all readiness", () => {
  const generatedAt = new Date("2026-08-27T01:02:03.000Z");
  const report = createRuntimeStatusReport({
    profile: "all",
    generatedAt,
    results: [
      {
        id: "api",
        label: "API",
        criticality: SERVICE_CRITICALITY.CORE,
        state: SERVICE_STATE.READY,
        url: "http://127.0.0.1/api",
        latencyMs: 2,
      },
      {
        id: "optional",
        label: "Optional",
        criticality: SERVICE_CRITICALITY.OPTIONAL,
        state: SERVICE_STATE.DEGRADED,
        reason: "stale",
        url: "http://127.0.0.1/optional",
        latencyMs: 9,
      },
      {
        id: "external",
        label: "External",
        criticality: SERVICE_CRITICALITY.EXTERNAL,
        state: SERVICE_STATE.UNAVAILABLE,
        reason: "offline",
        url: "http://127.0.0.1/external",
        latencyMs: 12,
      },
    ],
  });

  assert.deepEqual(report, {
    schemaVersion: RUNTIME_STATUS_SCHEMA_VERSION,
    profile: "all",
    generatedAt: "2026-08-27T01:02:03.000Z",
    summary: {
      ready: 1,
      degraded: 1,
      unavailable: 1,
      coreReady: true,
      allReady: false,
    },
    services: [
      {
        id: "api",
        label: "API",
        criticality: SERVICE_CRITICALITY.CORE,
        state: SERVICE_STATE.READY,
        url: "http://127.0.0.1/api",
        latencyMs: 2,
      },
      {
        id: "optional",
        label: "Optional",
        criticality: SERVICE_CRITICALITY.OPTIONAL,
        state: SERVICE_STATE.DEGRADED,
        reason: "stale",
        url: "http://127.0.0.1/optional",
        latencyMs: 9,
      },
      {
        id: "external",
        label: "External",
        criticality: SERVICE_CRITICALITY.EXTERNAL,
        state: SERVICE_STATE.UNAVAILABLE,
        reason: "offline",
        url: "http://127.0.0.1/external",
        latencyMs: 12,
      },
    ],
  });
});

test("formats a concise human-readable status line", () => {
  assert.equal(
    formatRuntimeStatusLine({
      id: "policy",
      label: "Policy Collector",
      criticality: SERVICE_CRITICALITY.OPTIONAL,
      state: SERVICE_STATE.DEGRADED,
      reason: "data is stale",
      url: "http://127.0.0.1/policy",
      latencyMs: 18,
    }),
    "WARN Policy Collector             http://127.0.0.1/policy · 18ms · data is stale",
  );
});
