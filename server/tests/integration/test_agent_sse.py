import json
import time


def test_agent_sse_has_one_started_one_terminal_and_monotonic_sequence(client):
    session = client.post(
        "/api/v1/agent/sessions",
        json={"runtime_id": "built-in", "context_paths": []},
    ).json()
    client.post(
        f"/api/v1/agent/sessions/{session['id']}/messages",
        json={"message": "Question"},
    )
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        history = client.app.state.services.agent_sessions.list_events(session["id"])
        if history and history[-1].type == "run.completed":
            break
        time.sleep(0.02)

    with client.stream("GET", f"/api/v1/agent/sessions/{session['id']}/events") as response:
        payloads = [
            json.loads(line.removeprefix("data: "))
            for line in response.iter_lines()
            if line.startswith("data: ")
        ]

    assert response.status_code == 200
    assert [event["sequence"] for event in payloads] == list(range(len(payloads)))
    assert [event["type"] for event in payloads].count("run.started") == 1
    assert (
        sum(event["type"] in {"run.completed", "run.failed", "run.cancelled"} for event in payloads)
        == 1
    )
