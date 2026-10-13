import { defineConfig } from 'vitest/config';
import { fileURLToPath } from 'node:url';
export default defineConfig({
  resolve:{alias:{'@':fileURLToPath(new URL('./bundled-runtimes/vibe-research/frontend/src',import.meta.url))}},
  test:{include:['tests/unit/earnings-evidence.test.ts','tests/unit/valuation-inputs.test.ts','tests/unit/fund-page-context.test.ts','tests/unit/fund-bridge-navigation.test.ts'],environment:'node'},
});
