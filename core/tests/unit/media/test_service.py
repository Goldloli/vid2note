from datetime import UTC, datetime

import pytest
from vid2note_core.media.service import MediaRangeError, MediaService, cache_key
from vid2note_core.source.registrar import SourceRegistrar, SourceRegistration
from vid2note_core.vault.layout import VaultLayout


class FakeRunner:
    def __init__(self):
        self.commands: list[list[str]] = []

    def run(self, command: list[str]) -> None:
        self.commands.append(command)
        output = command[-1]
        from pathlib import Path

        Path(output).write_bytes(b"rendered")


@pytest.fixture
def source(tmp_path):
    layout = VaultLayout.initialize(tmp_path / "vault")
    srt = tmp_path / "source.srt"
    srt.write_text("1\n00:00:00,000 --> 00:00:10,000\nEvidence.\n", encoding="utf-8")
    note = tmp_path / "note.md"
    note.write_text("# Summary\n", encoding="utf-8")
    original = tmp_path / "source.mp4"
    original.write_bytes(b"fake video")
    record = SourceRegistrar(layout).register(
        SourceRegistration(
            task_id="task_0123456789ab",
            canonical_url="https://example.com/video",
            title="Media evidence",
            imported_at=datetime(2026, 6, 18, tzinfo=UTC),
            srt_path=srt,
            note_path=note,
            original_path=original,
            duration_ms=10_000,
        )
    )
    return layout, record


def test_media_reference_rejects_end_beyond_duration(source):
    layout, record = source
    service = MediaService(layout, runner=FakeRunner(), ffmpeg="ffmpeg")

    with pytest.raises(MediaRangeError):
        service.clip(record.source_id, start_ms=0, end_ms=record.duration_ms + 1)


def test_frame_cache_key_includes_source_hash_and_timestamp():
    assert cache_key("abc", "frame", 1000, None, 0) != cache_key("abc", "frame", 2000, None, 0)


def test_clip_generation_adds_buffer_and_clamps_to_media_bounds(source):
    layout, record = source
    runner = FakeRunner()
    service = MediaService(layout, runner=runner, ffmpeg="ffmpeg")

    reference = service.clip(record.source_id, start_ms=500, end_ms=9500, buffer_ms=1500)

    assert reference.rendered_start_ms == 0
    assert reference.rendered_end_ms == record.duration_ms
    assert runner.commands[0][0] == "ffmpeg"
    assert "-ss" in runner.commands[0]


def test_repeated_frame_request_uses_cache(source):
    layout, record = source
    runner = FakeRunner()
    service = MediaService(layout, runner=runner, ffmpeg="ffmpeg")

    first = service.frame(record.source_id, timestamp_ms=1000)
    second = service.frame(record.source_id, timestamp_ms=1000)

    assert first.cached is False
    assert second.cached is True
    assert len(runner.commands) == 1


def test_promote_frame_copies_only_into_assets(source):
    layout, record = source
    service = MediaService(layout, runner=FakeRunner(), ffmpeg="ffmpeg")
    frame = service.frame(record.source_id, timestamp_ms=1000)

    promoted = service.promote(frame)

    assert promoted.asset_path.startswith(f"assets/{record.source_id}/")
    assert (layout.root / promoted.asset_path).read_bytes() == b"rendered"


def test_failed_render_never_leaves_a_cached_partial(source):
    layout, record = source

    class FailingRunner:
        def run(self, command: list[str]) -> None:
            from pathlib import Path

            Path(command[-1]).write_bytes(b"partial")
            raise RuntimeError("ffmpeg interrupted")

    service = MediaService(layout, runner=FailingRunner(), ffmpeg="ffmpeg")

    with pytest.raises(RuntimeError, match="interrupted"):
        service.frame(record.source_id, timestamp_ms=1000)

    assert list((layout.private / "cache" / "frames").iterdir()) == []


def test_promote_rejects_source_id_path_escape(source):
    layout, record = source
    service = MediaService(layout, runner=FakeRunner(), ffmpeg="ffmpeg")
    frame = service.frame(record.source_id, timestamp_ms=1000)

    with pytest.raises(MediaRangeError):
        service.promote(frame.model_copy(update={"source_id": "../../escape"}))

    assert not (layout.root.parent / "escape").exists()
