import time


def _wait_terminal(client, session_id):
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        events = client.app.state.services.agent_sessions.list_events(session_id)
        if events and events[-1].type in {"run.completed", "run.failed", "run.cancelled"}:
            return events
        time.sleep(0.02)
    raise AssertionError("agent run did not reach terminal state")


def test_list_runtimes_and_builtin_session_answers_from_wiki(client):
    layout = client.app.state.services.vault_layout
    page = layout.wiki / "concepts" / "agent-topic.md"
    content = "# Agent Topic\n\nCompounding rewards patience.\n"
    page.write_text(content, encoding="utf-8")
    before = page.read_bytes()

    runtimes = client.get("/api/v1/agents")
    session = client.post(
        "/api/v1/agent/sessions",
        json={"runtime_id": "built-in", "context_paths": ["wiki/concepts/agent-topic.md"]},
    )
    sent = client.post(
        f"/api/v1/agent/sessions/{session.json()['id']}/messages",
        json={"message": "What rewards patience?"},
    )
    events = _wait_terminal(client, session.json()["id"])

    assert runtimes.status_code == 200
    assert {item["id"] for item in runtimes.json()} == {"built-in", "codex", "claude"}
    assert session.status_code == 201
    assert sent.status_code == 202
    assert any("Compounding rewards patience" in str(event.payload) for event in events)
    assert [event.sequence for event in events] == list(range(len(events)))
    assert page.read_bytes() == before


def test_unknown_runtime_is_rejected(client):
    response = client.post(
        "/api/v1/agent/sessions", json={"runtime_id": "unknown", "context_paths": []}
    )
    assert response.status_code == 404


def test_sessions_can_be_listed_for_workspace_recovery(client):
    created = client.post(
        "/api/v1/agent/sessions", json={"runtime_id": "built-in", "context_paths": []}
    ).json()

    response = client.get("/api/v1/agent/sessions")

    assert response.status_code == 200
    assert response.json()[0]["id"] == created["id"]


def test_agent_event_stream_can_resume_after_previous_run(client):
    session = client.post(
        "/api/v1/agent/sessions", json={"runtime_id": "built-in", "context_paths": []}
    ).json()
    client.post(f"/api/v1/agent/sessions/{session['id']}/messages", json={"message": "first"})
    first = _wait_terminal(client, session["id"])
    client.post(f"/api/v1/agent/sessions/{session['id']}/messages", json={"message": "second"})

    with client.stream(
        "GET", f"/api/v1/agent/sessions/{session['id']}/events", params={"after": len(first)}
    ) as response:
        payload = "".join(response.iter_text())

    assert response.status_code == 200
    assert "run.started" in payload
    assert "run.completed" in payload
    assert first[0].run_id not in payload
