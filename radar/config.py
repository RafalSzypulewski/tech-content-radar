"""Load sources.yaml and topics.yaml."""

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel

SourceKind = Literal["rss", "hackernews", "devto"]
SourceType = Literal["blog", "video", "podcast", "release", "community"]


class Source(BaseModel):
    """One entry from sources.yaml, with defaults already applied."""

    id: str
    name: str
    kind: SourceKind
    type: SourceType
    url: str | None = None
    lang: Literal["en", "pl"] = "en"
    trust: float
    max_age_days: int
    always_include: bool = False
    query: list[str] = []
    min_points: int = 0
    tags: list[str] = []


class Profile(BaseModel):
    """A topic profile used for embedding similarity."""

    id: str
    text: str


class Topics(BaseModel):
    """Contents of topics.yaml."""

    keywords: list[str]
    profiles: list[Profile]
    tags: list[str]


def load_sources(path: Path) -> list[Source]:
    """Read sources.yaml and merge `defaults` into every source."""
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    defaults = data.get("defaults", {})
    return [Source(**{**defaults, **entry}) for entry in data["sources"]]


def load_topics(path: Path) -> Topics:
    """Read topics.yaml."""
    return Topics(**yaml.safe_load(path.read_text(encoding="utf-8")))
