import assert from "node:assert/strict";
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import os from "node:os";
import path from "node:path";
import test from "node:test";

import {
  claimProcessLock,
  inspectProcessLock,
  ProcessLockError,
  releaseProcessLock,
} from "../../scripts/lib/process-lock.mjs";

function storedPid(pidFile) {
  return JSON.parse(readFileSync(pidFile, "utf8")).pid;
}

function withPidFile(run) {
  const directory = mkdtempSync(path.join(os.tmpdir(), "newma-desk-lock-"));
  const pidFile = path.join(directory, "runtime", "stack.pid");
  try {
    run(pidFile);
  } finally {
    rmSync(directory, { recursive: true, force: true });
  }
}

test("claims a missing PID file atomically", () => {
  withPidFile((pidFile) => {
    const result = claimProcessLock(pidFile, {
      pid: 1234,
      isAlive: () => false,
      getIdentity: () => "process-1234",
    });

    assert.deepEqual(result, { pid: 1234, recoveredStaleLock: false });
    assert.equal(storedPid(pidFile), 1234);
  });
});

test("rejects a second live stack", () => {
  withPidFile((pidFile) => {
    claimProcessLock(pidFile, {
      pid: 1234,
      isAlive: () => false,
      getIdentity: () => "process-1234",
    });

    assert.throws(
      () => claimProcessLock(pidFile, {
        pid: 5678,
        isAlive: (pid) => pid === 1234,
        getIdentity: (pid) => `process-${pid}`,
        label: "Newma-Desk 统一启动器",
      }),
      (error) => error instanceof ProcessLockError
        && error.code === "ELOCKED"
        && /已运行（PID 1234）/.test(error.message),
    );
    assert.equal(storedPid(pidFile), 1234);
  });
});

test("replaces a stale or invalid PID file", () => {
  withPidFile((pidFile) => {
    claimProcessLock(pidFile, {
      pid: 1234,
      isAlive: () => false,
      getIdentity: () => "process-1234",
    });
    const recovered = claimProcessLock(pidFile, {
      pid: 5678,
      isAlive: () => false,
      getIdentity: () => "process-5678",
    });

    assert.deepEqual(recovered, { pid: 5678, recoveredStaleLock: true });
    assert.equal(storedPid(pidFile), 5678);

    writeFileSync(pidFile, "not-a-pid\n", "utf8");
    claimProcessLock(pidFile, {
      pid: 9012,
      isAlive: () => false,
      getIdentity: () => "process-9012",
    });
    assert.equal(storedPid(pidFile), 9012);
  });
});

test("recovers a stale lock after the operating system reuses its PID", () => {
  withPidFile((pidFile) => {
    claimProcessLock(pidFile, {
      pid: 1234,
      isAlive: () => false,
      getIdentity: () => "old-process",
    });

    assert.deepEqual(
      inspectProcessLock(pidFile, {
        isAlive: () => true,
        getIdentity: () => "unrelated-new-process",
      }),
      { active: false, pid: 1234, reason: "pid-reused" },
    );
    claimProcessLock(pidFile, {
      pid: 5678,
      isAlive: () => true,
      getIdentity: (pid) => (
        pid === 1234 ? "unrelated-new-process" : "process-5678"
      ),
    });
    assert.equal(storedPid(pidFile), 5678);
  });
});

test("only the owning process releases the PID file", () => {
  withPidFile((pidFile) => {
    claimProcessLock(pidFile, {
      pid: 1234,
      isAlive: () => false,
      getIdentity: () => "process-1234",
    });

    assert.equal(releaseProcessLock(pidFile, { pid: 5678 }), false);
    assert.equal(storedPid(pidFile), 1234);
    assert.equal(releaseProcessLock(pidFile, { pid: 1234 }), true);
    assert.equal(releaseProcessLock(pidFile, { pid: 1234 }), false);
  });
});
