"""Read and append data/raw/YYYY-MM-DD.jsonl files."""

from collections.abc import Iterable
from datetime import date, timedelta
from pathlib import Path

from radar.models import RawItem

DEDUPE_DAYS = 90


def _file_date(path: Path) -> date | None:
    """Parse the date from a raw file name; None for files like _meta.json."""
    try:
        return date.fromisoformat(path.stem)
    except ValueError:
        return None


def read_items(path: Path) -> list[RawItem]:
    """Read all items from one raw JSONL file."""
    lines = path.read_text(encoding="utf-8").splitlines()
    return [RawItem.model_validate_json(line) for line in lines if line.strip()]


def known_ids(raw_dir: Path, today: date, days: int = DEDUPE_DAYS) -> set[str]:
    """Ids of all items in raw files dated within the last `days` days."""
    ids: set[str] = set()
    if not raw_dir.exists():
        return ids
    oldest = today - timedelta(days=days)
    for path in raw_dir.glob("*.jsonl"):
        file_date = _file_date(path)
        if file_date is not None and file_date >= oldest:
            ids.update(item.id for item in read_items(path))
    return ids


def append_items(raw_dir: Path, day: date, items: Iterable[RawItem]) -> Path:
    """Append items to the raw file for `day`, creating it if needed."""
    raw_dir.mkdir(parents=True, exist_ok=True)
    path = raw_dir / f"{day.isoformat()}.jsonl"
    with path.open("a", encoding="utf-8", newline="\n") as f:
        for item in items:
            f.write(item.model_dump_json() + "\n")
    return path
