import sqlite3
from collections.abc import Iterator
from contextlib import closing, contextmanager
from pathlib import Path


class Database:
    """Öffnet pro Vorgang eine kurze Verbindung zur gemeinsamen SQLite-Datei."""

    def __init__(self, path: Path) -> None:
        self.path = path

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        with closing(sqlite3.connect(self.path, timeout=15)) as conn:
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON")
            with conn:  # Commit bei Erfolg, Rollback bei Fehler
                yield conn

    def init_schema(self, schema_path: Path) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path, timeout=15)) as conn:
            conn.executescript(schema_path.read_text(encoding="utf-8"))

    def ping(self) -> bool:
        try:
            with self.connect() as conn:
                conn.execute("SELECT 1")
            return True
        except sqlite3.Error:
            return False
