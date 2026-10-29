"""Write the review digest (review/YYYY-MM-DD.md)."""

import re
from datetime import date
from pathlib import Path

from radar.ranking import Final

REVIEW_DIR = Path("review")
_ID_COMMENT = re.compile(r"<!-- id: ([0-9a-f]+) -->")
_RELATED_COMMENT = re.compile(r"<!-- related: ([0-9a-f ]+) -->")
INSTRUCTIONS = (
    "Mark one box per item: keep = good material, skip = not interesting, "
    "write = make a blog draft."
)


def shown_ids(review_dir: Path = REVIEW_DIR) -> set[str]:
    """Ids already shown in any digest, as a main entry or as a related link."""
    ids: set[str] = set()
    for path in review_dir.glob("*.md"):
        text = path.read_text(encoding="utf-8")
        ids.update(_ID_COMMENT.findall(text))
        for group in _RELATED_COMMENT.findall(text):
            ids.update(group.split())
    return ids


def _entry(number: int, entry: Final) -> str:
    item, e = entry.item, entry.enrichment
    lines = [f"### {number}. {e.title_en or item.title} — score {entry.score:.2f}"]
    lines.append(f"<!-- id: {item.id} -->")
    if item.lang == "pl":
        lines.append(f"Original (PL): {item.title}")
    meta = [item.type, item.source_name, item.lang.upper(), item.published_at.date().isoformat()]
    lines.append(" · ".join([*meta, item.url]))
    lines.append(f"**Summary:** {e.summary_en}")
    lines.append(f"**Why:** {e.reason}")
    lines.append(f"**Tags:** {', '.join(e.tags)}")
    if entry.related:
        links = ", ".join(
            f"[{r.enrichment.title_en or r.item.title}]({r.item.url})" for r in entry.related
        )
        ids = " ".join(r.item.id for r in entry.related)
        lines.append(f"Related: {links} <!-- related: {ids} -->")
    # One list item per box: Markdown only renders a checkbox at the start of a list item.
    lines += ["- [ ] keep", "- [ ] skip", "- [ ] write"]
    return "\n".join(lines)


def render_digest(day: date, entries: list[Final]) -> str:
    """The digest Markdown for `entries` (already ranked and cut to size)."""
    parts = [f"# Review — {day.isoformat()} ({len(entries)} items)", INSTRUCTIONS]
    parts += [_entry(n, entry) for n, entry in enumerate(entries, start=1)]
    return "\n\n".join(parts) + "\n"


def write_digest(day: date, text: str, review_dir: Path = REVIEW_DIR) -> Path:
    """Write the digest without overwriting: a second run the same day gets -2, -3…"""
    review_dir.mkdir(parents=True, exist_ok=True)
    path = review_dir / f"{day.isoformat()}.md"
    n = 2
    while path.exists():
        path = review_dir / f"{day.isoformat()}-{n}.md"
        n += 1
    path.write_text(text, encoding="utf-8", newline="\n")
    return path
