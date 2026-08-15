import assert from "node:assert/strict";
import test from "node:test";

import { checkShellModDependencies } from "../../scripts/check-shell-mod-dependencies.mjs";


test("Shell keeps business Mod imports limited to the two embedded exceptions", async () => {
  assert.deepEqual(await checkShellModDependencies(), []);
});
