#!/usr/bin/env bash
# 拉取 vid2note 所需的外部二进制：ffmpeg / yt-dlp / BBDown
# 实际逻辑由 fetch_binaries.py 实现（支持 macOS arm64/x64 + Linux x64），
# 二进制落到 scripts/bin/，供 PyInstaller spec 与运行时 BinaryManager 使用。
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# 优先用仓库内 python，否则系统 python3
if [ -x "${SCRIPT_DIR}/../.venv/bin/python" ]; then
  PY="${SCRIPT_DIR}/../.venv/bin/python"
else
  PY="$(command -v python3 || command -v python)"
fi

echo ">>> Fetching external binaries via ${PY}"
exec "${PY}" "${SCRIPT_DIR}/fetch_binaries.py" "$@"
