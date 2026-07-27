import assert from "node:assert/strict";
import { EventEmitter } from "node:events";
import test from "node:test";

import {
  createHttpProbe,
  RuntimeSupervisor,
  SERVICE_CRITICALITY,
  SERVICE_STATE,
} from "../../scripts/lib/runtime-supervisor.mjs";

function fakeChild({ exitCode = null } = {}) {
  const child = new EventEmitter();
  child.exitCode = exitCode;
  child.signalCode = null;
  child.kill = () => {};
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

test("returns a degraded result when an optional Mod cannot start", async () => {
  const errors = [];
  const supervisor = new RuntimeSupervisor({
    optionalTimeoutMs: 10,
    pollIntervalMs: 1,
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
    spawnImpl: () => fakeChild({ exitCode: 1 }),
    logger: { log() {}, error() {} },
    sleep: async () => {},
  });

  await assert.rejects(
    supervisor.start(service({ criticality: SERVICE_CRITICALITY.CORE })),
    /启动失败/,
  );
});

test("isolates optional runtime exits but escalates core runtime exits", async () => {
  const errors = [];
  const coreFailures = [];
  const optionalChild = fakeChild();
  const coreChild = fakeChild();
  const children = [optionalChild, coreChild];
  const probeStates = new Map([
    ["optional", [SERVICE_STATE.UNAVAILABLE, SERVICE_STATE.READY]],
    ["core", [SERVICE_STATE.UNAVAILABLE, SERVICE_STATE.READY]],
  ]);
  const supervisor = new RuntimeSupervisor({
    spawnImpl: () => children.shift(),
    logger: { log() {}, error(message) { errors.push(message); } },
    onCoreFailure: (error) => coreFailures.push(error),
    sleep: async () => {},
  });

  const makeProbe = (id) => async () => ({
    state: probeStates.get(id).shift() ?? SERVICE_STATE.READY,
  });
  await supervisor.start(service({ id: "optional", probe: makeProbe("optional") }));
  await supervisor.start(service({
    id: "core",
    criticality: SERVICE_CRITICALITY.CORE,
    probe: makeProbe("core"),
  }));

  optionalChild.emit("exit", 1, null);
  assert.equal(coreFailures.length, 0);
  assert.ok(errors.some((message) => message.includes("可选 Mod 已降级")));

  coreChild.emit("exit", 1, null);
  assert.equal(coreFailures.length, 1);
  assert.match(coreFailures[0].message, /意外退出/);
});
