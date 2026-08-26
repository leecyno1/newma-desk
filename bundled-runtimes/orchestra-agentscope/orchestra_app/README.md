# Orchestra AgentScope Backend

AgentScope 2.0 based backend for the fixed 19-seat investment committee.

## Run

```bash
source ~/.codex/finance-env.sh
source .venv/bin/activate
python -m orchestra_app.main
```

The API listens on `http://127.0.0.1:8001` by default. Set
`ORCHESTRA_API_PORT` when that port is already occupied.

Install the complete Orchestra runtime with:

```bash
pip install -e '.[orchestra]'
```

- `GET /healthz`
- `GET /api/agents`
- `POST /api/runs`
- `GET /api/runs/{run_id}`
- `GET /api/runs/{run_id}/events`
- `POST /api/runs/{run_id}/cancel`

Use `mode: "demo"` for a deterministic workflow demonstration and `mode: "live"`
for AgentScope agents backed by the configured OpenAI-compatible model.

Live agents receive read-only `tushare_query` and `tavily_search` tools when
`TUSHARE_TOKEN` and `TAVILY_API_KEY` are configured. The OpenAI-compatible base
URL must include its API suffix, usually `/v1`.

## Persistence

SQLite remains the zero-configuration default:

```bash
export ORCHESTRA_DATABASE_PATH=/data/orchestra.db
```

For PostgreSQL, set a DSN before starting the API:

```bash
export ORCHESTRA_DATABASE_URL='postgresql://orchestra:password@127.0.0.1:5432/orchestra'
```

The same versioned schema ledger is applied to SQLite and PostgreSQL. PostgreSQL
job claims use `FOR UPDATE SKIP LOCKED`, so multiple API/worker processes can
claim database-backed jobs without duplicate execution.

Migrate an existing SQLite database without deleting target data:

```bash
python -m orchestra_app.migrate_database \
  --sqlite /data/orchestra.db \
  --postgres 'postgresql://orchestra:password@127.0.0.1:5432/orchestra'
```

The command copies users, portfolios, runs, events, artifacts, evidence,
encrypted secrets and job state. It is idempotent and reports source, inserted
and target row counts for each table.

## Durable Queue

Set `ORCHESTRA_REDIS_URL` to move task coordination to Redis. Business data and
research outputs remain in SQLite or PostgreSQL.

```bash
export ORCHESTRA_REDIS_URL='redis://127.0.0.1:6379/0'
```

Redis connection failure is reported in `/api/system/overview`; the service
falls back to the configured database queue so research runs remain available.

## Secret Vault

By default Orchestra creates a mode-`0600` Fernet key file at
`.orchestra/secret.key`. Production deployments should inject the key through a
secret manager:

```bash
export ORCHESTRA_SECRET_MASTER_KEY='your-url-safe-fernet-key'
```

Generate a key with `python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'`.
The system overview exposes only the key source and a non-secret fingerprint.
