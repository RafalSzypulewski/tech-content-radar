import shutil
from datetime import date
from pathlib import Path

import pytest

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


@pytest.mark.parametrize("command", [c for c in COMMANDS if c not in HANDLERS])
def test_stub_commands_report_not_implemented(command, capsys):
    assert main([command]) == 1
    assert "not implemented yet" in capsys.readouterr().err


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
