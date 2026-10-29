"""Pydantic models for data stored in JSONL files."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class RawItem(BaseModel):
    """One collected item: a line in data/raw/YYYY-MM-DD.jsonl."""

    id: str
    url: str
    canonical_url: str
    title: str
    source_id: str
    source_name: str
    type: str
    lang: Literal["en", "pl", "other"]
    published_at: datetime
    fetched_at: datetime
    author: str | None = None
    text: str = ""
    engagement: dict[str, int] = {}
    matched_keywords: list[str] = []


class Enrichment(BaseModel):
    """LLM score + summary for one item: a line in data/enriched/scores.jsonl.

    When scoring failed, `error` is set and the other fields are empty/zero.
    """

    id: str
    title_en: str = ""
    summary_en: str = ""
    relevance: int = 0
    quality: int = 0
    reason: str = ""
    tags: list[str] = []
    scored_at: datetime
    error: str | None = None
