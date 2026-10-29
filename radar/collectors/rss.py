"""RSS / Atom collector: blogs, Substack, Medium, YouTube channels, podcasts, GitHub releases."""

import calendar
from datetime import UTC, datetime
from html.parser import HTMLParser

import feedparser
import httpx

from radar.canonical import canonicalize, item_id
from radar.config import Source
from radar.models import RawItem

MAX_TEXT_CHARS = 4000


class _TextExtractor(HTMLParser):
    """Collect the text content of an HTML fragment."""

    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


def html_to_text(html: str) -> str:
    """Strip tags and collapse whitespace."""
    parser = _TextExtractor()
    parser.feed(html)
    parser.close()
    return " ".join(" ".join(parser.parts).split())


def _entry_text(entry: feedparser.FeedParserDict) -> str:
    """Full content if the feed has it, otherwise the summary/description."""
    if entry.get("content"):
        html = entry.content[0].get("value", "")
    else:
        html = entry.get("summary", "")
    return html_to_text(html)[:MAX_TEXT_CHARS]


def _entry_date(entry: feedparser.FeedParserDict) -> datetime | None:
    """Published (or updated) time as an aware UTC datetime."""
    parsed = entry.get("published_parsed") or entry.get("updated_parsed")
    if parsed is None:
        return None
    return datetime.fromtimestamp(calendar.timegm(parsed), tz=UTC)


def parse_feed(content: bytes, source: Source, fetched_at: datetime) -> list[RawItem]:
    """Turn feed XML into raw items. Entries without a link are skipped."""
    feed = feedparser.parse(content)
    items = []
    for entry in feed.entries:
        link = entry.get("link")
        if not link:
            continue
        canonical = canonicalize(link)
        items.append(
            RawItem(
                id=item_id(canonical),
                url=link,
                canonical_url=canonical,
                title=" ".join(entry.get("title", "").split()),
                source_id=source.id,
                source_name=source.name,
                type=source.type,
                lang=source.lang,
                published_at=_entry_date(entry) or fetched_at,
                fetched_at=fetched_at,
                author=entry.get("author") or None,
                text=_entry_text(entry),
            )
        )
    return items


def collect(client: httpx.Client, source: Source, fetched_at: datetime) -> list[RawItem]:
    """Download and parse one feed. Raises on HTTP errors."""
    response = client.get(source.url)
    response.raise_for_status()
    return parse_feed(response.content, source, fetched_at)
