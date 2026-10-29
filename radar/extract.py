"""Article text extraction with trafilatura for items with short feed text."""

import httpx
import trafilatura

from radar.collectors.rss import MAX_TEXT_CHARS

MIN_FEED_TEXT_CHARS = 500
TIMEOUT_SECONDS = 10


def needs_extraction(item_type: str, text: str) -> bool:
    """Only blog items whose feed text is shorter than 500 chars."""
    return item_type == "blog" and len(text) < MIN_FEED_TEXT_CHARS


def extract_text(client: httpx.Client, url: str) -> str | None:
    """Download the page and extract its main text; None on any failure."""
    try:
        response = client.get(url, timeout=TIMEOUT_SECONDS)
        response.raise_for_status()
    except httpx.HTTPError:
        return None
    text = trafilatura.extract(response.text)
    if not text:
        return None
    return " ".join(text.split())[:MAX_TEXT_CHARS]
