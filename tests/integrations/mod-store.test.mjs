import assert from "node:assert/strict";
import test from "node:test";

import {
  loadModStore,
  manifestsEqual,
  registerDefaultMods,
  standardizeDefaultMods,
} from "../../scripts/lib/mod-store.mjs";

function response(body, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

test("validates the project Mod store and keeps only three default examples", async () => {
  const store = await loadModStore({
    env: {
      VIBEDESK_INVESTMENT_WEB_URL: "https://investment.example",
      VIBEDESK_TRADING_WEB_URL: "https://trading.example",
    },
  });
  const defaults = store.mods.filter((mod) => mod.defaultInstall);

  assert.equal(store.mods.length, 17);
  assert.deepEqual(defaults.map((mod) => mod.id), [
    "daily-review",
    "alpha-lab",
    "watchlist",
  ]);
  assert.equal(
    store.mods.find((mod) => mod.id === "daily-review").manifest.entry.url,
    "https://investment.example/daily-review",
  );
  assert.equal(
    store.mods.find((mod) => mod.id === "alpha-lab").manifest.entry.url,
    "https://trading.example/alpha-zoo",
  );
  assert.equal(
    store.mods.find((mod) => mod.id === "market-daily").manifest.entry.url,
    "/mods/market-daily/",
  );
});

test("rejects unsafe configured external Mod origins", async () => {
  await assert.rejects(
    loadModStore({
      env: { VIBEDESK_INVESTMENT_WEB_URL: "https://user:pass@example.com" },
    }),
    /must be an HTTP\(S\) origin/,
  );
});

test("registers only default examples and skips identical published Mods", async () => {
  const store = await loadModStore();
  const desired = store.mods.filter((mod) => mod.defaultInstall).map((mod) => mod.manifest);
  const existing = {
    moduleId: desired[0].id,
    revision: 1,
    status: "published",
    manifest: desired[0],
    createdAt: "2026-07-21T00:00:00Z",
  };
  const calls = [];
  let revision = 1;
  const fetchImpl = async (url, init = {}) => {
    calls.push({ url: String(url), init });
    if (!init.method) return response([existing]);
    if (String(url).endsWith("/drafts")) return response({ revision: ++revision }, 201);
    return response({ status: "published" });
  };

  const result = await registerDefaultMods({ fetchImpl });

  assert.equal(result.skipped.length, 1);
  assert.equal(result.created.length, 2);
  assert.equal(calls.filter((call) => call.init.method === "POST").length, 4);
  assert.equal(manifestsEqual(existing.manifest, desired[0]), true);
});

test("standardizes only official store Mods and preserves third-party Mods", async () => {
  const store = await loadModStore();
  const defaults = store.mods.filter((mod) => mod.defaultInstall).map((mod) => mod.manifest);
  const current = [
    ...defaults.map((manifest, index) => ({
      moduleId: manifest.id,
      revision: index + 1,
      status: "published",
      manifest,
      createdAt: "2026-07-21T00:00:00Z",
    })),
    {
      moduleId: "news-radar",
      revision: 4,
      status: "published",
      manifest: store.mods.find((mod) => mod.id === "news-radar").manifest,
      createdAt: "2026-07-21T00:00:00Z",
    },
    {
      moduleId: "third-party",
      revision: 1,
      status: "published",
      manifest: { id: "third-party" },
      createdAt: "2026-07-21T00:00:00Z",
    },
  ];
  const calls = [];
  const fetchImpl = async (url, init = {}) => {
    calls.push({ url: String(url), init });
    if (!init.method) return response(current);
    return response({ status: "disabled" });
  };

  const result = await standardizeDefaultMods({ fetchImpl });

  assert.deepEqual(result.disabled, ["news-radar"]);
  assert.equal(
    calls.some((call) => call.url.endsWith("/api/mods/third-party/disable")),
    false,
  );
});
