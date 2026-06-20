from __future__ import annotations

import hashlib

from vid2note_core.parsers.srt_parser import SRTParser
from vid2note_core.source.models import TimelineSegment


def parse_srt(content: str) -> list[TimelineSegment]:
    items = SRTParser(min_duration=0, merge_gap=0).parse(content)
    segments: list[TimelineSegment] = []
    for sequence, item in enumerate(items, start=1):
        start_ms = round(item.start_seconds * 1000)
        end_ms = round(item.end_seconds * 1000)
        identity = f"{sequence}|{start_ms}|{end_ms}|{item.text}".encode()
        segment_id = f"seg-{sequence:06d}-{hashlib.sha256(identity).hexdigest()[:8]}"
        segments.append(
            TimelineSegment(
                segment_id=segment_id,
                start_ms=start_ms,
                end_ms=end_ms,
                text=item.text,
            )
        )
    return segments


def _timestamp(milliseconds: int) -> str:
    total_seconds, remainder = divmod(milliseconds, 1000)
    hours, remainder_seconds = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder_seconds, 60)
    suffix = f".{remainder:03d}" if remainder else ""
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}{suffix}"


def render_transcript(source_id: str, segments: list[TimelineSegment]) -> str:
    lines = ["---", f"source_id: {source_id}", "type: transcript", "---", "", "# Transcript", ""]
    for segment in segments:
        lines.extend(
            [
                f"## {_timestamp(segment.start_ms)}–{_timestamp(segment.end_ms)}",
                "",
                f"{segment.text} ^{segment.segment_id}",
                "",
            ]
        )
    return "\n".join(lines)
