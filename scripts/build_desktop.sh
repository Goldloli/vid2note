#!/usr/bin/env bash
# 完整 macOS 桌面端打包流水线（Phase 15-16）
#
# 步骤：
#   1. 拉取 ffmpeg/yt-dlp/BBDown 二进制到 scripts/bin/
#   2. PyInstaller 把 vid2note Python 后端打包到 python-dist/
#   3. 前端 Vite 构建（desktop/src/renderer → dist）
#   4. electron-builder 打包 mac arm64 .dmg
#
# 产物：desktop/dist-electron/vid2note-<version>-arm64.dmg
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
DESKTOP="${ROOT}/desktop"

# 选择 python 解释器
if [ -x "${ROOT}/.venv/bin/python" ]; then
  PY="${ROOT}/.venv/bin/python"
else
  PY="$(command -v python3 || command -v python)"
fi

echo "============================================================"
echo " vid2note macOS desktop build"
echo " root: ${ROOT}"
echo " python: ${PY}"
echo "============================================================"

# ── Step 1: 拉取二进制 ────────────────────────────────────
echo ""
echo "=== Step 1/4: Fetch external binaries (ffmpeg/yt-dlp/BBDown) ==="
"${SCRIPT_DIR}/fetch_binaries.sh"

# ── Step 2: PyInstaller 打包 Python 后端 ──────────────────
echo ""
echo "=== Step 2/4: Build Python backend with PyInstaller ==="
if ! "${PY}" -c "import PyInstaller" >/dev/null 2>&1; then
  echo "PyInstaller not found, installing..."
  "${PY}" -m pip install pyinstaller
fi
"${PY}" "${SCRIPT_DIR}/build.py"

# 校验产物
if [ ! -d "${ROOT}/python-dist/vid2note" ]; then
  echo "ERROR: PyInstaller 产物未生成: ${ROOT}/python-dist/vid2note"
  exit 1
fi
echo "Python backend -> ${ROOT}/python-dist/vid2note"

# ── Step 3: 前端构建 ──────────────────────────────────────
echo ""
echo "=== Step 3/4: Build frontend (Vite) ==="
if [ ! -d "${DESKTOP}/node_modules" ]; then
  echo "Installing npm dependencies..."
  (cd "${DESKTOP}" && npm install)
fi
(cd "${DESKTOP}" && npm run build)

# ── Step 4: electron-builder 打包 dmg ─────────────────────
echo ""
echo "=== Step 4/4: Package with electron-builder (mac arm64) ==="
(cd "${DESKTOP}" && npm run electron:build)

echo ""
echo "============================================================"
echo " BUILD COMPLETE"
echo "============================================================"
DMG="$(ls "${DESKTOP}/dist-electron/"*.dmg 2>/dev/null | head -1 || true)"
if [ -n "${DMG}" ]; then
  echo " DMG: ${DMG}"
else
  echo " (未找到 .dmg，请检查 desktop/dist-electron/)"
fi
