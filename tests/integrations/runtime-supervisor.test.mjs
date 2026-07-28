import assert from "node:assert/strict";
import { EventEmitter } from "node:events";
import test from "node:test";

import {
  createCompositeProbe,
  createHttpProbe,
  RuntimeSupervisor,
  SERVICE_CRITICALITY,
  SERVICE_STATE,
} from "../../scripts/lib/runtime-supervisor.mjs";

let nextPid = 10_000;

function fakeChild({ exitCode = null, exitOnKill = true } = {}) {
  const child = new EventEmitter();
  child.pid = nextPid++;
  child.exitCode = exitCode;
  child.signalCode = null;
  child.kills = [];
  child.kill = (signal) => {
    child.kills.push(signal);
    if (!exitOnKill || child.exitCode != null || child.signalCode != null) return;
    child.signalCode = signal;
    child.emit("exit", null, signal);
  };
  return child;
}

function service(overrides = {}) {
  return {
    id: "example",
    label: "Example Mod",
    criticality: SERVICE_CRITICALITY.OPTIONAL,
    command: "example",
    commandArgs: [],
    cwd: process.cwd(),
    env: {},
    url: "http://127.0.0.1:9999/health",
    probe: async () => ({ state: SERVICE_STATE.UNAVAILABLE }),
    ...overrides,
  };
}

function sequenceProbe(...states) {
  let index = 0;
  return async () => {
    const value = states[Math.min(index, states.length - 1)];
    index += 1;
    if (value instanceof Error) throw value;
    return typeof value === "string" ? { state: value } : value;
  };
}

function quietLogger() {
  return { log() {}, error() {} };
}

function manualScheduler() {
  const entries = [];
  return {
    schedule(callback, delay) {
      const entry = { callback, delay, cancelled: false };
      entries.push(entry);
      return entry;
    },
    cancelSchedule(entry) {
      entry.cancelled = true;
    },
    pending() {
      return entries.filter((entry) => !entry.cancelled).length;
    },
    async runNext() {
      const entry = entries.find((candidate) => !candidate.cancelled);
      assert.ok(entry, "expected a scheduled monitor callback");
      entry.cancelled = true;
      await entry.callback();
    },
  };
}

test("classifies an explicit HTTP 409 as degraded data freshness", async () => {
  const probe = createHttpProbe("http://example.test/healthz", {
    expectedService: "seven-cycle-platform",
    degradedStatuses: [409],
    fetchImpl: async () => new Response(
      JSON.stringify({
        freshness: "unavailable",
        caveats: ["published data is temporarily unavailable"],
      }),
      { status: 409, headers: { "Content-Type": "application/json" } },
    ),
  });

  assert.deepEqual(await probe(), {
    state: SERVICE_STATE.DEGRADED,
    httpStatus: 409,
    reason: "published data is temporarily unavailable",
    dataFreshness: "unavailable",
  });
});

test("requires every composite readiness check even when API health is green", async () => {
  const calls = [];
  const probe = createCompositeProbe([
    {
      label: "API health",
      probe: async () => {
        calls.push("health");
        return { state: SERVICE_STATE.READY };
      },
    },
    {
      label: "Research / Trading domain suites",
      probe: async () => {
        calls.push("domains");
        return {
          state: SERVICE_STATE.UNAVAILABLE,
          reason: "Research / Trading domain suites are incomplete",
        };
      },
    },
  ]);

  const result = await probe();

  assert.deepEqual(calls.sort(), ["domains", "health"]);
  assert.equal(result.state, SERVICE_STATE.UNAVAILABLE);
  assert.match(result.reason, /domain suites.*incomplete/i);
});

test("refuses an initial duplicate when composite readiness fails on an occupied port", async () => {
  let spawnCount = 0;
  const supervisor = new RuntimeSupervisor({
    endpointOccupied: async () => true,
    spawnImpl: () => {
      spawnCount += 1;
      return fakeChild();
    },
    logger: quietLogger(),
  });

  await assert.rejects(
    supervisor.start(service({
      criticality: SERVICE_CRITICALITY.CORE,
      probe: createCompositeProbe([
        { label: "API health", probe: async () => ({ state: SERVICE_STATE.READY }) },
        {
          label: "Research / Trading domain suites",
          probe: async () => ({ state: SERVICE_STATE.UNAVAILABLE }),
        },
      ]),
    })),
    /拒绝启动重复实例/,
  );
  assert.equal(spawnCount, 0);
});

test("core recovery stays failed while health is green but domain suites remain incomplete", async () => {
  const children = [fakeChild(), fakeChild()];
  const coreFailures = [];
  let spawnIndex = 0;
  let clock = 0;
  const probe = createCompositeProbe([
    {
      label: "API health",
      probe: sequenceProbe(
        SERVICE_STATE.UNAVAILABLE,
        SERVICE_STATE.READY,
        SERVICE_STATE.READY,
        SERVICE_STATE.READY,
      ),
    },
    {
      label: "Research / Trading domain suites",
      probe: sequenceProbe(
        SERVICE_STATE.UNAVAILABLE,
        SERVICE_STATE.READY,
        {
          state: SERVICE_STATE.UNAVAILABLE,
          reason: "Research / Trading domain suites are incomplete",
        },
        {
          state: SERVICE_STATE.UNAVAILABLE,
          reason: "Research / Trading domain suites are incomplete",
        },
      ),
    },
  ]);
  const supervisor = new RuntimeSupervisor({
    coreTimeoutMs: 1,
    pollIntervalMs: 1,
    monitorIntervalMs: -1,
    monitorFailureThreshold: 1,
    restartGraceMs: 0,
    portReleaseTimeoutMs: 0,
    platform: "win32",
    endpointOccupied: async () => false,
    spawnImpl: () => children[spawnIndex++],
    logger: quietLogger(),
    onCoreFailure: (error) => coreFailures.push(error),
    now: () => clock,
    sleep: async (durationMs) => {
      clock += Math.max(1, durationMs);
    },
  });

  await supervisor.start(service({
    criticality: SERVICE_CRITICALITY.CORE,
    probe,
  }));
  const recovery = await supervisor.monitorNow("example");

  assert.equal(spawnIndex, 2);
  assert.equal(recovery.state, SERVICE_STATE.UNAVAILABLE);
  assert.equal(supervisor.records.get("example").state, SERVICE_STATE.UNAVAILABLE);
  assert.equal(coreFailures.length, 1);
  assert.match(coreFailures[0].message, /domain suites.*incomplete/i);
  await supervisor.stopAll({ graceMs: 0 });
});

test("returns a degraded result when an optional Mod cannot start", async () => {
  const errors = [];
  const supervisor = new RuntimeSupervisor({
    optionalTimeoutMs: 10,
    pollIntervalMs: 1,
    monitorIntervalMs: -1,
    restartGraceMs: 0,
    platform: "win32",
    spawnImpl: () => fakeChild({ exitCode: 1 }),
    logger: { log() {}, error(message) { errors.push(message); } },
    sleep: async () => {},
  });

  const result = await supervisor.start(service());

  assert.equal(result.state, SERVICE_STATE.UNAVAILABLE);
  assert.equal(result.launch, "failed");
  assert.match(errors[0], /可选 Mod 已降级/);
});

test("rejects startup when a core service cannot start", async () => {
  const supervisor = new RuntimeSupervisor({
    coreTimeoutMs: 10,
    pollIntervalMs: 1,
    monitorIntervalMs: -1,
    restartGraceMs: 0,
    platform: "win32",
    spawnImpl: () => fakeChild({ exitCode: 1 }),
    logger: quietLogger(),
    sleep: async () => {},
  });

  await assert.rejects(
    supervisor.start(service({ criticality: SERVICE_CRITICALITY.CORE })),
    /启动失败/,
  );
});

test("keeps reused services under continuous monitoring", async () => {
  const scheduler = manualScheduler();
  let spawnCount = 0;
  const supervisor = new RuntimeSupervisor({
    monitorIntervalMs: 25,
    schedule: scheduler.schedule,
    cancelSchedule: scheduler.cancelSchedule,
    spawnImpl: () => {
      spawnCount += 1;
      return fakeChild();
    },
    logger: quietLogger(),
  });

  const result = await supervisor.start(service({
    probe: sequenceProbe(SERVICE_STATE.READY, SERVICE_STATE.READY),
  }));

  assert.equal(result.launch, "reused");
  assert.equal(scheduler.pending(), 1);
  await scheduler.runNext();
  assert.equal(scheduler.pending(), 1);
  assert.equal(spawnCount, 0);

  await supervisor.stopAll({ graceMs: 0 });
  assert.equal(scheduler.pending(), 0);
});

test("does not restart after one transient health-check failure", async () => {
  let spawnCount = 0;
  const supervisor = new RuntimeSupervisor({
    monitorIntervalMs: -1,
    monitorFailureThreshold: 2,
    spawnImpl: () => {
      spawnCount += 1;
      return fakeChild();
    },
    logger: quietLogger(),
  });
  await supervisor.start(service({
    probe: sequenceProbe(
      SERVICE_STATE.READY,
      SERVICE_STATE.UNAVAILABLE,
      SERVICE_STATE.READY,
    ),
  }));

  await supervisor.monitorNow("example");
  await supervisor.monitorNow("example");

  assert.equal(spawnCount, 0);
  assert.equal(supervisor.records.get("example").state, SERVICE_STATE.READY);
});

test("takes over a reused local service only after consecutive failures and a released port", async () => {
  const children = [];
  const supervisor = new RuntimeSupervisor({
    monitorIntervalMs: -1,
    monitorFailureThreshold: 2,
    restartGraceMs: 0,
    portReleaseTimeoutMs: 0,
    endpointOccupied: async () => false,
    spawnImpl: () => {
      const child = fakeChild();
      children.push(child);
      return child;
    },
    logger: quietLogger(),
  });
  await supervisor.start(service({
    probe: sequenceProbe(
      SERVICE_STATE.READY,
      SERVICE_STATE.UNAVAILABLE,
      SERVICE_STATE.UNAVAILABLE,
      SERVICE_STATE.READY,
    ),
  }));

  await supervisor.monitorNow("example");
  assert.equal(children.length, 0);
  await supervisor.monitorNow("example");

  assert.equal(children.length, 1);
  assert.equal(supervisor.records.get("example").launch, "started");
  await supervisor.stopAll({ graceMs: 0 });
});

test("restarts a supervisor-owned service after consecutive failures", async () => {
  const children = [fakeChild(), fakeChild()];
  let spawnIndex = 0;
  const supervisor = new RuntimeSupervisor({
    monitorIntervalMs: -1,
    monitorFailureThreshold: 2,
    restartGraceMs: 0,
    portReleaseTimeoutMs: 0,
    platform: "win32",
    endpointOccupied: async () => false,
    spawnImpl: () => children[spawnIndex++],
    logger: quietLogger(),
  });
  await supervisor.start(service({
    probe: sequenceProbe(
      SERVICE_STATE.UNAVAILABLE,
      SERVICE_STATE.READY,
      SERVICE_STATE.UNAVAILABLE,
      SERVICE_STATE.UNAVAILABLE,
      SERVICE_STATE.READY,
    ),
  }));

  await supervisor.monitorNow("example");
  assert.deepEqual(children[0].kills, []);
  await supervisor.monitorNow("example");

  assert.deepEqual(children[0].kills, ["SIGTERM"]);
  assert.equal(spawnIndex, 2);
  assert.equal(supervisor.records.get("example").child, children[1]);
  await supervisor.stopAll({ graceMs: 0 });
});

test("an owned core process exit is recovered before onCoreFailure is considered", async () => {
  const children = [fakeChild(), fakeChild()];
  const coreFailures = [];
  let spawnIndex = 0;
  const supervisor = new RuntimeSupervisor({
    monitorIntervalMs: -1,
    monitorFailureThreshold: 2,
    restartGraceMs: 0,
    portReleaseTimeoutMs: 0,
    platform: "win32",
    endpointOccupied: async () => false,
    spawnImpl: () => children[spawnIndex++],
    logger: quietLogger(),
    onCoreFailure: (error) => coreFailures.push(error),
  });
  await supervisor.start(service({
    criticality: SERVICE_CRITICALITY.CORE,
    probe: sequenceProbe(
      SERVICE_STATE.UNAVAILABLE,
      SERVICE_STATE.READY,
      SERVICE_STATE.UNAVAILABLE,
      SERVICE_STATE.UNAVAILABLE,
      SERVICE_STATE.READY,
    ),
  }));

  children[0].exitCode = 1;
  children[0].emit("exit", 1, null);
  assert.equal(coreFailures.length, 0);

  await supervisor.monitorNow("example");
  assert.equal(coreFailures.length, 0);
  await supervisor.monitorNow("example");

  assert.equal(spawnIndex, 2);
  assert.equal(coreFailures.length, 0);
  assert.equal(supervisor.records.get("example").child, children[1]);
  await supervisor.stopAll({ graceMs: 0 });
});

test("refuses to duplicate a reused process while its port is occupied", async () => {
  const errors = [];
  let spawnCount = 0;
  const supervisor = new RuntimeSupervisor({
    monitorIntervalMs: -1,
    monitorFailureThreshold: 2,
    portReleaseTimeoutMs: 0,
    endpointOccupied: async () => true,
    spawnImpl: () => {
      spawnCount += 1;
      return fakeChild();
    },
    logger: { log() {}, error(message) { errors.push(message); } },
  });
  await supervisor.start(service({
    probe: sequenceProbe(
      SERVICE_STATE.READY,
      SERVICE_STATE.UNAVAILABLE,
      SERVICE_STATE.UNAVAILABLE,
      SERVICE_STATE.UNAVAILABLE,
    ),
  }));

  await supervisor.monitorNow("example");
  await supervisor.monitorNow("example");

  assert.equal(spawnCount, 0);
  assert.ok(errors.some((message) => message.includes("拒绝启动重复实例")));
});

test("escalates a core failure only after its safe restart fails", async () => {
  const coreFailures = [];
  let spawnCount = 0;
  const supervisor = new RuntimeSupervisor({
    monitorIntervalMs: -1,
    monitorFailureThreshold: 2,
    portReleaseTimeoutMs: 0,
    endpointOccupied: async () => false,
    spawnImpl: () => {
      spawnCount += 1;
      throw new Error("restart spawn failed");
    },
    logger: quietLogger(),
    onCoreFailure: (error) => coreFailures.push(error),
  });
  await supervisor.start(service({
    criticality: SERVICE_CRITICALITY.CORE,
    probe: sequenceProbe(
      SERVICE_STATE.READY,
      SERVICE_STATE.UNAVAILABLE,
      SERVICE_STATE.UNAVAILABLE,
    ),
  }));

  await supervisor.monitorNow("example");
  assert.equal(coreFailures.length, 0);
  await supervisor.monitorNow("example");

  assert.equal(spawnCount, 1);
  assert.equal(coreFailures.length, 1);
  assert.match(coreFailures[0].message, /restart spawn failed/);
});

test("does not spawn an unavailable external service without a command", async () => {
  let spawnCount = 0;
  const errors = [];
  const supervisor = new RuntimeSupervisor({
    spawnImpl: () => {
      spawnCount += 1;
      return fakeChild();
    },
    logger: { log() {}, error(message) { errors.push(message); } },
  });

  const result = await supervisor.start(service({
    command: undefined,
    criticality: SERVICE_CRITICALITY.EXTERNAL,
  }));

  assert.equal(result.state, SERVICE_STATE.UNAVAILABLE);
  assert.equal(result.launch, "external");
  assert.equal(spawnCount, 0);
  assert.ok(errors.some((message) => message.includes("外部 Mod 已降级")));
});

test("stopAll terminates only children started by this supervisor", async () => {
  const scheduler = manualScheduler();
  const ownedChild = fakeChild();
  let spawnCount = 0;
  const supervisor = new RuntimeSupervisor({
    monitorIntervalMs: 25,
    restartGraceMs: 0,
    platform: "win32",
    schedule: scheduler.schedule,
    cancelSchedule: scheduler.cancelSchedule,
    spawnImpl: () => {
      spawnCount += 1;
      return ownedChild;
    },
    logger: quietLogger(),
  });

  await supervisor.start(service({
    id: "reused",
    probe: sequenceProbe(SERVICE_STATE.READY),
  }));
  await supervisor.start(service({
    id: "started",
    probe: sequenceProbe(SERVICE_STATE.UNAVAILABLE, SERVICE_STATE.READY),
  }));
  assert.equal(scheduler.pending(), 2);

  await supervisor.stopAll({ graceMs: 0 });

  assert.equal(spawnCount, 1);
  assert.deepEqual(ownedChild.kills, ["SIGTERM"]);
  assert.equal(scheduler.pending(), 0);
  assert.equal(supervisor.records.get("reused").child, null);
});

test("stopAll prevents an in-flight monitor from spawning after shutdown", async () => {
  let probeCount = 0;
  let releaseProbe;
  let spawnCount = 0;
  const coreFailures = [];
  const supervisor = new RuntimeSupervisor({
    monitorIntervalMs: -1,
    monitorFailureThreshold: 1,
    portReleaseTimeoutMs: 0,
    endpointOccupied: async () => false,
    spawnImpl: () => {
      spawnCount += 1;
      return fakeChild();
    },
    logger: quietLogger(),
    onCoreFailure: (error) => coreFailures.push(error),
  });
  await supervisor.start(service({
    criticality: SERVICE_CRITICALITY.CORE,
    probe: async () => {
      probeCount += 1;
      if (probeCount === 1) return { state: SERVICE_STATE.READY };
      return new Promise((resolve) => {
        releaseProbe = resolve;
      });
    },
  }));

  const monitoring = supervisor.monitorNow("example");
  await Promise.resolve();
  await supervisor.stopAll({ graceMs: 0 });
  releaseProbe({ state: SERVICE_STATE.UNAVAILABLE });
  await monitoring;

  assert.equal(spawnCount, 0);
  assert.equal(coreFailures.length, 0);
});
