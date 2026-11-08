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
    " categorization_status,"
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


_TRANSACTION_COLUMNS = (
    "SELECT transactions.id, transactions.statement_id, transactions.account_id,"
    " accounts.name AS account_name, accounts.bank_id, banks.name AS bank_name,"
    " transactions.date, transactions.amount_minor, transactions.currency,"
    " transactions.description, transactions.merchant_key, transactions.needs_review,"
    " categories.id AS category_id, categories.name AS category_name,"
    " category_assignments.source AS category_source,"
    " coalesce(category_assignments.needs_review, 0) AS category_needs_review"
    " FROM transactions JOIN accounts ON accounts.id = transactions.account_id"
    " JOIN banks ON banks.id = accounts.bank_id"
    # The latest assignment wins; earlier ones stay for audit.
    " LEFT JOIN category_assignments ON category_assignments.id = ("
    "   SELECT max(id) FROM category_assignments"
    "   WHERE category_assignments.transaction_id = transactions.id)"
    " LEFT JOIN categories ON categories.id = category_assignments.category_id"
)


def list_transactions(connection: sqlite3.Connection) -> list[sqlite3.Row]:
    return connection.execute(
        _TRANSACTION_COLUMNS + " ORDER BY transactions.date DESC, transactions.id DESC"
    ).fetchall()


def get_transaction(connection: sqlite3.Connection, transaction_id: int) -> sqlite3.Row | None:
    return connection.execute(
        _TRANSACTION_COLUMNS + " WHERE transactions.id = ?", (transaction_id,)
    ).fetchone()


def uncategorized_transactions(
    connection: sqlite3.Connection, statement_id: int | None = None
) -> list[sqlite3.Row]:
    """Transactions with no category assignment yet, with their bank's country."""
    query = (
        "SELECT transactions.id, transactions.statement_id, transactions.description,"
        " transactions.amount_minor, transactions.currency, banks.country"
        " FROM transactions JOIN accounts ON accounts.id = transactions.account_id"
        " JOIN banks ON banks.id = accounts.bank_id"
        " WHERE NOT EXISTS (SELECT 1 FROM category_assignments"
        "   WHERE category_assignments.transaction_id = transactions.id)"
    )
    params: tuple = ()
    if statement_id is not None:
        query += " AND transactions.statement_id = ?"
        params = (statement_id,)
    return connection.execute(query + " ORDER BY transactions.id", params).fetchall()


def set_merchant_keys(connection: sqlite3.Connection, keys: list[tuple[int, str]]) -> None:
    with connection:
        connection.executemany(
            "UPDATE transactions SET merchant_key = ? WHERE id = ?",
            [(key, transaction_id) for transaction_id, key in keys],
        )


def stored_category_for_merchant(connection: sqlite3.Connection, merchant_key: str) -> int | None:
    """The category another transaction of this merchant already has, preferring the
    user's own choice, then the most recent. Results still marked for review are ignored."""
    row = connection.execute(
        "SELECT category_assignments.category_id FROM transactions"
        " JOIN category_assignments ON category_assignments.id = ("
        "   SELECT max(id) FROM category_assignments"
        "   WHERE category_assignments.transaction_id = transactions.id)"
        " WHERE transactions.merchant_key = ? AND category_assignments.needs_review = 0"
        " ORDER BY category_assignments.source = 'user' DESC, category_assignments.id DESC"
        " LIMIT 1",
        (merchant_key,),
    ).fetchone()
    return row[0] if row else None


def add_category_assignments(
    connection: sqlite3.Connection, assignments: list[tuple[int, int, str, bool]]
) -> None:
    """Each item: (transaction_id, category_id, source, needs_review)."""
    with connection:
        connection.executemany(
            "INSERT INTO category_assignments (transaction_id, category_id, source, needs_review)"
            " VALUES (?, ?, ?, ?)",
            [(t, c, source, int(review)) for t, c, source, review in assignments],
        )


def set_categorization_status(
    connection: sqlite3.Connection, statement_ids: list[int], status: str
) -> None:
    with connection:
        connection.executemany(
            "UPDATE statements SET categorization_status = ? WHERE id = ?",
            [(status, statement_id) for statement_id in statement_ids],
        )


def transactions_not_set_by_user(connection: sqlite3.Connection) -> list[sqlite3.Row]:
    """Transactions a new rule may recategorize: never those the user set by hand."""
    return connection.execute(
        "SELECT transactions.id, transactions.merchant_key, transactions.amount_minor,"
        " category_assignments.category_id"
        " FROM transactions LEFT JOIN category_assignments ON category_assignments.id = ("
        "   SELECT max(id) FROM category_assignments"
        "   WHERE category_assignments.transaction_id = transactions.id)"
        " WHERE transactions.merchant_key IS NOT NULL"
        " AND coalesce(category_assignments.source, '') != 'user'"
    ).fetchall()


def list_categories(connection: sqlite3.Connection) -> list[sqlite3.Row]:
    return connection.execute(
        "SELECT id, name, region, is_default FROM categories ORDER BY name = 'Uncategorized', name"
    ).fetchall()


def get_category(connection: sqlite3.Connection, category_id: int) -> sqlite3.Row | None:
    return connection.execute(
        "SELECT id, name, region, is_default FROM categories WHERE id = ?", (category_id,)
    ).fetchone()


def category_id_by_name(connection: sqlite3.Connection, name: str) -> int | None:
    row = connection.execute("SELECT id FROM categories WHERE name = ?", (name,)).fetchone()
    return row[0] if row else None


def create_category(connection: sqlite3.Connection, name: str, region: str) -> sqlite3.Row:
    """Raises sqlite3.IntegrityError if the name exists."""
    with connection:
        category_id = connection.execute(
            "INSERT INTO categories (name, region) VALUES (?, ?)", (name, region)
        ).lastrowid
    return get_category(connection, category_id)


def rename_category(connection: sqlite3.Connection, category_id: int, name: str) -> None:
    """Raises sqlite3.IntegrityError if the name exists."""
    with connection:
        connection.execute("UPDATE categories SET name = ? WHERE id = ?", (name, category_id))


def category_in_use(connection: sqlite3.Connection, category_id: int) -> bool:
    return (
        connection.execute(
            "SELECT 1 FROM category_assignments WHERE category_id = ?"
            " UNION ALL SELECT 1 FROM rules WHERE category_id = ? LIMIT 1",
            (category_id, category_id),
        ).fetchone()
        is not None
    )


def delete_category(connection: sqlite3.Connection, category_id: int) -> None:
    with connection:
        connection.execute("DELETE FROM categories WHERE id = ?", (category_id,))


_RULE_COLUMNS = (
    "SELECT rules.id, match_type, pattern, amount_min_minor, amount_max_minor, category_id,"
    " categories.name AS category_name, priority"
    " FROM rules JOIN categories ON categories.id = rules.category_id"
)


def list_rules(connection: sqlite3.Connection) -> list[sqlite3.Row]:
    """In the order they are tried: highest priority first, then oldest."""
    return connection.execute(_RULE_COLUMNS + " ORDER BY priority DESC, rules.id").fetchall()


def get_rule(connection: sqlite3.Connection, rule_id: int) -> sqlite3.Row | None:
    return connection.execute(_RULE_COLUMNS + " WHERE rules.id = ?", (rule_id,)).fetchone()


def create_rule(
    connection: sqlite3.Connection,
    *,
    match_type: str,
    pattern: str,
    amount_min_minor: int | None,
    amount_max_minor: int | None,
    category_id: int,
    priority: int,
) -> sqlite3.Row:
    with connection:
        rule_id = connection.execute(
            "INSERT INTO rules (match_type, pattern, amount_min_minor, amount_max_minor,"
            " category_id, priority) VALUES (?, ?, ?, ?, ?, ?)",
            (match_type, pattern, amount_min_minor, amount_max_minor, category_id, priority),
        ).lastrowid
    return get_rule(connection, rule_id)


def update_rule(connection: sqlite3.Connection, rule_id: int, changes: dict) -> None:
    # Column names come only from this fixed set, never from the request.
    allowed = (
        "match_type",
        "pattern",
        "amount_min_minor",
        "amount_max_minor",
        "category_id",
        "priority",
    )
    columns = [column for column in allowed if column in changes]
    if not columns:
        return
    with connection:
        connection.execute(
            f"UPDATE rules SET {', '.join(f'{c} = ?' for c in columns)} WHERE id = ?",
            (*[changes[c] for c in columns], rule_id),
        )


def delete_rule(connection: sqlite3.Connection, rule_id: int) -> None:
    with connection:
        connection.execute("DELETE FROM rules WHERE id = ?", (rule_id,))
