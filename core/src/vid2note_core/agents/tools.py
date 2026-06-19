from __future__ import annotations

from collections.abc import Callable
from typing import Any

from vid2note_core.vault.repository import VaultRepository
from vid2note_core.wiki.models import ChangeSet
from vid2note_core.wiki.store import ChangeSetStore


class AgentToolbox:
    _NAMES = (
        "read_schema",
        "read_index",
        "read_page",
        "read_source",
        "search_text",
        "propose_changeset",
        "request_media",
    )

    def __init__(
        self,
        repository: VaultRepository,
        changesets: ChangeSetStore,
        *,
        media_request: Callable[..., Any] | None = None,
    ):
        self.repository = repository
        self.changesets = changesets
        self.media_request = media_request
        self.calls: list[str] = []

    def names(self) -> tuple[str, ...]:
        return self._NAMES

    def read_schema(self) -> str:
        self.calls.append("read_schema")
        return self.repository.read_page("AGENTS.md").content

    def read_index(self) -> str:
        self.calls.append("read_index")
        return self.repository.read_page("index.md").content

    def read_page(self, path: str) -> str:
        self.calls.append("read_page")
        if not path.startswith("wiki/"):
            raise ValueError("read_page is limited to formal Wiki pages")
        return self.repository.read_page(path).content

    def read_source(self, path: str) -> str:
        self.calls.append("read_source")
        if not path.startswith("sources/") and not (
            path.startswith("raw/") and path.endswith("/transcript.md")
        ):
            raise ValueError("read_source is limited to source evidence")
        return self.repository.read_page(path).content

    def search_text(self, query: str) -> list[dict[str, object]]:
        self.calls.append("search_text")
        return [item.model_dump(mode="json") for item in self.repository.search(query)]

    def propose_changeset(self, changeset: ChangeSet) -> str:
        self.calls.append("propose_changeset")
        self.changesets.save_pending(changeset)
        return changeset.id

    def request_media(self, **request: object) -> object:
        self.calls.append("request_media")
        if self.media_request is None:
            raise RuntimeError("media requests are unavailable")
        return self.media_request(**request)
