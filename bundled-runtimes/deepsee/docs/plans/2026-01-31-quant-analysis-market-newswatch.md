# Quantitative Analysis (Market + Newswatch) Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a “量化分析” section to AI Summary for `market` and `newswatch`, showing stance distribution (e.g., 60% 看好 / 40% 看空) per topic + simple inline visualization, while keeping `#<id>` badges clickable for jump/popover.

**Architecture:** Extend the LLM output schema to include a `quant` block (topic → stance → ids), then render a deterministic “quant section” server-side (Markdown + safe HTML bars). Frontend continues to convert `#id` into badges and supports popover/jump as today.

**Tech Stack:** FastAPI, existing SiliconFlow LLM call path (`app/routers/ai.py` + `app/services/llm_client.py`), minimal HTML-in-Markdown rendering via `marked` in `static/index.html`, pytest.

---

## Quant Schema (v1)

We enforce structured quant output from the model to avoid unreliable parsing from prose.

### For `market`

```json
{
  "markdown": "…",
  "quant": {
    "topics": [
      {
        "topic": "贵金属暴跌",
        "bullish_ids": ["31874", "31891"],
        "bearish_ids": ["31911"],
        "neutral_ids": []
      }
    ]
  }
}
```

### For `newswatch`

Same schema but stance labels map to **利好/利空/中性** (still represented as bullish/bearish/neutral for unified renderer):

```json
{
  "markdown": "…",
  "quant": {
    "topics": [
      {
        "topic": "黄金突破",
        "bullish_ids": ["3043446"],
        "bearish_ids": [],
        "neutral_ids": ["3043030"]
      }
    ]
  }
}
```

Constraints:
- `topic` length 4–18 chars preferred.
- `*_ids` must be strings; allow numeric strings.
- Each topic’s ids must be de-duplicated.
- Topics should reference ids that also appear in markdown via `#<id>` or `#id` whenever possible.

---

## Rendering Format (Markdown + Safe HTML)

The backend generates a deterministic quant section appended to `market_markdown` and `newswatch_markdown`:

```md
## 量化分析

| 议题 | 样本 | 看好 | 看空 | 中性 |
| --- | ---: | ---: | ---: | ---: |
| 贵金属暴跌 | 10 | 60% (6) | 40% (4) | 0% (0) |

<div class="quant-bars" data-topic="贵金属暴跌">
  <div class="quant-bar bullish" style="width:60%"><span>看好 60%</span></div>
  <div class="quant-bar bearish" style="width:40%"><span>看空 40%</span></div>
</div>

证据：
- 看好：#<id> #<id>
- 看空：#<id>
```

Why HTML-in-Markdown:
- Stable visuals without extra chart libs.
- Keeps existing clickable badge behavior (`#id` → `.msg-badge`) and popovers.

---

### Task 1: Update prompts to output `quant` (market + newswatch)

**Files:**
- Modify: `data/ai_config.json` (runtime config; do not commit)
- Modify: `app/services/llm_client.py` (defaults, so fresh installs inherit)

**Step 1: Write failing tests for prompt templates (static checks)**

Create `tests/test_quant_prompts.py`:

```python
import json
from app.services.llm_client import DEFAULT_MODULE_PROMPTS

def test_market_prompt_requires_quant_json():
    u = DEFAULT_MODULE_PROMPTS["market"]["user"]
    assert "\"quant\"" in u
    assert "\"markdown\"" in u

def test_newswatch_prompt_requires_quant_json():
    u = DEFAULT_MODULE_PROMPTS["newswatch"]["user"]
    assert "\"quant\"" in u
    assert "## 海外/地缘" in u
```

**Step 2: Run to verify it fails**

Run: `pytest -q tests/test_quant_prompts.py`
Expected: FAIL (defaults not yet updated).

**Step 3: Update default prompts**

In `app/services/llm_client.py`, update `DEFAULT_MODULE_PROMPTS["market"]` and `["newswatch"]`:
- Require output JSON `{ "markdown": string, "quant": { "topics": [...] } }`
- Add explicit instructions: ids must map to stance buckets; max topics (e.g. 6-12).

**Step 4: Update runtime prompts (optional but recommended)**

Update `data/ai_config.json` (local runtime) similarly so the currently running instance uses it.

**Step 5: Run tests**

Run: `pytest -q tests/test_quant_prompts.py`
Expected: PASS.

**Step 6: Commit (code only; do NOT commit runtime data)**

```bash
git add app/services/llm_client.py tests/test_quant_prompts.py
git commit -m "feat: add quant schema requirement to market/news prompts"
```

---

### Task 2: Implement quant rendering utility (pure, testable)

**Files:**
- Create: `app/services/quant_analysis.py`
- Test: `tests/test_quant_analysis.py`

**Step 1: Write failing unit tests**

```python
from app.services.quant_analysis import normalize_quant, render_quant_section_markdown

def test_render_quant_section_includes_table_and_bars():
    quant = {
        "topics": [
            {"topic": "贵金属", "bullish_ids": ["1","2","2"], "bearish_ids": ["3"], "neutral_ids": []}
        ]
    }
    q = normalize_quant(quant)
    md = render_quant_section_markdown(q, module="market")
    assert "## 量化分析" in md
    assert "| 议题 |" in md
    assert "quant-bar bullish" in md
    assert "#1" in md or "#<1" in md
```

**Step 2: Run test to verify it fails**

Run: `pytest -q tests/test_quant_analysis.py`
Expected: FAIL (module missing).

**Step 3: Implement minimal utility**

`app/services/quant_analysis.py` responsibilities:
- `normalize_quant(quant: dict) -> dict`: validate schema, dedupe ids, compute counts/percent.
- `render_quant_section_markdown(quant: dict, module: str) -> str`: generate Markdown + safe HTML bars.
- Escape `topic` into HTML safely; never include raw model HTML.

**Step 4: Run tests**

Run: `pytest -q tests/test_quant_analysis.py`
Expected: PASS.

**Step 5: Commit**

```bash
git add app/services/quant_analysis.py tests/test_quant_analysis.py
git commit -m "feat: add quant analysis renderer for ai summary"
```

---

### Task 3: Append quant section in `/api/ai/summary` for market + newswatch

**Files:**
- Modify: `app/routers/ai.py`
- Test: `tests/test_ai_summary_quant_append.py`

**Step 1: Add failing test for append behavior**

Use FastAPI TestClient and monkeypatch LLM call to return a deterministic JSON string:

```python
import json
from fastapi.testclient import TestClient
from app.main import app

def test_ai_summary_market_appends_quant(monkeypatch):
    from app.services import llm_client
    def fake_chat(messages, temperature=0.3, model_override=None, force_json=False):
        return json.dumps({
            "markdown": "# 市场观点总结\\n- A #1\\n",
            "quant": {"topics":[{"topic":"贵金属","bullish_ids":["1"],"bearish_ids":[],"neutral_ids":[]}]}
        }, ensure_ascii=False)
    monkeypatch.setattr(llm_client, "siliconflow_chat", fake_chat)
    c = TestClient(app)
    r = c.post("/api/ai/summary-local", json={"messages":[{"id":1,"derived":{"summary":"ai: x"}}], "modules":["market"], "temperature":0.3, "prompts":{}})
    assert r.status_code == 200
    out = r.json()
    md = (out.get("result") or {}).get("market_markdown","")
    assert "## 量化分析" in md
```

**Step 2: Run test; expect FAIL**

Run: `pytest -q tests/test_ai_summary_quant_append.py`

**Step 3: Implement append logic**

In `app/routers/ai.py` inside `_run_summary_local` parsing path:
- When `parsed` contains both `markdown` and `quant`, call:
  - `normalize_quant(parsed["quant"])`
  - `render_quant_section_markdown(...)`
  - Append to `result[result_key]` with a blank line separator.
- Limit to modules: `market`, `newswatch`.
- If `quant` missing/invalid: do nothing (v1).

**Step 4: Run tests**

Run: `pytest -q tests/test_ai_summary_quant_append.py`
Expected: PASS.

**Step 5: Commit**

```bash
git add app/routers/ai.py tests/test_ai_summary_quant_append.py
git commit -m "feat: append quant section to market/news ai summary"
```

---

### Task 4: Append quant section in `/api/newsfeed/ai/summarize` fallback route

**Files:**
- Modify: `app/routers/news.py`
- Test: `tests/test_news_summarize_quant.py`

**Step 1: Write failing test**

Monkeypatch SiliconFlow call in the same way; expect returned markdown contains `## 量化分析`.

**Step 2: Implement**

In `app/routers/news.py:summarize_news`:
- Parse model output as JSON; extract `markdown` and `quant`.
- Append quant section (same renderer) before returning.

**Step 3: Run tests**

Run: `pytest -q tests/test_news_summarize_quant.py`

**Step 4: Commit**

```bash
git add app/routers/news.py tests/test_news_summarize_quant.py
git commit -m "feat: add quant rendering to news summarize endpoint"
```

---

### Task 5: Frontend styles for quant bars (minimal CSS)

**Files:**
- Modify: `static/index.html` (CSS section)

**Step 1: Add CSS (no behavior changes)**

Add styles:
- `.quant-bars` container with rounded background and overflow hidden
- `.quant-bar.bullish` green, `.bearish` red, `.neutral` gray
- Ensure dark-mode variables match existing theme variables (`--tone-green-*`, `--tone-red-*`, etc.)

**Step 2: Manual verification**
- Run service: `bash scripts/manage.sh restart`
- Open AI总结 and confirm bars render and do not break badge clicks.

**Step 3: Commit**

```bash
git add static/index.html
git commit -m "style: add quant bar visualization styles"
```

---

### Task 6: End-to-end verification + docs

**Files:**
- Create: `docs/quant-analysis.md` (short usage notes)

**Step 1: Verify core flows**
- `curl http://127.0.0.1:8001/api/health`
- Generate AI summary for 1 day with `market` + `newswatch` enabled.
- Confirm:
  - `## 量化分析` appears under both sections
  - `#id` turns into badges (hover shows popover; click jumps)
  - News popover “打开原文” works

**Step 2: Run full test suite**

Run: `pytest -q`
Expected: PASS.

**Step 3: Commit docs**

```bash
git add docs/quant-analysis.md
git commit -m "docs: add quant analysis usage notes"
```

---

## Notes / Constraints

- **Security:** Do not accept raw model HTML. Only allow backend-generated HTML (known template) embedded in markdown.
- **Cost:** Quant uses the same LLM call response; no extra calls in v1. (We’re just asking the model for an extra `quant` object in the same completion.)
- **Clickability:** Keep using `#<id>` / `#id` in markdown. Frontend already converts to badges and popovers.

