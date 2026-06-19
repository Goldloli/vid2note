import pytest
from vid2note_core.vault.layout import VaultLayout
from vid2note_core.vault.models import VaultConflict, VaultPathError
from vid2note_core.vault.repository import VaultRepository


@pytest.fixture
def repository(tmp_path):
    return VaultRepository(VaultLayout.initialize(tmp_path / "vault"))


@pytest.fixture
def page(repository):
    return repository.read_page("index.md")


def test_repository_rejects_escape(repository):
    with pytest.raises(VaultPathError):
        repository.read_page("../outside.md")


def test_repository_rejects_symlink_outside_root(repository, tmp_path):
    outside = tmp_path / "outside.md"
    outside.write_text("outside")
    (repository.root / "escape.md").symlink_to(outside)

    with pytest.raises(VaultPathError):
        repository.read_page("escape.md")


def test_human_update_requires_matching_base_hash(repository, page):
    with pytest.raises(VaultConflict):
        repository.update_human(page.path, "changed", base_hash="stale")


def test_human_update_is_atomic_and_returns_new_hash(repository, page):
    updated = repository.update_human(page.path, "changed\n", base_hash=page.content_hash)

    assert updated.content == "changed\n"
    assert updated.content_hash != page.content_hash
    assert not list(repository.root.glob(".index.md.*.tmp"))


def test_read_page_parses_frontmatter(repository):
    target = repository.layout.wiki / "concepts" / "poc.md"
    target.write_text("---\ntitle: POC\nsources:\n  - src_1\n---\n# POC\n")

    page = repository.read_page("wiki/concepts/poc.md")

    assert page.frontmatter == {"title": "POC", "sources": ["src_1"]}
