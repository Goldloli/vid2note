# ============================================
# 课程字幕整理工具 - 前端 Dockerfile
# 容器内 nginx 监听 80
# ============================================

# 阶段1: 构建阶段
FROM node:20-alpine AS builder

WORKDIR /app

# 复制 package 文件
COPY package.json package-lock.json* ./

# 安装依赖（优先 npm ci；无 lockfile 时回退到 npm install）
RUN if [ -f package-lock.json ]; then npm ci; else npm install; fi

# 复制源代码
COPY . .

# 构建生产版本
RUN npm run build

# ============================================
# 阶段2: 生产阶段 (Nginx)
# ============================================
FROM nginx:1.25-alpine

# 安装 envsubst + wget（用于健康检查）
RUN apk add --no-cache gettext wget

# 复制 nginx 配置模板（用 .template 后缀，nginx 官方镜像会自动 envsubst）
COPY nginx.conf /etc/nginx/templates/default.conf.template

# 复制构建产物
COPY --from=builder /app/dist /usr/share/nginx/html

# nginx 默认会通过 docker-entrypoint.sh 替换 templates/ 下的 ${VAR}
# 默认监听 80
EXPOSE 80

# 健康检查（容器内 nginx 监听 80）
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD wget --quiet --tries=1 --spider http://localhost:80/ || exit 1
