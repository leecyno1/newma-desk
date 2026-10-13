import { readFile, readdir, stat } from "node:fs/promises";

async function newestFile(pathname) {
  let metadata;
  try {
    metadata = await stat(pathname);
  } catch (error) {
    if (error?.code === "ENOENT") return null;
    throw error;
  }
  if (metadata.isFile()) {
    return { path: pathname, mtimeMs: metadata.mtimeMs };
  }
  if (!metadata.isDirectory()) return null;

  let newest = null;
  for (const entry of await readdir(pathname, { withFileTypes: true })) {
    const candidate = await newestFile(`${pathname}/${entry.name}`);
    if (candidate && (!newest || candidate.mtimeMs > newest.mtimeMs)) {
      newest = candidate;
    }
  }
  return newest;
}

export async function runtimeBuildDecision({
  output,
  inputs,
  force = false,
  signature,
  signatureFile,
}) {
  if (force) return { build: true, reason: "forced", newestInput: null };

  let outputMetadata;
  try {
    outputMetadata = await stat(output);
  } catch (error) {
    if (error?.code === "ENOENT") {
      return { build: true, reason: "missing-output", newestInput: null };
    }
    throw error;
  }

  if (signature !== undefined) {
    let currentSignature;
    try {
      currentSignature = await readFile(signatureFile, "utf8");
    } catch (error) {
      if (error?.code === "ENOENT") {
        return { build: true, reason: "missing-signature", newestInput: null };
      }
      throw error;
    }
    if (currentSignature.trimEnd() !== signature) {
      return { build: true, reason: "signature-changed", newestInput: null };
    }
  }

  let newest = null;
  for (const input of inputs) {
    const candidate = await newestFile(input);
    if (candidate && (!newest || candidate.mtimeMs > newest.mtimeMs)) {
      newest = candidate;
    }
  }
  if (newest && newest.mtimeMs > outputMetadata.mtimeMs) {
    return {
      build: true,
      reason: "stale-output",
      newestInput: newest.path,
    };
  }
  return {
    build: false,
    reason: "current",
    newestInput: newest?.path || null,
  };
}

export async function runRuntimeBuildTasks(
  tasks,
  { concurrency = 2 } = {},
) {
  if (!Number.isInteger(concurrency) || concurrency < 1) {
    throw new TypeError("Runtime build concurrency must be a positive integer");
  }
  const results = new Array(tasks.length);
  const workerCount = Math.min(tasks.length, concurrency);
  let nextIndex = 0;
  let firstFailure = null;

  async function worker() {
    while (!firstFailure) {
      const index = nextIndex;
      nextIndex += 1;
      if (index >= tasks.length) return;
      try {
        results[index] = await tasks[index]();
      } catch (error) {
        firstFailure = error;
      }
    }
  }

  await Promise.all(Array.from({ length: workerCount }, () => worker()));
  if (firstFailure) throw firstFailure;
  return results;
}
