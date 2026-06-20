from pathlib import Path

from vid2note_core.agents.parsers.codex_jsonl import CodexJsonlParser

FIXTURES = Path(__file__).parents[2] / "fixtures" / "agents" / "codex"


def test_codex_parser_maps_recorded_success():
    parser = CodexJsonlParser()
    events = [
        event
        for line in (FIXTURES / "success.jsonl").read_text().splitlines()
        for event in parser.parse_line(line)
    ]

    assert [event.type for event in events] == [
        "session",
        "thinking",
        "message",
        "file",
        "usage",
        "completed",
    ]
    assert events[0].payload["native_session_id"] == "thread-1"


def test_unknown_native_event_becomes_diagnostic_not_failure():
    parser = CodexJsonlParser()
    events = parser.parse_line('{"type":"future.event","value":1}')
    assert events == []
    assert parser.diagnostics[-1].code == "unknown_native_event"
