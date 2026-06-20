from datetime import UTC, datetime

from vid2note_core.agents.models import AgentEvent


def test_event_json_round_trip_is_stable():
    event = AgentEvent(
        run_id="run_0123456789ab",
        sequence=3,
        type="message.delta",
        timestamp=datetime(2026, 6, 19, tzinfo=UTC),
        payload={"text": "answer"},
    )

    assert AgentEvent.model_validate_json(event.model_dump_json()) == event
