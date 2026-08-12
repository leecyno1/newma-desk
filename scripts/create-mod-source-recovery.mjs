#!/usr/bin/env node

import { createHash } from "node:crypto";
import {
  copyFileSync,
  mkdirSync,
  mkdtempSync,
  readFileSync,
  renameSync,
  rmSync,
  statSync,
  writeFileSync,
} from "node:fs";
import os from "node:os";
import path from "node:path";
import { execFileSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const repoRoot = fileURLToPath(new URL("../", import.meta.url));
const lockPath = path.join(repoRoot, "config", "mod-project-source-lock.json");
const defaultLabel = "newma-desk-release-ready-2026-08-09";
const bundledSourceLockName = "mod-project-source-lock.json";

function git(cwd, ...args) {
  return execFileSync("git", args, {
    cwd,
    encoding: "utf8",
    stdio: ["ignore", "pipe", "pipe"],
  }).trim();
}

function sha256(filePath) {
  const hash = createHash("sha256");
  hash.update(readFileSync(filePath));
  return hash.digest("hex");
}

function parseArgs(argv) {
  const options = { label: defaultLabel, output: undefined };
  for (let index = 0; index < argv.length; index += 1) {
    const argument = argv[index];
    if (argument === "--label") {
      if (argv[index + 1] === undefined) throw new Error("--label requires a value");
      options.label = argv[index + 1];
      index += 1;
    } else if (argument === "--output") {
      if (argv[index + 1] === undefined) throw new Error("--output requires a value");
      options.output = argv[index + 1];
      index += 1;
    } else {
      throw new Error(`unknown argument: ${argument}`);
    }
  }
  if (!options.label || !/^[A-Za-z0-9._-]+$/.test(options.label)) {
    throw new Error("--label must contain only letters, digits, dots, underscores, or hyphens");
  }
  return options;
}

function createBundle(project, tempDirectory) {
  if (!/^[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?$/.test(project.id || "")) {
    throw new Error("source lock contains an unsafe project id");
  }
  const projectPath = path.join(repoRoot, project.path);
  const fileName = `${project.id}.bundle`;
  const bundlePath = path.join(tempDirectory, fileName);
  execFileSync("git", [
    "bundle",
    "create",
    bundlePath,
    project.branch.current,
  ], {
    cwd: projectPath,
    stdio: "inherit",
  });
  execFileSync("git", ["bundle", "verify", bundlePath], {
    cwd: projectPath,
    stdio: "inherit",
  });
  return {
    id: project.id,
    sourcePath: project.path,
    remote: project.remote.url,
    branch: project.branch.current,
    commit: project.commit,
    bundle: fileName,
    bytes: statSync(bundlePath).size,
    sha256: sha256(bundlePath),
  };
}

function main() {
  const options = parseArgs(process.argv.slice(2));
  execFileSync("node", [
    "scripts/check-mod-project-sources.mjs",
    "--fail-on-dirty",
  ], {
    cwd: repoRoot,
    stdio: "inherit",
  });

  const lock = JSON.parse(readFileSync(lockPath, "utf8"));
  const outputDirectory = path.resolve(
    repoRoot,
    options.output || path.join("release-artifacts", options.label),
  );
  const outputParent = path.dirname(outputDirectory);
  mkdirSync(outputParent, { recursive: true });

  try {
    statSync(outputDirectory);
    throw new Error(`recovery directory already exists: ${outputDirectory}`);
  } catch (error) {
    if (error?.code !== "ENOENT") throw error;
  }

  const tempDirectory = mkdtempSync(path.join(outputParent, ".recovery-tmp-"));
  try {
    const projects = lock.projects.map((project) => createBundle(project, tempDirectory));
    copyFileSync(lockPath, path.join(tempDirectory, bundledSourceLockName));
    const manifest = {
      schemaVersion: "1.1",
      label: options.label,
      generatedAt: new Date().toISOString(),
      host: {
        platform: os.platform(),
        architecture: os.arch(),
      },
      rootRepository: {
        branch: git(repoRoot, "branch", "--show-current"),
        commit: git(repoRoot, "rev-parse", "HEAD"),
      },
      sourceLock: {
        repositoryPath: path.relative(repoRoot, lockPath),
        file: bundledSourceLockName,
        sha256: sha256(lockPath),
      },
      projects,
    };
    writeFileSync(
      path.join(tempDirectory, "manifest.json"),
      `${JSON.stringify(manifest, null, 2)}\n`,
      "utf8",
    );
    writeFileSync(
      path.join(tempDirectory, "README.txt"),
      [
        `Newma-Desk Mod source recovery: ${options.label}`,
        "",
        "Verify and restore with:",
        `  npm run release:recovery:verify -- ${outputDirectory}`,
        "",
        "The verifier checks the bundled source lock and every SHA-256 digest,",
        "clones each complete bundle into a disposable directory, and confirms",
        "the locked branch, commit, remote metadata, and clean status.",
        "",
      ].join("\n"),
      "utf8",
    );
    renameSync(tempDirectory, outputDirectory);
  } catch (error) {
    rmSync(tempDirectory, { recursive: true, force: true });
    throw error;
  }

  process.stdout.write(`Created recovery set: ${outputDirectory}\n`);
}

main();
