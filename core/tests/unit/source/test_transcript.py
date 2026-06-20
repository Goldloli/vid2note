import pytest
from pydantic import ValidationError
from vid2note_core.source.models import TimelineSegment
from vid2note_core.source.transcript import parse_srt, render_transcript

SRT = """1
00:00:01,000 --> 00:00:03,500
First line

2
00:00:04,000 --> 00:00:06,000
Second line
"""


def test_srt_builds_stable_segments_and_block_ids():
    first = parse_srt(SRT)
    second = parse_srt(SRT)

    assert first == second
    assert first[0].segment_id.startswith("seg-000001-")
    assert first[0].start_ms == 1000
    assert first[0].end_ms == 3500


def test_transcript_markdown_contains_time_headings_and_blocks():
    markdown = render_transcript("src_20260618_a1b2c3d4", parse_srt(SRT))

    assert "## 00:00:01–00:00:03.500" in markdown
    assert "First line ^seg-000001-" in markdown


def test_timeline_segment_rejects_reversed_range():
    with pytest.raises(ValidationError):
        TimelineSegment(segment_id="seg-1", start_ms=2000, end_ms=1000, text="bad")
