import {
  mkdirSync,
  readFileSync,
  renameSync,
  unlinkSync,
  writeFileSync,
} from "node:fs";
import path from "node:path";

import { processIdentity, processIsAlive } from "./process-lock.mjs";

function readLedger(ledgerFile) {
  try {
    const value = JSON.parse(readFileSync(ledgerFile, "utf8"));
    if (
      value?.version !== 1
      || !Number.isInteger(value.owner?.pid)
      || !Array.isArray(value.processes)
    ) return null;
    return value;
  } catch (error) {
    if (error?.code === "ENOENT" || error instanceof SyntaxError) return null;
    throw error;
  }
}

function removeLedger(ledgerFile) {
  try {
    unlinkSync(ledgerFile);
  } catch (error) {
    if (error?.code !== "ENOENT") throw error;
  }
}

function writeLedger(ledgerFile, value) {
  mkdirSync(path.dirname(ledgerFile), { recursive: true });
  const temporary = `${ledgerFile}.${value.owner.pid}.tmp`;
  writeFileSync(temporary, `${JSON.stringify(value)}\n`, "utf8");
  renameSync(temporary, ledgerFile);
}

function identityMatches(entry, { isAlive, getIdentity }) {
  if (!isAlive(entry.pid) || !entry.processIdentity) return false;
  return getIdentity(entry.pid) === entry.processIdentity;
}

function ownerIsActive(owner, { isAlive, getIdentity }) {
  if (!isAlive(owner.pid)) return false;
  if (!owner.processIdentity) return true;
  const currentIdentity = getIdentity(owner.pid);
  return !currentIdentity || currentIdentity === owner.processIdentity;
}

function defaultTerminate(pid, signal) {
  try {
    if (process.platform === "win32") process.kill(pid, signal);
    else process.kill(-pid, signal);
  } catch (error) {
    if (error?.code !== "ESRCH") throw error;
  }
}

export function createRuntimeProcessLedger(
  ledgerFile,
  {
    ownerPid = process.pid,
    getIdentity = processIdentity,
  } = {},
) {
  const processes = new Map();
  const owner = {
    pid: ownerPid,
    processIdentity: getIdentity(ownerPid),
  };
  const persist = () => writeLedger(ledgerFile, {
    version: 1,
    owner,
    processes: [...processes.values()],
  });
  persist();

  return {
    track(service, child) {
      if (!Number.isInteger(child?.pid) || child.pid <= 0) return false;
      processes.set(child.pid, {
        serviceId: service.id,
        pid: child.pid,
        processIdentity: getIdentity(child.pid),
      });
      persist();
      return true;
    },
    untrack(child) {
      if (!Number.isInteger(child?.pid) || !processes.delete(child.pid)) return false;
      persist();
      return true;
    },
    clear() {
      processes.clear();
      removeLedger(ledgerFile);
    },
  };
}

export async function recoverRuntimeProcesses(
  ledgerFile,
  {
    isAlive = processIsAlive,
    getIdentity = processIdentity,
    terminate = defaultTerminate,
    sleep = (durationMs) => new Promise((resolve) => setTimeout(resolve, durationMs)),
    graceMs = 400,
  } = {},
) {
  const ledger = readLedger(ledgerFile);
  if (!ledger) {
    removeLedger(ledgerFile);
    return {
      status: "empty",
      recoveredServiceIds: [],
      skippedServiceIds: [],
    };
  }
  if (ownerIsActive(ledger.owner, { isAlive, getIdentity })) {
    return {
      status: "active-owner",
      ownerPid: ledger.owner.pid,
      recoveredServiceIds: [],
      skippedServiceIds: [],
    };
  }

  const matched = [];
  const skippedServiceIds = [];
  for (const entry of ledger.processes) {
    if (identityMatches(entry, { isAlive, getIdentity })) matched.push(entry);
    else if (isAlive(entry.pid)) skippedServiceIds.push(entry.serviceId);
  }
  for (const entry of matched) terminate(entry.pid, "SIGTERM");
  if (matched.length > 0 && graceMs > 0) await sleep(graceMs);
  for (const entry of matched) {
    if (identityMatches(entry, { isAlive, getIdentity })) {
      terminate(entry.pid, "SIGKILL");
    }
  }
  removeLedger(ledgerFile);
  return {
    status: "recovered",
    recoveredServiceIds: matched.map(({ serviceId }) => serviceId),
    skippedServiceIds,
  };
}
