import assert from "node:assert/strict";
import { mkdir, mkdtemp, rm, utimes, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";

import {
  runRuntimeBuildTasks,
  runtimeBuildDecision,
} from "../../scripts/lib/runtime-build.mjs";

async function fixture() {
  const root = await mkdtemp(path.join(os.tmpdir(), "newma-runtime-build-"));
  const source = path.join(root, "src");
  const output = path.join(root, "dist", "index.html");
  await mkdir(source, { recursive: true });
  await mkdir(path.dirname(output), { recursive: true });
  return { root, source, output };
}

async function setTime(file, milliseconds) {
  const value = new Date(milliseconds);
  await utimes(file, value, value);
}

test("builds when the output artifact is missing", async (context) => {
  const files = await fixture();
  context.after(() => rm(files.root, { recursive: true, force: true }));
  await writeFile(path.join(files.source, "main.ts"), "export {}\n");

  const decision = await runtimeBuildDecision({
    output: files.output,
    inputs: [files.source],
  });

  assert.equal(decision.build, true);
  assert.equal(decision.reason, "missing-output");
});

test("forces a build even when the output is current", async (context) => {
  const files = await fixture();
  context.after(() => rm(files.root, { recursive: true, force: true }));
  await writeFile(files.output, "built");

  const decision = await runtimeBuildDecision({
    output: files.output,
    inputs: [files.source],
    force: true,
  });

  assert.equal(decision.build, true);
  assert.equal(decision.reason, "forced");
});

test("skips a build when every input is older than the output", async (context) => {
  const files = await fixture();
  context.after(() => rm(files.root, { recursive: true, force: true }));
  const input = path.join(files.source, "main.ts");
  await writeFile(input, "export {}\n");
  await writeFile(files.output, "built");
  await setTime(input, 1_000);
  await setTime(files.output, 2_000);

  const decision = await runtimeBuildDecision({
    output: files.output,
    inputs: [files.source],
  });

  assert.equal(decision.build, false);
  assert.equal(decision.reason, "current");
});

test("rebuilds when a nested source file is newer than the output", async (context) => {
  const files = await fixture();
  context.after(() => rm(files.root, { recursive: true, force: true }));
  const nested = path.join(files.source, "canvas", "node.ts");
  await mkdir(path.dirname(nested), { recursive: true });
  await writeFile(nested, "export {}\n");
  await writeFile(files.output, "built");
  await setTime(files.output, 1_000);
  await setTime(nested, 2_000);

  const decision = await runtimeBuildDecision({
    output: files.output,
    inputs: [files.source],
  });

  assert.equal(decision.build, true);
  assert.equal(decision.reason, "stale-output");
  assert.equal(decision.newestInput, nested);
});

test("rebuilds when the cached artifact belongs to another build variant", async (context) => {
  const files = await fixture();
  context.after(() => rm(files.root, { recursive: true, force: true }));
  const signatureFile = path.join(path.dirname(files.output), ".newma-build-signature");
  await writeFile(files.output, "built");
  await writeFile(signatureFile, "standalone\n");

  const decision = await runtimeBuildDecision({
    output: files.output,
    inputs: [files.source],
    signature: "integrated:/mod-runtime/trading/",
    signatureFile,
  });

  assert.equal(decision.build, true);
  assert.equal(decision.reason, "signature-changed");
});

test("reuses an artifact with the requested build signature", async (context) => {
  const files = await fixture();
  context.after(() => rm(files.root, { recursive: true, force: true }));
  const signatureFile = path.join(path.dirname(files.output), ".newma-build-signature");
  await writeFile(files.output, "built");
  await writeFile(signatureFile, "integrated:/mod-runtime/trading/\n");

  const decision = await runtimeBuildDecision({
    output: files.output,
    inputs: [files.source],
    signature: "integrated:/mod-runtime/trading/",
    signatureFile,
  });

  assert.equal(decision.build, false);
  assert.equal(decision.reason, "current");
});

test("runs independent builds with bounded concurrency and preserves result order", async () => {
  const releases = [];
  const started = [];
  let active = 0;
  let maxActive = 0;
  const tasks = ["first", "second", "third"].map((name) => async () => {
    started.push(name);
    active += 1;
    maxActive = Math.max(maxActive, active);
    await new Promise((resolve) => releases.push(resolve));
    active -= 1;
    return name;
  });

  const running = runRuntimeBuildTasks(tasks, { concurrency: 2 });
  assert.deepEqual(started, ["first", "second"]);
  assert.equal(maxActive, 2);

  releases.shift()();
  await new Promise((resolve) => setImmediate(resolve));
  assert.deepEqual(started, ["first", "second", "third"]);

  while (releases.length > 0) releases.shift()();
  assert.deepEqual(await running, ["first", "second", "third"]);
  assert.equal(maxActive, 2);
});

test("waits for in-flight builds before returning the first failure", async () => {
  let release;
  let settled = false;
  const running = runRuntimeBuildTasks([
    async () => new Promise((resolve) => {
      release = resolve;
    }),
    async () => {
      throw new Error("build failed");
    },
    async () => {
      throw new Error("must not start");
    },
  ], { concurrency: 2 });
  void running.then(
    () => { settled = true; },
    () => { settled = true; },
  );

  await new Promise((resolve) => setImmediate(resolve));
  assert.equal(settled, false);
  release();
  await assert.rejects(running, /build failed/);
});
