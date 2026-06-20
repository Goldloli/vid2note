from __future__ import annotations

import re
from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

PageType = Literal["concept", "entity", "topic", "comparison"]

_SECTIONS: tuple[tuple[PageType, str], ...] = (
    ("concept", "Concepts"),
    ("entity", "Entities"),
    ("topic", "Topics"),
    ("comparison", "Comparisons"),
)
_SECTION_TYPES = {heading: page_type for page_type, heading in _SECTIONS}
_ENTRY = re.compile(
    r"^- \[\[(?P<path>[^|\]]+)\|(?P<title>[^\]]+)\]\] — "
    r"(?P<summary>.*)；(?P<count>\d+) 个来源。$"
)
_USER_NOTES = re.compile(
    r"<!-- user-notes:start -->(?P<body>.*?)<!-- user-notes:end -->",
    re.DOTALL,
)


class IndexEntry(BaseModel):
    model_config = ConfigDict(frozen=True)

    page_id: str
    title: str
    path: str
    summary: str
    page_type: PageType
    source_count: int = Field(ge=0)
    updated: date


def render_index(entries: list[IndexEntry], *, existing: str = "") -> str:
    user_notes_match = _USER_NOTES.search(existing)
    user_notes = user_notes_match.group("body").strip("\n") if user_notes_match else ""
    lines = ["# Index", ""]
    for page_type, heading in _SECTIONS:
        lines.extend([f"## {heading}", ""])
        selected = sorted(
            (entry for entry in entries if entry.page_type == page_type),
            key=lambda entry: (entry.title.casefold(), entry.path),
        )
        for entry in selected:
            lines.append(
                f"- [[{entry.path}|{entry.title}]] — {entry.summary}；{entry.source_count} 个来源。"
            )
        if selected:
            lines.append("")
    lines.extend(["<!-- user-notes:start -->", user_notes, "<!-- user-notes:end -->", ""])
    return "\n".join(lines)


def parse_index(content: str) -> list[IndexEntry]:
    page_type: PageType | None = None
    entries: list[IndexEntry] = []
    for line in content.splitlines():
        if line.startswith("## "):
            page_type = _SECTION_TYPES.get(line[3:].strip())
            continue
        match = _ENTRY.match(line)
        if match is None or page_type is None:
            continue
        path = match.group("path")
        slug = re.sub(r"[^a-z0-9]+", "_", path.rsplit("/", 1)[-1].removesuffix(".md").lower())
        entries.append(
            IndexEntry(
                page_id=f"{page_type}_{slug.strip('_')}",
                title=match.group("title"),
                path=path,
                summary=match.group("summary"),
                page_type=page_type,
                source_count=int(match.group("count")),
                updated=date.min,
            )
        )
    return entries
