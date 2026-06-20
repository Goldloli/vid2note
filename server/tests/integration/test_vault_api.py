import json

from fastapi.testclient import TestClient
from vid2note_server.main import create_app


def _write_wiki_page(client) -> None:
    page = client.app.state.services.vault_layout.wiki / "concepts" / "poc-trap.md"
    page.write_text(
        "---\ntitle: POC Trap\ntype: concept\n---\n\n# POC Trap\n\nPrototype evidence.\n",
        encoding="utf-8",
    )


def test_vault_tree_read_search_and_human_update(client):
    _write_wiki_page(client)

    tree = client.get("/api/v1/vault/tree")
    assert tree.status_code == 200
    assert any(item["path"] == "wiki/concepts/poc-trap.md" for item in tree.json())

    result = client.get("/api/v1/vault/search", params={"q": "POC"}).json()
    assert result[0]["path"] == "wiki/concepts/poc-trap.md"
    page = client.get("/api/v1/vault/page", params={"path": result[0]["path"]}).json()
    response = client.put(
        "/api/v1/vault/page",
        params={"path": page["path"]},
        json={"content": page["content"] + "\nHuman note.\n", "base_hash": page["content_hash"]},
    )

    assert response.status_code == 200
    assert response.json()["content"].endswith("Human note.\n")
    entries = [
        json.loads(line)
        for line in client.app.state.services.vault_layout.log.read_text().splitlines()
        if line.startswith("{")
    ]
    assert entries[-1]["operation"] == "human-edit"


def test_vault_page_rejects_stale_base_hash(client):
    response = client.put(
        "/api/v1/vault/page",
        params={"path": "index.md"},
        json={"content": "changed", "base_hash": "stale"},
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "VAULT_CONFLICT"


def test_vault_page_rejects_path_escape(client):
    response = client.get("/api/v1/vault/page", params={"path": "../secret.md"})

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VAULT_PATH_INVALID"


def test_missing_vault_page_returns_typed_not_found(client):
    response = client.get("/api/v1/vault/page", params={"path": "wiki/missing.md"})

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "HTTP_404"


def test_vault_backlinks_returns_pages_that_link_to_target(client):
    _write_wiki_page(client)
    linking = client.app.state.services.vault_layout.wiki / "linking.md"
    linking.write_text(
        "---\ntitle: Linking page\n---\n\nSee [[wiki/concepts/poc-trap.md|the trap]].\n",
        encoding="utf-8",
    )

    response = client.get("/api/v1/vault/backlinks", params={"path": "wiki/concepts/poc-trap.md"})

    assert response.status_code == 200
    assert response.json() == [{"path": "wiki/linking.md", "title": "Linking page"}]


def test_markdown_sources_survive_state_database_deletion(tmp_path):
    data_root = tmp_path / "data"
    with TestClient(create_app(data_root)) as first:
        source = first.post(
            "/api/v1/sources/ingest",
            json={
                "title": "Durable source",
                "srt_content": "1\n00:00:00,000 --> 00:00:01,000\nDurable.\n",
                "note_content": "# Durable\n",
            },
        ).json()
        source_note = next(first.app.state.services.vault_layout.sources.glob("src_*.md"))
        source_note_relative = source_note.relative_to(first.app.state.services.vault_layout.root)
        database = first.app.state.services.paths.database

    database.unlink()

    with TestClient(create_app(data_root)) as restarted:
        assert restarted.get(f"/api/v1/sources/{source['source_id']}").status_code == 200
        page = restarted.get("/api/v1/vault/page", params={"path": source_note_relative.as_posix()})
        assert page.status_code == 200
        assert "Durable" in page.json()["content"]
        assert restarted.app.state.services.vault_layout.index.is_file()
        assert restarted.app.state.services.vault_layout.log.is_file()
