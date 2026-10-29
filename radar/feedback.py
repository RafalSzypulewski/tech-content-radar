"""Parse keep / skip / write checkboxes from review/*.md (the files are the source of truth)."""

import re
from pathlib import Path
from typing import Literal

Label = Literal["keep", "skip", "write"]
PRIORITY: dict[str, int] = {"write": 3, "keep": 2, "skip": 1}

_ID = re.compile(r"<!-- id: ([0-9a-f]+) -->")
_BOX = re.compile(r"- \[([ xX])\] (keep|skip|write)\b")
_HEADING = re.compile(r"^### ", re.MULTILINE)


def parse_review(text: str) -> dict[str, Label]:
    """Feedback per item id in one digest.

    A block runs from an item heading to the next one; it counts only if it has exactly
    one id comment. Unchecked boxes = no feedback; several checked: write > keep > skip.
    """
    feedback: dict[str, Label] = {}
    for block in _HEADING.split(text)[1:]:
        ids = _ID.findall(block)
        if len(ids) != 1:
            continue
        checked = [label for mark, label in _BOX.findall(block) if mark in "xX"]
        if checked:
            feedback[ids[0]] = max(checked, key=PRIORITY.__getitem__)
    return feedback


def parse_all(review_dir: Path = Path("review")) -> dict[str, Label]:
    """Feedback from every digest; if an id appears twice, the later file wins."""
    feedback: dict[str, Label] = {}
    for path in sorted(review_dir.glob("*.md")):
        feedback.update(parse_review(path.read_text(encoding="utf-8")))
    return feedback
