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
