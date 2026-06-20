from pathlib import Path

from vid2note_core.agents.parsers.claude_stream import ClaudeStreamParser

FIXTURES = Path(__file__).parents[2] / "fixtures" / "agents" / "claude"


def test_claude_parser_maps_recorded_success():
    parser = ClaudeStreamParser()
    events = [
        event
        for line in (FIXTURES / "success.jsonl").read_text().splitlines()
        for event in parser.parse_line(line)
    ]

    assert [event.type for event in events] == [
        "session",
        "thinking",
        "message",
        "usage",
        "completed",
    ]
    assert events[0].payload["native_session_id"] == "claude-session"


def test_claude_resume_missing_has_explicit_error_code():
    parser = ClaudeStreamParser()
    line = (FIXTURES / "resume-missing.jsonl").read_text().strip()
    event = parser.parse_line(line)[0]
    assert event.type == "failed"
    assert event.payload["code"] == "AGENT_RESUME_MISSING"
