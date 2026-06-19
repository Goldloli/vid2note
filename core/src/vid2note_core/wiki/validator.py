from __future__ import annotations

import re
from pathlib import Path, PurePath
from typing import Literal

import yaml

from vid2note_core.source.identity import SourceIdentityRepository
from vid2note_core.vault.layout import VaultLayout
from vid2note_core.vault.repository import VaultRepository
from vid2note_core.wiki.models import (
    ChangeSet,
    Citation,
    ValidationIssue,
    ValidationResult,
)

_PAGE_TYPES = {"concept", "entity", "topic", "comparison"}
_SOURCE_ID = re.compile(r"^src_\d{8}_[0-9a-f]{8}$")
_WIKILINK = re.compile(r"\[\[([^|\]]+)(?:\|[^\]]+)?\]\]")
_REQUIRED_FRONTMATTER = {
    "id",
    "title",
    "page_type",
    "status",
    "sources",
    "created_at",
    "updated_at",
}


class ChangeSetValidator:
    def __init__(self, layout: VaultLayout, repository: VaultRepository):
        self.layout = layout
        self.repository = repository
        self.sources = SourceIdentityRepository(layout.root)

    def validate(self, changeset: ChangeSet) -> ValidationResult:
        issues: list[ValidationIssue] = []
        proposed_paths = {operation.path for operation in changeset.operations}
        for index, operation in enumerate(changeset.operations):
            path = self._safe_wiki_path(operation.path)
            if path is None:
                issues.append(self._issue("PATH_INVALID", "error", index, operation.path))
                continue
            exists = path.is_file()
            current = None
            if operation.action == "create":
                if exists:
                    issues.append(self._issue("CREATE_PATH_EXISTS", "error", index, operation.path))
            else:
                if not exists:
                    issues.append(
                        self._issue("UPDATE_PATH_MISSING", "error", index, operation.path)
                    )
                else:
                    current = self.repository.read_page(operation.path)
                    if operation.base_hash != current.content_hash:
                        issues.append(
                            self._issue("STALE_BASE_HASH", "error", index, operation.path)
                        )
                    if operation.before != current.content:
                        issues.append(
                            self._issue("BEFORE_MISMATCH", "error", index, operation.path)
                        )
                    current_frontmatter = current.frontmatter or {}
                    if current_frontmatter.get("id") != operation.page_id:
                        issues.append(
                            self._issue("PAGE_ID_CHANGED", "error", index, operation.path)
                        )

            frontmatter = _frontmatter(operation.after)
            missing = sorted(_REQUIRED_FRONTMATTER - set(frontmatter))
            if missing:
                issues.append(
                    self._issue(
                        "FRONTMATTER_REQUIRED",
                        "error",
                        index,
                        operation.path,
                        f"Missing frontmatter fields: {', '.join(missing)}",
                    )
                )
            if frontmatter.get("id") != operation.page_id:
                issues.append(self._issue("PAGE_ID_CHANGED", "error", index, operation.path))
            if frontmatter.get("page_type") not in _PAGE_TYPES:
                issues.append(self._issue("PAGE_TYPE_INVALID", "error", index, operation.path))

            frontmatter_sources = frontmatter.get("sources", [])
            if isinstance(frontmatter_sources, list):
                for source_id in frontmatter_sources:
                    if not isinstance(source_id, str) or self._source(source_id) is None:
                        issues.append(self._issue("SOURCE_UNKNOWN", "error", index, operation.path))
            for citation in operation.citations:
                self._validate_citation(citation, issues, index, operation.path)
            if not operation.citations and _contains_key_fact(operation.after):
                issues.append(
                    self._issue(
                        "KEY_CLAIM_WITHOUT_CITATION",
                        "warning",
                        index,
                        operation.path,
                    )
                )
            for target in _WIKILINK.findall(operation.after):
                if target in proposed_paths:
                    continue
                target_path = self._safe_wiki_path(target)
                if target_path is None or not target_path.is_file():
                    issues.append(self._issue("BROKEN_WIKILINK", "error", index, operation.path))

        for contradiction in changeset.contradictions:
            for citation in [*contradiction.citations_a, *contradiction.citations_b]:
                self._validate_citation(citation, issues, None, None)
        return ValidationResult(
            valid=not any(issue.severity == "error" for issue in issues),
            issues=issues,
        )

    def _validate_citation(
        self,
        citation: Citation,
        issues: list[ValidationIssue],
        operation_index: int | None,
        path: str | None,
    ) -> None:
        source = self._source(citation.source_id)
        if source is None:
            issues.append(self._issue("SOURCE_UNKNOWN", "error", operation_index, path))
        elif citation.end_ms > source.duration_ms:
            issues.append(self._issue("CITATION_OUT_OF_RANGE", "error", operation_index, path))

    def _source(self, source_id: str):
        if not _SOURCE_ID.fullmatch(source_id):
            return None
        return self.sources.get(source_id)

    def _safe_wiki_path(self, relative_path: str) -> Path | None:
        supplied = PurePath(relative_path)
        if (
            supplied.is_absolute()
            or ".." in supplied.parts
            or not relative_path.startswith("wiki/")
        ):
            return None
        candidate = (self.layout.root / relative_path).resolve(strict=False)
        wiki_root = self.layout.wiki.resolve()
        if candidate.suffix.lower() != ".md" or not candidate.is_relative_to(wiki_root):
            return None
        return candidate

    @staticmethod
    def _issue(
        code: str,
        severity: Literal["error", "warning"],
        operation_index: int | None,
        path: str | None,
        message: str | None = None,
    ) -> ValidationIssue:
        return ValidationIssue(
            code=code,
            severity=severity,
            operation_index=operation_index,
            path=path,
            message=message or code.replace("_", " ").lower(),
        )


def _frontmatter(content: str) -> dict[str, object]:
    if not content.startswith("---\n"):
        return {}
    payload, separator, _ = content[4:].partition("\n---\n")
    if not separator:
        return {}
    try:
        parsed = yaml.safe_load(payload)
    except yaml.YAMLError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _contains_key_fact(content: str) -> bool:
    body = content.split("\n---\n", 1)[-1]
    return bool(
        re.search(r"\d|[\"“”][^\"“”]+[\"“”]|根据视频|according to the video", body, re.I)
        or len(re.findall(r"\b[A-Z][A-Za-z0-9_-]+\b", body)) >= 2
    )
