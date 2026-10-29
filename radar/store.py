"""Local SQLite cache (data/local.db). Disposable: everything can be rebuilt from git."""

import sqlite3
from array import array
from pathlib import Path

from radar import rawstore
from radar.models import RawItem

DEFAULT_PATH = Path("data/local.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS items (
    id TEXT PRIMARY KEY,
    data TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS embeddings (
    id TEXT NOT NULL,
    model TEXT NOT NULL,
    vector BLOB NOT NULL,
    PRIMARY KEY (id, model)
);
"""


class Store:
    """Thin wrapper around the SQLite connection."""

    def __init__(self, path: Path = DEFAULT_PATH) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(path)
        self.conn.executescript(SCHEMA)

    def close(self) -> None:
        self.conn.close()

    def load_raw(self, raw_dir: Path) -> int:
        """Insert items from every raw JSONL file; existing ids are left as they are.

        Returns the number of newly inserted items.
        """
        before = self.count_items()
        with self.conn:
            for path in sorted(raw_dir.glob("*.jsonl")):
                self.conn.executemany(
                    "INSERT OR IGNORE INTO items (id, data) VALUES (?, ?)",
                    [(item.id, item.model_dump_json()) for item in rawstore.read_items(path)],
                )
        return self.count_items() - before

    def count_items(self) -> int:
        return self.conn.execute("SELECT COUNT(*) FROM items").fetchone()[0]

    def items(self) -> list[RawItem]:
        """All cached items."""
        rows = self.conn.execute("SELECT data FROM items ORDER BY id")
        return [RawItem.model_validate_json(data) for (data,) in rows]

    def get_embeddings(self, model: str, ids: list[str]) -> dict[str, list[float]]:
        """Cached vectors for `ids` (missing ids are simply absent)."""
        result = {}
        for item_id in ids:
            row = self.conn.execute(
                "SELECT vector FROM embeddings WHERE id = ? AND model = ?", (item_id, model)
            ).fetchone()
            if row:
                result[item_id] = array("f", row[0]).tolist()
        return result

    def put_embeddings(self, model: str, vectors: dict[str, list[float]]) -> None:
        """Cache vectors, stored as float32 bytes."""
        with self.conn:
            self.conn.executemany(
                "INSERT OR REPLACE INTO embeddings (id, model, vector) VALUES (?, ?, ?)",
                [(i, model, array("f", v).tobytes()) for i, v in vectors.items()],
            )
