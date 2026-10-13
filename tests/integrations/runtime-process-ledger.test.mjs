import assert from "node:assert/strict";
import { existsSync, mkdtempSync, readFileSync, rmSync } from "node:fs";
import os from "node:os";
import path from "node:path";
import test from "node:test";

import {
  createRuntimeProcessLedger,
  recoverRuntimeProcesses,
} from "../../scripts/lib/runtime-process-ledger.mjs";

function fixture() {
  const root = mkdtempSync(path.join(os.tmpdir(), "newma-runtime-ledger-"));
  return {
    root,
    ledgerFile: path.join(root, "runtime", "managed-processes.json"),
  };
}

test("tracks and removes processes owned by the current stack", (context) => {
  const files = fixture();
  context.after(() => rmSync(files.root, { recursive: true, force: true }));
  const ledger = createRuntimeProcessLedger(files.ledgerFile, {
    ownerPid: 10,
    getIdentity: (pid) => `process-${pid}`,
  });

  ledger.track({ id: "desk" }, { pid: 20 });
  assert.deepEqual(
    JSON.parse(readFileSync(files.ledgerFile, "utf8")).processes,
    [{ serviceId: "desk", pid: 20, processIdentity: "process-20" }],
  );

  ledger.untrack({ pid: 20 });
  assert.deepEqual(
    JSON.parse(readFileSync(files.ledgerFile, "utf8")).processes,
    [],
  );
  ledger.clear();
  assert.equal(existsSync(files.ledgerFile), false);
});

test("recovers identity-matched children from a stale stack owner", async (context) => {
  const files = fixture();
  context.after(() => rmSync(files.root, { recursive: true, force: true }));
  const ledger = createRuntimeProcessLedger(files.ledgerFile, {
    ownerPid: 10,
    getIdentity: (pid) => `process-${pid}`,
  });
  ledger.track({ id: "crucix" }, { pid: 20 });
  const alive = new Set([20]);
  const signals = [];

  const recovery = await recoverRuntimeProcesses(files.ledgerFile, {
    isAlive: (pid) => alive.has(pid),
    getIdentity: (pid) => `process-${pid}`,
    terminate: (pid, signal) => {
      signals.push([pid, signal]);
      alive.delete(pid);
    },
    sleep: async () => {},
  });

  assert.deepEqual(recovery, {
    status: "recovered",
    recoveredServiceIds: ["crucix"],
    skippedServiceIds: [],
  });
  assert.deepEqual(signals, [[20, "SIGTERM"]]);
  assert.equal(existsSync(files.ledgerFile), false);
});

test("never terminates a live PID whose identity no longer matches", async (context) => {
  const files = fixture();
  context.after(() => rmSync(files.root, { recursive: true, force: true }));
  const ledger = createRuntimeProcessLedger(files.ledgerFile, {
    ownerPid: 10,
    getIdentity: (pid) => `old-${pid}`,
  });
  ledger.track({ id: "fund-web" }, { pid: 20 });
  const signals = [];

  const recovery = await recoverRuntimeProcesses(files.ledgerFile, {
    isAlive: (pid) => pid === 20,
    getIdentity: (pid) => `new-${pid}`,
    terminate: (...args) => signals.push(args),
    sleep: async () => {},
  });

  assert.deepEqual(recovery.skippedServiceIds, ["fund-web"]);
  assert.deepEqual(signals, []);
  assert.equal(existsSync(files.ledgerFile), false);
});

test("refuses recovery while the recorded stack owner is still active", async (context) => {
  const files = fixture();
  context.after(() => rmSync(files.root, { recursive: true, force: true }));
  createRuntimeProcessLedger(files.ledgerFile, {
    ownerPid: 10,
    getIdentity: (pid) => `process-${pid}`,
  });

  const recovery = await recoverRuntimeProcesses(files.ledgerFile, {
    isAlive: (pid) => pid === 10,
    getIdentity: (pid) => `process-${pid}`,
  });

  assert.deepEqual(recovery, {
    status: "active-owner",
    ownerPid: 10,
    recoveredServiceIds: [],
    skippedServiceIds: [],
  });
  assert.equal(existsSync(files.ledgerFile), true);
});
