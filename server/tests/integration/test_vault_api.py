import json


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
