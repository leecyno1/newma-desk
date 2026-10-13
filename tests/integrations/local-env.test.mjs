import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import test from "node:test";

const loader = new URL("../../scripts/lib/local-env.mjs", import.meta.url).href;

test("local configuration loads from the repo and reaches child services", (t) => {
  const repo = mkdtempSync(path.join(tmpdir(), "desk-env-"));
  t.after(() => rmSync(repo, { recursive: true, force: true }));
  writeFileSync(path.join(repo, ".env"), 'TUSHARE_TOKEN="local-test-token"\nNEWMA_DESK_RUNTIME_PROFILE=core\n');
  const env = { ...process.env, NEWMA_DESK_RUNTIME_PROFILE: "local" };
  delete env.TUSHARE_TOKEN;
  const result = spawnSync(process.execPath, ["--input-type=module", "-e", `
    import { loadLocalEnvironment } from ${JSON.stringify(loader)};
    import { spawnSync } from "node:child_process";
    loadLocalEnvironment(${JSON.stringify(repo)});
    const child = spawnSync(process.execPath, ["-e", 'process.exit(process.env.TUSHARE_TOKEN === "local-test-token" && process.env.NEWMA_DESK_RUNTIME_PROFILE === "local" ? 0 : 1)']);
    process.exit(child.status ?? 1);
  `], { env });
  assert.equal(result.status, 0, result.stderr.toString());
});

test("an absent local configuration is optional", (t) => {
  const repo = mkdtempSync(path.join(tmpdir(), "desk-env-"));
  t.after(() => rmSync(repo, { recursive: true, force: true }));
  const result = spawnSync(process.execPath, ["--input-type=module", "-e", `
    import { loadLocalEnvironment } from ${JSON.stringify(loader)};
    loadLocalEnvironment(${JSON.stringify(repo)});
  `]);
  assert.equal(result.status, 0, result.stderr.toString());
});
