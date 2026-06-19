from __future__ import annotations

import re
from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict

from vid2note_core.vault.layout import VaultLayout
from vid2note_core.vault.repository import VaultRepository
from vid2note_core.wiki.index import parse_index

_WIKILINK = re.compile(r"\[\[([^|\]]+)(?:\|[^\]]+)?\]\]")


class WikiLintIssue(BaseModel):
    model_config = ConfigDict(frozen=True)

    code: str
    severity: Literal["error", "warning"]
    path: str | None = None
    message: str


class WikiLintReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    issues: list[WikiLintIssue]

    @property
    def healthy(self) -> bool:
        return not any(issue.severity == "error" for issue in self.issues)


class WikiLinter:
    def __init__(self, layout: VaultLayout, repository: VaultRepository):
        self.layout = layout
        self.repository = repository

    def run(self, *, today: date | None = None) -> WikiLintReport:
        current_date = today or date.today()
        issues: list[WikiLintIssue] = []
        entries = parse_index(self.layout.index.read_text(encoding="utf-8"))
        indexed = {entry.path: entry for entry in entries}
        wiki_paths = {
            entry.path for entry in self.repository.tree() if entry.path.startswith("wiki/")
        }
        for path in indexed:
            if path not in wiki_paths:
                issues.append(_issue("MISSING_PAGE", "error", path))
        for path in sorted(wiki_paths):
            if path not in indexed:
                issues.append(_issue("ORPHAN_PAGE", "warning", path))
            page = self.repository.read_page(path)
            frontmatter = page.frontmatter or {}
            entry = indexed.get(path)
            sources = frontmatter.get("sources", [])
            source_count = len(sources) if isinstance(sources, list) else 0
            if entry is not None and (
                entry.title != frontmatter.get("title") or entry.source_count != source_count
            ):
                issues.append(_issue("INDEX_DRIFT", "warning", path))
            for target in _WIKILINK.findall(page.content):
                if target not in wiki_paths:
                    issues.append(_issue("BROKEN_WIKILINK", "error", path))
            body = page.content.split("\n---\n", 1)[-1]
            if re.search(r"\d|根据视频|according to the video", body, re.I) and not re.search(
                r"vid2note://source/[^\s)]+\?start=\d+&end=\d+", body
            ):
                issues.append(_issue("MISSING_CITATION", "warning", path))
            if "## 观点 A" in body and "## 观点 B" in body:
                issues.append(_issue("CONTRADICTION", "warning", path))
            if re.search(r"\bTODO\b|待研究|research gap", body, re.I):
                issues.append(_issue("RESEARCH_GAP", "warning", path))
            updated = _date(frontmatter.get("updated_at"))
            if frontmatter.get("status") == "stale" or (
                updated is not None and (current_date - updated).days > 365
            ):
                issues.append(_issue("STALE_CLAIM", "warning", path))
        return WikiLintReport(issues=issues)


def _date(value: object) -> date | None:
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError:
            return None
    return None


def _issue(
    code: str,
    severity: Literal["error", "warning"],
    path: str,
) -> WikiLintIssue:
    return WikiLintIssue(
        code=code,
        severity=severity,
        path=path,
        message=code.replace("_", " ").lower(),
    )
