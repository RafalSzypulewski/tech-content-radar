"""Wrapper around the local `claude` CLI (headless mode, uses the subscription).

Never uses the Anthropic API: if ANTHROPIC_API_KEY is set we abort, because the
CLI would then bill the API instead of the subscription.
"""

import json
import os
import re
import shutil
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, Field, ValidationError

from radar.models import Enrichment, RawItem

PROMPTS_DIR = Path("prompts")
TIMEOUT_SECONDS = 300
ITEM_TEXT_CHARS = 1500
RETRY_REMINDER = (
    "\n\nIMPORTANT: your previous answer was not valid. Return ONLY a valid JSON array "
    "with one object per item id, no prose and no code fences."
)
_FENCE = re.compile(r"^```(?:json)?\s*(.*?)\s*```$", re.DOTALL)


class LLMSetupError(Exception):
    """The environment is not safe or not able to run the claude CLI. Abort the run."""


class LLMCallError(Exception):
    """One claude call failed or returned an unusable answer."""


class ScoreAnswer(BaseModel):
    """One item in the model's JSON answer."""

    id: str
    title_en: str
    summary_en: str
    relevance: int = Field(ge=1, le=10)
    quality: int = Field(ge=1, le=10)
    reason: str
    tags: list[str] = []


def claude_executable() -> str:
    """Path of the claude CLI. Raises LLMSetupError if it must not or cannot be used."""
    if os.environ.get("ANTHROPIC_API_KEY"):
        raise LLMSetupError(
            "ANTHROPIC_API_KEY is set. The claude CLI would bill the Anthropic API instead of "
            "your subscription. Unset it and run again."
        )
    path = shutil.which("claude")
    if path is None:
        raise LLMSetupError(
            "The `claude` command was not found. Install Claude Code and log in "
            "(https://claude.com/claude-code), then run again."
        )
    return path


def run_claude(executable: str, prompt: str) -> str:
    """Send `prompt` over stdin to `claude -p` and return the model's answer text.

    Runs in an empty temp dir with tools disabled, so no project files or CLAUDE.md
    end up in the prompt.
    """
    with tempfile.TemporaryDirectory() as workdir:
        try:
            completed = subprocess.run(
                [
                    executable,
                    "-p",
                    "--output-format",
                    "json",
                    "--tools",
                    "",
                    "--no-session-persistence",
                    "--strict-mcp-config",
                ],
                input=prompt,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=TIMEOUT_SECONDS,
                cwd=workdir,
            )
        except subprocess.TimeoutExpired as exc:
            raise LLMCallError(f"claude timed out after {TIMEOUT_SECONDS} s") from exc
    if completed.returncode != 0:
        raise LLMCallError(f"claude exited with {completed.returncode}: {completed.stderr[:500]}")
    try:
        envelope = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise LLMCallError(f"claude output is not JSON: {completed.stdout[:200]!r}") from exc
    if envelope.get("is_error"):
        raise LLMCallError(f"claude reported an error: {str(envelope.get('result'))[:500]}")
    return envelope.get("result") or ""


def parse_json_answer(text: str) -> object:
    """Parse the model's answer as JSON, tolerating ```json code fences around it."""
    text = text.strip()
    match = _FENCE.match(text)
    if match:
        text = match.group(1)
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise LLMCallError(f"answer is not valid JSON: {exc}") from exc


def render(template: str, **values: str) -> str:
    """Fill `{name}` placeholders. Other braces (e.g. JSON examples) are left alone."""
    for name, value in values.items():
        template = template.replace("{" + name + "}", value)
    return template


def build_score_prompt(template: str, items: list[RawItem], tags: list[str]) -> str:
    """The scoring prompt for one batch."""
    payload = [
        {
            "id": item.id,
            "title": item.title,
            "lang": item.lang,
            "type": item.type,
            "source_name": item.source_name,
            "text": item.text[:ITEM_TEXT_CHARS],
        }
        for item in items
    ]
    return render(
        template,
        tags=", ".join(tags),
        items=json.dumps(payload, ensure_ascii=False, indent=2),
    )


def parse_score_answer(text: str, allowed_tags: list[str]) -> dict[str, ScoreAnswer]:
    """Validate the answer; returns answers by id. Unknown tags are dropped."""
    data = parse_json_answer(text)
    if not isinstance(data, list):
        raise LLMCallError("answer is not a JSON array")
    answers = {}
    for entry in data:
        try:
            answer = ScoreAnswer.model_validate(entry)
        except ValidationError:
            continue  # treated like a missing id
        answer.tags = [t for t in answer.tags if t in allowed_tags]
        answers[answer.id] = answer
    return answers


def _to_enrichment(answer: ScoreAnswer, scored_at: datetime) -> Enrichment:
    return Enrichment(**answer.model_dump(), scored_at=scored_at)


def score_batch(
    executable: str,
    template: str,
    items: list[RawItem],
    tags: list[str],
    now: datetime,
) -> list[Enrichment]:
    """Score one batch. Items missing from the answer are retried once, then marked as errors."""
    results: dict[str, Enrichment] = {}
    pending = items
    error = ""
    for attempt in range(2):
        prompt = build_score_prompt(template, pending, tags)
        if attempt:
            prompt += RETRY_REMINDER
        try:
            answers = parse_score_answer(run_claude(executable, prompt), tags)
        except LLMCallError as exc:
            error = str(exc)
            continue
        for item in pending:
            if item.id in answers:
                results[item.id] = _to_enrichment(answers[item.id], now)
        pending = [item for item in pending if item.id not in results]
        if not pending:
            break
        error = "missing or invalid in the answer"
    for item in pending:
        results[item.id] = Enrichment(id=item.id, scored_at=now, error=error)
    return [results[item.id] for item in items]


def score_items(
    items: list[RawItem], tags: list[str], batch_size: int, now: datetime
) -> list[Enrichment]:
    """Score all items in batches. Raises LLMSetupError before doing any work if unsafe."""
    executable = claude_executable()
    template = (PROMPTS_DIR / "score.md").read_text(encoding="utf-8")
    results = []
    for start in range(0, len(items), batch_size):
        results += score_batch(executable, template, items[start : start + batch_size], tags, now)
    return results
