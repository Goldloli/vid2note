def test_wiki_lint_returns_structured_report(client):
    response = client.get("/api/v1/wiki/lint")

    assert response.status_code == 200
    assert response.json() == {"issues": [], "healthy": True}


def test_wiki_lint_repair_proposal_creates_changeset_without_writing_wiki(client):
    source = client.post(
        "/api/v1/sources/ingest",
        json={
            "title": "Health source",
            "srt_content": "1\n00:00:00,000 --> 00:00:01,000\nEvidence.\n",
            "note_content": "# Health source\n",
        },
    ).json()
    page = client.app.state.services.vault_layout.wiki / "orphan.md"
    page.write_text(
        "---\nid: wiki_health_orphan\ntitle: Health orphan\ntype: concept\n"
        f"sources:\n  - {source['source_id']}\n---\n\n# Health orphan\n",
        encoding="utf-8",
    )
    before = page.read_bytes()

    response = client.post("/api/v1/wiki/lint/propose")

    assert response.status_code == 201
    assert response.json()["status"] == "pending"
    assert response.json()["operations"][0]["path"] == "wiki/orphan.md"
    assert page.read_bytes() == before
