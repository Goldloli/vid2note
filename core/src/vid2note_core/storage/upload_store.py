"""上传文件存储

任务创建前的文件上传（SRT/PDF/TXT）落盘到这里。返回的 file_id 可在
创建任务时引用（task_repo 的 srt_file/pdf_file/txt_file 字段）。

布局：
  {base_dir}/uploads/<file_id>/<original_name>

file_id 格式 file_<12 位 hex>（与 security.validate_file_id 一致），防止路径遍历。
"""

from __future__ import annotations

import secrets
from pathlib import Path

from vid2note_core.utils.security import secure_filename


class UploadStore:
    def __init__(self, base_dir: Path | None = None):
        self.base_dir = Path(base_dir or "data/uploads")
        self.base_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def generate_file_id() -> str:
        """生成 file_<12 位 hex> 格式的 file_id。"""
        return f"file_{secrets.token_hex(6)}"

    def _file_dir(self, file_id: str) -> Path:
        """file_id 校验 + 目录解析（防路径遍历）。"""
        if not file_id.startswith("file_") or "/" in file_id or ".." in file_id:
            raise ValueError(f"非法 file_id: {file_id}")
        return self.base_dir / file_id

    def save(self, file_id: str, original_name: str, data: bytes) -> Path:
        """保存上传文件，返回落盘路径。

        Args:
            file_id: 由 generate_file_id 生成
            original_name: 原始文件名（会被 secure_filename 清理）
            data: 文件字节内容
        """
        safe_name = secure_filename(original_name)
        d = self._file_dir(file_id)
        d.mkdir(parents=True, exist_ok=True)
        path = d / safe_name
        path.write_bytes(data)
        return path

    def get_path(self, file_id: str) -> Path | None:
        """返回已上传文件的路径；不存在返回 None。"""
        d = self._file_dir(file_id)
        if not d.exists():
            return None
        files = [f for f in d.iterdir() if f.is_file()]
        return files[0] if files else None

    def get_name(self, file_id: str) -> str | None:
        """返回已上传文件的原名（去路径后的文件名）。"""
        p = self.get_path(file_id)
        return p.name if p else None

    def delete(self, file_id: str) -> bool:
        """删除上传文件，返回是否删除成功。"""
        d = self._file_dir(file_id)
        if d.exists():
            import shutil

            shutil.rmtree(d)
            return True
        return False

    def exists(self, file_id: str) -> bool:
        return self.get_path(file_id) is not None
