from datetime import UTC, datetime

from radar.collectors.rss import html_to_text, parse_feed
from tests.conftest import NOW, make_source


def test_parse_atom(feed_bytes):
    items = parse_feed(feed_bytes("atom.xml"), make_source(), NOW)

    assert [i.title for i in items] == ["Taming flaky tests in CI", "Gardening tips"]
    first = items[0]
    assert first.url.startswith("https://www.example.com/2026/10/flaky-tests/?utm_source")
    assert first.canonical_url == "https://example.com/2026/10/flaky-tests"
    assert first.published_at == datetime(2026, 10, 27, 19, 0, tzinfo=UTC)
    assert first.fetched_at == NOW
    assert first.author == "Jane Tester"
    assert first.text == (
        "Flaky tests erode trust in the suite. Here is how we quarantine them & fix them."
    )
    assert (first.source_id, first.type, first.lang) == ("example", "blog", "en")
    # no <published>: falls back to <updated>
    assert items[1].published_at == datetime(2026, 10, 20, 8, 0, tzinfo=UTC)
    assert items[1].author is None


def test_parse_rss2_polish(feed_bytes):
    items = parse_feed(feed_bytes("rss2.xml"), make_source(lang="pl"), NOW)

    assert len(items) == 2  # the entry without a link is skipped
    first = items[0]
    assert first.title == "Automatyzacja testów z Playwright"
    assert first.canonical_url == "https://blog.example.pl/playwright-od-zera"
    assert first.published_at == datetime(2026, 10, 26, 8, 30, tzinfo=UTC)
    assert first.author == "Jan Kowalski"
    assert first.text == "Jak zacząć automatyzację testów w Playwright."
    assert first.lang == "pl"


def test_parse_youtube(feed_bytes):
    items = parse_feed(feed_bytes("youtube.xml"), make_source(type="video"), NOW)

    assert [i.canonical_url for i in items] == [
        "https://youtube.com/watch?v=abc123XYZ_-",
        "https://youtube.com/watch?v=short00001",
    ]
    assert items[0].text == "A quick tour of Playwright test automation."
    assert items[0].type == "video"
    assert items[0].author == "Example Channel"


def test_text_is_truncated(feed_bytes):
    long_feed = feed_bytes("rss2.xml").replace(
        b"Jak zacz", b"x" * 5000 + b" Jak zacz"
    )
    items = parse_feed(long_feed, make_source(), NOW)
    assert len(items[0].text) == 4000


def test_html_to_text():
    assert html_to_text("<p>a&nbsp;<b>b</b></p>\n<p>c &lt;d&gt;</p>") == "a b c <d>"
