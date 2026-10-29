from datetime import UTC, datetime
from pathlib import Path

import pytest

from radar.config import Source

FIXTURES = Path(__file__).parent / "fixtures"
NOW = datetime(2026, 10, 29, 12, 0, tzinfo=UTC)


def make_source(**overrides) -> Source:
    """A valid RSS source; override any field."""
    fields = {
        "id": "example",
        "name": "Example",
        "kind": "rss",
        "type": "blog",
        "url": "https://example.com/feed",
        "lang": "en",
        "trust": 0.5,
        "max_age_days": 21,
    }
    return Source(**{**fields, **overrides})


@pytest.fixture
def feed_bytes():
    """Read a feed fixture by file name."""
    return lambda name: (FIXTURES / "feeds" / name).read_bytes()
