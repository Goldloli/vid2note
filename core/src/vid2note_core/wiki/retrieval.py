from __future__ import annotations

import re
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict

from vid2note_core.vault.models import VaultPage, VaultTreeEntry
from vid2note_core.wiki.index import IndexEntry, parse_index


class ReadableVault(Protocol):
    def read_page(self, relative_path: str) -> VaultPage: ...

    def tree(self) -> list[VaultTreeEntry]: ...


class ContextPage(BaseModel):
    model_config = ConfigDict(frozen=True)

    path: str
    content: str
    knowledge_layer: Literal["wiki", "source", "raw"]


class RetrievalResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    schema_text: str
    index_text: str
    pages: list[ContextPage]


class WikiRetriever:
    def __init__(self, repository: ReadableVault, *, max_pages: int = 12):
        self.repository = repository
        self.max_pages = max_pages

    def find_context(self, query: str) -> RetrievalResult:
        schema = self.repository.read_page("AGENTS.md")
        index = self.repository.read_page("index.md")
        query_tokens = _tokens(query)
        ranked = sorted(
            parse_index(index.content),
            key=lambda entry: (-_score(entry, query_tokens), entry.path),
        )
        pages: list[ContextPage] = []
        seen: set[str] = set()
        for entry in ranked:
            if _score(entry, query_tokens) <= 0 or len(pages) >= self.max_pages:
                continue
            page = self.repository.read_page(entry.path)
            pages.append(ContextPage(path=page.path, content=page.content, knowledge_layer="wiki"))
            seen.add(page.path)

        if len(pages) < self.max_pages:
            for tree_entry in sorted(self.repository.tree(), key=_fallback_order):
                if tree_entry.path in seen or tree_entry.path in {
                    "AGENTS.md",
                    "index.md",
                    "log.md",
                }:
                    continue
                layer = _knowledge_layer(tree_entry.path)
                if layer is None:
                    continue
                try:
                    page = self.repository.read_page(tree_entry.path)
                except (FileNotFoundError, OSError, UnicodeError):
                    continue
                if not query_tokens.intersection(_tokens(page.content)):
                    continue
                pages.append(
                    ContextPage(path=page.path, content=page.content, knowledge_layer=layer)
                )
                seen.add(page.path)
                if len(pages) >= self.max_pages:
                    break
        return RetrievalResult(
            schema_text=schema.content,
            index_text=index.content,
            pages=pages,
        )


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+|[\u4e00-\u9fff]", text.casefold()))


def _score(entry: IndexEntry, query_tokens: set[str]) -> int:
    title_tokens = _tokens(entry.title)
    summary_tokens = _tokens(entry.summary)
    return 3 * len(query_tokens & title_tokens) + len(query_tokens & summary_tokens)


def _knowledge_layer(path: str) -> Literal["wiki", "source", "raw"] | None:
    if path.startswith("wiki/"):
        return "wiki"
    if path.startswith("sources/"):
        return "source"
    if path.startswith("raw/") and path.endswith("/transcript.md"):
        return "raw"
    return None


def _fallback_order(entry: VaultTreeEntry) -> tuple[int, str]:
    layer = _knowledge_layer(entry.path)
    priorities = {"wiki": 0, "source": 1, "raw": 2, None: 3}
    return priorities[layer], entry.path
