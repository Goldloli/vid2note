from vid2note_core.agents.tools import AgentToolbox
from vid2note_core.vault.layout import VaultLayout
from vid2note_core.vault.repository import VaultRepository
from vid2note_core.wiki.store import ChangeSetStore


def test_builtin_tools_have_no_shell_or_arbitrary_write(tmp_path):
    layout = VaultLayout.initialize(tmp_path / "vault")
    toolbox = AgentToolbox(VaultRepository(layout), ChangeSetStore(layout.root))

    assert set(toolbox.names()) == {
        "read_schema",
        "read_index",
        "read_page",
        "read_source",
        "search_text",
        "propose_changeset",
        "request_media",
    }


def test_toolbox_reads_schema_then_index_through_repository(tmp_path):
    layout = VaultLayout.initialize(tmp_path / "vault")
    toolbox = AgentToolbox(VaultRepository(layout), ChangeSetStore(layout.root))

    assert toolbox.read_schema().startswith("# vid2note Wiki Schema")
    assert toolbox.read_index().startswith("# Index")
    assert toolbox.calls[:2] == ["read_schema", "read_index"]
