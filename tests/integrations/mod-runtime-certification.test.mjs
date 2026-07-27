import assert from "node:assert/strict";
import test from "node:test";

import {
  createRuntimeCertification,
  requiredRuntimeChecks,
  summarizeRuntimeCertifications,
} from "../../scripts/lib/mod-runtime-certification.mjs";

const passed = { status: "passed" };

test("requires Agent Context only for declared Level 3 Mods", () => {
  assert.deepEqual(requiredRuntimeChecks(1), [
    "health",
    "embed",
    "bridge",
    "responsive",
  ]);
  assert.deepEqual(requiredRuntimeChecks(2), [
    "health",
    "embed",
    "bridge",
    "responsive",
  ]);
  assert.deepEqual(requiredRuntimeChecks(3), [
    "health",
    "embed",
    "bridge",
    "responsive",
    "agentContext",
  ]);
});

test("never promotes a declared level when a required runtime check fails", () => {
  const result = createRuntimeCertification({
    id: "market-daily",
    declaredLevel: 3,
    shellOrigin: "http://127.0.0.1:5888",
    checks: {
      health: passed,
      embed: passed,
      bridge: passed,
      responsive: passed,
      agentContext: { status: "failed", detail: "context missing" },
    },
    testedAt: "2026-07-26T00:00:00.000Z",
  });

  assert.equal(result.status, "failed");
  assert.equal(result.certifiedLevel, null);
  assert.deepEqual(result.failedChecks, ["agentContext"]);
});

test("certifies only the declared level after every required check passes", () => {
  const result = createRuntimeCertification({
    id: "instock-czsc",
    declaredLevel: 2,
    shellOrigin: "http://127.0.0.1:5888",
    checks: {
      health: passed,
      embed: passed,
      bridge: passed,
      responsive: passed,
    },
    testedAt: "2026-07-26T00:00:00.000Z",
  });

  assert.equal(result.status, "certified");
  assert.equal(result.certifiedLevel, 2);
  assert.deepEqual(summarizeRuntimeCertifications([result]), {
    total: 1,
    certified: 1,
    failed: 0,
    byDeclaredLevel: {
      1: { total: 0, certified: 0 },
      2: { total: 1, certified: 1 },
      3: { total: 0, certified: 0 },
    },
  });
});
