FROM node:22-bookworm-slim AS web-builder

WORKDIR /app

COPY package.json package-lock.json tsconfig.base.json ./
COPY apps ./apps
COPY packages ./packages
COPY modules ./modules
COPY mod-projects/vibe-research/frontend ./mod-projects/vibe-research/frontend
COPY mod-projects/vibe-trading/frontend ./mod-projects/vibe-trading/frontend

RUN npm ci \
    && npm ci --prefix mod-projects/vibe-research/frontend \
    && npm ci --prefix mod-projects/vibe-trading/frontend \
    && NEWMA_DESK_INTEGRATED=1 NEWMA_DOCK_INTEGRATED=1 VITE_BASE_PATH=/mod-runtime/research/ VITE_API_BASE=/api/research npm run build --prefix mod-projects/vibe-research/frontend \
    && NEWMA_DESK_INTEGRATED=1 NEWMA_DOCK_INTEGRATED=1 VITE_NEWMA_DESK_INTEGRATED=1 VITE_BASE_PATH=/mod-runtime/trading/ VITE_API_BASE=/api/trading npm run build --prefix mod-projects/vibe-trading/frontend \
    && npm run build -w @newma-desk/portfolio-center \
    && npm run build -w @newma-desk/creator-studio \
    && npm run build -w @newma-desk/desk

FROM python:3.12-slim-bookworm AS python-builder

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    VIRTUAL_ENV=/opt/venv \
    PATH=/opt/venv/bin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        ca-certificates \
        libgomp1 \
    && python -m venv "$VIRTUAL_ENV" \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY services/api ./services/api
COPY scripts/measure-domain-runtime.py ./scripts/measure-domain-runtime.py
COPY mod-projects/vibe-research/backend ./mod-projects/vibe-research/backend
COPY deploy/server/constraints-domain-runtime.txt ./deploy/server/constraints-domain-runtime.txt
COPY deploy/server/requirements-domain-runtime.txt ./deploy/server/requirements-domain-runtime.txt
COPY deploy/server/requirements-trading-integrated.txt ./deploy/server/requirements-trading-integrated.txt
COPY mod-projects/vibe-trading/pyproject.toml ./mod-projects/vibe-trading/pyproject.toml
COPY mod-projects/vibe-trading/agent ./mod-projects/vibe-trading/agent

RUN python -m pip install --upgrade pip setuptools wheel \
    && python -m pip install --no-cache-dir -c deploy/server/constraints-domain-runtime.txt ./services/api \
    && python -m pip install --no-cache-dir -r deploy/server/requirements-domain-runtime.txt \
    && python -m pip check \
    && NEWMA_DESK_INTEGRATED_DOMAIN_RUNTIME=1 \
       PYTHONPATH=mod-projects/vibe-research/backend:mod-projects/vibe-trading/agent \
       python scripts/measure-domain-runtime.py --root /app --max-rss-mib 192

FROM python:3.12-slim-bookworm AS api-runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    VIRTUAL_ENV=/opt/venv \
    PATH=/opt/venv/bin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY --from=python-builder /opt/venv /opt/venv
COPY services/api ./services/api
COPY config ./config
COPY integrations ./integrations
COPY mods ./mods
COPY vendor ./vendor

COPY mod-projects/vibe-research/backend ./mod-projects/vibe-research/backend
COPY mod-projects/vibe-research/a-stock-data ./mod-projects/vibe-research/a-stock-data
COPY mod-projects/vibe-research/global-stock-data ./mod-projects/vibe-research/global-stock-data
COPY --from=web-builder /app/mod-projects/vibe-research/frontend/dist ./mod-projects/vibe-research/frontend/dist

COPY mod-projects/vibe-trading/pyproject.toml ./mod-projects/vibe-trading/pyproject.toml
COPY mod-projects/vibe-trading/agent ./mod-projects/vibe-trading/agent
COPY --from=web-builder /app/mod-projects/vibe-trading/frontend/dist ./mod-projects/vibe-trading/frontend/dist

COPY --from=web-builder /app/modules/portfolio-center/dist ./modules/portfolio-center/dist
COPY --from=web-builder /app/modules/creator-studio/dist ./modules/creator-studio/dist

RUN rm -rf \
    /app/mod-projects/vibe-trading/agent/runs \
    /app/mod-projects/vibe-trading/agent/sessions \
    /app/mod-projects/vibe-trading/agent/uploads

CMD ["python", "-m", "uvicorn", "vibe_visualization_api.main:app", "--app-dir", "services/api", "--host", "0.0.0.0", "--port", "8911"]

FROM node:22-bookworm-slim AS ops-runtime

WORKDIR /app

COPY config ./config
COPY integrations ./integrations
COPY mods ./mods
COPY scripts ./scripts

CMD ["node", "scripts/register-store-defaults.mjs", "--api-url=http://api:8911"]

FROM nginx:1.27-alpine AS desk-runtime

COPY deploy/server/nginx.desk.conf /etc/nginx/conf.d/default.conf
COPY --from=web-builder /app/apps/shell/dist /usr/share/nginx/html
