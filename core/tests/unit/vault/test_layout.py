from vid2note_core.vault.layout import VaultLayout


def test_initialize_creates_human_readable_vault(tmp_path):
    layout = VaultLayout.initialize(tmp_path / "vault")

    assert layout.agents.read_text().startswith("# vid2note Wiki Schema")
    assert layout.index.read_text().startswith("# Index")
    assert layout.log.read_text().startswith("# Log")
    assert layout.wiki.joinpath("concepts").is_dir()
    assert layout.private.joinpath("cache", "clips").is_dir()
    schema = layout.agents.read_text()
    assert "`id`" in schema
    assert "`concept`, `entity`, `topic`, and `comparison`" in schema


def test_initialize_does_not_overwrite_existing_templates(tmp_path):
    root = tmp_path / "vault"
    root.mkdir()
    (root / "index.md").write_text("# My Index\n")

    VaultLayout.initialize(root)

    assert (root / "index.md").read_text() == "# My Index\n"
