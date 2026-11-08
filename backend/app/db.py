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


def get_account(connection: sqlite3.Connection, account_id: int) -> sqlite3.Row | None:
    return connection.execute(
        "SELECT accounts.id, bank_id, type, accounts.name, csv_mapping, banks.currency,"
        " banks.default_date_format"
        " FROM accounts JOIN banks ON banks.id = accounts.bank_id WHERE accounts.id = ?",
        (account_id,),
    ).fetchone()


def save_account_csv_mapping(
    connection: sqlite3.Connection, account_id: int, csv_mapping_json: str
) -> None:
    with connection:
        connection.execute(
            "UPDATE accounts SET csv_mapping = ? WHERE id = ?", (csv_mapping_json, account_id)
        )


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


_STATEMENT_COLUMNS = (
    "SELECT statements.id, statements.account_id, accounts.bank_id, banks.name AS bank_name,"
    " accounts.name AS account_name,"
    " statement_files.filename, statements.currency, period_start, period_end,"
    " reconciliation_status, opening_balance_minor, closing_balance_minor,"
    " reconciliation_difference_minor, row_count, imported_count, duplicate_count,"
    " statement_files.uploaded_at"
    " FROM statements"
    " JOIN statement_files ON statement_files.id = statements.file_id"
    " JOIN accounts ON accounts.id = statements.account_id"
    " JOIN banks ON banks.id = accounts.bank_id"
)


def find_statement_id_by_sha256(connection: sqlite3.Connection, sha256: str) -> int | None:
    row = connection.execute(
        "SELECT statements.id FROM statements"
        " JOIN statement_files ON statement_files.id = statements.file_id"
        " WHERE statement_files.sha256 = ?",
        (sha256,),
    ).fetchone()
    return row[0] if row else None


def get_statement(connection: sqlite3.Connection, statement_id: int) -> sqlite3.Row | None:
    return connection.execute(
        _STATEMENT_COLUMNS + " WHERE statements.id = ?", (statement_id,)
    ).fetchone()


def list_statements(connection: sqlite3.Connection) -> list[sqlite3.Row]:
    return connection.execute(_STATEMENT_COLUMNS + " ORDER BY statements.id DESC").fetchall()


def create_statement(
    connection: sqlite3.Connection,
    *,
    sha256: str,
    filename: str,
    mime: str,
    file_bytes: bytes,
    account_id: int,
    currency: str,
    period_start: str | None,
    period_end: str | None,
    opening_balance_minor: int | None,
    closing_balance_minor: int | None,
    reconciliation_status: str,
    reconciliation_difference_minor: int | None,
    transactions: list[dict],
) -> int:
    """Store the file, the statement and its transactions in one database transaction.

    Each transaction dict has row_index, date, amount_minor, description,
    normalized_description, raw_row (JSON text) and fingerprint. Fingerprints already
    stored (from an overlapping statement) are skipped and counted as duplicates.
    Returns the new statement id.
    """
    with connection:
        file_id = connection.execute(
            "INSERT INTO statement_files (sha256, filename, mime, bytes) VALUES (?, ?, ?, ?)",
            (sha256, filename, mime, file_bytes),
        ).lastrowid
        statement_id = connection.execute(
            "INSERT INTO statements (file_id, account_id, currency, period_start, period_end,"
            " opening_balance_minor, closing_balance_minor, reconciliation_status,"
            " reconciliation_difference_minor, row_count, imported_count, duplicate_count)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 0)",
            (
                file_id,
                account_id,
                currency,
                period_start,
                period_end,
                opening_balance_minor,
                closing_balance_minor,
                reconciliation_status,
                reconciliation_difference_minor,
                len(transactions),
            ),
        ).lastrowid
        imported_count = 0
        for transaction in transactions:
            cursor = connection.execute(
                "INSERT INTO transactions (statement_id, account_id, row_index, date,"
                " amount_minor, currency, description, normalized_description, raw_row,"
                " fingerprint) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
                # Only a repeated fingerprint is skipped; any other violation still raises.
                " ON CONFLICT (fingerprint) DO NOTHING",
                (
                    statement_id,
                    account_id,
                    transaction["row_index"],
                    transaction["date"],
                    transaction["amount_minor"],
                    currency,
                    transaction["description"],
                    transaction["normalized_description"],
                    transaction["raw_row"],
                    transaction["fingerprint"],
                ),
            )
            imported_count += cursor.rowcount
        connection.execute(
            "UPDATE statements SET imported_count = ?, duplicate_count = ? WHERE id = ?",
            (imported_count, len(transactions) - imported_count, statement_id),
        )
    return statement_id


def list_transactions(connection: sqlite3.Connection) -> list[sqlite3.Row]:
    return connection.execute(
        "SELECT transactions.id, transactions.statement_id, transactions.account_id,"
        " accounts.name AS account_name, accounts.bank_id, banks.name AS bank_name,"
        " transactions.date, transactions.amount_minor, transactions.currency,"
        " transactions.description, transactions.needs_review"
        " FROM transactions JOIN accounts ON accounts.id = transactions.account_id"
        " JOIN banks ON banks.id = accounts.bank_id"
        " ORDER BY transactions.date DESC, transactions.id DESC"
    ).fetchall()
