import json
import subprocess

import pytest
import yaml

from radar import draft, llm
from radar.draft import (
    DraftAnswer,
    ask_claude,
    build_prompt,
    make_roundup,
    read_drafted,
    record_drafted,
    render_draft,
    write_draft,
)
from radar.models import Enrichment
from tests.conftest import NOW
from tests.test_store import _item

DAY = NOW.date()


def _pairs():
    a = _item("aaaaaaaaaaaa", title="Flaky tests").model_copy(
        update={"url": "https://example.com/flaky", "text": "x" * 3000}
    )
    b = _item("bbbbbbbbbbbb", title="Testy w Playwright").model_copy(
        update={"url": "https://blog.example.pl/pw", "lang": "pl", "source_name": "Blog PL"}
    )
    return [
        (a, Enrichment(id=a.id, scored_at=NOW, title_en="Flaky tests", summary_en="About flakes.")),
        (b, Enrichment(id=b.id, scored_at=NOW, title_en="Tests in Playwright", summary_en="PW.")),
    ]


def _answer(ids=("aaaaaaaaaaaa", "bbbbbbbbbbbb")) -> dict:
    return {
        "intro": "Two reads about reliable tests.",
        "items": [
            {"id": i, "heading": f"Heading {i[0]}", "summary": f"Summary {i[0]}."} for i in ids
        ],
    }


def _completed(result: str):
    envelope = {"type": "result", "is_error": False, "result": result}
    return subprocess.CompletedProcess(
        args=[], returncode=0, stdout=json.dumps(envelope), stderr=""
    )


def _front_matter(text: str) -> dict:
    assert text.startswith("---\n")
    return yaml.safe_load(text.split("---\n")[1])


def test_draft_front_matter_is_valid():
    text = render_draft(DAY, DraftAnswer.model_validate(_answer()), _pairs())

    assert _front_matter(text) == {
        "title": "Testing & AI roundup — 2026-10-29",
        "date": DAY,
        "tags": ["testing", "automation", "ai"],
        "draft": True,
    }


def test_draft_body_has_links_and_take_placeholders():
    text = render_draft(DAY, DraftAnswer.model_validate(_answer()), _pairs())

    assert "\n\nTwo reads about reliable tests.\n\n## Heading a\n" in text
    assert "Summary a. [Original on Example](https://example.com/flaky)" in text
    assert "Summary b. [Original on Blog PL](https://blog.example.pl/pw)" in text
    assert text.count("<!-- your take: -->") == 2


def test_draft_ignores_ids_the_model_invented():
    answer = DraftAnswer.model_validate(_answer(("aaaaaaaaaaaa", "ffffffffffff")))
    text = render_draft(DAY, answer, _pairs())
    assert "Heading f" not in text


def test_build_prompt():
    template = (llm.PROMPTS_DIR / "draft.md").read_text(encoding="utf-8")
    prompt = build_prompt(template, DAY, _pairs())

    assert "published on 2026-10-29" in prompt
    payload = json.loads(prompt.split("Items:\n\n", 1)[1])
    assert [p["id"] for p in payload] == ["aaaaaaaaaaaa", "bbbbbbbbbbbb"]
    assert len(payload[0]["text"]) == 1500
    assert payload[1]["url"] == "https://blog.example.pl/pw"


def test_draft_prompt_rules():
    template = (llm.PROMPTS_DIR / "draft.md").read_text(encoding="utf-8")
    assert "Summarize in your own words. Never copy" in template
    assert "Always write in English" in template
    assert "original link is added automatically" in template


def test_ask_claude_retries_on_missing_item(mocker):
    run = mocker.patch("radar.llm.subprocess.run")
    run.side_effect = [
        _completed(json.dumps(_answer(("aaaaaaaaaaaa",)))),
        _completed("```json\n" + json.dumps(_answer()) + "\n```"),
    ]

    answer = ask_claude("/bin/claude", "prompt", {"aaaaaaaaaaaa", "bbbbbbbbbbbb"})

    assert len(answer.items) == 2
    assert llm.RETRY_REMINDER in run.call_args_list[1].kwargs["input"]


def test_ask_claude_gives_up_after_retry(mocker):
    mocker.patch("radar.llm.subprocess.run", side_effect=[_completed("no"), _completed("{}")])
    with pytest.raises(llm.LLMCallError):
        ask_claude("/bin/claude", "prompt", {"aaaaaaaaaaaa"})


def test_write_draft_never_overwrites(tmp_path):
    names = [write_draft(DAY, str(n), tmp_path).name for n in range(3)]
    assert names == [
        "2026-10-29-roundup.md",
        "2026-10-29-roundup-2.md",
        "2026-10-29-roundup-3.md",
    ]


def test_drafted_ids_accumulate(tmp_path):
    path = tmp_path / "drafted.json"
    assert read_drafted(path) == set()
    record_drafted({"b", "a"}, path)
    record_drafted({"c"}, path)
    assert read_drafted(path) == {"a", "b", "c"}


def test_make_roundup_records_ids_only_on_success(tmp_path, monkeypatch, mocker):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    (tmp_path / "prompts").mkdir()
    (tmp_path / "prompts" / "draft.md").write_text("{date}\n{items}", encoding="utf-8")
    mocker.patch("radar.llm.shutil.which", return_value="/bin/claude")
    run = mocker.patch("radar.llm.subprocess.run")

    run.side_effect = [_completed("bad"), _completed("bad")]
    with pytest.raises(llm.LLMCallError):
        make_roundup(DAY, _pairs())
    assert read_drafted() == set()
    assert not draft.DRAFTS_DIR.exists()

    run.side_effect = [_completed(json.dumps(_answer()))]
    path = make_roundup(DAY, _pairs())
    assert path.as_posix() == "drafts/2026-10-29-roundup.md"
    assert read_drafted() == {"aaaaaaaaaaaa", "bbbbbbbbbbbb"}
