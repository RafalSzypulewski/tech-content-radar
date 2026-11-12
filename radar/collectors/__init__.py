"""Run all collectors: dedupe, pre-filter and append to data/raw/."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import httpx

from radar import rawstore
from radar.collectors import devto, hackernews, rss
from radar.config import Source
from radar.extract import extract_text, needs_extraction
from radar.language import detect_lang
from radar.models import RawItem
from radar.prefilter import Term, keep, keyword_score

USER_AGENT = "tech-content-radar/0.1 (+https://github.com/RafalSzypulewski/tech-content-radar)"
COLLECTORS = {"rss": rss.collect, "hackernews": hackernews.collect, "devto": devto.collect}


@dataclass
class SourceStats:
    """Per-source counts for the summary table."""

    source_id: str
    fetched: int = 0
    new: int = 0
    kept: int = 0
    error: str = ""


def collect_all(
    sources: list[Source],
    terms: list[Term],
    raw_dir: Path,
    now: datetime,
    client: httpx.Client,
    min_score: int,
    on_source: Callable[[SourceStats], None] = lambda stat: None,
) -> list[SourceStats]:
    """Collect every source; one failing source never stops the run.

    `on_source` is called with each source's stats as soon as that source is done.
    """
    seen = rawstore.known_ids(raw_dir, now.date())
    kept_items = []
    stats = []
    for source in sources:
        stat = SourceStats(source.id)
        stats.append(stat)
        try:
            collector = COLLECTORS.get(source.kind)
            if collector is None:
                stat.error = f"kind '{source.kind}' not supported yet"
                continue
            try:
                items = collector(client, source, now)
            except Exception as exc:  # any source failure is logged, never fatal
                stat.error = f"{type(exc).__name__}: {exc}"
                continue
            stat.fetched = len(items)
            for item in items:
                if item.id in seen:
                    continue
                seen.add(item.id)
                stat.new += 1
                score, matched = keyword_score(f"{item.title} {item.text}", terms)
                item = item.model_copy(update={"matched_keywords": matched})
                if keep(item, source, now, score, min_score):
                    stat.kept += 1
                    kept_items.append(add_text_and_lang(client, item, source))
        finally:
            on_source(stat)
    if kept_items:
        rawstore.append_items(raw_dir, now.date(), kept_items)
    return stats


def add_text_and_lang(client: httpx.Client, item: RawItem, source: Source) -> RawItem:
    """Fill in article text for short blog items, then detect the language.

    Runs only on kept items, so pages are not downloaded again for items the
    pre-filter drops on every run.
    """
    text = item.text
    if needs_extraction(item.type, text):
        extracted = extract_text(client, item.url)
        if extracted and len(extracted) > len(text):
            text = extracted
    lang = detect_lang(f"{item.title}\n{text}", fallback=source.lang)
    return item.model_copy(update={"text": text, "lang": lang})


def make_client() -> httpx.Client:
    """HTTP client with a polite User-Agent and sane timeouts."""
    return httpx.Client(
        headers={"User-Agent": USER_AGENT}, timeout=20, follow_redirects=True
    )


HEADER = ("source", "fetched", "new", "kept", "errors")


def format_row(cells: tuple[str, ...], source_width: int) -> str:
    """One table line. Number columns have fixed widths so rows can be printed one by one."""
    widths = (source_width, len("fetched"), 5, 5)
    return "  ".join(c.ljust(w) for c, w in zip(cells[:4], widths, strict=True)) + "  " + cells[4]


def stats_cells(stat: SourceStats) -> tuple[str, ...]:
    """A source's stats as table cells, in HEADER order."""
    return (stat.source_id, str(stat.fetched), str(stat.new), str(stat.kept), stat.error)
