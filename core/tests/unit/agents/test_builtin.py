import asyncio

from vid2note_core.agents.builtin import BuiltinRuntime
from vid2note_core.agents.models import AgentRunInput
from vid2note_core.agents.tools import AgentToolbox
from vid2note_core.vault.layout import VaultLayout
from vid2note_core.vault.repository import VaultRepository
from vid2note_core.wiki.store import ChangeSetStore


async def _collect(runtime, run_input):
    return [event async for event in runtime.run(run_input)]


def test_builtin_answers_index_first_with_evidence_layers(tmp_path):
    layout = VaultLayout.initialize(tmp_path / "vault")
    (layout.wiki / "concepts" / "topic.md").write_text(
        "---\nid: concept_topic\ntitle: Topic\npage_type: concept\nstatus: active\n"
        "sources: []\ncreated_at: 2026-06-18\nupdated_at: 2026-06-19\n---\n\n"
        "# Topic\n\nCompounding rewards patience.\n",
        encoding="utf-8",
    )
    toolbox = AgentToolbox(VaultRepository(layout), ChangeSetStore(layout.root))
    runtime = BuiltinRuntime(toolbox)

    events = asyncio.run(
        _collect(
            runtime,
            AgentRunInput(
                run_id="run_0123456789ab",
                session_id="session_0123456789ab",
                message="What rewards patience?",
                context_paths=["wiki/concepts/topic.md"],
            ),
        )
    )

    assert toolbox.calls[:2] == ["read_schema", "read_index"]
    assert [event.type for event in events] == [
        "run.started",
        "message.delta",
        "run.completed",
    ]
    assert "Compounding rewards patience" in events[1].payload["text"]
    assert events[1].payload["knowledge_layer"] == "wiki"
