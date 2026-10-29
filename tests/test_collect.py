import httpx
import respx

from radar.collectors import collect_all, format_summary
from radar.rawstore import read_items
from tests.conftest import NOW, make_source

KEYWORDS = ["testing", "flaky", "automatyzacja", "playwright"]


def _sources():
    return [
        make_source(id="atom", url="https://a.example.com/feed"),
        make_source(id="broken", url="https://broken.example.com/feed"),
        make_source(id="pl", url="https://pl.example.com/feed", lang="pl"),
        make_source(id="hn", kind="hackernews", type="community", url=None),
    ]


def _mock_feeds(feed_bytes):
    respx.get("https://a.example.com/feed").respond(200, content=feed_bytes("atom.xml"))
    respx.get("https://broken.example.com/feed").respond(500)
    respx.get("https://pl.example.com/feed").respond(200, content=feed_bytes("rss2.xml"))


@respx.mock
def test_collect_all_writes_kept_items_and_survives_broken_source(tmp_path, feed_bytes):
    _mock_feeds(feed_bytes)
    raw = tmp_path / "raw"

    with httpx.Client() as client:
        stats = collect_all(_sources(), KEYWORDS, raw, NOW, client)

    by_id = {s.source_id: s for s in stats}
    assert (by_id["atom"].fetched, by_id["atom"].new, by_id["atom"].kept) == (2, 2, 1)
    assert "500" in by_id["broken"].error
    # pl: playwright post kept; old post dropped by age
    assert (by_id["pl"].fetched, by_id["pl"].kept) == (2, 1)
    assert "not supported" in by_id["hn"].error

    items = read_items(raw / "2026-10-29.jsonl")
    assert [i.title for i in items] == [
        "Taming flaky tests in CI",
        "Automatyzacja testów z Playwright",
    ]
    assert items[0].matched_keywords == ["flaky"]
    assert items[1].matched_keywords == ["automatyzacja", "playwright"]


@respx.mock
def test_second_run_dedupes(tmp_path, feed_bytes):
    _mock_feeds(feed_bytes)
    raw = tmp_path / "raw"

    with httpx.Client() as client:
        collect_all(_sources(), KEYWORDS, raw, NOW, client)
        stats = collect_all(_sources(), KEYWORDS, raw, NOW, client)

    assert sum(s.new for s in stats if s.source_id == "atom") == 1  # only the dropped one again
    assert sum(s.kept for s in stats) == 0
    assert len(read_items(raw / "2026-10-29.jsonl")) == 2


@respx.mock
def test_same_url_from_two_sources_is_kept_once(tmp_path, feed_bytes):
    respx.get("https://a.example.com/feed").respond(200, content=feed_bytes("atom.xml"))
    respx.get("https://b.example.com/feed").respond(200, content=feed_bytes("atom.xml"))
    sources = [
        make_source(id="a", url="https://a.example.com/feed"),
        make_source(id="b", url="https://b.example.com/feed"),
    ]

    with httpx.Client() as client:
        collect_all(sources, KEYWORDS, tmp_path, NOW, client)

    assert len(read_items(tmp_path / "2026-10-29.jsonl")) == 1


def test_no_file_written_when_nothing_kept(tmp_path):
    collect_all([], KEYWORDS, tmp_path / "raw", NOW, httpx.Client())
    assert not (tmp_path / "raw").exists()


def test_format_summary():
    from radar.collectors import SourceStats

    table = format_summary([SourceStats("atom", 2, 2, 1), SourceStats("x", error="boom")])
    lines = table.splitlines()
    assert lines[0].split() == ["source", "fetched", "new", "kept", "errors"]
    assert lines[1].split() == ["atom", "2", "2", "1"]
    assert lines[2].split() == ["x", "0", "0", "0", "boom"]
