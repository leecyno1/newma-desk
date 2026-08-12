#!/usr/bin/env node

import { spawn } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { inspectProcessLock } from "./lib/process-lock.mjs";

const repoRoot = fileURLToPath(new URL("../", import.meta.url));
const npmCommand = process.platform === "win32" ? "npm.cmd" : "npm";
const stackPidFile = (
  process.env.NEWMA_DESK_STACK_PID_FILE
  || process.env.NEWMA_DOCK_STACK_PID_FILE
  || process.env.VIBEDESK_STACK_PID_FILE
  || path.join(repoRoot, "runtime", "newma-desk-stack.pid")
);
const selectedLevelThreeMods = [
  "market-daily",
  "market-scanner",
  "multi-timeframe",
  "relative-strength",
  "event-timeline",
  "trading-replay",
  "watchlist",
].join(",");

const coreChecks = [
  {
    label: "Newma-Desk API",
    url: "http://127.0.0.1:8911/api/health",
    accepts: (response, body) => response.ok && body?.ok === true,
  },
  {
    label: "Research / Trading domain suites",
    url: "http://127.0.0.1:8911/api/domain-suites",
    accepts: (response, body) => response.ok
      && body?.ok === true
      && body?.suites?.research === true
      && body?.suites?.trading === true,
  },
  {
    label: "Newma-Desk",
    url: "http://127.0.0.1:5888/",
    accepts: (response) => response.ok,
  },
];

async function checkCore() {
  const results = await Promise.all(coreChecks.map(async (check) => {
    try {
      const response = await fetch(check.url, {
        headers: { Accept: "application/json, text/html" },
        signal: AbortSignal.timeout(1_500),
      });
      const contentType = response.headers.get("content-type") || "";
      const body = contentType.includes("application/json")
        ? await response.json()
        : undefined;
      return { label: check.label, ready: check.accepts(response, body) };
    } catch {
      return { label: check.label, ready: false };
    }
  }));
  return {
    ready: results.every((result) => result.ready || result.optional),
    missing: results.filter((result) => !result.ready && !result.optional).map((result) => result.label),
  };
}

function run(command, args, { env = process.env } = {}) {
  return new Promise((resolve, reject) => {
    const child = spawn(command, args, {
      cwd: repoRoot,
      env,
      stdio: "inherit",
    });
    child.once("error", reject);
    child.once("exit", (code, signal) => {
      if (code === 0) resolve();
      else {
        reject(new Error(
          `${command} ${args.join(" ")} failed: code=${code ?? "-"} signal=${signal ?? "-"}`,
        ));
      }
    });
  });
}

async function waitForCore(stack, timeoutMs = 180_000) {
  const deadline = Date.now() + timeoutMs;
  let stackExit;
  if (stack) {
    stack.once("exit", (code, signal) => {
      stackExit = { code, signal };
    });
  }
  let lastMissing = coreChecks.map((check) => check.label);
  while (Date.now() < deadline) {
    if (stackExit) {
      const owner = inspectProcessLock(stackPidFile);
      if (!owner.active || owner.pid === stack?.pid) {
        throw new Error(
          `Newma-Desk stack exited before certification: code=${stackExit.code ?? "-"} signal=${stackExit.signal ?? "-"}`,
        );
      }
      process.stdout.write(
        `WAIT existing Newma-Desk stack startup (PID ${owner.pid})\n`,
      );
      stack = undefined;
      stackExit = undefined;
    }
    const status = await checkCore();
    if (status.ready) return;
    lastMissing = status.missing;
    await new Promise((resolve) => setTimeout(resolve, 500));
  }
  throw new Error(`Newma-Desk core did not become ready: ${lastMissing.join(", ")}`);
}

async function stopStack(stack) {
  if (stack && stack.exitCode === null && stack.signalCode === null) {
    const exited = new Promise((resolve) => stack.once("exit", resolve));
    stack.kill("SIGTERM");
    const stopped = await Promise.race([
      exited.then(() => true),
      new Promise((resolve) => setTimeout(() => resolve(false), 15_000)),
    ]);
    if (!stopped && stack.exitCode === null && stack.signalCode === null) {
      stack.kill("SIGKILL");
    }
  }
}

async function main() {
  const requireExternal =
    (
      process.env.NEWMA_DESK_REQUIRE_EXTERNAL_MODS ||
      process.env.NEWMA_DOCK_REQUIRE_EXTERNAL_MODS ||
      process.env.VIBEDESK_REQUIRE_EXTERNAL_MODS
    ) === "1";
  const initial = await checkCore();
  let stack;

  if (!initial.ready) {
    const owner = inspectProcessLock(stackPidFile);
    if (owner.active) {
      process.stdout.write(
        `WAIT existing Newma-Desk stack startup (PID ${owner.pid}); missing: ${initial.missing.join(", ")}\n`,
      );
    } else {
      process.stdout.write(
        `START Newma-Desk release stack; missing: ${initial.missing.join(", ")}\n`,
      );
      stack = spawn(process.execPath, ["scripts/dev-stack.mjs"], {
        cwd: repoRoot,
        env: process.env,
        stdio: "inherit",
      });
    }
    await waitForCore(stack);
  } else {
    process.stdout.write("REUSE running Newma-Desk core stack\n");
  }

  try {
    await run(npmCommand, [
      "run",
      "dev:status",
      ...(requireExternal ? ["--", "--strict"] : []),
    ]);
    await run(npmCommand, ["run", "mods:compat"]);
    await run(npmCommand, [
      "run",
      "mods:certify",
      "--",
      "--mod",
      selectedLevelThreeMods,
    ]);
    await run(npmCommand, ["run", "test:e2e:sidebar"]);
    await run(npmCommand, ["run", "test:e2e:market"]);
    await run(npmCommand, ["run", "test:e2e:domain-suites"]);
  } finally {
    if (stack) await stopStack(stack);
  }
}

await main();
