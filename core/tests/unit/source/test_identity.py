from datetime import date

from vid2note_core.source.identity import SourceIdentityRepository, normalize_url


def test_same_content_reuses_source_id(tmp_path):
    identities = SourceIdentityRepository(tmp_path / "vault")
    first = identities.get_or_create("https://example.com/watch?v=1", b"same", date(2026, 6, 18))
    second = identities.get_or_create(
        "https://example.com/watch?v=1&utm_source=x", b"same", date(2026, 6, 19)
    )

    assert first.source_id == second.source_id
    assert first.source_id.startswith("src_20260618_")
    assert second.imported_at == first.imported_at


def test_normalize_url_removes_tracking_but_preserves_content_id():
    assert normalize_url("https://EXAMPLE.com/watch?utm_medium=x&v=abc&lang=zh#part") == (
        "https://example.com/watch?lang=zh&v=abc"
    )


def test_different_content_gets_a_different_source_id(tmp_path):
    identities = SourceIdentityRepository(tmp_path / "vault")

    first = identities.get_or_create(None, b"one", date(2026, 6, 18))
    second = identities.get_or_create(None, b"two", date(2026, 6, 18))

    assert first.source_id != second.source_id
