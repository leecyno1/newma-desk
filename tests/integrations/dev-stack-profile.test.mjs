import assert from "node:assert/strict";
import test from "node:test";

import {
  createRuntimeProfilePlan,
  resolveRuntimeProfile,
} from "../../scripts/lib/dev-stack-profile.mjs";

const GROUP_NAMES = [
  "core",
  "worldIntel",
  "crucix",
  "policyCollector",
  "openChatCut",
  "instock",
  "fundAnalysis",
  "orchestra",
  "sevenCycle",
  "deepsee",
];

function serviceGroups() {
  return Object.fromEntries(
    GROUP_NAMES.map((name) => [name, [{ id: name }]]),
  );
}

function ids(services) {
  return services.map(({ id }) => id);
}

test("defaults to the compatible all profile", () => {
  assert.equal(resolveRuntimeProfile([], {}), "all");
});

test("accepts profile flags and lets CLI override the environment", () => {
  assert.equal(
    resolveRuntimeProfile(["--profile", "core"], {
      NEWMA_DESK_RUNTIME_PROFILE: "local",
    }),
    "core",
  );
  assert.equal(resolveRuntimeProfile(["--profile=local"], {}), "local");
  assert.equal(resolveRuntimeProfile(["--core"], {}), "core");
});

test("accepts compatible Desk environment prefixes", () => {
  assert.equal(
    resolveRuntimeProfile([], { NEWMA_DESK_RUNTIME_PROFILE: "local" }),
    "local",
  );
  assert.equal(
    resolveRuntimeProfile([], { NEWMA_DOCK_RUNTIME_PROFILE: "core" }),
    "core",
  );
  assert.equal(
    resolveRuntimeProfile([], { VIBEDESK_RUNTIME_PROFILE: "all" }),
    "all",
  );
});

test("rejects unknown or incomplete profile flags", () => {
  assert.throws(
    () => resolveRuntimeProfile(["--profile", "fast"], {}),
    /core, local, all/,
  );
  assert.throws(
    () => resolveRuntimeProfile(["--profile"], {}),
    /缺少 Profile/,
  );
});

test("core profile keeps the Desk core and first-party intelligence only", () => {
  const plan = createRuntimeProfilePlan("core", serviceGroups());

  assert.deepEqual(ids(plan.preCoreServices), ["worldIntel"]);
  assert.deepEqual(ids(plan.coreServices), ["core"]);
  assert.deepEqual(ids(plan.optionalServices), []);
  assert.deepEqual(ids(plan.allServices), ["worldIntel", "core"]);
  assert.deepEqual(plan.externalRuntimeIds, ["world-intel"]);
});

test("local profile adds common finance runtimes without heavy specialist tools", () => {
  const plan = createRuntimeProfilePlan("local", serviceGroups());

  assert.deepEqual(ids(plan.preCoreServices), [
    "worldIntel",
    "crucix",
    "policyCollector",
  ]);
  assert.deepEqual(ids(plan.optionalServices), [
    "instock",
    "fundAnalysis",
    "orchestra",
  ]);
  assert.ok(!ids(plan.allServices).includes("openChatCut"));
  assert.ok(!ids(plan.allServices).includes("sevenCycle"));
  assert.ok(!ids(plan.allServices).includes("deepsee"));
});

test("all profile preserves the existing complete startup set", () => {
  const plan = createRuntimeProfilePlan("all", serviceGroups());

  assert.deepEqual(ids(plan.optionalServices), [
    "openChatCut",
    "instock",
    "fundAnalysis",
    "orchestra",
    "sevenCycle",
    "deepsee",
  ]);
  assert.deepEqual(ids(plan.allServices), [
    "worldIntel",
    "crucix",
    "policyCollector",
    "core",
    "openChatCut",
    "instock",
    "fundAnalysis",
    "orchestra",
    "sevenCycle",
    "deepsee",
  ]);
});

test("accepts profile definitions compiled from Runtime Descriptor 2.0", () => {
  const plan = createRuntimeProfilePlan(
    "local",
    {
      core: [{ id: "core" }],
      "world-intel": [{ id: "world-intel" }],
      instock: [{ id: "instock" }],
    },
    {
      core: { preCore: ["world-intel"], optional: [], externalRuntimeIds: ["world-intel"] },
      local: {
        preCore: ["world-intel"],
        optional: ["instock"],
        externalRuntimeIds: ["world-intel", "instock"],
      },
      all: { preCore: ["world-intel"], optional: ["instock"] },
    },
  );

  assert.deepEqual(ids(plan.allServices), ["world-intel", "core", "instock"]);
  assert.deepEqual(plan.externalRuntimeIds, ["world-intel", "instock"]);
});
