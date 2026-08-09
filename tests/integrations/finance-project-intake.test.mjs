import assert from "node:assert/strict";
import test from "node:test";

import {
  loadFinanceProjectIntake,
  validateFinanceProjectIntake,
} from "../../scripts/lib/finance-project-intake.mjs";

test("finance intake registry enforces one reviewed form per repository", async () => {
  const registry = await loadFinanceProjectIntake();
  const report = validateFinanceProjectIntake(registry);

  assert.equal(report.ok, true, report.errors.join("\n"));
  assert.equal(new Set(registry.projects.map((project) => project.source)).size, registry.projects.length);
  assert.ok(registry.projects.some((project) => project.mode === "complete-suite"));
  assert.ok(registry.projects.some((project) => project.mode === "data-provider"));
  assert.ok(registry.projects.some((project) => project.mode === "agent-capability"));
  assert.ok(registry.projects.some((project) => project.mode === "reject"));
  for (const project of registry.projects.filter((entry) => entry.mode === "agent-capability")) {
    assert.equal(project.presentation, "agent-only");
    assert.equal(project.pages, undefined);
  }
});

test("complete projects remain one Suite in one investment column", async () => {
  const registry = await loadFinanceProjectIntake();
  const suites = registry.projects.filter((project) => project.mode === "complete-suite");

  for (const project of suites) {
    assert.equal(project.preserveWholeProject, true);
    assert.deepEqual(project.consumers, [project.primaryColumn]);
    assert.equal(project.defaultEnabled, false);
    assert.match(project.suiteId, /^[a-z0-9]+(?:-[a-z0-9]+)*$/u);
  }
});

test("non-Suite sources cannot declare pages and rejected sources need a gate", async () => {
  const registry = await loadFinanceProjectIntake();
  const invalid = structuredClone(registry);
  const provider = invalid.projects.find((project) => project.mode === "data-provider");
  provider.pages = [{ id: "should-not-exist" }];
  const rejected = invalid.projects.find((project) => project.mode === "reject");
  delete rejected.reconsiderationGate;

  const report = validateFinanceProjectIntake(invalid);
  assert.equal(report.ok, false);
  assert.ok(report.errors.some((error) => error.includes("cannot declare independent Mod pages")));
  assert.ok(report.errors.some((error) => error.includes("requires a reconsiderationGate")));
});

test("duplicate repositories and cross-column complete Suites are rejected", async () => {
  const registry = await loadFinanceProjectIntake();
  const invalid = structuredClone(registry);
  const suite = invalid.projects.find((project) => project.mode === "complete-suite");
  suite.consumers.push("fundamentals");
  invalid.projects.push({ ...structuredClone(invalid.projects[0]), id: "duplicate-source" });

  const report = validateFinanceProjectIntake(invalid);
  assert.equal(report.ok, false);
  assert.ok(report.errors.some((error) => error.includes("source repository appears more than once")));
  assert.ok(report.errors.some((error) => error.includes("consumers must contain only its primaryColumn")));
});

test("sources below the threshold cannot be marked as an active intake mode", async () => {
  const registry = await loadFinanceProjectIntake();
  const invalid = structuredClone(registry);
  const reference = invalid.projects.find((project) => project.mode === "reference-only");
  reference.mode = "agent-capability";
  reference.presentation = "agent-only";

  const report = validateFinanceProjectIntake(invalid);
  assert.equal(report.ok, false);
  assert.ok(report.errors.some((error) => error.includes("below the adoption threshold")));
});

test("report-oriented Agent capabilities cannot become navigation pages", async () => {
  const registry = await loadFinanceProjectIntake();
  const invalid = structuredClone(registry);
  const capability = invalid.projects.find((project) => project.mode === "agent-capability");
  capability.presentation = "mod-page";
  capability.pages = [{ id: "report-page" }];

  const report = validateFinanceProjectIntake(invalid);
  assert.equal(report.ok, false);
  assert.ok(report.errors.some((error) => error.includes("cannot declare independent Mod pages")));
  assert.ok(report.errors.some((error) => error.includes("presentation must be agent-only")));
});
