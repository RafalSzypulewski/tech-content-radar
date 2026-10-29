import pytest

from radar.feedback import parse_all, parse_review


def _block(item_id: str, keep=" ", skip=" ", write=" ", number=1) -> str:
    return (
        f"### {number}. Title — score 0.80\n"
        f"<!-- id: {item_id} -->\n"
        "blog · Source · EN · 2026-10-27 · https://example.com\n"
        "**Summary:** …\n"
        f"- [{keep}] keep\n- [{skip}] skip\n- [{write}] write\n"
    )


def _digest(*blocks: str) -> str:
    return "# Review — 2026-10-29 (2 items)\n\nMark one box per item: …\n\n" + "\n".join(blocks)


@pytest.mark.parametrize(
    ("marks", "expected"),
    [
        ((" ", " ", " "), None),
        (("x", " ", " "), "keep"),
        ((" ", "x", " "), "skip"),
        ((" ", " ", "x"), "write"),
        (("X", " ", " "), "keep"),  # capital X counts too
        (("x", "x", " "), "keep"),  # keep > skip
        ((" ", "x", "x"), "write"),  # write > skip
        (("x", " ", "x"), "write"),  # write > keep
        (("x", "x", "x"), "write"),
    ],
)
def test_all_checkbox_combinations(marks, expected):
    keep, skip, write = marks
    feedback = parse_review(_digest(_block("aaaaaaaaaaaa", keep, skip, write)))
    assert feedback.get("aaaaaaaaaaaa") == expected


def test_several_items():
    text = _digest(
        _block("aaaaaaaaaaaa", keep="x", number=1),
        _block("bbbbbbbbbbbb", number=2),
        _block("cccccccccccc", skip="x", number=3),
    )
    assert parse_review(text) == {"aaaaaaaaaaaa": "keep", "cccccccccccc": "skip"}


def test_old_one_line_checkbox_format_still_parses():
    block = _block("aaaaaaaaaaaa").replace(
        "- [ ] keep\n- [ ] skip\n- [ ] write\n", "- [ ] keep  - [x] skip  - [ ] write\n"
    )
    assert parse_review(_digest(block)) == {"aaaaaaaaaaaa": "skip"}


@pytest.mark.parametrize(
    "block",
    [
        # no id comment
        "### 1. T — score 0.5\n- [x] keep\n",
        # two id comments in one block (ambiguous)
        "### 1. T — score 0.5\n<!-- id: aaaaaaaaaaaa -->\n<!-- id: bbbbbbbbbbbb -->\n- [x] keep\n",
        # broken id comment
        "### 1. T — score 0.5\n<!-- id aaaaaaaaaaaa -->\n- [x] keep\n",
        # unknown label / malformed boxes
        "### 1. T — score 0.5\n<!-- id: aaaaaaaaaaaa -->\n- [x] maybe\n- [xx] keep\n- [] skip\n",
    ],
)
def test_malformed_blocks_are_ignored(block):
    good = _block("cccccccccccc", write="x", number=2)
    assert parse_review(_digest(block, good)) == {"cccccccccccc": "write"}


def test_text_before_first_heading_is_ignored():
    text = "<!-- id: aaaaaaaaaaaa -->\n- [x] keep\n" + _digest(_block("bbbbbbbbbbbb"))
    assert parse_review(text) == {}


def test_parse_all_later_file_wins(tmp_path):
    (tmp_path / "2026-10-28.md").write_text(_digest(_block("aaaaaaaaaaaa", skip="x")), "utf-8")
    (tmp_path / "2026-10-29.md").write_text(_digest(_block("aaaaaaaaaaaa", keep="x")), "utf-8")
    (tmp_path / "2026-10-29-2.md").write_text(_digest(_block("bbbbbbbbbbbb", write="x")), "utf-8")

    assert parse_all(tmp_path) == {"aaaaaaaaaaaa": "keep", "bbbbbbbbbbbb": "write"}


def test_parse_all_missing_dir(tmp_path):
    assert parse_all(tmp_path / "missing") == {}
