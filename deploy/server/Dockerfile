FROM python:3.12-slim-bookworm

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        ca-certificates \
        curl \
        git \
        gnupg \
        libcairo2 \
        libffi8 \
        libgdk-pixbuf-2.0-0 \
        libpango-1.0-0 \
        libpangocairo-1.0-0 \
        shared-mime-info \
    && curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY . .

RUN npm ci \
    && python -m pip install --no-cache-dir -e services/api \
    && python -m pip install --no-cache-dir -r mod-projects/vibe-research/backend/requirements.txt \
    && python -m pip install --no-cache-dir -e mod-projects/vibe-trading \
    && npm ci --prefix mod-projects/vibe-research/frontend \
    && npm ci --prefix mod-projects/vibe-trading/frontend \
    && NEWMA_DESK_INTEGRATED=1 NEWMA_DOCK_INTEGRATED=1 VITE_BASE_PATH=/mod-runtime/research/ VITE_API_BASE=/api/research npm run build --prefix mod-projects/vibe-research/frontend \
    && NEWMA_DESK_INTEGRATED=1 NEWMA_DOCK_INTEGRATED=1 VITE_BASE_PATH=/mod-runtime/trading/ VITE_API_BASE=/api/trading npm run build --prefix mod-projects/vibe-trading/frontend \
    && npm run build

CMD ["python", "-m", "uvicorn", "vibe_visualization_api.main:app", "--app-dir", "services/api", "--host", "0.0.0.0", "--port", "8911"]
