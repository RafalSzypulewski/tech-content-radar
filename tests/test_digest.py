from datetime import UTC, date, datetime

from radar.digest import render_digest, shown_ids, write_digest
from radar.models import Enrichment, RawItem
from radar.ranking import Final
from tests.conftest import FIXTURES, NOW

DAY = date(2026, 10, 29)


def _final(item_id, title, url, score, *, lang="en", source="Google Testing Blog", **enrich):
    item = RawItem(
        id=item_id,
        url=url,
        canonical_url=url,
        title=title,
        source_id="s",
        source_name=source,
        type="blog",
        lang=lang,
        published_at=datetime(2026, 10, 27 if lang == "en" else 26, 9, tzinfo=UTC),
        fetched_at=NOW,
    )
    fields = {"title_en": title, "summary_en": "", "reason": "", "tags": []}
    return Final(item, Enrichment(id=item_id, scored_at=NOW, **{**fields, **enrich}), score)


def _entries():
    best = _final(
        "7f3a9c1b2d4e",
        "Flaky tests: a field guide",
        "https://testing.example.com/flaky",
        0.871,
        summary_en="How to find, quarantine and fix flaky tests.",
        reason="Practical and squarely about test automation.",
        tags=["test-automation", "tutorial"],
    )
    best.related = [
        _final("aaaaaaaaaaaa", "Flaky tests at scale", "https://other.example.com/flaky-scale", 0.6)
    ]
    polish = _final(
        "0123456789ab",
        "Automatyzacja testów z Playwright",
        "https://blog.example.pl/playwright",
        0.614,
        lang="pl",
        source="Blog PL",
        title_en="Test automation with Playwright",
        summary_en="An intro to Playwright for Polish readers.",
        reason="Relevant, but introductory.",
        tags=["test-automation"],
    )
    return [best, polish]


def test_digest_snapshot():
    expected = (FIXTURES / "digest_expected.md").read_text(encoding="utf-8")
    assert render_digest(DAY, _entries()) == expected


def test_shown_ids_include_related_items(tmp_path):
    write_digest(DAY, render_digest(DAY, _entries()), tmp_path)
    (tmp_path / "notes.md").write_text("no ids here", encoding="utf-8")

    assert shown_ids(tmp_path) == {"7f3a9c1b2d4e", "aaaaaaaaaaaa", "0123456789ab"}


def test_shown_ids_empty_dir(tmp_path):
    assert shown_ids(tmp_path / "missing") == set()


def test_write_digest_never_overwrites(tmp_path):
    first = write_digest(DAY, "first", tmp_path)
    second = write_digest(DAY, "second", tmp_path)
    third = write_digest(DAY, "third", tmp_path)

    assert [p.name for p in (first, second, third)] == [
        "2026-10-29.md",
        "2026-10-29-2.md",
        "2026-10-29-3.md",
    ]
    assert first.read_text(encoding="utf-8") == "first"
    assert b"\r\n" not in first.read_bytes()


def test_empty_title_en_falls_back_to_original():
    entry = _final("abcdefabcdef", "Original title", "https://x.example.com", 0.5, title_en="")
    assert "### 1. Original title — score 0.50" in render_digest(DAY, [entry])
