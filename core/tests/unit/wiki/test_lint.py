from datetime import date

from vid2note_core.vault.layout import VaultLayout
from vid2note_core.vault.repository import VaultRepository
from vid2note_core.wiki.index import IndexEntry, render_index
from vid2note_core.wiki.lint import WikiLinter


def _page(*, title="Topic", sources=1, body="Claim 42.", status="active"):
    source_lines = "\n".join(f"  - src_20260618_{index:08x}" for index in range(sources))
    return (
        "---\nid: concept_topic\n"
        f"title: {title}\npage_type: concept\nstatus: {status}\n"
        f"sources:\n{source_lines}\n"
        "created_at: 2025-01-01\nupdated_at: 2025-01-01\n---\n\n"
        f"# {title}\n\n{body}\n"
    )


def test_lint_reports_orphans_broken_links_missing_citations_and_gaps(tmp_path):
    layout = VaultLayout.initialize(tmp_path / "vault")
    page = layout.wiki / "concepts" / "topic.md"
    page.write_text(
        _page(body="Claim 42. [[wiki/concepts/missing.md]] TODO: research gap."),
        encoding="utf-8",
    )

    report = WikiLinter(layout, VaultRepository(layout)).run(today=date(2026, 6, 19))
    codes = {issue.code for issue in report.issues}

    assert {"ORPHAN_PAGE", "BROKEN_WIKILINK", "MISSING_CITATION", "RESEARCH_GAP"} <= codes


def test_lint_reports_index_drift_missing_pages_contradictions_and_stale_claims(tmp_path):
    layout = VaultLayout.initialize(tmp_path / "vault")
    page = layout.wiki / "concepts" / "topic.md"
    page.write_text(
        _page(
            sources=2,
            status="stale",
            body=(
                "## 观点 A\nClaim A.\n\n## 观点 B\nClaim B.\n\n"
                "[Evidence](vid2note://source/src_20260618_00000000?start=0&end=1000)"
            ),
        ),
        encoding="utf-8",
    )
    layout.index.write_text(
        render_index(
            [
                IndexEntry(
                    page_id="concept_topic",
                    title="Wrong title",
                    path="wiki/concepts/topic.md",
                    summary="Summary",
                    page_type="concept",
                    source_count=1,
                    updated=date(2025, 1, 1),
                ),
                IndexEntry(
                    page_id="concept_missing",
                    title="Missing",
                    path="wiki/concepts/missing.md",
                    summary="Missing",
                    page_type="concept",
                    source_count=1,
                    updated=date(2025, 1, 1),
                ),
            ]
        ),
        encoding="utf-8",
    )

    report = WikiLinter(layout, VaultRepository(layout)).run(today=date(2026, 6, 19))
    codes = {issue.code for issue in report.issues}

    assert {"INDEX_DRIFT", "MISSING_PAGE", "CONTRADICTION", "STALE_CLAIM"} <= codes
