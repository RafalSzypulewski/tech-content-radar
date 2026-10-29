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
