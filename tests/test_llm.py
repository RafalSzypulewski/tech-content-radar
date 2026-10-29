import json
import subprocess

import pytest

from radar import llm
from radar.llm import (
    LLMCallError,
    LLMSetupError,
    build_score_prompt,
    claude_executable,
    parse_json_answer,
    render,
    run_claude,
    score_batch,
    score_items,
)
from tests.conftest import NOW
from tests.test_store import _item

TAGS = ["test-automation", "ai", "tutorial"]
TEMPLATE = "Tags: {tags}\nItems:\n{items}\nExample: [{\"id\": \"x\"}]"


def _answer(item_id: str, **overrides) -> dict:
    fields = {
        "id": item_id,
        "title_en": f"Title {item_id}",
        "summary_en": "A summary.",
        "relevance": 8,
        "quality": 7,
        "reason": "Practical.",
        "tags": ["test-automation"],
    }
    return {**fields, **overrides}


def _completed(result: str, returncode: int = 0, is_error: bool = False):
    envelope = {"type": "result", "is_error": is_error, "result": result}
    return subprocess.CompletedProcess(
        args=[], returncode=returncode, stdout=json.dumps(envelope), stderr="boom"
    )


@pytest.fixture
def fake_run(mocker):
    """Patch subprocess.run; set .side_effect to a list of answers (str) or exceptions."""
    run = mocker.patch("radar.llm.subprocess.run")

    def responses(*answers):
        run.side_effect = [a if isinstance(a, Exception) else _completed(a) for a in answers]
        return run

    return responses


# --- environment checks ---------------------------------------------------------------


def test_api_key_aborts(monkeypatch, mocker):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    mocker.patch("radar.llm.shutil.which", return_value="/usr/bin/claude")
    with pytest.raises(LLMSetupError, match="ANTHROPIC_API_KEY"):
        claude_executable()


def test_missing_claude_gives_clear_error(monkeypatch, mocker):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    mocker.patch("radar.llm.shutil.which", return_value=None)
    with pytest.raises(LLMSetupError, match="`claude` command was not found"):
        claude_executable()


def test_score_items_checks_environment_before_calling(monkeypatch, mocker):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    run = mocker.patch("radar.llm.subprocess.run")
    with pytest.raises(LLMSetupError):
        score_items([_item("a")], TAGS, batch_size=20, now=NOW)
    run.assert_not_called()


# --- the subprocess call ----------------------------------------------------------------


def test_run_claude_sends_prompt_on_stdin(fake_run):
    run = fake_run("hello")

    assert run_claude("/bin/claude", "my prompt") == "hello"

    args, kwargs = run.call_args
    assert args[0][:4] == ["/bin/claude", "-p", "--output-format", "json"]
    assert args[0][4:6] == ["--tools", ""]
    assert "my prompt" not in args[0]
    assert kwargs["input"] == "my prompt"
    assert kwargs["timeout"] == 300
    assert kwargs["encoding"] == "utf-8"
    assert kwargs["cwd"]  # a temp dir, not the repo


@pytest.mark.parametrize(
    "completed",
    [
        _completed("x", returncode=1),
        _completed("Credit balance too low", is_error=True),
        subprocess.CompletedProcess(args=[], returncode=0, stdout="not json", stderr=""),
    ],
)
def test_run_claude_failures(mocker, completed):
    mocker.patch("radar.llm.subprocess.run", return_value=completed)
    with pytest.raises(LLMCallError):
        run_claude("/bin/claude", "p")


def test_run_claude_timeout(mocker):
    mocker.patch(
        "radar.llm.subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="claude", timeout=300)
    )
    with pytest.raises(LLMCallError, match="timed out"):
        run_claude("/bin/claude", "p")


# --- parsing ----------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    ['[{"a": 1}]', '```json\n[{"a": 1}]\n```', '```\n[{"a": 1}]\n```', '  [{"a": 1}]\n'],
)
def test_parse_json_answer_tolerates_fences(text):
    assert parse_json_answer(text) == [{"a": 1}]


def test_parse_json_answer_invalid():
    with pytest.raises(LLMCallError):
        parse_json_answer("Sure! Here are the scores: ...")


def test_render_leaves_other_braces_alone():
    assert render(TEMPLATE, tags="a, b", items="[]") == (
        'Tags: a, b\nItems:\n[]\nExample: [{"id": "x"}]'
    )


def test_build_score_prompt_sends_expected_fields():
    item = _item("a", title="Zażółć").model_copy(update={"text": "x" * 3000, "lang": "pl"})

    prompt = build_score_prompt(TEMPLATE, [item], TAGS)

    payload = json.loads(prompt.split("Items:\n", 1)[1].split("\nExample:")[0])
    assert payload == [
        {
            "id": "a",
            "title": "Zażółć",
            "lang": "pl",
            "type": "blog",
            "source_name": "Example",
            "text": "x" * 1500,
        }
    ]
    assert "Tags: test-automation, ai, tutorial" in prompt


def test_score_prompt_template_requires_english():
    template = llm.PROMPTS_DIR.joinpath("score.md").read_text(encoding="utf-8")
    assert "Write all output in English, even when the source is in Polish." in template
    assert "{tags}" in template and "{items}" in template


# --- batches: valid, fences, retry, errors -----------------------------------------------


def test_valid_response(fake_run):
    run = fake_run(json.dumps([_answer("a"), _answer("b", tags=["ai", "made-up"])]))

    results = score_batch("/bin/claude", TEMPLATE, [_item("a"), _item("b")], TAGS, NOW)

    assert [r.id for r in results] == ["a", "b"]
    assert results[0].relevance == 8 and results[0].quality == 7
    assert results[0].title_en == "Title a" and results[0].error is None
    assert results[0].scored_at == NOW
    assert results[1].tags == ["ai"]  # unknown tag dropped
    assert run.call_count == 1


def test_response_in_code_fences(fake_run):
    fake_run("```json\n" + json.dumps([_answer("a")]) + "\n```")
    [result] = score_batch("/bin/claude", TEMPLATE, [_item("a")], TAGS, NOW)
    assert result.error is None


def test_invalid_json_retries_then_succeeds(fake_run):
    run = fake_run("not json at all", json.dumps([_answer("a")]))

    [result] = score_batch("/bin/claude", TEMPLATE, [_item("a")], TAGS, NOW)

    assert result.error is None
    assert run.call_count == 2
    assert "Return ONLY a valid JSON array" in run.call_args_list[1].kwargs["input"]


def test_invalid_json_twice_records_error(fake_run):
    run = fake_run("nope", "still nope")

    results = score_batch("/bin/claude", TEMPLATE, [_item("a"), _item("b")], TAGS, NOW)

    assert run.call_count == 2
    assert all(r.error and "not valid JSON" in r.error for r in results)
    assert all(r.relevance == 0 for r in results)


def test_missing_ids_are_retried_alone(fake_run):
    run = fake_run(json.dumps([_answer("a")]), json.dumps([_answer("b")]))

    results = score_batch("/bin/claude", TEMPLATE, [_item("a"), _item("b")], TAGS, NOW)

    assert [(r.id, r.error) for r in results] == [("a", None), ("b", None)]
    retry_prompt = run.call_args_list[1].kwargs["input"]
    assert '"id": "b"' in retry_prompt and '"id": "a"' not in retry_prompt


def test_still_missing_after_retry_records_error(fake_run):
    fake_run(json.dumps([_answer("a")]), json.dumps([_answer("x-unrequested")]))

    results = score_batch("/bin/claude", TEMPLATE, [_item("a"), _item("b")], TAGS, NOW)

    assert results[0].error is None
    assert results[1].error == "missing or invalid in the answer"


def test_out_of_range_score_counts_as_missing(fake_run):
    fake_run(json.dumps([_answer("a", relevance=11)]), json.dumps([_answer("a", relevance=10)]))
    [result] = score_batch("/bin/claude", TEMPLATE, [_item("a")], TAGS, NOW)
    assert result.relevance == 10


def test_cli_failure_retries_then_records_error(fake_run):
    fake_run(LLMCallError("exit 1"), LLMCallError("exit 1 again"))
    [result] = score_batch("/bin/claude", TEMPLATE, [_item("a")], TAGS, NOW)
    assert result.error == "exit 1 again"


def test_score_items_batches_and_continues_after_failed_batch(monkeypatch, mocker, tmp_path):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    mocker.patch("radar.llm.shutil.which", return_value="/bin/claude")
    (tmp_path / "score.md").write_text(TEMPLATE, encoding="utf-8")
    mocker.patch("radar.llm.PROMPTS_DIR", tmp_path)
    run = mocker.patch("radar.llm.subprocess.run")
    run.side_effect = [
        _completed("garbage"),
        _completed("garbage"),
        _completed(json.dumps([_answer("c")])),
    ]

    results = score_items([_item("a"), _item("b"), _item("c")], TAGS, batch_size=2, now=NOW)

    assert [(r.id, r.error is None) for r in results] == [("a", False), ("b", False), ("c", True)]
    assert run.call_count == 3
