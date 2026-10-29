import shutil
import subprocess
from datetime import date
from pathlib import Path

import pytest

from radar import draft
from radar.__main__ import COMMANDS, HANDLERS, main
from radar.enriched import append_scores, read_scores, read_state
from radar.models import Enrichment
from radar.rawstore import append_items
from tests.conftest import NOW, FakeEmbedder
from tests.test_store import _item


def test_help_lists_all_commands(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["--help"])
    assert exc.value.code == 0
    out = capsys.readouterr().out
    for name in COMMANDS:
        assert name in out


def test_missing_command_is_an_error():
    with pytest.raises(SystemExit) as exc:
        main([])
    assert exc.value.code == 2


def test_every_command_has_a_handler():
    assert set(HANDLERS) == set(COMMANDS)


def test_enrich_aborts_when_api_key_is_set(monkeypatch, capsys):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    assert main(["enrich"]) == 1
    assert "ANTHROPIC_API_KEY is set" in capsys.readouterr().err


def test_enrich_scores_top_unscored_items(tmp_path, monkeypatch, mocker):
    root = Path(__file__).resolve().parent.parent
    for name in ("sources.yaml", "topics.yaml"):
        shutil.copy(root / name, tmp_path / name)
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("LLM_MAX_ITEMS", raising=False)
    items = [_item("a", title="test test"), _item("b", title="garden"), _item("c", title="test")]
    append_items(Path("data/raw"), date(2026, 10, 29), items)
    mocker.patch("radar.llm.claude_executable", return_value="/bin/claude")
    mocker.patch("radar.embeddings.SentenceTransformerEmbedder", FakeEmbedder)
    score = mocker.patch(
        "radar.llm.score_items",
        side_effect=lambda items, tags, batch_size, now: [
            Enrichment(id=i.id, scored_at=now, relevance=5, quality=5) for i in items
        ],
    )

    assert main(["enrich", "--max-items", "2"]) == 0
    assert main(["enrich", "--max-items", "2"]) == 0

    first, second = (c.args[0] for c in score.call_args_list)
    assert len(first) == 2 and score.call_args_list[0].args[2] == 20
    assert {i.id for i in second} == {"a", "b", "c"} - {i.id for i in first}
    assert set(read_scores(Path("data/enriched/scores.jsonl"))) == {"a", "b", "c"}


def test_digest_does_not_repeat_items(tmp_path, monkeypatch, mocker, capsys):
    root = Path(__file__).resolve().parent.parent
    shutil.copy(root / "sources.yaml", tmp_path / "sources.yaml")
    monkeypatch.chdir(tmp_path)
    for name in ("DIGEST_SIZE", "CLUSTER_THRESHOLD", "FRESHNESS_HALF_LIFE_DAYS"):
        monkeypatch.delenv(name, raising=False)
    mocker.patch("radar.embeddings.SentenceTransformerEmbedder", FakeEmbedder)
    raw = Path("data/raw")
    append_items(raw, date(2026, 10, 29), [_item("a", "test"), _item("b", "garden")])
    scores = Path("data/enriched/scores.jsonl")
    append_scores([Enrichment(id=i, scored_at=NOW, relevance=5, quality=5) for i in "ab"], scores)

    assert main(["digest"]) == 0
    first = Path("review").glob("*.md")
    [first] = list(first)
    assert "(2 items)" in first.read_text(encoding="utf-8")

    assert main(["digest"]) == 0
    assert "nothing written" in capsys.readouterr().out
    assert len(list(Path("review").glob("*.md"))) == 1

    append_items(raw, date(2026, 10, 29), [_item("c", "ai")])
    append_scores([Enrichment(id="c", scored_at=NOW, relevance=5, quality=5)], scores)
    assert main(["digest"]) == 0
    [second] = [p for p in Path("review").glob("*.md") if p != first]
    text = second.read_text(encoding="utf-8")
    assert "(1 items)" in text and "<!-- id: c -->" in text


def test_digest_uses_feedback_and_writes_state(tmp_path, monkeypatch, mocker, capsys):
    root = Path(__file__).resolve().parent.parent
    shutil.copy(root / "sources.yaml", tmp_path / "sources.yaml")
    monkeypatch.chdir(tmp_path)
    for name in ("DIGEST_SIZE", "CLUSTER_THRESHOLD", "FRESHNESS_HALF_LIFE_DAYS"):
        monkeypatch.delenv(name, raising=False)
    mocker.patch("radar.embeddings.SentenceTransformerEmbedder", FakeEmbedder)
    # earlier digest: a garden post was skipped, a cooking post was kept
    raw = Path("data/raw")
    append_items(raw, date(2026, 10, 28), [_item("a1", "garden"), _item("a2", "cook")])
    Path("review").mkdir()
    Path("review/2026-10-28.md").write_text(
        "# Review — 2026-10-28 (2 items)\n\n"
        "### 1. G — score 0.5\n<!-- id: a1 -->\n- [ ] keep\n- [x] skip\n- [ ] write\n\n"
        "### 2. C — score 0.5\n<!-- id: a2 -->\n- [x] keep\n- [ ] skip\n- [ ] write\n",
        encoding="utf-8",
    )
    # two new items, equal scores: one like the skipped post, one like the kept post
    append_items(raw, date(2026, 10, 29), [_item("b1", "garden"), _item("b2", "cook")])
    append_scores(
        [Enrichment(id=i, scored_at=NOW, relevance=5, quality=5) for i in ("b1", "b2")],
        Path("data/enriched/scores.jsonl"),
    )

    assert main(["digest"]) == 0

    assert "(feedback: 1 kept/written, 1 skipped)" in capsys.readouterr().out
    [digest] = [p for p in Path("review").glob("*.md") if p.name != "2026-10-28.md"]
    text = digest.read_text(encoding="utf-8")
    assert text.index("<!-- id: b2 -->") < text.index("<!-- id: b1 -->")
    state = read_state(Path("data/enriched/state.json"))
    assert state["last_digest"] == digest.as_posix()
    assert "last_processed_at" in state


# --- draft --------------------------------------------------------------------------------


def _write_marked_review(text_marks: dict[str, str]) -> None:
    blocks = "".join(
        f"### {n}. T — score 0.5\n<!-- id: {i} -->\n"
        f"- [{'x' if m == 'keep' else ' '}] keep\n- [ ] skip\n"
        f"- [{'x' if m == 'write' else ' '}] write\n\n"
        for n, (i, m) in enumerate(text_marks.items(), 1)
    )
    Path("review").mkdir(exist_ok=True)
    Path("review/2026-10-28.md").write_text(f"# Review — 2026-10-28 (2 items)\n\n{blocks}", "utf-8")


def test_draft_never_drafts_an_item_twice(tmp_path, monkeypatch, mocker, capsys):
    monkeypatch.chdir(tmp_path)
    append_items(Path("data/raw"), date(2026, 10, 28), [_item("a1"), _item("a2"), _item("a3")])
    append_scores(
        [Enrichment(id=i, scored_at=NOW, title_en=i) for i in ("a1", "a2", "a3")],
        Path("data/enriched/scores.jsonl"),
    )
    _write_marked_review({"a1": "write", "a2": "keep"})
    roundup = mocker.patch(
        "radar.draft.make_roundup",
        side_effect=lambda day, pairs: (
            draft.record_drafted({i.id for i, _ in pairs}) or Path("drafts/x.md")
        ),
    )

    assert main(["draft"]) == 0
    assert main(["draft"]) == 0  # a1 already drafted
    _write_marked_review({"a1": "write", "a2": "keep", "a3": "write"})
    assert main(["draft"]) == 0

    drafted = [[item.id for item, _ in call.args[1]] for call in roundup.call_args_list]
    assert drafted == [["a1"], ["a3"]]
    assert "no new items marked 'write'" in capsys.readouterr().out


# --- run-local ----------------------------------------------------------------------------


@pytest.fixture
def steps(mocker):
    """Mock every step of run-local and record the order they run in."""
    calls: list[str] = []

    def step(name, result=None, effect=None):
        def run(*args, **kwargs):
            calls.append(name)
            if effect:
                effect()
            return result or 0

        return run

    def git(*args):
        calls.append("git " + " ".join(a for a in args if a != "--"))

    def make(digest_writes=True, staged=("review/new.md",), **results):
        mocker.patch("radar.__main__._git", side_effect=git)
        mocker.patch(
            "radar.__main__.subprocess.run",
            side_effect=lambda cmd, **kw: (
                calls.append("git diff --cached")
                or subprocess.CompletedProcess(cmd, 0, stdout="\n".join(staged))
            ),
        )
        mocker.patch("radar.__main__.cmd_enrich", side_effect=step("enrich", results.get("enrich")))
        state = {"last_digest": None}
        mocker.patch("radar.enriched.read_state", side_effect=lambda *a, **k: dict(state))
        mocker.patch(
            "radar.__main__.cmd_digest",
            side_effect=step(
                "digest",
                results.get("digest"),
                (lambda: state.update(last_digest="review/new.md")) if digest_writes else None,
            ),
        )
        mocker.patch("radar.__main__.cmd_draft", side_effect=step("draft", results.get("draft")))
        mocker.patch("radar.__main__.cmd_notify", side_effect=step("notify", results.get("notify")))
        return calls

    return make


def test_run_local_step_order(tmp_path, monkeypatch, steps):
    monkeypatch.chdir(tmp_path)
    for d in ("data/enriched", "review", "drafts"):
        Path(d).mkdir(parents=True)
    calls = steps()

    assert main(["run-local"]) == 0

    assert [c.split(" -m ")[0] for c in calls] == [
        "git pull --rebase --autostash",
        "enrich",
        "digest",
        "draft",
        "notify",
        "git add data/enriched review drafts",
        "git diff --cached",
        "git commit",
        "git pull --rebase --autostash",
        "git push",
    ]


def test_run_local_flags(tmp_path, monkeypatch, steps):
    monkeypatch.chdir(tmp_path)
    Path("review").mkdir()
    calls = steps()

    assert main(["run-local", "--no-push", "--no-email", "--max-items", "5"]) == 0

    assert "notify" not in calls and "git push" not in calls
    assert calls[-3] == "git add review"  # only existing output paths are added
    assert calls[-2] == "git diff --cached"
    assert calls[-1].startswith("git commit -m local: ")
    assert calls[-1].endswith(" review/new.md")  # the staged files, by name
    from radar import __main__ as cli

    assert cli.cmd_enrich.call_args.args[0].max_items == 5


def test_run_local_no_email_without_new_digest(tmp_path, monkeypatch, steps):
    monkeypatch.chdir(tmp_path)
    calls = steps(digest_writes=False)
    assert main(["run-local"]) == 0
    assert "notify" not in calls


@pytest.mark.parametrize("failing", ["enrich", "digest"])
def test_run_local_stops_when_a_core_step_fails(tmp_path, monkeypatch, steps, failing):
    monkeypatch.chdir(tmp_path)
    calls = steps(**{failing: 1})
    assert main(["run-local"]) == 1
    assert calls[-1] == failing
    assert not any(c.startswith("git commit") for c in calls)


def test_run_local_continues_when_draft_or_email_fails(tmp_path, monkeypatch, steps):
    monkeypatch.chdir(tmp_path)
    Path("review").mkdir()
    calls = steps(draft=1, notify=1)
    assert main(["run-local"]) == 0
    assert "git push" in calls


def test_run_local_nothing_staged_skips_commit(tmp_path, monkeypatch, steps, capsys):
    monkeypatch.chdir(tmp_path)
    Path("review").mkdir()
    calls = steps(staged=())
    assert main(["run-local"]) == 0
    assert not any(c.startswith("git commit") for c in calls)
    assert "nothing to commit" in capsys.readouterr().out


def test_commit_with_empty_drafts_folder_in_a_real_repo(tmp_path, monkeypatch):
    """Regression: an empty drafts/ folder made `git commit -- drafts` fail."""
    from radar.__main__ import _commit_and_push

    monkeypatch.chdir(tmp_path)
    for args in (
        ["init", "-q"],
        ["config", "user.email", "t@example.com"],
        ["config", "user.name", "T"],
    ):
        subprocess.run(["git", *args], check=True)
    Path("drafts").mkdir()
    Path("review").mkdir()
    Path("review/2026-10-29.md").write_text("# Review", encoding="utf-8")
    Path("unrelated.txt").write_text("not mine", encoding="utf-8")
    subprocess.run(["git", "add", "unrelated.txt"], check=True)  # staged by the user

    _commit_and_push(push=False)

    committed = subprocess.run(
        ["git", "show", "--name-only", "--format=", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()
    assert committed == ["review/2026-10-29.md"]
