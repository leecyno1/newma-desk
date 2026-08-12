import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { execFileSync } from "node:child_process";
import { mkdtemp, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";

import {
  computeIndexSha256,
  computeWorktreeSha256,
} from "../../scripts/check-mod-project-sources.mjs";

function git(repoPath, ...args) {
  return execFileSync("git", ["-C", repoPath, ...args], {
    encoding: "buffer",
    stdio: ["ignore", "pipe", "pipe"],
  });
}

function statusSha256(repoPath) {
  return createHash("sha256")
    .update(git(repoPath, "status", "--porcelain=v1", "-z"))
    .digest("hex");
}

async function fingerprints(repoPath) {
  return {
    status: statusSha256(repoPath),
    index: computeIndexSha256(repoPath),
    worktree: await computeWorktreeSha256(repoPath),
  };
}

test("source fingerprints detect same-path content changes and ignore excluded files", async (t) => {
  const repoPath = await mkdtemp(path.join(os.tmpdir(), "newma-source-fingerprint-"));
  t.after(() => rm(repoPath, { recursive: true, force: true }));

  git(repoPath, "init", "--quiet");
  git(repoPath, "config", "user.email", "test@example.com");
  git(repoPath, "config", "user.name", "Newma Test");
  await writeFile(path.join(repoPath, ".gitignore"), "ignored.txt\n");
  await writeFile(path.join(repoPath, "tracked.txt"), "base\n");
  git(repoPath, "add", ".gitignore", "tracked.txt");
  git(repoPath, "commit", "--quiet", "-m", "baseline");

  await writeFile(path.join(repoPath, "tracked.txt"), "unstaged-one\n");
  const unstagedOne = await fingerprints(repoPath);
  await writeFile(path.join(repoPath, "tracked.txt"), "unstaged-two\n");
  const unstagedTwo = await fingerprints(repoPath);
  assert.equal(unstagedOne.status, unstagedTwo.status);
  assert.equal(unstagedOne.index, unstagedTwo.index);
  assert.notEqual(unstagedOne.worktree, unstagedTwo.worktree);

  git(repoPath, "add", "tracked.txt");
  const stagedOne = await fingerprints(repoPath);
  await writeFile(path.join(repoPath, "tracked.txt"), "staged-three\n");
  git(repoPath, "add", "tracked.txt");
  const stagedTwo = await fingerprints(repoPath);
  assert.equal(stagedOne.status, stagedTwo.status);
  assert.notEqual(stagedOne.index, stagedTwo.index);
  assert.notEqual(stagedOne.worktree, stagedTwo.worktree);

  await writeFile(path.join(repoPath, "untracked.txt"), "untracked-one\n");
  const untrackedOne = await fingerprints(repoPath);
  await writeFile(path.join(repoPath, "untracked.txt"), "untracked-two\n");
  const untrackedTwo = await fingerprints(repoPath);
  assert.equal(untrackedOne.status, untrackedTwo.status);
  assert.equal(untrackedOne.index, untrackedTwo.index);
  assert.notEqual(untrackedOne.worktree, untrackedTwo.worktree);

  await writeFile(path.join(repoPath, "ignored.txt"), "ignored-one\n");
  const ignoredOne = await fingerprints(repoPath);
  await writeFile(path.join(repoPath, "ignored.txt"), "ignored-two\n");
  const ignoredTwo = await fingerprints(repoPath);
  assert.deepEqual(ignoredOne, ignoredTwo);
});
