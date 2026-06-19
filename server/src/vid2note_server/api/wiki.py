from datetime import UTC, datetime
from secrets import token_hex

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from vid2note_core.wiki.lint import WikiLinter, WikiLintIssue
from vid2note_core.wiki.models import ChangeOperation, ChangeSet

from vid2note_server.dependencies import ServicesDependency
from vid2note_server.schemas.changesets import AutonomyModeRequest, AutonomyModeResponse
from vid2note_server.schemas.common import ERROR_RESPONSES

router = APIRouter(prefix="/wiki", tags=["wiki"], responses=ERROR_RESPONSES)


class WikiLintResponse(BaseModel):
    issues: list[WikiLintIssue]
    healthy: bool


@router.get("/lint", response_model=WikiLintResponse)
async def lint_wiki(services: ServicesDependency):
    report = WikiLinter(services.vault_layout, services.vault).run()
    return WikiLintResponse(issues=report.issues, healthy=report.healthy)


@router.post("/lint/propose", response_model=ChangeSet, status_code=201)
async def propose_lint_repairs(services: ServicesDependency):
    report = WikiLinter(services.vault_layout, services.vault).run()
    operations: list[ChangeOperation] = []
    source_ids: set[str] = set()
    for issue in report.issues:
        if issue.code not in {"ORPHAN_PAGE", "INDEX_DRIFT"} or issue.path is None:
            continue
        page = services.vault.read_page(issue.path)
        frontmatter = page.frontmatter or {}
        page_id = frontmatter.get("id")
        sources = frontmatter.get("sources")
        if not isinstance(page_id, str) or not isinstance(sources, list):
            continue
        page_sources = [item for item in sources if isinstance(item, str)]
        if not page_sources:
            continue
        source_ids.update(page_sources)
        operations.append(
            ChangeOperation(
                page_id=page_id,
                path=page.path,
                base_hash=page.content_hash,
                action="update",
                before=page.content,
                after=page.content,
                rationale=f"Reconcile Wiki index for {issue.code.lower()}",
                citations=[],
            )
        )
    if not operations or not source_ids:
        raise HTTPException(409, "没有可安全自动修复的索引问题")
    changeset = ChangeSet(
        id=f"chg_{token_hex(6)}",
        created_at=datetime.now(UTC),
        source_ids=sorted(source_ids),
        base_revision="wiki-lint",
        agent_runtime="wiki-linter",
        summary="Reconcile orphan pages and Wiki index drift",
        operations=operations,
        contradictions=[],
    )
    services.changesets.save_pending(changeset)
    return changeset


@router.get("/policy", response_model=AutonomyModeResponse)
async def get_wiki_policy(services: ServicesDependency):
    return {"mode": services.config.load().autonomy_mode}


@router.put("/policy", response_model=AutonomyModeResponse)
async def update_wiki_policy(request: AutonomyModeRequest, services: ServicesDependency):
    config = services.config.load()
    config.autonomy_mode = request.mode
    services.config.save(config)
    return {"mode": config.autonomy_mode}
