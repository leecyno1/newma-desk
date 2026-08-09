#!/usr/bin/env node

import { createHash } from "node:crypto";
import { createReadStream, readFileSync } from "node:fs";
import { lstat, readlink } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { execFileSync } from "node:child_process";

const repoRoot = fileURLToPath(new URL("../", import.meta.url));
const lockPath = path.join(repoRoot, "config", "mod-project-source-lock.json");
const args = new Set(process.argv.slice(2));
const jsonOutput = args.has("--json");
const failOnDirty = args.has("--fail-on-dirty");

function readJson(file) {
  return JSON.parse(readFileSync(file, "utf8"));
}

function git(repoPath, ...gitArgs) {
  return execFileSync("git", ["-C", repoPath, ...gitArgs], {
    encoding: "utf8",
    stdio: ["ignore", "pipe", "pipe"],
  }).trim();
}

function gitBuffer(repoPath, ...gitArgs) {
  return execFileSync("git", ["-C", repoPath, ...gitArgs], {
    encoding: "buffer",
    maxBuffer: 256 * 1024 * 1024,
    stdio: ["ignore", "pipe", "pipe"],
  });
}

function nullSeparatedBuffers(buffer) {
  const values = [];
  let start = 0;
  for (let index = 0; index < buffer.length; index += 1) {
    if (buffer[index] !== 0) continue;
    if (index > start) values.push(buffer.subarray(start, index));
    start = index + 1;
  }
  if (start < buffer.length) values.push(buffer.subarray(start));
  return values;
}

function statusSummary(statusBuffer) {
  const lines = statusBuffer
    .toString("utf8")
    .split("\0")
    .filter(Boolean);
  let staged = 0;
  let unstaged = 0;
  let untracked = 0;
  for (const line of lines) {
    if (line.startsWith("??")) {
      untracked += 1;
      continue;
    }
    if (line[0] && line[0] !== " ") staged += 1;
    if (line[1] && line[1] !== " ") unstaged += 1;
  }
  return {
    entries: lines.length,
    staged,
    unstaged,
    untracked,
  };
}

function sha256(buffer) {
  return createHash("sha256").update(buffer).digest("hex");
}

function hashLength(hash, length) {
  const buffer = Buffer.allocUnsafe(8);
  buffer.writeBigUInt64BE(BigInt(length));
  hash.update(buffer);
}

function hashField(hash, label, value) {
  const buffer = Buffer.isBuffer(value) ? value : Buffer.from(String(value));
  hash.update(`${label}\0`);
  hashLength(hash, buffer.length);
  hash.update(buffer);
}

function absolutePathBuffer(repoPath, relativePath) {
  return Buffer.concat([
    Buffer.from(`${path.resolve(repoPath)}${path.sep}`),
    relativePath,
  ]);
}

async function hashRegularFile(hash, filePath, expectedSize) {
  hash.update("content\0");
  hashLength(hash, expectedSize);
  let bytesRead = 0;
  for await (const chunk of createReadStream(filePath)) {
    bytesRead += chunk.length;
    hash.update(chunk);
  }
  if (bytesRead !== expectedSize) {
    throw new Error(`file changed while fingerprinting: ${filePath.toString()}`);
  }
}

export function computeIndexSha256(repoPath) {
  return sha256(gitBuffer(repoPath, "ls-files", "--stage", "-z"));
}

export async function computeWorktreeSha256(repoPath) {
  const listedPaths = nullSeparatedBuffers(
    gitBuffer(repoPath, "ls-files", "--cached", "--others", "--exclude-standard", "-z"),
  ).sort(Buffer.compare);
  const hash = createHash("sha256");
  hash.update("newma-desk-worktree-v1\0");

  for (const relativePath of listedPaths) {
    hashField(hash, "path", relativePath);
    const filePath = absolutePathBuffer(repoPath, relativePath);
    let stats;
    try {
      stats = await lstat(filePath);
    } catch (error) {
      if (error?.code === "ENOENT") {
        hashField(hash, "type", "deleted");
        continue;
      }
      throw error;
    }

    if (stats.isSymbolicLink()) {
      hashField(hash, "type", "symlink");
      hashField(hash, "target", await readlink(filePath, { encoding: "buffer" }));
      continue;
    }
    if (stats.isFile()) {
      hashField(hash, "type", "file");
      hashField(hash, "executable", (stats.mode & 0o111) === 0 ? "0" : "1");
      await hashRegularFile(hash, filePath, stats.size);
      continue;
    }

    hashField(hash, "type", stats.isDirectory() ? "directory" : "other");
    hashField(hash, "mode", stats.mode & 0o7777);
  }

  return hash.digest("hex");
}

function compareCounts(expected, actual) {
  return expected.entries === actual.entries
    && expected.staged === actual.staged
    && expected.unstaged === actual.unstaged
    && expected.untracked === actual.untracked;
}

export async function inspectProject(project, root = repoRoot) {
  const repoPath = path.join(root, project.path);
  const remoteUrl = git(repoPath, "remote", "get-url", project.remote.name);
  const branch = git(repoPath, "branch", "--show-current");
  let upstream = "";
  try {
    upstream = git(repoPath, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}");
  } catch {
    upstream = "";
  }
  const commit = git(repoPath, "rev-parse", "HEAD");
  const statusBuffer = gitBuffer(repoPath, "status", "--porcelain=v1", "-z");
  const statusSha256 = sha256(statusBuffer);
  const indexSha256 = computeIndexSha256(repoPath);
  const worktreeSha256 = await computeWorktreeSha256(repoPath);
  const counts = statusSummary(statusBuffer);
  const dirty = counts.entries > 0;

  const issues = [];
  if (remoteUrl !== project.remote.url) {
    issues.push(`remote mismatch: ${remoteUrl} !== ${project.remote.url}`);
  }
  if (branch !== project.branch.current) {
    issues.push(`branch mismatch: ${branch} !== ${project.branch.current}`);
  }
  if (upstream !== project.branch.upstream) {
    issues.push(`upstream mismatch: ${upstream || "(none)"} !== ${project.branch.upstream}`);
  }
  if (commit !== project.commit) {
    issues.push(`commit mismatch: ${commit} !== ${project.commit}`);
  }
  if (statusSha256 !== project.workingTree.statusSha256) {
    issues.push("working tree status fingerprint mismatch");
  }
  if (indexSha256 !== project.workingTree.indexSha256) {
    issues.push("index content fingerprint mismatch");
  }
  if (worktreeSha256 !== project.workingTree.worktreeSha256) {
    issues.push("working tree content fingerprint mismatch");
  }
  if (!compareCounts(project.workingTree.counts, counts)) {
    issues.push("working tree counts mismatch");
  }
  if (failOnDirty && dirty) {
    issues.push("repository is dirty");
  }

  return {
    id: project.id,
    path: project.path,
    remoteUrl,
    branch,
    upstream,
    commit,
    dirty,
    statusSha256,
    indexSha256,
    worktreeSha256,
    counts,
    issues,
    ok: issues.length === 0,
  };
}

async function main() {
  const lock = readJson(lockPath);
  const results = await Promise.all(lock.projects.map((project) => inspectProject(project)));
  const ok = results.every((result) => result.ok);

  if (jsonOutput) {
    process.stdout.write(JSON.stringify({
      lock: lockPath,
      overlayPolicy: lock.workspacePolicy.overlayPolicy,
      ok,
      results,
    }, null, 2) + "\n");
  } else {
    process.stdout.write(`Lock: ${path.relative(repoRoot, lockPath)}\n`);
    process.stdout.write(`Overlay policy: ${lock.workspacePolicy.overlayPolicy.status} — ${lock.workspacePolicy.overlayPolicy.reason}\n`);
    for (const result of results) {
      process.stdout.write(`\n[${result.ok ? "OK" : "FAIL"}] ${result.id}\n`);
      process.stdout.write(`  path: ${result.path}\n`);
      process.stdout.write(`  remote: ${result.remoteUrl}\n`);
      process.stdout.write(`  branch: ${result.branch} (${result.upstream || "no upstream"})\n`);
      process.stdout.write(`  commit: ${result.commit}\n`);
      process.stdout.write(`  dirty: ${result.dirty} | entries=${result.counts.entries} staged=${result.counts.staged} unstaged=${result.counts.unstaged} untracked=${result.counts.untracked}\n`);
      process.stdout.write(`  statusSha256: ${result.statusSha256}\n`);
      process.stdout.write(`  indexSha256: ${result.indexSha256}\n`);
      process.stdout.write(`  worktreeSha256: ${result.worktreeSha256}\n`);
      for (const issue of result.issues) {
        process.stdout.write(`  issue: ${issue}\n`);
      }
    }
  }

  if (!ok) {
    process.exitCode = 1;
  }
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  await main();
}
