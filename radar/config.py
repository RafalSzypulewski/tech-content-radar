"""Load sources.yaml, topics.yaml and settings (overridable via .env)."""

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import yaml
from dotenv import load_dotenv
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


@dataclass(frozen=True)
class Settings:
    """Tunable numbers; each can be overridden by an environment variable of the same name."""

    LLM_MAX_ITEMS: int = 60
    LLM_BATCH_SIZE: int = 20
    DIGEST_SIZE: int = 20
    CLUSTER_THRESHOLD: float = 0.85
    BACKLOG_ALERT: int = 100
    FRESHNESS_HALF_LIFE_DAYS: float = 7.0


def load_settings(env_file: Path | None = Path(".env")) -> Settings:
    """Defaults, overridden by `env_file` (if it exists) and the environment."""
    if env_file is not None:
        load_dotenv(env_file)
    defaults = Settings()
    overrides = {
        name: type(getattr(defaults, name))(os.environ[name])
        for name in Settings.__dataclass_fields__
        if name in os.environ
    }
    return Settings(**overrides)
