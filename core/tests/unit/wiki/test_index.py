from datetime import date

from vid2note_core.wiki.index import IndexEntry, parse_index, render_index


def test_index_round_trip_is_stably_sorted_and_preserves_user_notes():
    existing = "# Index\n\n<!-- user-notes:start -->\nPinned by human.\n<!-- user-notes:end -->\n"
    entries = [
        IndexEntry(
            page_id="topic_zeta",
            title="Zeta",
            path="wiki/topics/zeta.md",
            summary="Last topic",
            page_type="topic",
            source_count=1,
            updated=date(2026, 6, 19),
        ),
        IndexEntry(
            page_id="concept_alpha",
            title="Alpha",
            path="wiki/concepts/alpha.md",
            summary="First concept",
            page_type="concept",
            source_count=2,
            updated=date(2026, 6, 18),
        ),
    ]

    rendered = render_index(entries, existing=existing)
    parsed = parse_index(rendered)

    assert rendered.index("Alpha") < rendered.index("Zeta")
    assert "Pinned by human." in rendered
    assert parsed[0].path == "wiki/concepts/alpha.md"
    assert parsed[0].source_count == 2


def test_index_uses_fixed_obsidian_link_format():
    entry = IndexEntry(
        page_id="concept_poc_trap",
        title="POC Trap",
        path="wiki/concepts/poc-trap.md",
        summary="Why AI POCs fail",
        page_type="concept",
        source_count=2,
        updated=date(2026, 6, 19),
    )

    rendered = render_index([entry])

    assert "- [[wiki/concepts/poc-trap.md|POC Trap]] — Why AI POCs fail；2 个来源。" in rendered
