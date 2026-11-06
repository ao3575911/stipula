"""SQLite lifecycle. WAL on disk, explicit transactions in the service."""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path

MIGRATIONS = Path(__file__).resolve().parent / "migrations"


def connect(path: str) -> sqlite3.Connection:
    if path != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, isolation_level=None, check_same_thread=False)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 5000")
    if path != ":memory:":
        connection.execute("PRAGMA journal_mode = WAL")
    return connection


def apply_migrations(connection: sqlite3.Connection) -> list[str]:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version TEXT PRIMARY KEY,
            applied_at INTEGER NOT NULL
        )
        """
    )
    applied = {row["version"] for row in connection.execute("SELECT version FROM schema_migrations")}
    newly: list[str] = []
    for path in sorted(MIGRATIONS.glob("*.sql")):
        if path.name in applied:
            continue
        script = path.read_text(encoding="utf-8")
        connection.executescript(script)
        connection.execute(
            "INSERT OR IGNORE INTO schema_migrations (version, applied_at) VALUES (?, ?)",
            (path.name, int(time.time())),
        )
        newly.append(path.name)
    return newly


def integrity_ok(connection: sqlite3.Connection) -> bool:
    row = connection.execute("PRAGMA integrity_check").fetchone()
    return bool(row and row[0] == "ok")
