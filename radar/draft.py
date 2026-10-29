"""Blog roundup drafts (drafts/YYYY-MM-DD-roundup.md) for items marked `write`, via claude -p."""

import json
from datetime import date
from pathlib import Path

from pydantic import BaseModel, ValidationError

from radar import llm
from radar.models import Enrichment, RawItem

DRAFTS_DIR = Path("drafts")
DRAFTED_PATH = Path("data/enriched/drafted.json")
ITEM_TEXT_CHARS = 1500


class DraftItem(BaseModel):
    id: str
    heading: str
    summary: str


class DraftAnswer(BaseModel):
    intro: str
    items: list[DraftItem]


def read_drafted(path: Path = DRAFTED_PATH) -> set[str]:
    """Ids already used in a draft."""
    if not path.exists():
        return set()
    return set(json.loads(path.read_text(encoding="utf-8")))


def record_drafted(ids: set[str], path: Path = DRAFTED_PATH) -> None:
    """Add ids to the drafted list so they are never drafted twice."""
    path.parent.mkdir(parents=True, exist_ok=True)
    all_ids = sorted(read_drafted(path) | ids)
    path.write_text(json.dumps(all_ids, indent=2) + "\n", encoding="utf-8", newline="\n")


def build_prompt(template: str, day: date, pairs: list[tuple[RawItem, Enrichment]]) -> str:
    """The draft prompt for the chosen items."""
    payload = [
        {
            "id": item.id,
            "title": item.title,
            "title_en": e.title_en,
            "source_name": item.source_name,
            "url": item.url,
            "summary_en": e.summary_en,
            "text": item.text[:ITEM_TEXT_CHARS],
        }
        for item, e in pairs
    ]
    return llm.render(
        template,
        date=day.isoformat(),
        items=json.dumps(payload, ensure_ascii=False, indent=2),
    )


def ask_claude(executable: str, prompt: str, ids: set[str]) -> DraftAnswer:
    """Get a valid answer covering every id; one retry, then LLMCallError."""
    error = ""
    for attempt in range(2):
        try:
            text = llm.run_claude(executable, prompt + (llm.RETRY_REMINDER if attempt else ""))
            answer = DraftAnswer.model_validate(llm.parse_json_answer(text))
        except (llm.LLMCallError, ValidationError) as exc:
            error = str(exc)
            continue
        missing = ids - {i.id for i in answer.items}
        if not missing:
            return answer
        error = f"answer is missing items: {', '.join(sorted(missing))}"
    raise llm.LLMCallError(error)


def render_draft(day: date, answer: DraftAnswer, pairs: list[tuple[RawItem, Enrichment]]) -> str:
    """Markdown with front matter; links come from our data, not from the model."""
    by_id = {item.id: item for item, _ in pairs}
    parts = [
        "---\n"
        f'title: "Testing & AI roundup — {day.isoformat()}"\n'
        f"date: {day.isoformat()}\n"
        "tags: [testing, automation, ai]\n"
        "draft: true\n"
        "---",
        answer.intro.strip(),
    ]
    for entry in answer.items:
        item = by_id.get(entry.id)
        if item is None:
            continue  # the model added an id we did not ask for
        parts.append(
            f"## {entry.heading.strip()}\n"
            f"{entry.summary.strip()} [Original on {item.source_name}]({item.url})\n\n"
            "<!-- your take: -->"
        )
    return "\n\n".join(parts) + "\n"


def write_draft(day: date, text: str, drafts_dir: Path = DRAFTS_DIR) -> Path:
    """Write the roundup without overwriting an earlier one from the same day."""
    drafts_dir.mkdir(parents=True, exist_ok=True)
    path = drafts_dir / f"{day.isoformat()}-roundup.md"
    n = 2
    while path.exists():
        path = drafts_dir / f"{day.isoformat()}-roundup-{n}.md"
        n += 1
    path.write_text(text, encoding="utf-8", newline="\n")
    return path


def make_roundup(day: date, pairs: list[tuple[RawItem, Enrichment]]) -> Path:
    """Generate, write and record one roundup. Raises LLMSetupError / LLMCallError."""
    executable = llm.claude_executable()
    template = (llm.PROMPTS_DIR / "draft.md").read_text(encoding="utf-8")
    prompt = build_prompt(template, day, pairs)
    answer = ask_claude(executable, prompt, {item.id for item, _ in pairs})
    path = write_draft(day, render_draft(day, answer, pairs))
    record_drafted({item.id for item, _ in pairs})
    return path
