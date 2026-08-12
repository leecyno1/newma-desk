#!/usr/bin/env node

import { createHash } from "node:crypto";
import {
  mkdtempSync,
  readFileSync,
  rmSync,
  statSync,
} from "node:fs";
import os from "node:os";
import path from "node:path";
import { execFileSync } from "node:child_process";

function assertSafeFileName(value, field) {
  if (
    typeof value !== "string"
    || value === ""
    || value === "."
    || value === ".."
    || path.basename(value) !== value
  ) {
    throw new Error(`${field} must be a plain file name`);
  }
}

function sha256(filePath) {
  const hash = createHash("sha256");
  hash.update(readFileSync(filePath));
  return hash.digest("hex");
}

function git(cwd, ...args) {
  return execFileSync("git", args, {
    cwd,
    encoding: "utf8",
    stdio: ["ignore", "pipe", "pipe"],
  }).trim();
}

function verifyProject(recoveryDirectory, project, restoreRoot, lockedProject = undefined) {
  if (!project || typeof project !== "object") {
    throw new Error("recovery manifest contains an invalid project entry");
  }
  if (!/^[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?$/.test(project.id || "")) {
    throw new Error("project id contains unsafe characters");
  }
  assertSafeFileName(project.bundle, `${project.id}: bundle`);
  if (!Number.isSafeInteger(project.bytes) || project.bytes <= 0) {
    throw new Error(`${project.id}: invalid bundle size`);
  }
  if (!/^[a-f0-9]{64}$/.test(project.sha256 || "")) {
    throw new Error(`${project.id}: invalid SHA-256 digest`);
  }
  if (lockedProject) {
    const comparisons = [
      ["source path", project.sourcePath, lockedProject.path],
      ["remote", project.remote, lockedProject.remote?.url],
      ["branch", project.branch, lockedProject.branch?.current],
      ["commit", project.commit, lockedProject.commit],
    ];
    for (const [field, actual, expected] of comparisons) {
      if (actual !== expected) {
        throw new Error(`${project.id}: ${field} does not match bundled source lock`);
      }
    }
  }
  const bundlePath = path.join(recoveryDirectory, project.bundle);
  const stats = statSync(bundlePath);
  if (stats.size !== project.bytes) {
    throw new Error(`${project.id}: bundle size mismatch`);
  }
  if (sha256(bundlePath) !== project.sha256) {
    throw new Error(`${project.id}: SHA-256 mismatch`);
  }
  execFileSync("git", ["bundle", "verify", bundlePath], { stdio: "inherit" });

  const clonePath = path.join(restoreRoot, project.id);
  execFileSync("git", [
    "clone",
    "--quiet",
    "--branch",
    project.branch,
    bundlePath,
    clonePath,
  ], { stdio: "inherit" });
  const commit = git(clonePath, "rev-parse", "HEAD");
  if (commit !== project.commit) {
    throw new Error(`${project.id}: restored commit ${commit} does not match ${project.commit}`);
  }
  if (git(clonePath, "status", "--porcelain=v1") !== "") {
    throw new Error(`${project.id}: restored worktree is not clean`);
  }
  process.stdout.write(`RESTORED ${project.id} ${commit}\n`);
}

function readBundledSourceLock(recoveryDirectory, manifest) {
  if (!manifest.sourceLock || typeof manifest.sourceLock !== "object") {
    throw new Error("schema 1.1 recovery manifest requires a bundled source lock");
  }
  assertSafeFileName(manifest.sourceLock.file, "source lock file");
  if (!/^[a-f0-9]{64}$/.test(manifest.sourceLock.sha256 || "")) {
    throw new Error("source lock has an invalid SHA-256 digest");
  }
  const sourceLockPath = path.join(recoveryDirectory, manifest.sourceLock.file);
  if (sha256(sourceLockPath) !== manifest.sourceLock.sha256) {
    throw new Error("bundled source lock SHA-256 mismatch");
  }
  const sourceLock = JSON.parse(readFileSync(sourceLockPath, "utf8"));
  if (!Array.isArray(sourceLock.projects)) {
    throw new Error("bundled source lock has no projects array");
  }
  return sourceLock;
}

function main() {
  const requestedPath = process.argv[2];
  if (!requestedPath) {
    throw new Error("usage: verify-mod-source-recovery.mjs <recovery-directory>");
  }
  const recoveryDirectory = path.resolve(requestedPath);
  const manifest = JSON.parse(
    readFileSync(path.join(recoveryDirectory, "manifest.json"), "utf8"),
  );
  if (!["1.0", "1.1"].includes(manifest.schemaVersion) || !Array.isArray(manifest.projects)) {
    throw new Error("unsupported recovery manifest");
  }

  const sourceLock = manifest.schemaVersion === "1.1"
    ? readBundledSourceLock(recoveryDirectory, manifest)
    : undefined;
  const lockedProjects = new Map(
    (sourceLock?.projects || []).map((project) => [project.id, project]),
  );
  if (sourceLock && lockedProjects.size !== manifest.projects.length) {
    throw new Error("manifest project count does not match bundled source lock");
  }

  const restoreRoot = mkdtempSync(path.join(os.tmpdir(), "newma-desk-recovery-"));
  try {
    const seenProjectIds = new Set();
    for (const project of manifest.projects) {
      if (seenProjectIds.has(project.id)) {
        throw new Error(`duplicate project id: ${project.id}`);
      }
      seenProjectIds.add(project.id);
      const lockedProject = sourceLock ? lockedProjects.get(project.id) : undefined;
      if (sourceLock && !lockedProject) {
        throw new Error(`${project.id}: missing from bundled source lock`);
      }
      verifyProject(recoveryDirectory, project, restoreRoot, lockedProject);
    }
  } finally {
    rmSync(restoreRoot, { recursive: true, force: true });
  }
  process.stdout.write(`Recovery verification passed: ${manifest.label}\n`);
}

main();
