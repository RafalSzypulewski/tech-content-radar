import pytest

from radar.canonical import canonicalize, item_id


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        # scheme and host lowercased, www. removed
        ("HTTPS://WWW.Example.COM/Post", "https://example.com/Post"),
        ("http://www.example.com/a", "http://example.com/a"),
        # fragment dropped
        ("https://example.com/a#section-2", "https://example.com/a"),
        # trailing slash stripped
        ("https://example.com/a/", "https://example.com/a"),
        ("https://example.com/", "https://example.com"),
        # tracking params dropped, others kept in order with original encoding
        ("https://example.com/a?utm_source=x&utm_medium=y", "https://example.com/a"),
        ("https://example.com/a?UTM_Campaign=x", "https://example.com/a"),
        ("https://example.com/a?fbclid=1&id=5&gclid=2", "https://example.com/a?id=5"),
        ("https://example.com/a?ref=hn&source=rss", "https://example.com/a"),
        ("https://example.com/a?b=2&a=1", "https://example.com/a?b=2&a=1"),
        ("https://example.com/a?q=hello%20world&utm_x=1", "https://example.com/a?q=hello%20world"),
        ("https://example.com/a?referrer=x", "https://example.com/a?referrer=x"),
        # YouTube variants
        ("https://youtu.be/abc123", "https://youtube.com/watch?v=abc123"),
        ("https://youtu.be/abc123?t=42", "https://youtube.com/watch?v=abc123"),
        ("https://www.youtube.com/shorts/abc123", "https://youtube.com/watch?v=abc123"),
        ("https://www.youtube.com/watch?v=abc123&t=10s", "https://youtube.com/watch?v=abc123"),
        ("https://www.youtube.com/watch?feature=share&v=abc123", "https://youtube.com/watch?v=abc123"),
        ("https://m.youtube.com/watch?v=abc123", "https://youtube.com/watch?v=abc123"),
        ("http://YouTube.com/watch?v=abc123#x", "https://youtube.com/watch?v=abc123"),
        # non-video YouTube pages are treated like any other URL
        ("https://www.youtube.com/channel/UCx/", "https://youtube.com/channel/UCx"),
    ],
)
def test_canonicalize(url, expected):
    assert canonicalize(url) == expected


def test_item_id_is_12_hex_chars_and_stable():
    first = item_id("https://example.com/a")
    assert len(first) == 12
    assert int(first, 16) >= 0
    assert first == item_id("https://example.com/a")
    assert first != item_id("https://example.com/b")


def test_equivalent_urls_get_the_same_id():
    a = item_id(canonicalize("https://www.example.com/post/?utm_source=x#top"))
    b = item_id(canonicalize("https://example.com/post"))
    assert a == b
