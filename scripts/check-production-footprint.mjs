#!/usr/bin/env node

import { readFile, readdir, stat } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const repoRoot = fileURLToPath(new URL("../", import.meta.url));
const defaultPolicyPath = path.join(repoRoot, "config", "production-footprint.json");

function objectValue(value) {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? value
    : undefined;
}

function formatBytes(value) {
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KiB`;
  return `${(value / 1024 / 1024).toFixed(2)} MiB`;
}

async function filesUnder(directory) {
  const files = [];
  for (const entry of await readdir(directory, { withFileTypes: true })) {
    const entryPath = path.join(directory, entry.name);
    if (entry.isDirectory()) files.push(...await filesUnder(entryPath));
    else if (entry.isFile()) files.push(entryPath);
  }
  return files;
}

async function artifactResult(root, artifact) {
  const directory = path.resolve(root, artifact.path);
  let files;
  try {
    files = await filesUnder(directory);
  } catch (error) {
    if (error?.code !== "ENOENT") throw error;
    return {
      id: artifact.id,
      path: artifact.path,
      status: artifact.required ? "failed" : "skipped",
      totalBytes: 0,
      largestFileBytes: 0,
      largestFile: null,
      errors: artifact.required ? [`build artifact is missing: ${artifact.path}`] : [],
      warnings: artifact.required ? [] : [`optional build artifact is missing: ${artifact.path}`],
    };
  }

  let totalBytes = 0;
  let largestFileBytes = 0;
  let largestFile = null;
  for (const file of files) {
    const size = (await stat(file)).size;
    totalBytes += size;
    if (size > largestFileBytes) {
      largestFileBytes = size;
      largestFile = path.relative(root, file);
    }
  }
  const errors = [];
  if (totalBytes > artifact.maxTotalBytes) {
    errors.push(
      `total ${formatBytes(totalBytes)} exceeds ${formatBytes(artifact.maxTotalBytes)}`,
    );
  }
  if (largestFileBytes > artifact.maxFileBytes) {
    errors.push(
      `${largestFile} is ${formatBytes(largestFileBytes)}, above ${formatBytes(artifact.maxFileBytes)}`,
    );
  }
  const searchableFiles = files.filter((file) =>
    [".css", ".html", ".js", ".json", ".map", ".txt"].includes(path.extname(file))
  );
  const remainingForbiddenText = new Set(artifact.forbiddenText ?? []);
  for (const file of searchableFiles) {
    if (remainingForbiddenText.size === 0) break;
    const content = await readFile(file, "utf8");
    for (const forbiddenText of remainingForbiddenText) {
      if (!content.includes(forbiddenText)) continue;
      errors.push(
        `${path.relative(root, file)} contains forbidden bundle text: ${forbiddenText}`,
      );
      remainingForbiddenText.delete(forbiddenText);
    }
  }
  return {
    id: artifact.id,
    path: artifact.path,
    status: errors.length === 0 ? "passed" : "failed",
    totalBytes,
    largestFileBytes,
    largestFile,
    errors,
    warnings: [],
  };
}

function requirementDistributions(content) {
  const distributions = new Set();
  for (const rawLine of content.split(/\r?\n/u)) {
    const line = rawLine.split("#", 1)[0].trim();
    if (!line || line.startsWith("-")) continue;
    const match = /^([A-Za-z0-9][A-Za-z0-9._-]*)/u.exec(line);
    if (match) distributions.add(match[1].toLowerCase().replace(/[._]+/gu, "-"));
  }
  return distributions;
}

async function requirementsResult(root, policy) {
  const requirementPath = path.resolve(root, policy.path);
  let content;
  try {
    content = await readFile(requirementPath, "utf8");
  } catch (error) {
    if (error?.code !== "ENOENT") throw error;
    return {
      id: policy.id,
      status: policy.required ? "failed" : "skipped",
      errors: policy.required ? [`requirements file is missing: ${policy.path}`] : [],
      warnings: policy.required ? [] : [`optional requirements file is missing: ${policy.path}`],
    };
  }
  const installed = requirementDistributions(content);
  const forbidden = policy.forbiddenDistributions
    .map((name) => name.toLowerCase().replace(/[._]+/gu, "-"))
    .filter((name) => installed.has(name));
  return {
    id: policy.id,
    status: forbidden.length === 0 ? "passed" : "failed",
    errors: forbidden.map((name) => `forbidden integrated dependency: ${name}`),
    warnings: [],
  };
}

async function dockerContextResult(root, policy) {
  const ignorePath = path.resolve(root, policy.ignoreFile);
  const lines = (await readFile(ignorePath, "utf8"))
    .split(/\r?\n/u)
    .map((line) => line.trim())
    .filter((line) => line && !line.startsWith("#"));
  const present = new Set(lines);
  const missing = policy.requiredPatterns.filter((pattern) => !present.has(pattern));
  return {
    id: "docker-build-context",
    status: missing.length === 0 ? "passed" : "failed",
    errors: missing.map((pattern) => `missing .dockerignore pattern: ${pattern}`),
    warnings: [],
  };
}

export async function loadProductionFootprintPolicy(policyPath = defaultPolicyPath) {
  const policy = JSON.parse(await readFile(policyPath, "utf8"));
  if (policy.schemaVersion !== "1.0") {
    throw new Error("production footprint policy must use schemaVersion 1.0");
  }
  if (!Array.isArray(policy.artifacts) || !objectValue(policy.dockerContext)) {
    throw new Error("production footprint policy is incomplete");
  }
  return policy;
}

export async function checkProductionFootprint({
  root = repoRoot,
  policyPath = defaultPolicyPath,
} = {}) {
  const policy = await loadProductionFootprintPolicy(policyPath);
  const artifacts = await Promise.all(
    policy.artifacts.map((artifact) => artifactResult(root, artifact)),
  );
  const dockerContext = await dockerContextResult(root, policy.dockerContext);
  const pythonRequirements = await Promise.all(
    (policy.pythonRequirements ?? []).map((entry) => requirementsResult(root, entry)),
  );
  const results = [...artifacts, dockerContext, ...pythonRequirements];
  return {
    ok: results.every((result) => result.status !== "failed"),
    results,
  };
}

async function main() {
  const report = await checkProductionFootprint();
  for (const result of report.results) {
    const label = result.status.toUpperCase().padEnd(7);
    const size = result.totalBytes === undefined
      ? ""
      : ` total=${formatBytes(result.totalBytes)} largest=${formatBytes(result.largestFileBytes)}`;
    process.stdout.write(`${label} ${result.id}${size}\n`);
    for (const warning of result.warnings) process.stdout.write(`  WARN ${warning}\n`);
    for (const error of result.errors) process.stdout.write(`  ERROR ${error}\n`);
  }
  if (!report.ok) process.exitCode = 1;
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  await main();
}
