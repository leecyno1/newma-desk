# Repository Guidelines

> **新 Agent 必读**：先看 `AGENTS_ONBOARDING.md`，它有完整的 memory 写入指引和首次部署流程。

## Project Structure & Module Organization
- `app/`: FastAPI app (`main.py`), `routers/*`, `services/*`, models/db/config/schemas.
- `data/`: SQLite DB and AI artifacts (default `data/app.db`). Runtime output; do not commit.
- `scripts/`: Helper scripts; entry `scripts/manage.sh`.
- `static/`: Minimal UI served at `/` and `/static/*`.
- `docs/`, `n8n/`: Reference docs and sample n8n workflows.
  - `docs/wechatapi-docs/`: WeChatAPI iPad protocol docs (142 pages, full mirror)
- `tests/`: Put tests under `tests/test_*.py`.

## Agent Companion Package
For Hermes/Agent-side skills, API docs, and cloud deployment scripts, see:
**https://github.com/leecyno1/wx-auto** (Agent Skill + WeChatAPI reference + deploy tools)

## Build, Test, and Development Commands
- First install: `cp .env.example .env && bash scripts/manage.sh install`
- Hot reload dev: `bash scripts/manage.sh dev`
- Background service: `bash scripts/manage.sh start` · `status` | `logs -f` | `stop`
- Data sync: `bash scripts/manage.sh sync` (incremental) or `bash scripts/manage.sh syncfull 30`
- Manual run: `uvicorn app.main:app --host 127.0.0.1 --port 8001`
- Quick checks: `curl http://127.0.0.1:8001/api/health` and `curl 'http://127.0.0.1:8001/api/messages?q=hello'`

## Coding Style & Naming Conventions
- Python 3.11+; PEP 8; 4 spaces; soft limit 100-120 columns.
- Files/modules: `snake_case.py`; classes: `CamelCase`; functions/vars: `snake_case`.
- Prefer type hints; small, focused functions.
- HTTP layer in `routers/*`; business logic in `services/*`.

## Testing Guidelines
- Use `pytest` with FastAPI `TestClient` or `httpx`.
- Name tests `tests/test_*.py`.
- Use a temporary SQLite file per test run to isolate the DB; never modify `data/app.db`.
- Run locally: `pytest -q`

## Commit & Pull Request Guidelines
- Conventional Commits (e.g., `feat: add /api/reports`). Keep commits clear and focused.
- PRs include: purpose/summary, UI screenshots (if applicable), test plan (curl or steps), config/migration notes, linked issues.

## Security & Configuration Tips
- Secrets live in `.env`; do not commit. Update `.env.example` when adding keys.
- Default CORS is permissive; tighten in `app/main.py` before production.
- Back up `data/app.db`; set `DATABASE_URL` in `.env` to move storage.
- For n8n, secure `N8N_AUTH_TOKEN`; use `Authorization: Bearer <token>` in requests.
