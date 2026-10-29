import sys

import pytest

from radar.embeddings import (
    SentenceTransformerEmbedder,
    cosine,
    embed_items,
    item_text,
    relevance,
)
from radar.store import Store
from tests.conftest import FakeEmbedder
from tests.test_store import _item


def test_cosine():
    assert cosine([1, 0], [1, 0]) == pytest.approx(1.0)
    assert cosine([1, 0], [0, 1]) == pytest.approx(0.0)
    assert cosine([1, 1], [-1, -1]) == pytest.approx(-1.0)
    assert cosine([0, 0], [1, 0]) == 0.0


def test_relevance_is_max_similarity_clamped():
    profiles = [[1.0, 0.0], [0.0, 1.0]]
    assert relevance([1.0, 1.0], profiles) == pytest.approx(0.7071, abs=1e-4)
    assert relevance([1.0, 0.0], profiles) == pytest.approx(1.0)
    assert relevance([-1.0, -1.0], profiles) == 0.0
    assert relevance([1.0, 0.0], []) == 0.0


def test_item_text_uses_title_and_start_of_text():
    item = _item("a", title="Title").model_copy(update={"text": "x" * 2000})
    assert item_text(item) == "Title\n" + "x" * 500


def test_embed_items_caches_vectors(tmp_path):
    store = Store(tmp_path / "local.db")
    embedder = FakeEmbedder()
    a, b = _item("a", title="Test test"), _item("b", title="AI garden")

    first = embed_items(store, embedder, [a])
    both = embed_items(store, embedder, [a, b])

    assert first == {"a": [2.0, 0.0, 0.0, 0.0]}
    assert both == {"a": [2.0, 0.0, 0.0, 0.0], "b": [0.0, 1.0, 1.0, 0.0]}
    assert embedder.calls == [["Test test\n"], ["AI garden\n"]]  # "a" embedded only once


def test_embed_items_with_no_items_skips_model(tmp_path):
    embedder = FakeEmbedder()
    assert embed_items(Store(tmp_path / "local.db"), embedder, []) == {}
    assert embedder.calls == []


def test_sentence_transformer_embedder_loads_model_once(mocker):
    fake_module = mocker.MagicMock()
    model = fake_module.SentenceTransformer.return_value
    model.encode.return_value.tolist.return_value = [[0.1]]
    mocker.patch.dict(sys.modules, {"sentence_transformers": fake_module})
    embedder = SentenceTransformerEmbedder()

    assert embedder.embed(["a"]) == [[0.1]]
    embedder.embed(["b"])

    fake_module.SentenceTransformer.assert_called_once_with(
        "paraphrase-multilingual-MiniLM-L12-v2"
    )
    model.encode.assert_called_with(["b"], normalize_embeddings=True)
