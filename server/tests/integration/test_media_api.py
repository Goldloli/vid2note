from datetime import UTC, datetime

from vid2note_core.source.registrar import SourceRegistration


class FakeRunner:
    def run(self, command: list[str]) -> None:
        from pathlib import Path

        Path(command[-1]).write_bytes(b"rendered")


def _source_with_media(client, tmp_path):
    srt = tmp_path / "media.srt"
    srt.write_text("1\n00:00:00,000 --> 00:00:05,000\nEvidence.\n", encoding="utf-8")
    note = tmp_path / "note.md"
    note.write_text("# Summary\n", encoding="utf-8")
    original = tmp_path / "video.mp4"
    original.write_bytes(b"fake video")
    return client.app.state.services.source_registrar.register(
        SourceRegistration(
            task_id="task_0123456789ab",
            canonical_url="https://example.com/media",
            title="Media API",
            imported_at=datetime(2026, 6, 18, tzinfo=UTC),
            srt_path=srt,
            note_path=note,
            original_path=original,
            duration_ms=5000,
        )
    )


def test_media_frame_and_clip_are_cached(client, tmp_path):
    source = _source_with_media(client, tmp_path)
    client.app.state.services.media.runner = FakeRunner()
    client.app.state.services.media.ffmpeg = "ffmpeg"

    frame = client.get(
        "/api/v1/media/frame", params={"source_id": source.source_id, "timestamp_ms": 1000}
    )
    clip = client.get(
        "/api/v1/media/clip",
        params={"source_id": source.source_id, "start_ms": 1000, "end_ms": 3000},
    )
    repeated = client.get(
        "/api/v1/media/frame", params={"source_id": source.source_id, "timestamp_ms": 1000}
    )

    assert frame.status_code == 200
    assert clip.status_code == 200
    assert repeated.json()["cached"] is True
    assert clip.json()["rendered_start_ms"] == 0
    assert clip.json()["rendered_end_ms"] == 4500


def test_media_unavailable_returns_typed_details(client):
    source = client.post(
        "/api/v1/sources/ingest",
        json={
            "title": "Transcript only",
            "canonical_url": "https://example.com/transcript",
            "srt_content": "1\n00:00:00,000 --> 00:00:01,000\nWords.\n",
            "note_content": "# Note\n",
        },
    ).json()

    response = client.get(
        "/api/v1/media/frame", params={"source_id": source["source_id"], "timestamp_ms": 500}
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "SOURCE_MEDIA_UNAVAILABLE"
    assert response.json()["error"]["details"]["canonical_url"] == source["canonical_url"]
