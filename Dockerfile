# 阶段1:前端构建
FROM node:20-alpine AS fe
WORKDIR /fe
COPY frontend/package*.json ./
RUN npm ci || npm install
COPY frontend/ ./
RUN npm run build

# 阶段2:生产(单容器,同源托管 API + 前端静态)
FROM python:3.11-slim
WORKDIR /app/backend
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PYTHONPATH=/app/backend \
    DATA_ROOT=/app/data DB_PATH=/app/data/tasks.db
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*
COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir -r /app/backend/requirements.txt faster-whisper
COPY backend/src /app/backend/src
COPY --from=fe /fe/dist /app/frontend/dist
RUN mkdir -p /app/data
EXPOSE 8765
HEALTHCHECK --interval=30s --timeout=10s --start-period=25s --retries=3 \
    CMD curl -sf http://localhost:8765/api/v1/health || exit 1
CMD ["python", "-m", "uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8765"]
