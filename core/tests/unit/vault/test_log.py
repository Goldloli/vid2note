from vid2note_core.vault.layout import VaultLayout
from vid2note_core.vault.repository import VaultRepository


def test_human_update_appends_log_entry_without_content(tmp_path):
    repository = VaultRepository(VaultLayout.initialize(tmp_path / "vault"))
    page = repository.read_page("index.md")

    repository.update_human(page.path, "private changed body", base_hash=page.content_hash)
    log = repository.layout.log.read_text()

    assert "human-edit" in log
    assert '"path": "index.md"' in log
    assert page.content_hash in log
    assert "private changed body" not in log
