import shutil
from datetime import date
from pathlib import Path

import pytest

from radar.__main__ import COMMANDS, HANDLERS, main
from radar.enriched import read_scores
from radar.models import Enrichment
from radar.rawstore import append_items
from tests.conftest import FakeEmbedder
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
