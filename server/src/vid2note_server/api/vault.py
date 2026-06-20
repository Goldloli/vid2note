import re

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from vid2note_server.dependencies import ServicesDependency
from vid2note_server.schemas.common import ERROR_RESPONSES
from vid2note_server.schemas.vault import (
    HumanPageUpdate,
    VaultPage,
    VaultSearchResult,
    VaultTreeEntry,
)

router = APIRouter(prefix="/vault", tags=["vault"], responses=ERROR_RESPONSES)


class VaultBacklink(BaseModel):
    path: str
    title: str


@router.get("/tree", response_model=list[VaultTreeEntry])
async def vault_tree(services: ServicesDependency):
    return services.vault.tree()


@router.get("/backlinks", response_model=list[VaultBacklink])
async def vault_backlinks(path: str, services: ServicesDependency):
    try:
        services.vault.read_page(path)
    except FileNotFoundError as exc:
        raise HTTPException(404, "页面不存在") from exc
    pattern = re.compile(r"\[\[" + re.escape(path) + r"(?:\|[^\]]+)?\]\]")
    backlinks: list[VaultBacklink] = []
    for entry in services.vault.tree():
        if entry.path == path:
            continue
        page = services.vault.read_page(entry.path)
        if pattern.search(page.content):
            frontmatter = page.frontmatter or {}
            title = frontmatter.get("title")
            backlinks.append(
                VaultBacklink(
                    path=entry.path,
                    title=title if isinstance(title, str) else entry.name,
                )
            )
    return backlinks


@router.get("/page", response_model=VaultPage)
async def read_vault_page(path: str, services: ServicesDependency):
    try:
        return services.vault.read_page(path)
    except FileNotFoundError as exc:
        raise HTTPException(404, "页面不存在") from exc


@router.put("/page", response_model=VaultPage)
async def update_vault_page(path: str, update: HumanPageUpdate, services: ServicesDependency):
    try:
        return services.vault.update_human(path, update.content, base_hash=update.base_hash)
    except FileNotFoundError as exc:
        raise HTTPException(404, "页面不存在") from exc


@router.get("/search", response_model=list[VaultSearchResult])
async def search_vault(
    services: ServicesDependency,
    q: str = Query(min_length=1, max_length=200),
    limit: int = Query(default=50, ge=1, le=50),
):
    return services.vault.search(q, limit=limit)
