# Skill Registry Governance

This repository should treat `skills/` as a curated runtime surface, not as a dump
folder for every upstream skill explored during research.

## Current Rule

- `core`: Newma workflow skills that are directly called by intake, draft,
  transwrite, video, or publish stages.
- `bridge`: Thin wrappers around external tools, such as HTML Anything,
  html-video, Bilibili upload, Xiaohongshu publish, or social upload.
- `external-candidate`: Useful upstream skills discovered during research but not
  yet wired into the Newma workflow.
- `archive`: Historical Newma skills kept for reference only.
- `rejected`: Skills that are incompatible, unsafe, duplicated, or too heavy for
  the workflow.

## Commit Policy

- Do not bulk-add newly downloaded upstream skills.
- A new skill can be tracked only after it has a `SKILL.md`, a clear invocation
  path from a stage, and no generated media/cache files.
- Large media, temporary article drafts, audio, video, screenshots, and browser
  state must stay outside the repository and outside skill roots.
- Upstream project URLs belong in registry/config/docs so future sync work is
  traceable.

## Current Local Candidate Buckets

- Finance/data candidates: `a-stock-data`, `yfinance-data`,
  `tushare-openclaw-skill`, `openclaw-stock-kb`, `llmquant-*`, `alphaear-*`.
- Video/media candidates: `html-anything`, `media-downloader`,
  `gemini-image-service`, `pptx-generator`, `url-to-markdown`.
- General agent/runtime candidates: `agent-browser`, `agentmail`, `github`,
  `mcp-builder`, `skill-*`, `verification-before-completion`.
- Anthropic financial-service examples: `anthropic-fs-*`; keep as references
  unless a concrete Newma stage uses them.

## Next Hardening Step

Add a lightweight registry file once a candidate is promoted. The registry should
record `name`, `category`, `upstream_url`, `local_path`, `stage`, and
`promotion_reason`.
