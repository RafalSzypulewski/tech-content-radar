import httpx
import respx

from radar.collectors import collect_all, format_summary
from radar.rawstore import read_items
from tests.conftest import FIXTURES, NOW, make_source

KEYWORDS = ["testing", "flaky", "automatyzacja", "playwright"]


def _sources():
    return [
        make_source(id="atom", url="https://a.example.com/feed"),
        make_source(id="broken", url="https://broken.example.com/feed"),
        make_source(id="pl", url="https://pl.example.com/feed", lang="pl"),
    ]


def _mock_feeds(feed_bytes):
    respx.get("https://a.example.com/feed").respond(200, content=feed_bytes("atom.xml"))
    respx.get("https://broken.example.com/feed").respond(500)
    respx.get("https://pl.example.com/feed").respond(200, content=feed_bytes("rss2.xml"))
    # article pages for text extraction of short blog items
    article = (FIXTURES / "article.html").read_text(encoding="utf-8")
    respx.route(host="www.example.com").respond(200, html=article)
    respx.route(host="blog.example.pl").respond(404)


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

    items = read_items(raw / "2026-10-29.jsonl")
    assert [i.title for i in items] == [
        "Taming flaky tests in CI",
        "Automatyzacja testów z Playwright",
    ]
    assert items[0].matched_keywords == ["flaky"]
    assert items[1].matched_keywords == ["automatyzacja", "playwright"]
    # short feed text replaced by the extracted article; failed extraction keeps feed text
    assert "quarantined the flaky tests" in items[0].text
    assert items[1].text == "Jak zacząć automatyzację testów w Playwright."
    assert [i.lang for i in items] == ["en", "pl"]


@respx.mock
def test_detected_language_overrides_source_lang(tmp_path):
    respx.get("https://dev.to/api/articles").respond(
        200,
        json=[
            {
                "id": 1,
                "title": "Testy jednostkowe w Pythonie krok po kroku",
                "url": "https://dev.to/ktos/testy-1",
                "description": "Jak pisać czytelne testy jednostkowe w pytest.",
                "published_at": "2026-10-28T08:00:00Z",
            }
        ],
    )
    source = make_source(id="devto", kind="devto", type="community", url=None, tags=["testing"])

    with httpx.Client() as client:
        collect_all([source], ["testy"], tmp_path, NOW, client)

    [item] = read_items(tmp_path / "2026-10-29.jsonl")
    assert item.lang == "pl"  # the source says "en"
    assert item.text == "Jak pisać czytelne testy jednostkowe w pytest."  # community: no extraction


def test_unsupported_kind_is_reported(tmp_path):
    source = make_source(id="x")
    source.kind = "gopher"  # bypasses validation on purpose

    [stat] = collect_all([source], KEYWORDS, tmp_path, NOW, httpx.Client())

    assert "not supported" in stat.error


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
    respx.route(host="www.example.com").respond(404)
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
