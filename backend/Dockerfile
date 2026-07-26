# ============================================
# 课程字幕整理工具 - 后端 Dockerfile
# 实际监听端口：8765
# ============================================

# 阶段1: 基础镜像
FROM python:3.11-slim AS base

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONFAULTHANDLER=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# 安装系统依赖（PyMuPDF/Pillow 需要）
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libffi-dev \
    libssl-dev \
    && rm -rf /var/lib/apt/lists/*

# ============================================
# 阶段2: 依赖安装
# ============================================
FROM base AS deps

COPY requirements.txt .
RUN pip install --user --no-cache-dir -r requirements.txt

# ============================================
# 阶段3: 生产镜像
# ============================================
FROM base AS production

# 复制已安装的依赖
COPY --from=deps /root/.local /root/.local
ENV PATH=/root/.local/bin:$PATH

# 创建必要的目录
RUN mkdir -p /app/uploads /app/temp /app/logs /app/config /app/output

# 复制应用代码
COPY src/ ./src/
COPY run.py .

# 暴露后端实际监听端口
EXPOSE 8765

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8765/health')" || exit 1

# 启动命令
CMD ["python", "run.py"]
