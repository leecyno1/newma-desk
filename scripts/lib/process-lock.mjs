import { execFileSync } from "node:child_process";
import {
  mkdirSync,
  readFileSync,
  unlinkSync,
  writeFileSync,
} from "node:fs";
import path from "node:path";

function readLock(pidFile) {
  try {
    const raw = readFileSync(pidFile, "utf8").trim();
    if (/^[1-9][0-9]*$/.test(raw)) {
      return { pid: Number(raw), processIdentity: null, version: 0 };
    }
    const parsed = JSON.parse(raw);
    if (
      parsed?.version !== 1
      || !Number.isInteger(parsed.pid)
      || parsed.pid <= 0
      || (parsed.processIdentity !== null && typeof parsed.processIdentity !== "string")
    ) {
      return null;
    }
    return parsed;
  } catch (error) {
    if (error?.code === "ENOENT") return null;
    if (error instanceof SyntaxError) return null;
    throw error;
  }
}

function processIsAlive(pid) {
  if (!Number.isInteger(pid) || pid <= 0) return false;
  try {
    process.kill(pid, 0);
    return true;
  } catch (error) {
    return error?.code === "EPERM";
  }
}

function processIdentity(pid) {
  if (process.platform === "win32") return null;
  try {
    const output = execFileSync(
      "ps",
      ["-p", String(pid), "-o", "lstart=", "-o", "command="],
      { encoding: "utf8", stdio: ["ignore", "pipe", "ignore"] },
    ).trim();
    return output || null;
  } catch {
    return null;
  }
}

export function inspectProcessLock(
  pidFile,
  {
    isAlive = processIsAlive,
    getIdentity = processIdentity,
  } = {},
) {
  const lock = readLock(pidFile);
  if (!lock) return { active: false, pid: null, reason: "missing-or-invalid" };
  if (!isAlive(lock.pid)) {
    return { active: false, pid: lock.pid, reason: "dead" };
  }
  if (lock.processIdentity) {
    const currentIdentity = getIdentity(lock.pid);
    if (currentIdentity && currentIdentity !== lock.processIdentity) {
      return { active: false, pid: lock.pid, reason: "pid-reused" };
    }
  }
  return { active: true, pid: lock.pid, reason: "live" };
}

export function claimProcessLock(
  pidFile,
  {
    pid = process.pid,
    isAlive = processIsAlive,
    getIdentity = processIdentity,
    label = "进程",
  } = {},
) {
  mkdirSync(path.dirname(pidFile), { recursive: true });
  const identity = getIdentity(pid);
  const content = `${JSON.stringify({
    version: 1,
    pid,
    processIdentity: identity,
  })}\n`;

  for (let attempt = 0; attempt < 3; attempt += 1) {
    try {
      writeFileSync(pidFile, content, { encoding: "utf8", flag: "wx" });
      return { pid, recoveredStaleLock: attempt > 0 };
    } catch (error) {
      if (error?.code !== "EEXIST") throw error;

      const existing = inspectProcessLock(pidFile, { isAlive, getIdentity });
      if (existing.active && existing.pid === pid) {
        return { pid, recoveredStaleLock: false };
      }
      if (existing.active) {
        throw new Error(`${label}已运行（PID ${existing.pid}）。`);
      }

      try {
        unlinkSync(pidFile);
      } catch (unlinkError) {
        if (unlinkError?.code !== "ENOENT") throw unlinkError;
      }
    }
  }

  throw new Error(`${label}单实例锁竞争失败，请稍后重试。`);
}

export function releaseProcessLock(pidFile, { pid = process.pid } = {}) {
  if (readLock(pidFile)?.pid !== pid) return false;
  try {
    unlinkSync(pidFile);
    return true;
  } catch (error) {
    if (error?.code === "ENOENT") return false;
    throw error;
  }
}
