import assert from "node:assert/strict";
import test from "node:test";

import {
  loadFirstPartyMods,
  manifestsEqual,
  registerFirstPartyMods,
} from "../../scripts/lib/first-party-mods.mjs";

function response(body, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

test("builds the first Vibe Investment and Vibe Trading Mods", async () => {
  const integrations = await loadFirstPartyMods({
    env: {
      VIBEDESK_INVESTMENT_WEB_URL: "https://investment.example",
      VIBEDESK_TRADING_WEB_URL: "https://trading.example",
    },
  });

  assert.equal(integrations.length, 2);
  assert.equal(integrations[0].id, "vibe-investment");
  assert.equal(integrations[0].manifests.length, 9);
  assert.equal(integrations[1].id, "vibe-trading");
  assert.equal(integrations[1].manifests.length, 7);
  assert.equal(
    integrations[0].manifests.find((mod) => mod.id === "daily-review").entry.url,
    "https://investment.example/daily-review",
  );
  assert.equal(
    integrations[1].manifests.find((mod) => mod.id === "alpha-lab").entry.url,
    "https://trading.example/alpha-zoo",
  );
});

test("rejects unsafe first-party origins", async () => {
  await assert.rejects(
    loadFirstPartyMods({
      env: { VIBEDESK_INVESTMENT_WEB_URL: "https://user:pass@example.com" },
    }),
    /must be an HTTP\(S\) origin/,
  );
});

test("registers changed Mods and skips identical published Mods", async () => {
  const integrations = await loadFirstPartyMods();
  const desired = integrations.flatMap((integration) => integration.manifests);
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
    if (String(url).endsWith("/drafts")) {
      revision += 1;
      return response({ revision }, 201);
    }
    return response({ status: "published" });
  };

  const result = await registerFirstPartyMods({ fetchImpl });

  assert.equal(result.skipped.length, 1);
  assert.equal(result.created.length, desired.length - 1);
  assert.equal(
    calls.filter((call) => call.init.method === "POST").length,
    (desired.length - 1) * 2,
  );
  assert.equal(manifestsEqual(existing.manifest, desired[0]), true);
});
