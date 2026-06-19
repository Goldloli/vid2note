import pytest
from vid2note_core.agents.events import AgentEventEmitter


def test_emitter_has_monotonic_sequence_and_one_terminal():
    emitter = AgentEventEmitter("run_0123456789ab")

    events = [
        emitter.emit("run.started", {}),
        emitter.emit("message.delta", {"text": "ok"}),
        emitter.emit("run.completed", {}),
    ]

    assert [event.sequence for event in events] == [0, 1, 2]
    assert [event.type for event in events].count("run.started") == 1
    assert (
        sum(event.type.startswith("run.") and event.type != "run.started" for event in events) == 1
    )
    with pytest.raises(RuntimeError, match="terminal"):
        emitter.emit("message.delta", {"text": "late"})


def test_emitter_rejects_second_started_event():
    emitter = AgentEventEmitter("run_0123456789ab")
    emitter.emit("run.started", {})

    with pytest.raises(RuntimeError, match="started"):
        emitter.emit("run.started", {})
