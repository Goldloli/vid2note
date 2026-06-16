"""安全工具"""

import re
from pathlib import Path

_FILE_ID_PATTERN = re.compile(r"^file_[a-f0-9]{12}$")
_TASK_ID_PATTERN = re.compile(r"^task_[a-f0-9]{12}$")

# 提示词注入检测模式
PROMPT_INJECTION_PATTERNS = [
    re.compile(r"<\s*system\s*>", re.IGNORECASE),
    re.compile(r"ignore\s+(all\s+)?previous\s+(instructions|commands)", re.IGNORECASE),
    re.compile(r"forget\s+(all\s+)?previous\s+(instructions|commands)", re.IGNORECASE),
    re.compile(r"you\s+are\s+now\s+", re.IGNORECASE),
    re.compile(r"new\s+role\s*:", re.IGNORECASE),
    re.compile(r"override\s+previous", re.IGNORECASE),
]

MAX_CONTENT_LENGTH = 100_000


def is_safe_path(base_dir: Path, target_path: Path) -> bool:
    """确保 target_path 在 base_dir 内（防路径遍历）"""
    try:
        target_path.resolve().relative_to(base_dir.resolve())
        return True
    except ValueError:
        return False


def secure_filename(name: str) -> str:
    """清理文件名，移除危险字符"""
    if not name:
        return "unnamed"
    # 先提取纯文件名（防路径遍历）
    name = Path(name).name
    # 移除路径分隔符和危险字符（保留 . 用于扩展名）
    name = re.sub(r'[\\/:*?"<>| ]', "_", name)
    # 移除前导/尾随空格和点
    name = name.strip(" .")
    if not name:
        return "unnamed"
    return name


def validate_file_id(file_id: str) -> bool:
    return bool(_FILE_ID_PATTERN.match(file_id))


def validate_task_id(task_id: str) -> bool:
    return bool(_TASK_ID_PATTERN.match(task_id))


def sanitize_content(content: str) -> str:
    """清理用户内容，防止提示词注入"""
    if not content or not isinstance(content, str):
        return ""

    # 1. 先转义 XML-like 标签（包括 <system>）
    content = content.replace("<", "&lt;").replace(">", "&gt;")

    # 2. 检测注入尝试并标记
    for pattern in PROMPT_INJECTION_PATTERNS:
        if pattern.search(content):
            content = f"[已过滤潜在注入内容]\n{content}"
            break

    # 3. 限制长度
    if len(content) > MAX_CONTENT_LENGTH:
        content = content[:MAX_CONTENT_LENGTH] + "\n[内容已截断]"

    return content
