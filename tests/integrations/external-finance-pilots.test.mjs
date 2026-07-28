import assert from "node:assert/strict";
import test from "node:test";

import {
  checkConfiguredExternalFinancePilots,
  checkExternalFinancePilotDescriptor,
  loadExternalFinancePilotDescriptor,
} from "../../scripts/lib/external-finance-pilots.mjs";

test("checked-in finance pilots are default-off and satisfy isolation policy", async () => {
  const result = await checkConfiguredExternalFinancePilots();

  assert.equal(result.ok, true, result.errors.join("\n"));
  assert.deepEqual(
    result.pilots.map(({ id, mode, decision }) => ({ id, mode, decision })),
    [
      { id: "daily-stock-analysis", mode: "analysis-only", decision: "no-go" },
      { id: "quantdinger", mode: "paper-only", decision: "no-go" },
    ],
  );
  assert.match(result.warnings.join("\n"), /blocked-unpinned-requirements/);
});

test("validator rejects live trading, secret environments, and reserved ports", async () => {
  const descriptor = await loadExternalFinancePilotDescriptor();
  const unsafe = structuredClone(descriptor);
  const pilot = unsafe.pilots[1];
  pilot.activation.defaultEnabled = true;
  pilot.runtime.origin = "http://127.0.0.1:8911";
  pilot.isolation.environmentAllowlist.push("ALPACA_API_KEY");
  pilot.capabilities.allow.push("trade.execute");

  const result = checkExternalFinancePilotDescriptor(unsafe);

  assert.equal(result.ok, false);
  assert.match(result.errors.join("\n"), /default-disabled/);
  assert.match(result.errors.join("\n"), /reserved port 8911/);
  assert.match(result.errors.join("\n"), /credential environment ALPACA_API_KEY/);
  assert.match(result.errors.join("\n"), /privileged capability trade.execute/);
});

test("validator rejects missing paper-only proof gates", async () => {
  const descriptor = await loadExternalFinancePilotDescriptor();
  const unsafe = structuredClone(descriptor);
  unsafe.pilots[1].acceptanceGates = unsafe.pilots[1].acceptanceGates.filter(
    (gate) => !["paper-only-proof", "credential-isolation"].includes(gate),
  );

  const result = checkExternalFinancePilotDescriptor(unsafe);

  assert.equal(result.ok, false);
  assert.match(result.errors.join("\n"), /paper-only-proof/);
  assert.match(result.errors.join("\n"), /credential-isolation/);
});
