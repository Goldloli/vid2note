import json

import pytest
from vid2note_core.agents.workspace import AgentWorkspace, AgentWorkspaceViolation
from vid2note_core.vault.layout import VaultLayout
from vid2note_core.vault.repository import VaultRepository


def _workspace(tmp_path):
    layout = VaultLayout.initialize(tmp_path / "vault")
    page = layout.wiki / "concepts" / "poc-trap.md"
    page.write_text("# POC Trap\n", encoding="utf-8")
    source = layout.sources / "src_a--talk.md"
    source.write_text("# Source\n", encoding="utf-8")
    workspace = AgentWorkspace.create(
        layout,
        VaultRepository(layout),
        "run_0123456789ab",
        ["wiki/concepts/poc-trap.md", "sources/src_a--talk.md"],
    )
    return layout, workspace


def test_workspace_contains_only_selected_context(tmp_path):
    _, workspace = _workspace(tmp_path)

    assert workspace.relative_files() == {
        "AGENTS.md",
        "index.md",
        "wiki/concepts/poc-trap.md",
        "sources/src_a--talk.md",
        "run-manifest.json",
    }


def test_cli_edit_never_changes_live_vault(tmp_path):
    layout, workspace = _workspace(tmp_path)
    before = (layout.wiki / "concepts" / "poc-trap.md").read_bytes()

    workspace.write_text("wiki/concepts/poc-trap.md", "changed in sandbox")

    assert (layout.wiki / "concepts" / "poc-trap.md").read_bytes() == before
    diff = workspace.collect_diff()
    assert diff[0].action == "update"


def test_diff_rejects_binary_symlink_and_out_of_scope_paths(tmp_path):
    _, workspace = _workspace(tmp_path)
    workspace.write_bytes("wiki/binary.bin", b"\x00")
    with pytest.raises(AgentWorkspaceViolation):
        workspace.collect_diff()
    (workspace.root / "wiki" / "binary.bin").unlink()
    (workspace.root / "wiki" / "escape.md").symlink_to(tmp_path / "outside.md")
    with pytest.raises(AgentWorkspaceViolation):
        workspace.collect_diff()


def test_manifest_has_hashes_but_no_live_absolute_path(tmp_path):
    layout, workspace = _workspace(tmp_path)
    manifest = json.loads((workspace.root / "run-manifest.json").read_text())

    assert manifest["run_id"] == "run_0123456789ab"
    assert len(manifest["files"]["wiki/concepts/poc-trap.md"]) == 64
    assert str(layout.root) not in json.dumps(manifest)


def test_workspace_rejects_non_context_vault_files(tmp_path):
    layout = VaultLayout.initialize(tmp_path / "vault")
    with pytest.raises(AgentWorkspaceViolation):
        AgentWorkspace.create(
            layout,
            VaultRepository(layout),
            "run_0123456789ab",
            ["log.md"],
        )


def test_diff_uses_run_baseline_when_live_vault_changes_concurrently(tmp_path):
    layout, workspace = _workspace(tmp_path)
    original = "# POC Trap\n"
    (layout.wiki / "concepts" / "poc-trap.md").write_text(
        "# POC Trap\n\nHuman edit.\n", encoding="utf-8"
    )
    workspace.write_text("wiki/concepts/poc-trap.md", "# POC Trap\n\nAgent edit.\n")

    diff = workspace.collect_diff()[0]

    assert diff.before == original
    assert "Human edit" not in diff.before


def test_rename_can_also_edit_content_when_page_id_is_stable(tmp_path):
    layout = VaultLayout.initialize(tmp_path / "vault")
    old = layout.wiki / "concepts" / "old.md"
    old.write_text("---\nid: stable_page\n---\n\nOld\n", encoding="utf-8")
    workspace = AgentWorkspace.create(
        layout,
        VaultRepository(layout),
        "run_0123456789ab",
        ["wiki/concepts/old.md"],
    )
    (workspace.root / "wiki" / "concepts" / "old.md").unlink()
    workspace.write_text("wiki/concepts/new.md", "---\nid: stable_page\n---\n\nNew\n")

    diff = workspace.collect_diff()[0]

    assert diff.action == "rename"
    assert diff.old_path == "wiki/concepts/old.md"
    assert diff.path == "wiki/concepts/new.md"
