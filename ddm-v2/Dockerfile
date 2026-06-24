# ---- Stage 1: 建置 React 前端 → /fe/dist ----
FROM node:20-slim AS frontend
ARG HTTP_PROXY
ARG HTTPS_PROXY
ARG NO_PROXY
ENV HTTP_PROXY=${HTTP_PROXY} HTTPS_PROXY=${HTTPS_PROXY} NO_PROXY=${NO_PROXY}
WORKDIR /fe
COPY src/frontend/package.json src/frontend/package-lock.json ./
RUN npm ci
COPY src/frontend/ ./
RUN npm run build

# ---- Stage 2: Python runtime（API + 前端 dist 同一容器） ----
FROM python:3.11-slim

# Accept proxy settings as build-time args (forwarded from host env by docker-compose)
ARG HTTP_PROXY
ARG HTTPS_PROXY
ARG NO_PROXY
ARG http_proxy
ARG https_proxy
ARG no_proxy

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    DDM_ROOT_DIR=/app \
    DDM_DATA_DIR=/app/data \
    HTTP_PROXY=${HTTP_PROXY} \
    HTTPS_PROXY=${HTTPS_PROXY} \
    NO_PROXY=${NO_PROXY} \
    http_proxy=${http_proxy} \
    https_proxy=${https_proxy} \
    no_proxy=${no_proxy}

WORKDIR /app

RUN useradd --create-home --shell /usr/sbin/nologin appuser

COPY pyproject.toml README.md ./
COPY src ./src
COPY alembic.ini ./
COPY migrations ./migrations
COPY scripts ./scripts
COPY entrypoint.sh ./entrypoint.sh
# 前端 build 產物（main.py 會在根目錄服務此 SPA）
COPY --from=frontend /fe/dist ./src/frontend/dist

RUN pip install --upgrade pip \
    && pip install -e . \
    && mkdir -p /app/data \
    && chmod +x /app/entrypoint.sh \
    && chown -R appuser:appuser /app

USER appuser

EXPOSE 8000

ENTRYPOINT ["/app/entrypoint.sh"]