from vid2note_server import entrypoint


def test_frozen_entrypoint_starts_loopback_server_from_environment(monkeypatch):
    called = {}
    monkeypatch.setenv("VID2NOTE_HOST", "127.0.0.1")
    monkeypatch.setenv("VID2NOTE_PORT", "19090")
    monkeypatch.setattr(entrypoint.uvicorn, "run", lambda app, **options: called.update(options))

    entrypoint.main()

    assert called == {"host": "127.0.0.1", "port": 19090, "log_level": "info"}
