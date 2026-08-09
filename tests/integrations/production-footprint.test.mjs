import assert from "node:assert/strict";
import { mkdtemp, mkdir, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";

import { checkProductionFootprint } from "../../scripts/check-production-footprint.mjs";

async function fixture(policy) {
  const root = await mkdtemp(path.join(os.tmpdir(), "newma-footprint-"));
  await mkdir(path.join(root, "config"), { recursive: true });
  await writeFile(
    path.join(root, "config", "production-footprint.json"),
    JSON.stringify(policy),
  );
  return root;
}

test("accepts artifacts and integrated requirements within their budgets", async () => {
  const root = await fixture({
    schemaVersion: "1.0",
    artifacts: [{
      id: "desk",
      path: "dist",
      required: true,
      maxTotalBytes: 10,
      maxFileBytes: 10,
      forbiddenText: ["native model key"],
    }],
    dockerContext: { ignoreFile: ".dockerignore", requiredPatterns: ["**/.venv"] },
    pythonRequirements: [{
      id: "trading",
      path: "requirements.txt",
      required: true,
      forbiddenDistributions: ["langchain"],
    }],
  });
  try {
    await mkdir(path.join(root, "dist"));
    await writeFile(path.join(root, "dist", "index.js"), "small");
    await writeFile(path.join(root, ".dockerignore"), "**/.venv\n");
    await writeFile(path.join(root, "requirements.txt"), "pandas>=2\n");

    const report = await checkProductionFootprint({
      root,
      policyPath: path.join(root, "config", "production-footprint.json"),
    });

    assert.equal(report.ok, true);
    assert.ok(report.results.every((result) => result.status === "passed"));
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

test("reports bundle growth, context leaks and forbidden dependencies together", async () => {
  const root = await fixture({
    schemaVersion: "1.0",
    artifacts: [{
      id: "desk",
      path: "dist",
      required: true,
      maxTotalBytes: 3,
      maxFileBytes: 3,
      forbiddenText: ["native model key"],
    }],
    dockerContext: { ignoreFile: ".dockerignore", requiredPatterns: ["**/.venv"] },
    pythonRequirements: [{
      id: "trading",
      path: "requirements.txt",
      required: true,
      forbiddenDistributions: ["langchain-core"],
    }],
  });
  try {
    await mkdir(path.join(root, "dist"));
    await writeFile(path.join(root, "dist", "index.js"), "too large native model key");
    await writeFile(path.join(root, ".dockerignore"), "node_modules\n");
    await writeFile(path.join(root, "requirements.txt"), "langchain_core==1.0\n");

    const report = await checkProductionFootprint({
      root,
      policyPath: path.join(root, "config", "production-footprint.json"),
    });

    assert.equal(report.ok, false);
    assert.ok(report.results.flatMap((result) => result.errors).some((error) => error.includes("exceeds")));
    assert.ok(report.results.flatMap((result) => result.errors).some((error) => error.includes("forbidden bundle text")));
    assert.ok(report.results.flatMap((result) => result.errors).some((error) => error.includes(".dockerignore")));
    assert.ok(report.results.flatMap((result) => result.errors).some((error) => error.includes("langchain-core")));
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});
