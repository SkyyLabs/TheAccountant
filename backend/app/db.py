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


def list_banks(connection: sqlite3.Connection) -> list[sqlite3.Row]:
    return connection.execute(
        "SELECT id, name, country, currency, default_date_format, is_default"
        " FROM banks ORDER BY is_default DESC, country DESC, name"
    ).fetchall()


def get_bank(connection: sqlite3.Connection, bank_id: str) -> sqlite3.Row | None:
    return connection.execute(
        "SELECT id, name, country, currency, default_date_format, is_default"
        " FROM banks WHERE id = ?",
        (bank_id,),
    ).fetchone()


def create_bank(
    connection: sqlite3.Connection,
    bank_id: str,
    name: str,
    country: str,
    currency: str,
    default_date_format: str,
) -> sqlite3.Row:
    """Insert a user-added bank. Raises sqlite3.IntegrityError if the id or name exists."""
    with connection:
        connection.execute(
            "INSERT INTO banks (id, name, country, currency, default_date_format)"
            " VALUES (?, ?, ?, ?, ?)",
            (bank_id, name, country, currency, default_date_format),
        )
    return get_bank(connection, bank_id)


def list_accounts(connection: sqlite3.Connection, bank_id: str | None = None) -> list[sqlite3.Row]:
    query = "SELECT id, bank_id, type, name FROM accounts"
    params: tuple = ()
    if bank_id is not None:
        query += " WHERE bank_id = ?"
        params = (bank_id,)
    return connection.execute(query + " ORDER BY bank_id, name", params).fetchall()


def create_account(
    connection: sqlite3.Connection, bank_id: str, account_type: str, name: str
) -> sqlite3.Row:
    """Insert an account. Raises sqlite3.IntegrityError if the bank already has that name."""
    with connection:
        cursor = connection.execute(
            "INSERT INTO accounts (bank_id, type, name) VALUES (?, ?, ?)",
            (bank_id, account_type, name),
        )
    return connection.execute(
        "SELECT id, bank_id, type, name FROM accounts WHERE id = ?", (cursor.lastrowid,)
    ).fetchone()
