from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel
from pydantic.types import JsonValue

from vid2note_core.errors import Vid2NoteError


class VaultError(Vid2NoteError):
    pass


class VaultPathError(VaultError):
    def __init__(self, path: str):
        super().__init__(
            f"Vault path is not allowed: {path}",
            code="VAULT_PATH_INVALID",
            user_message="知识库路径无效",
            step="vault",
        )


class VaultConflict(VaultError):  # noqa: N818 - domain term used by the HTTP contract
    def __init__(self, path: str):
        super().__init__(
            f"Vault page changed since it was read: {path}",
            code="VAULT_CONFLICT",
            user_message="页面已在其他位置修改，请重新加载后再保存",
            step="vault",
        )


class VaultPage(BaseModel):
    path: str
    content: str
    content_hash: str
    modified_at: datetime
    frontmatter: dict[str, JsonValue] | None = None


class HumanPageUpdate(BaseModel):
    content: str
    base_hash: str
