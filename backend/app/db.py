"""The single SQLite repository layer. All SQL in the app lives in this module."""

import sqlite3
from pathlib import Path

MIGRATIONS_DIR = Path(__file__).parent / "migrations"


def connect(database_path: Path) -> sqlite3.Connection:
    database_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA journal_mode = WAL")
    return connection


def schema_version(connection: sqlite3.Connection) -> int:
    return connection.execute("PRAGMA user_version").fetchone()[0]


def migrate(connection: sqlite3.Connection, migrations_dir: Path = MIGRATIONS_DIR) -> int:
    """Apply numbered NNNN_name.sql files newer than PRAGMA user_version, in order.

    Each file runs in its own transaction together with the version bump, so a failing
    migration leaves the database at the previous version. Returns the new version.
    """
    current = schema_version(connection)
    for path in sorted(migrations_dir.glob("[0-9][0-9][0-9][0-9]_*.sql")):
        number = int(path.name[:4])
        if number <= current:
            continue
        if number != current + 1:
            raise RuntimeError(f"migration {path.name} skips version {current + 1}")
        script = path.read_text()
        # executescript commits any open transaction first, so BEGIN/COMMIT live in the script.
        connection.executescript(f"BEGIN;\n{script}\nPRAGMA user_version = {number};\nCOMMIT;")
        current = number
    return current
