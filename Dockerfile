# syntax=docker/dockerfile:1

# 阶段 1：前端构建
FROM node:22-alpine AS fe
WORKDIR /fe
COPY frontend/package*.json ./
ARG NPM_REGISTRY=https://registry.npmjs.org
RUN --mount=type=cache,target=/root/.npm \
    npm ci --registry="${NPM_REGISTRY}" --prefer-offline --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# 阶段 2：生产运行时（单容器、同源托管）
FROM python:3.11-slim

ARG APP_UID=1000
ARG APP_GID=1000

LABEL org.opencontainers.image.title="vid2note" \
      org.opencontainers.image.description="Turn videos into Markdown notes and mind maps" \
      org.opencontainers.image.source="https://github.com/Goldloli/vid2note" \
      org.opencontainers.image.licenses="MIT"

WORKDIR /app/backend
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PYTHONPATH=/app/backend \
    DATA_ROOT=/app/data DB_PATH=/app/data/tasks.db
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg curl ca-certificates \
    && groupadd --gid "${APP_GID}" app \
    && useradd --uid "${APP_UID}" --gid "${APP_GID}" --no-log-init --create-home app \
    && rm -rf /var/lib/apt/lists/*
COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir -r /app/backend/requirements.txt
COPY backend/src /app/backend/src
COPY --from=fe /fe/dist /app/frontend/dist
RUN mkdir -p /app/data /app/logs \
    && chown -R app:app /app/data /app/logs

USER app
EXPOSE 8765
HEALTHCHECK --interval=30s --timeout=10s --start-period=25s --retries=3 \
    CMD curl -sf http://localhost:8765/api/v1/health || exit 1
CMD ["python", "-m", "uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8765"]
