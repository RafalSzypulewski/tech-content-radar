from datetime import date

from radar.models import RawItem
from radar.rawstore import append_items, known_ids, read_items
from tests.conftest import NOW


def _item(item_id: str) -> RawItem:
    return RawItem(
        id=item_id,
        url=f"https://example.com/{item_id}",
        canonical_url=f"https://example.com/{item_id}",
        title="Zażółć gęślą jaźń",
        source_id="example",
        source_name="Example",
        type="blog",
        lang="pl",
        published_at=NOW,
        fetched_at=NOW,
        engagement={"points": 3},
    )


def test_append_and_read_round_trip(tmp_path):
    path = append_items(tmp_path / "raw", date(2026, 10, 29), [_item("a"), _item("b")])
    append_items(tmp_path / "raw", date(2026, 10, 29), [_item("c")])

    assert path.name == "2026-10-29.jsonl"
    assert [i.id for i in read_items(path)] == ["a", "b", "c"]
    assert read_items(path)[0] == _item("a")
    assert path.read_bytes().count(b"\n") == 3
    assert b"\r\n" not in path.read_bytes()


def test_known_ids_only_last_90_days(tmp_path):
    raw = tmp_path / "raw"
    append_items(raw, date(2026, 10, 29), [_item("today")])
    append_items(raw, date(2026, 7, 31), [_item("day90")])
    append_items(raw, date(2026, 7, 30), [_item("day91")])
    (raw / "_meta.json").write_text("{}", encoding="utf-8")

    assert known_ids(raw, date(2026, 10, 29)) == {"today", "day90"}


def test_known_ids_missing_dir(tmp_path):
    assert known_ids(tmp_path / "nope", date(2026, 10, 29)) == set()
