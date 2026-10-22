import { defineConfig } from 'vitest/config';
import { fileURLToPath } from 'node:url';
export default defineConfig({
  resolve:{dedupe:['react','react-dom'],alias:{
    '@':fileURLToPath(new URL('./bundled-runtimes/vibe-research/frontend/src',import.meta.url)),
    // 使用研究项目已安装的ESM Router，避免其CJS入口加载第二份React。
    'react-router-dom':fileURLToPath(new URL('./bundled-runtimes/vibe-research/frontend/node_modules/react-router-dom/dist/index.mjs',import.meta.url)),
    'react-router/dom':fileURLToPath(new URL('./bundled-runtimes/vibe-research/frontend/node_modules/react-router/dist/development/dom-export.mjs',import.meta.url)),
    'react-router':fileURLToPath(new URL('./bundled-runtimes/vibe-research/frontend/node_modules/react-router/dist/development/index.mjs',import.meta.url)),
  }},
  esbuild:{jsx:'automatic'},
  test:{server:{deps:{inline:[/react-router/]}},include:['tests/unit/catalyst-calendar.test.tsx','tests/unit/catalyst-storage-auth.test.ts','tests/unit/research-data-auth.test.ts','tests/unit/crucix-auth.test.ts','tests/unit/macro-liquidity.test.tsx','tests/unit/idea-funnel.test.tsx','tests/unit/peer-review.test.ts','tests/unit/peer-storage.test.tsx','tests/unit/research-data.test.ts','tests/unit/research-analysis.test.ts','tests/unit/research-backup.test.tsx','tests/unit/earnings-storage.test.tsx','tests/unit/valuation-storage.test.tsx','tests/unit/research-input-auth.test.tsx','tests/unit/research-files.test.tsx','tests/unit/industry-workspace.test.ts','tests/unit/industry-artifact.test.ts','tests/unit/earnings-evidence.test.ts','tests/unit/valuation-inputs.test.ts','tests/unit/fund-page-context.test.ts','tests/unit/fund-bridge-navigation.test.ts','tests/unit/fund-flow-window.test.ts','tests/unit/stock-data.test.tsx','tests/unit/research-layout.test.tsx','tests/unit/research-watchlist.test.tsx','tests/unit/research-memo.test.tsx','tests/unit/thesis-tracker.test.tsx','tests/unit/research-bridge-config.test.ts'],environment:'node'},
});
