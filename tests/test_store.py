from datetime import date

from radar.models import RawItem
from radar.rawstore import append_items
from radar.store import Store
from tests.conftest import NOW


def _item(item_id: str, title: str = "t") -> RawItem:
    return RawItem(
        id=item_id,
        url=f"https://example.com/{item_id}",
        canonical_url=f"https://example.com/{item_id}",
        title=title,
        source_id="example",
        source_name="Example",
        type="blog",
        lang="en",
        published_at=NOW,
        fetched_at=NOW,
    )


def test_load_raw_is_idempotent(tmp_path):
    raw = tmp_path / "raw"
    append_items(raw, date(2026, 10, 28), [_item("a"), _item("b")])
    append_items(raw, date(2026, 10, 29), [_item("c")])
    (raw / "_meta.json").write_text("{}", encoding="utf-8")
    store = Store(tmp_path / "local.db")

    assert store.load_raw(raw) == 3
    assert store.load_raw(raw) == 0
    assert [i.id for i in store.items()] == ["a", "b", "c"]
    assert store.items()[0] == _item("a")


def test_load_raw_adds_only_new_items(tmp_path):
    raw = tmp_path / "raw"
    append_items(raw, date(2026, 10, 28), [_item("a")])
    store = Store(tmp_path / "local.db")
    store.load_raw(raw)

    append_items(raw, date(2026, 10, 29), [_item("b")])
    assert store.load_raw(raw) == 1
    assert store.count_items() == 2


def test_store_survives_reopen(tmp_path):
    raw = tmp_path / "raw"
    append_items(raw, date(2026, 10, 28), [_item("a")])
    Store(tmp_path / "local.db").load_raw(raw)

    reopened = Store(tmp_path / "local.db")
    assert reopened.count_items() == 1
    assert reopened.load_raw(raw) == 0


def test_embeddings_round_trip_per_model(tmp_path):
    store = Store(tmp_path / "local.db")
    store.put_embeddings("m1", {"a": [0.5, -1.0, 2.0]})

    assert store.get_embeddings("m1", ["a", "missing"]) == {"a": [0.5, -1.0, 2.0]}
    assert store.get_embeddings("m2", ["a"]) == {}
