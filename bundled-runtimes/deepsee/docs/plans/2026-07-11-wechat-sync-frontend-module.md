# WeChat Sync Frontend Module Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task.

**Goal:** Extract the WeChat track policy and manual-sync orchestration from the large inline script into `static/modules/wechat-sync.js` without changing UI behavior or existing global call sites.

**Architecture:** Add one dependency-light browser IIFE that owns WeChat track state and exposes a frozen `window.WechatSyncModule` API. Keep small global compatibility wrappers in `static/index.html` so existing inline event bindings and old callers retain the same function names. The module resolves shared page helpers from `window` only when a function is invoked, because those helpers are declared later by the main inline script.

**Tech Stack:** Vanilla browser JavaScript, FastAPI static files, pytest source-contract tests, Node.js syntax/runtime smoke checks.

---

## Constraints

- Do not alter layout, CSS, labels, endpoint paths, request payloads, loading text, cancellation behavior, or message refresh/derive behavior.
- Patch only the WeChat sync implementation blocks and the new script include in `static/index.html`; preserve all unrelated user edits.
- Keep `pullFromChatlogDays` and every existing public function name callable from the global scope.
- Do not move gateway configuration, trigger rules, message rendering, compare, or send-management logic.
- Do not stage, commit, reset, or overwrite the working tree.
- Never write tests to `data/app.db`.

## Task 1: Lock the extraction contract with failing tests

**Files:**

- Create: `tests/test_wechat_sync_frontend_module.py`
- Read: `static/index.html:22392-22619`
- Read: `static/index.html:24718-24766`
- Read: `static/index.html:25006-25090`

**Step 1: Add source-boundary tests**

Add tests that require:

```python
MODULE_JS = PROJECT_ROOT / "static" / "modules" / "wechat-sync.js"

assert MODULE_JS.exists()
assert '<script src="/static/modules/wechat-sync.js"></script>' in index_source
assert index_source.index('/static/modules/wechat-sync.js') < index_source.index(
    'function normalizeWechatTrackPolicy'
)
assert 'const WECHAT_TRACK_DEFS' not in index_source
assert 'window.WechatSyncModule' in module_source
```

Assert that the inline implementations are replaced by thin wrappers for:

```text
normalizeWechatTrackPolicy
renderWechatTrackOrder
collectWechatTrackPolicy
updateWechatTrackPolicySummary
moveWechatTrack
moveWechatTrackBefore
renderWechatDualTrackState
loadWechatDualTrackState
saveWechatDualTrackPolicy
runWechatDualTrackSync
syncIncrementalAndReload
```

Also assert that `pullFromChatlogDays(days, pullOp)` remains and delegates to `syncIncrementalAndReload(days, pullOp)`.

**Step 2: Add module API and behavior smoke tests**

Use `node --check static/modules/wechat-sync.js` and a small Node `vm` harness to evaluate the IIFE with a synthetic `window`. Verify at least:

```javascript
const normalized = window.WechatSyncModule.normalizeTrackPolicy({mode: 'chatlog_only'});
assert.deepStrictEqual(normalized.order, ['chatlog', 'wx_cli', 'wechatapi']);
assert.deepStrictEqual(normalized.enabled, ['chatlog', 'wx_cli']);
assert.strictEqual(normalized.useMultiple, false);
```

Verify the public API is frozen and exposes all methods used by the wrappers.

**Step 3: Run the new tests and confirm RED**

Run:

```bash
pytest -q tests/test_wechat_sync_frontend_module.py
```

Expected: fail because `static/modules/wechat-sync.js` and the script include do not yet exist.

## Task 2: Create the standalone WeChat sync module

**Files:**

- Create: `static/modules/wechat-sync.js`
- Test: `tests/test_wechat_sync_frontend_module.py`

**Step 1: Add the IIFE and owned state**

Use this shape:

```javascript
(function initWechatSyncModule(global) {
    'use strict';

    const TRACK_DEFS = Object.freeze([
        Object.freeze({key: 'wechatapi', label: 'WeChat API', kind: '云端实时回调'}),
        Object.freeze({key: 'chatlog', label: 'chatlog_alpha', kind: '本地历史补齐'}),
        Object.freeze({key: 'wx_cli', label: 'wx-cli', kind: '本地 CLI 读取'}),
    ]);

    let trackOrder = TRACK_DEFS.map(item => item.key);
    let enabledTracks = new Set(trackOrder);
```

Do not perform DOM queries, network requests, or event binding at module load time.

**Step 2: Move the track policy/UI functions unchanged in behavior**

Move the logic currently implemented by:

```text
normalizeWechatTrackPolicy
renderWechatTrackOrder
collectWechatTrackPolicy
updateWechatTrackPolicySummary
moveWechatTrack
moveWechatTrackBefore
renderWechatDualTrackState
```

Use a local HTML escaping fallback when `window.escapeHtml` is not yet defined; otherwise delegate to the page helper.

**Step 3: Move state/policy/run requests unchanged in behavior**

Move:

```text
loadWechatDualTrackState
saveWechatDualTrackPolicy
runWechatDualTrackSync
syncIncrementalAndReload
```

Resolve existing helpers dynamically from `global` at call time. Preserve these endpoints and request semantics exactly:

```text
GET  /api/sync/wechat/dual-track/state
POST /api/sync/wechat/dual-track/policy
POST /api/sync/wechat/dual-track?days=N
```

Preserve pull cancellation, status messages, post-sync message reload, dashboard refresh, auto-derive, and filter reset behavior.

**Step 4: Export one explicit API**

Expose only:

```javascript
global.WechatSyncModule = Object.freeze({
    normalizeTrackPolicy,
    renderTrackOrder,
    collectTrackPolicy,
    updateTrackPolicySummary,
    moveTrack,
    moveTrackBefore,
    renderDualTrackState,
    loadDualTrackState,
    saveDualTrackPolicy,
    runDualTrackSync,
    syncIncrementalAndReload,
});
```

Do not also write the legacy names directly onto `window`; compatibility stays visible in `index.html`.

## Task 3: Replace inline implementations with compatibility wrappers

**Files:**

- Modify: `static/index.html:10653`
- Modify: `static/index.html:22392-22619`
- Modify: `static/index.html:24718-24766`
- Test: `tests/test_wechat_sync_frontend_module.py`

**Step 1: Load the module before the main application script**

Insert immediately before the main body script:

```html
<script src="/static/modules/wechat-sync.js"></script>
```

The static mount already serves all files under `/static`.

**Step 2: Replace the first implementation block with thin wrappers**

Use wrappers of this form:

```javascript
function normalizeWechatTrackPolicy(policy = {}) {
    return window.WechatSyncModule.normalizeTrackPolicy(policy);
}

async function loadWechatDualTrackState(silent = false) {
    return window.WechatSyncModule.loadDualTrackState(silent);
}
```

Each wrapper must contain only delegation. Keep the legacy function name, defaults, async return shape, and argument order.

**Step 3: Replace `syncIncrementalAndReload` with a thin wrapper**

```javascript
async function syncIncrementalAndReload(days = 7, pullOp = null) {
    return window.WechatSyncModule.syncIncrementalAndReload(days, pullOp);
}
```

Leave `pullFromChatlogDays` as the existing old-name wrapper and leave `initMessageListButtons` wiring in place.

**Step 4: Run extraction tests**

Run:

```bash
pytest -q tests/test_wechat_sync_frontend_module.py
```

Expected: pass.

## Task 4: Regression and boundary verification

**Files:**

- Test: `tests/test_frontend_module_copy.py`
- Test: `tests/test_wechat_gateway_frontend.py`
- Test: `tests/test_wechat_gateway_settings_modules.py`
- Test: `tests/test_production_guardrails.py`

**Step 1: Run frontend source-contract regressions**

Run:

```bash
pytest -q \
  tests/test_wechat_sync_frontend_module.py \
  tests/test_frontend_module_copy.py \
  tests/test_wechat_gateway_frontend.py \
  tests/test_wechat_gateway_settings_modules.py \
  tests/test_production_guardrails.py
```

Use a temporary `DATABASE_URL` for all tests.

**Step 2: Parse both JavaScript surfaces**

Run:

```bash
node --check static/modules/wechat-sync.js
```

Extract the main body script to a temporary file and run `node --check` against it, so wrapper replacement cannot leave an unbalanced brace or template literal.

**Step 3: Verify the narrow diff**

Confirm:

```text
static/modules/wechat-sync.js   new module only
static/index.html               one script include + compatibility wrappers only
tests/test_wechat_sync_frontend_module.py
```

Unrelated sections of `static/index.html`, `app/routers/ai.py`, and `app/services/hermes_bridge.py` must retain their pre-task content. The working tree must remain unstaged and uncommitted.

