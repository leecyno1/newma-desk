import assert from "node:assert/strict";
import { EventEmitter } from "node:events";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { resolveExternalModRuntimes } from "../../scripts/lib/external-mod-runtimes.mjs";
import { createRuntimeServiceGroups } from "../../scripts/lib/runtime-descriptor-services.mjs";
import { RuntimeSupervisor, SERVICE_STATE } from "../../scripts/lib/runtime-supervisor.mjs";

import {
  sevenCycleLaunch,
  sevenCyclePreparation,
} from "../../scripts/lib/seven-cycle-runtime.mjs";

const workspace = "/projects/cycle";
const endpoint = { port: 14176 };
const localCommand = `${workspace}/.venv/bin/seven-cycle`;
const seed = `${workspace}/scripts/build_seed_catalog.py`;
const exists = (candidate) => [localCommand, `${workspace}/.venv/bin/python`, seed].includes(candidate);

test("installed candidate uses only its executable and explicit product paths", () => {
  const env = {
    NEWMA_DESK_SEVEN_CYCLE_EXECUTABLE: "/isolated/venv/bin/seven-cycle",
    NEWMA_DESK_SEVEN_CYCLE_PRODUCT_ROOT: "/isolated/products",
    NEWMA_DESK_SEVEN_CYCLE_WEB_ROOT: "/isolated/web/dist",
  };
  const configuredExists = (candidate) => candidate === env.NEWMA_DESK_SEVEN_CYCLE_EXECUTABLE;
  assert.deepEqual(sevenCycleLaunch({ workspace, endpoint, env, exists: configuredExists }), {
    command: env.NEWMA_DESK_SEVEN_CYCLE_EXECUTABLE,
    commandArgs: ["serve", "--host", "127.0.0.1", "--port", "14176",
      "--product-root", "/isolated/products", "--catalog-root", "/isolated/products/catalogs",
      "--web-root", "/isolated/web/dist"],
  });
  assert.equal(sevenCyclePreparation({ workspace, env, exists: configuredExists }), null);
});

test("legacy snapshot keeps its command and seed preparation", () => {
  const launch = sevenCycleLaunch({ workspace, endpoint, env: {}, exists });
  assert.equal(launch.command, localCommand);
  assert.deepEqual(launch.commandArgs, ["serve", "--host", "127.0.0.1", "--port", "14176"]);
  assert.deepEqual(sevenCyclePreparation({ workspace, env: {}, exists }), {
    command: `${workspace}/.venv/bin/python`, commandArgs: ["scripts/build_seed_catalog.py"],
  });
});

test("native project without the Desk-only seed script has no preparation", () => {
  assert.equal(sevenCyclePreparation({ workspace, env: {}, exists: (p) => p !== seed }), null);
});

test("explicit data roots never run the workspace seed script", () => {
  const env = { NEWMA_DESK_SEVEN_CYCLE_PRODUCT_ROOT: "candidate/products" };
  const launch = sevenCycleLaunch({ workspace, endpoint, env, exists });
  assert.ok(launch.commandArgs.includes(`${workspace}/candidate/products`));
  assert.ok(launch.commandArgs.includes(`${workspace}/candidate/products/catalogs`));
  assert.ok(launch.commandArgs.includes(`${workspace}/web/dist`));
  assert.equal(sevenCyclePreparation({ workspace, env, exists }), null);
});

test("missing explicitly selected executable fails instead of falling back", () => {
  assert.throws(() => sevenCycleLaunch({ workspace, endpoint, exists,
    env: { NEWMA_DESK_SEVEN_CYCLE_EXECUTABLE: "/missing/seven-cycle" },
  }), /Seven Cycle.*executable/);
});

test("compatible env aliases, explicit catalog and repair flag are retained", () => {
  const env = {
    VIBEDESK_SEVEN_CYCLE_PRODUCT_ROOT: "/alias/products",
    NEWMA_DOCK_SEVEN_CYCLE_CATALOG_ROOT: "/alias/catalogs",
    NEWMA_DESK_SEVEN_CYCLE_PRODUCT_ROOT: "/chosen/products",
  };
  const launch = sevenCycleLaunch({ workspace, endpoint, env, exists, repairCatalogOnStart: true });
  assert.ok(launch.commandArgs.includes("/chosen/products"));
  assert.ok(!launch.commandArgs.includes("/alias/products"));
  assert.ok(launch.commandArgs.includes("/alias/catalogs"));
  assert.equal(launch.commandArgs.at(-1), "--repair-catalog-on-start");
});

test("legacy source without a local install preserves the uv launch", () => {
  assert.deepEqual(sevenCycleLaunch({ workspace, endpoint, env: {}, exists: () => false }), {
    command: "uv", commandArgs: ["run", "seven-cycle", "serve", "--host", "127.0.0.1", "--port", "14176"],
  });
  assert.deepEqual(sevenCyclePreparation({ workspace, env: {}, exists: (p) => p === seed }), {
    command: "uv", commandArgs: ["run", "python", "scripts/build_seed_catalog.py"],
  });
});

test("the actual Desk descriptor recovers the same installed candidate without seed preparation", async () => {
  const input = JSON.parse(await readFile(new URL("../../config/external-mod-runtimes.json", import.meta.url), "utf8"));
  const env = {
    NEWMA_DESK_SEVEN_CYCLE_WORKSPACE: "/candidate/runtime",
    NEWMA_DESK_SEVEN_CYCLE_EXECUTABLE: "/candidate/venv/bin/seven-cycle",
    NEWMA_DESK_SEVEN_CYCLE_WEB_URL: "http://127.0.0.1:14176",
    NEWMA_DESK_SEVEN_CYCLE_PRODUCT_ROOT: "/candidate/products",
    NEWMA_DESK_SEVEN_CYCLE_WEB_ROOT: "/candidate/dist",
  };
  const catalog = resolveExternalModRuntimes(input, { repoRoot: "/desk", homeDir: "/user", env, exists: () => true });
  const runtime = catalog.byId["seven-cycle"];
  let prepared = false;
  const [service] = createRuntimeServiceGroups({ runtimes: [runtime] }, {
    env, exists: () => true, launchAdapters: { "seven-cycle": sevenCycleLaunch },
    prepareAdapters: { "seven-cycle": (options) => {
      prepared = true;
      assert.equal(sevenCyclePreparation({ ...options, env, exists: () => true }), null);
    } },
  })["seven-cycle"];
  assert.equal(service.command, env.NEWMA_DESK_SEVEN_CYCLE_EXECUTABLE);
  assert.equal(service.cwd, env.NEWMA_DESK_SEVEN_CYCLE_WORKSPACE);
  assert.equal(service.url, "http://127.0.0.1:14176/healthz");
  assert.ok(service.commandArgs.includes("/candidate/products/catalogs"));
  await service.prepare();
  assert.equal(prepared, true);

  // Exercise recovery after reuse, not just command generation. No real process
  // is stopped or launched; the installed package and paired roots must survive.
  const states = [SERVICE_STATE.READY, SERVICE_STATE.UNAVAILABLE, SERVICE_STATE.READY];
  const launches = [];
  service.probe = async () => ({ state: states.shift() ?? SERVICE_STATE.READY });
  const supervisor = new RuntimeSupervisor({
    monitorIntervalMs: 0, monitorFailureThreshold: 1, restartGraceMs: 0,
    platform: "win32", endpointOccupied: async () => false,
    logger: { log() {}, error() {} },
    spawnImpl: (command, commandArgs, options) => {
      launches.push({ command, commandArgs, cwd: options.cwd });
      const child = new EventEmitter();
      child.exitCode = null;
      child.signalCode = null;
      child.kill = (signal) => {
        child.signalCode = signal;
        child.emit("exit", null, signal);
      };
      return child;
    },
  });
  try {
    assert.equal((await supervisor.start(service)).launch, "reused");
    assert.equal(launches.length, 0);
    prepared = false;
    assert.equal((await supervisor.monitorNow(service.id)).state, SERVICE_STATE.READY);
    assert.equal(prepared, true);
    assert.deepEqual(launches, [{
      command: env.NEWMA_DESK_SEVEN_CYCLE_EXECUTABLE,
      commandArgs: ["serve", "--host", "127.0.0.1", "--port", "14176",
        "--product-root", "/candidate/products", "--catalog-root", "/candidate/products/catalogs",
        "--web-root", "/candidate/dist"],
      cwd: env.NEWMA_DESK_SEVEN_CYCLE_WORKSPACE,
    }]);
  } finally {
    await supervisor.stopAll({ graceMs: 0 });
  }
});
