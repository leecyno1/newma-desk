# Vibe HTML Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the current Shell and Structured Renderer into the first simple Vibe Web Base by moving navigation metadata into Module Manifest, sharing the existing visual tokens, and emitting Agent-readable semantic HTML.

**Architecture:** Extend the existing version-1 Module Manifest compatibly instead of introducing a new platform layer. Keep the current Research/Trading visual direction, extract only shared CSS variables, and enhance the renderer so its browser HTML carries stable `data-vibe-*` semantics and safe embedded chart JSON. Model/Agent Gateway separation remains a separate implementation plan.

**Tech Stack:** React 19, TypeScript, Zod, Vite, ECharts, Vitest, FastAPI/Pydantic compatibility validation

---

## File Structure

- `packages/contracts/src/module.ts` and `services/api/.../schemas.py`: shared optional navigation metadata.
- `packages/ui-foundation/`: CSS variables extracted from the existing dark interface.
- `packages/structured-renderer/`: semantic Vibe HTML output and safe JSON embedding.
- `apps/shell/`: base branding and manifest-driven navigation.
- `modules/market-daily/`: first module using navigation metadata and shared tokens.
- `docs/vibe-html.md`: short author-facing generation rules for future Agents.

### Task 1: Add navigation metadata to Module Manifest

**Files:**
- Modify: `packages/contracts/src/module.ts`
- Modify: `packages/contracts/src/module.test.ts`
- Modify: `services/api/vibe_visualization_api/control_plane/schemas.py`
- Modify: `services/api/tests/control_plane/test_routes.py`
- Modify: `modules/market-daily/module.json`

- [x] **Step 1: Write failing TypeScript contract tests**

Add a manifest fixture containing:

```ts
navigation: {
  groupLabel: "市场",
  groupOrder: 20,
  itemOrder: 10,
  icon: "market",
}
```

Assert parsing preserves the object, rejects negative order values, rejects unknown navigation fields, and keeps existing manifests without `navigation` valid.

- [x] **Step 2: Run the contract test and confirm failure**

Run: `npm run test:run -w @vibe-visualization/contracts -- module.test.ts`

Expected: the navigation fixture is stripped or rejected because the schema does not yet declare `navigation`.

- [x] **Step 3: Implement the TypeScript schema**

Add:

```ts
export const moduleNavigationSchema = z.object({
  groupLabel: z.string().min(1).max(40),
  groupOrder: z.number().int().nonnegative().default(100),
  itemOrder: z.number().int().nonnegative().default(100),
  icon: z.enum(["research", "market", "quant", "module"]).default("module"),
}).strict();
```

Add `navigation: moduleNavigationSchema.optional()` to `moduleManifestSchema`.

- [x] **Step 4: Add matching Pydantic validation and API coverage**

Create `ModuleNavigation` with camel-case aliases and the same limits, then add:

```py
navigation: ModuleNavigation | None = None
```

to `ModuleManifest`. Extend the draft route test to assert navigation survives repository serialization.

- [x] **Step 5: Update market-daily and run both suites**

Run:

```bash
npm run test:run -w @vibe-visualization/contracts
services/api/.venv/bin/pytest services/api/tests/control_plane/test_routes.py -q
```

Expected: all tests pass.

- [x] **Step 6: Commit**

```bash
git add packages/contracts services/api/vibe_visualization_api/control_plane/schemas.py services/api/tests/control_plane/test_routes.py modules/market-daily/module.json
git commit -m "feat: describe module navigation in manifests"
```

### Task 2: Make the Shell a manifest-driven Vibe Visualization base

**Files:**
- Modify: `apps/shell/src/components/Sidebar.tsx`
- Modify: `apps/shell/src/App.test.tsx`
- Modify: `apps/shell/src/styles.css`

- [x] **Step 1: Write failing Shell tests**

Create published modules with non-default navigation values and assert:

```text
- groupLabel is rendered instead of the category key;
- groupOrder controls group order;
- itemOrder controls module order;
- a manifest without navigation still renders under its category;
- the brand says Vibe Visualization and Web Base.
```

- [x] **Step 2: Run the Shell tests and confirm failure**

Run: `npm run test:run -w @vibe-visualization/shell -- App.test.tsx`

Expected: fixed Research/Market/Quant labels and module-id sorting do not satisfy the new expectations.

- [x] **Step 3: Implement manifest-driven navigation**

Replace fixed category label/order lookup with values derived from each group's first sorted manifest navigation object. Sort modules by `navigation.itemOrder`, then `moduleId`. Map only the stable icon keys to Lucide icons; unknown or absent navigation uses the existing Boxes icon.

Change the brand copy to:

```tsx
<strong>Vibe Visualization</strong>
<small>Web Base</small>
```

- [x] **Step 4: Run Shell tests**

Run: `npm run test:run -w @vibe-visualization/shell`

Expected: 40 existing tests plus the new navigation assertions pass.

- [x] **Step 5: Commit**

```bash
git add apps/shell
git commit -m "feat: make shell navigation module-driven"
```

### Task 3: Extract the existing visual tokens

**Files:**
- Create: `packages/ui-foundation/package.json`
- Create: `packages/ui-foundation/src/tokens.css`
- Modify: `apps/shell/package.json`
- Modify: `apps/shell/src/main.tsx`
- Modify: `apps/shell/src/styles.css`
- Modify: `modules/market-daily/package.json`
- Modify: `modules/market-daily/src/main.tsx`
- Modify: `modules/market-daily/src/styles.css`
- Modify: `package-lock.json`

- [x] **Step 1: Create the CSS-only workspace package**

Define package export `./tokens.css` and extract the current values into variables including:

```css
:root {
  --vibe-bg: #0d1011;
  --vibe-surface: #121516;
  --vibe-surface-raised: #171a1b;
  --vibe-border: #272a2c;
  --vibe-text: #eef1f0;
  --vibe-text-muted: #8c9496;
  --vibe-positive: #e66a62;
  --vibe-negative: #49b68f;
  --vibe-radius-sm: 8px;
  --vibe-radius-md: 12px;
  --vibe-font-ui: Inter, "PingFang SC", "Microsoft YaHei", sans-serif;
  --vibe-font-mono: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
}
```

- [x] **Step 2: Import tokens into Shell and market-daily**

Import `@vibe-visualization/ui-foundation/tokens.css` before each local stylesheet and replace the repeated root palette/font declarations with the shared variables. Do not change layout, spacing, or visible hierarchy in this task.

- [x] **Step 3: Install workspace metadata and verify builds**

Run:

```bash
npm install
npm run build -w @vibe-visualization/shell
npm run build -w @vibe-visualization/market-daily
```

Expected: both builds exit 0 with unchanged page structure.

- [x] **Step 4: Commit**

```bash
git add packages/ui-foundation apps/shell modules/market-daily package-lock.json
git commit -m "feat: share vibe visualization design tokens"
```

### Task 4: Emit semantic Vibe HTML from the Structured Renderer

**Files:**
- Create: `packages/structured-renderer/src/embeddedJson.ts`
- Create: `packages/structured-renderer/src/embeddedJson.test.ts`
- Modify: `packages/structured-renderer/src/StructuredView.tsx`
- Modify: `packages/structured-renderer/src/StructuredView.test.tsx`
- Modify: `packages/structured-renderer/src/blocks/ChartBlock.tsx`
- Modify: `packages/structured-renderer/src/blocks/MetricsBlock.tsx`
- Modify: `packages/structured-renderer/src/blocks/TableBlock.tsx`
- Modify: `packages/structured-renderer/src/blocks/MarkdownBlock.tsx`
- Modify: `packages/structured-renderer/src/blocks/FiltersBlock.tsx`
- Modify: `packages/structured-renderer/src/blocks/ActionsBlock.tsx`

- [x] **Step 1: Write failing semantic HTML tests**

Assert the rendered document contains:

```text
data-vibe-page="1.0"
data-vibe-title="..."
data-vibe-block="metrics|table|chart|markdown|filters|actions"
data-vibe-block-id="..."
```

For charts, assert a `script[type="application/json"][data-vibe-chart-option]` element contains parseable JSON matching the chart option.

- [x] **Step 2: Write safe embedded JSON tests**

Define:

```ts
export function serializeEmbeddedJson(value: unknown): string
```

Tests must confirm round-trip parsing and confirm the serialized result contains none of literal `<`, `>`, `&`, U+2028, or U+2029 characters, including an input such as `</script><script>alert(1)</script>`.

- [x] **Step 3: Run renderer tests and confirm failure**

Run: `npm run test:run -w @vibe-visualization/structured-renderer`

Expected: semantic attributes and serializer do not exist.

- [x] **Step 4: Implement safe serialization and semantic attributes**

Use JSON serialization followed by replacements:

```ts
return JSON.stringify(value)
  .replaceAll("<", "\\u003c")
  .replaceAll(">", "\\u003e")
  .replaceAll("&", "\\u0026")
  .replaceAll("\u2028", "\\u2028")
  .replaceAll("\u2029", "\\u2029");
```

Add stable attributes to the page and every block. In `ChartBlock`, render the visual chart and a non-executable JSON script using `dangerouslySetInnerHTML` only with `serializeEmbeddedJson(option)`.

- [x] **Step 5: Run renderer and market tests**

Run:

```bash
npm run test:run -w @vibe-visualization/structured-renderer
npm run test:run -w @vibe-visualization/market-daily
```

Expected: all tests pass and the existing chart remains visible.

- [x] **Step 6: Commit**

```bash
git add packages/structured-renderer
git commit -m "feat: emit semantic vibe html"
```

### Task 5: Document the first Agent-facing HTML convention

**Files:**
- Create: `docs/vibe-html.md`
- Modify: `docs/superpowers/plans/2026-07-20-vibe-html-foundation.md`

- [x] **Step 1: Write the author guide**

Document:

```text
- use Structured Renderer before generating a custom static app;
- use ECharts for standard charts;
- use semantic table and text fallbacks for visual-only content;
- preserve data time and source in page data;
- keep stable block IDs across revisions;
- use the shared CSS tokens;
- do not put secrets in HTML;
- structured, static, and external module selection rules;
- future extension choices: Cytoscape.js, React Three Fiber, MapLibre.
```

Include one complete industry-chain page outline and one quant/backtest page outline using existing block types.

- [x] **Step 2: Run full verification**

Run:

```bash
npm test
npm run typecheck
npm run build
services/api/.venv/bin/pytest services/api/tests -q
npm run test:e2e
git diff --check
```

Expected: all commands exit 0.

- [x] **Step 3: Mark completed checkboxes and commit**

```bash
git add docs
git commit -m "docs: define the vibe html foundation"
```

## Completion Gate

- A module controls its own sidebar label, order, and icon through Manifest.
- The Shell identifies itself as Vibe Visualization Web Base.
- Shell and market-daily share the extracted current design tokens.
- Structured Renderer emits stable machine-readable HTML semantics.
- Chart options are embedded safely as non-executable JSON.
- The existing market module works directly and embedded with no visual redesign.
- Model/Agent Gateway separation is documented but not partially implemented in this plan.
