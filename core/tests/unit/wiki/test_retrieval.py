from datetime import UTC, datetime

from vid2note_core.vault.models import VaultPage, VaultTreeEntry
from vid2note_core.vault.repository import content_hash
from vid2note_core.wiki.retrieval import WikiRetriever


class RecordingRepository:
    def __init__(self):
        self.read_order: list[str] = []
        self.pages = {
            "AGENTS.md": "Wiki schema",
            "index.md": (
                "# Index\n\n## Concepts\n\n"
                "- [[wiki/concepts/poc-trap.md|POC Trap]] — AI POC 为什么失败；2 个来源。\n"
            ),
            "wiki/concepts/poc-trap.md": "# POC Trap\n\nCompiled conclusion.",
            "sources/source.md": "# Source\n\nTemporary source inference.",
        }

    def read_page(self, path: str) -> VaultPage:
        self.read_order.append(path)
        content = self.pages[path]
        return VaultPage(
            path=path,
            content=content,
            content_hash=content_hash(content),
            modified_at=datetime(2026, 6, 19, tzinfo=UTC),
        )

    def tree(self) -> list[VaultTreeEntry]:
        return [VaultTreeEntry(path=path, name=path.rsplit("/", 1)[-1]) for path in self.pages]


def test_retrieval_reads_schema_then_index_before_pages():
    repository = RecordingRepository()
    retriever = WikiRetriever(repository)

    result = retriever.find_context("AI POC 为什么失败")

    assert repository.read_order[:2] == ["AGENTS.md", "index.md"]
    assert result.pages[0].path == "wiki/concepts/poc-trap.md"
    assert result.pages[0].knowledge_layer == "wiki"


def test_retrieval_falls_back_to_sources_without_mixing_layers():
    repository = RecordingRepository()
    retriever = WikiRetriever(repository)

    result = retriever.find_context("Temporary source inference")

    source = next(page for page in result.pages if page.path == "sources/source.md")
    assert source.knowledge_layer == "source"
    assert all(page.knowledge_layer in {"wiki", "source", "raw"} for page in result.pages)
