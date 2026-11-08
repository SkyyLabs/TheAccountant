"""The single SQLite repository layer. All SQL in the app lives in this module."""

import re
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

MIGRATIONS_DIR = Path(__file__).parent / "migrations"


def connect(database_path: Path) -> sqlite3.Connection:
    database_path.parent.mkdir(parents=True, exist_ok=True)
    # Used by one request at a time, but FastAPI may hand it from the thread that opened it
    # (the dependency) to another (the endpoint).
    connection = sqlite3.connect(database_path, check_same_thread=False)
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
    # Table rebuilds (SQLite's way to change a constraint) need foreign keys off while they
    # run; every migration is checked for broken references before it commits.
    connection.execute("PRAGMA foreign_keys = OFF")
    try:
        for path in sorted(migrations_dir.glob("[0-9][0-9][0-9][0-9]_*.sql")):
            number = int(path.name[:4])
            if number <= current:
                continue
            if number != current + 1:
                raise RuntimeError(f"migration {path.name} skips version {current + 1}")
            script = path.read_text()
            # executescript commits any open transaction first, so BEGIN lives in the script.
            connection.executescript(f"BEGIN;\n{script}\nPRAGMA user_version = {number};")
            broken = connection.execute("PRAGMA foreign_key_check").fetchall()
            if broken:
                connection.execute("ROLLBACK")
                raise RuntimeError(f"migration {path.name} breaks {len(broken)} references")
            connection.execute("COMMIT")
            current = number
    finally:
        connection.execute("PRAGMA foreign_keys = ON")
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


def get_account_bank(connection: sqlite3.Connection, account_id: int) -> str:
    return connection.execute(
        "SELECT bank_id FROM accounts WHERE id = ?", (account_id,)
    ).fetchone()[0]


def save_account_csv_mapping(
    connection: sqlite3.Connection, account_id: int, csv_mapping_json: str
) -> None:
    with connection:
        connection.execute(
            "UPDATE accounts SET csv_mapping = ? WHERE id = ?", (csv_mapping_json, account_id)
        )


_ACCOUNT_COLUMNS = (
    "SELECT accounts.id, accounts.bank_id, banks.name AS bank_name, accounts.type, accounts.name"
    " FROM accounts JOIN banks ON banks.id = accounts.bank_id"
)


def list_accounts(connection: sqlite3.Connection, bank_id: str | None = None) -> list[sqlite3.Row]:
    query = _ACCOUNT_COLUMNS
    params: tuple = ()
    if bank_id is not None:
        query += " WHERE accounts.bank_id = ?"
        params = (bank_id,)
    return connection.execute(query + " ORDER BY banks.name, accounts.name", params).fetchall()


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
        _ACCOUNT_COLUMNS + " WHERE accounts.id = ?", (cursor.lastrowid,)
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


_IMPORT_COLUMNS = (
    "SELECT id, filename, status, progress_done, progress_total, error, rejected_count,"
    " uploaded_at FROM statement_files"
)


def create_import(
    connection: sqlite3.Connection, *, sha256: str, filename: str, mime: str, file_bytes: bytes
) -> int:
    """Store an uploaded file as an import in progress."""
    with connection:
        return connection.execute(
            "INSERT INTO statement_files (sha256, filename, mime, bytes, status)"
            " VALUES (?, ?, ?, ?, 'processing')",
            (sha256, filename, mime, file_bytes),
        ).lastrowid


def find_import_by_sha256(connection: sqlite3.Connection, sha256: str) -> sqlite3.Row | None:
    return connection.execute(_IMPORT_COLUMNS + " WHERE sha256 = ?", (sha256,)).fetchone()


def delete_failed_import(connection: sqlite3.Connection, import_id: int) -> None:
    """A failed import has no statements; removing it lets the same file be tried again."""
    with connection:
        connection.execute(
            "DELETE FROM statement_files WHERE id = ? AND status = 'failed'", (import_id,)
        )


def import_file_bytes(connection: sqlite3.Connection, import_id: int) -> bytes:
    return connection.execute(
        "SELECT bytes FROM statement_files WHERE id = ?", (import_id,)
    ).fetchone()[0]


def set_import_progress(
    connection: sqlite3.Connection, import_id: int, done: int, total: int
) -> None:
    with connection:
        connection.execute(
            "UPDATE statement_files SET progress_done = ?, progress_total = ? WHERE id = ?",
            (done, total, import_id),
        )


def finish_import(
    connection: sqlite3.Connection,
    import_id: int,
    *,
    status: str,
    error: str | None = None,
    rejected_count: int = 0,
) -> None:
    with connection:
        connection.execute(
            "UPDATE statement_files SET status = ?, error = ?, rejected_count = ? WHERE id = ?",
            (status, error, rejected_count, import_id),
        )


def list_imports(connection: sqlite3.Connection) -> list[sqlite3.Row]:
    return connection.execute(_IMPORT_COLUMNS + " ORDER BY id DESC").fetchall()


def get_import(connection: sqlite3.Connection, import_id: int) -> sqlite3.Row | None:
    return connection.execute(_IMPORT_COLUMNS + " WHERE id = ?", (import_id,)).fetchone()


def find_or_create_bank(
    connection: sqlite3.Connection, name: str, country: str, currency: str
) -> str:
    """The bank whose name matches (a default bank's name inside the statement's, e.g.
    "HDFC Bank" in "HDFC BANK Ltd."), or a new one under the name as printed."""
    lowered = name.lower()
    for row in list_banks(connection):
        if row["name"].lower() in lowered or row["id"].replace("_", " ") in lowered.split():
            return row["id"]
    bank_id = re.sub(r"[^a-z0-9]+", "_", lowered).strip("_") or "unknown_bank"
    with connection:
        connection.execute(
            "INSERT OR IGNORE INTO banks (id, name, country, currency, default_date_format)"
            " VALUES (?, ?, ?, ?, ?)",
            (bank_id, name, country, currency, "YYYY-MM-DD"),
        )
    # The name may already exist under another id: return whichever row holds it.
    return connection.execute(
        "SELECT id FROM banks WHERE id = ? OR name = ? ORDER BY id = ? DESC LIMIT 1",
        (bank_id, name, bank_id),
    ).fetchone()[0]


def statement_ids_for_file(connection: sqlite3.Connection, sha256: str) -> list[int]:
    return [
        row[0]
        for row in connection.execute(
            "SELECT statements.id FROM statements"
            " JOIN statement_files ON statement_files.id = statements.file_id"
            " WHERE statement_files.sha256 = ? ORDER BY statements.id",
            (sha256,),
        )
    ]


def find_or_create_account(
    connection: sqlite3.Connection, bank_id: str, account_type: str, name: str
) -> int:
    row = connection.execute(
        "SELECT id FROM accounts WHERE bank_id = ? AND name = ?", (bank_id, name)
    ).fetchone()
    return row[0] if row else create_account(connection, bank_id, account_type, name)["id"]


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


def statements_of_import(connection: sqlite3.Connection, import_id: int) -> list[sqlite3.Row]:
    return connection.execute(
        _STATEMENT_COLUMNS + " WHERE statements.file_id = ? ORDER BY statements.id", (import_id,)
    ).fetchall()


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
    file_id: int | None = None,
) -> int:
    """Store the file (unless file_id names one already stored), the statement and its
    transactions in one database transaction.

    Each transaction dict has row_index, date, amount_minor, description,
    normalized_description, raw_row (JSON text) and fingerprint. Fingerprints already
    stored (from an overlapping statement) are skipped and counted as duplicates.
    Returns the new statement id.
    """
    with connection:
        if file_id is None:
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
                " fingerprint, needs_review) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
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
                    int(transaction.get("needs_review", False)),
                ),
            )
            imported_count += cursor.rowcount
        connection.execute(
            "UPDATE statements SET imported_count = ?, duplicate_count = ? WHERE id = ?",
            (imported_count, len(transactions) - imported_count, statement_id),
        )
    return statement_id


def statement_file_id(connection: sqlite3.Connection, statement_id: int) -> int:
    return connection.execute(
        "SELECT file_id FROM statements WHERE id = ?", (statement_id,)
    ).fetchone()[0]


_TRANSACTION_FROM = (
    " FROM transactions JOIN accounts ON accounts.id = transactions.account_id"
    " JOIN banks ON banks.id = accounts.bank_id"
    # The latest assignment wins; earlier ones stay for audit.
    " LEFT JOIN category_assignments ON category_assignments.id = ("
    "   SELECT max(id) FROM category_assignments"
    "   WHERE category_assignments.transaction_id = transactions.id)"
    " LEFT JOIN categories ON categories.id = category_assignments.category_id"
)
_TRANSACTION_COLUMNS = (
    "SELECT transactions.id, transactions.statement_id, transactions.account_id,"
    " accounts.name AS account_name, accounts.bank_id, banks.name AS bank_name,"
    " transactions.date, transactions.amount_minor, transactions.currency,"
    " transactions.description, transactions.merchant_key, transactions.needs_review,"
    " categories.id AS category_id, categories.name AS category_name,"
    " category_assignments.source AS category_source,"
    " coalesce(category_assignments.needs_review, 0) AS category_needs_review" + _TRANSACTION_FROM
)


@dataclass(frozen=True)
class TransactionFilters:
    """Every filter is optional; lists match any of their values. Amounts filter on the
    size of the amount (money in or out alike), in minor units."""

    date_from: str | None = None
    date_to: str | None = None
    category_ids: list[int] = field(default_factory=list)
    account_ids: list[int] = field(default_factory=list)
    currency: str | None = None
    amount_min_minor: int | None = None
    amount_max_minor: int | None = None
    text: str | None = None
    # Leave out categories marked excluded_from_spending (transfers, card payments).
    spending_only: bool = False


def _where(filters: TransactionFilters) -> tuple[str, list]:
    conditions: list[str] = []
    params: list = []
    if filters.date_from:
        conditions.append("transactions.date >= ?")
        params.append(filters.date_from)
    if filters.date_to:
        conditions.append("transactions.date <= ?")
        params.append(filters.date_to)
    if filters.category_ids:
        conditions.append(f"categories.id IN ({', '.join('?' * len(filters.category_ids))})")
        params.extend(filters.category_ids)
    if filters.account_ids:
        conditions.append(
            f"transactions.account_id IN ({', '.join('?' * len(filters.account_ids))})"
        )
        params.extend(filters.account_ids)
    if filters.currency:
        conditions.append("transactions.currency = ?")
        params.append(filters.currency)
    if filters.amount_min_minor is not None:
        conditions.append("abs(transactions.amount_minor) >= ?")
        params.append(filters.amount_min_minor)
    if filters.amount_max_minor is not None:
        conditions.append("abs(transactions.amount_minor) <= ?")
        params.append(filters.amount_max_minor)
    if filters.spending_only:
        conditions.append("coalesce(categories.excluded_from_spending, 0) = 0")
    if filters.text:
        escaped = filters.text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        conditions.append("transactions.description LIKE ? ESCAPE '\\'")
        params.append(f"%{escaped}%")
    return (" WHERE " + " AND ".join(conditions) if conditions else ""), params


def list_transactions(
    connection: sqlite3.Connection, filters: TransactionFilters | None = None
) -> list[sqlite3.Row]:
    where, params = _where(filters or TransactionFilters())
    return connection.execute(
        _TRANSACTION_COLUMNS + where + " ORDER BY transactions.date DESC, transactions.id DESC",
        params,
    ).fetchall()


# Money in and money out are both reported as positive totals, per currency: never summed
# across currencies.
_TOTALS = (
    " sum(CASE WHEN transactions.amount_minor > 0 THEN transactions.amount_minor ELSE 0 END)"
    " AS money_in_minor,"
    " sum(CASE WHEN transactions.amount_minor < 0 THEN -transactions.amount_minor ELSE 0 END)"
    " AS money_out_minor,"
    " count(*) AS transaction_count"
)


def summarize_transactions(connection: sqlite3.Connection, filters: TransactionFilters) -> dict:
    where, params = _where(filters)
    totals = connection.execute(
        "SELECT transactions.currency,"
        + _TOTALS
        + _TRANSACTION_FROM
        + where
        + " GROUP BY transactions.currency ORDER BY transactions.currency",
        params,
    ).fetchall()
    by_month = connection.execute(
        "SELECT substr(transactions.date, 1, 7) AS month, transactions.currency,"
        + _TOTALS
        + _TRANSACTION_FROM
        + where
        + " GROUP BY month, transactions.currency ORDER BY month, transactions.currency",
        params,
    ).fetchall()
    by_category = connection.execute(
        "SELECT categories.id AS category_id, categories.name AS category_name,"
        " transactions.currency,"
        + _TOTALS
        + _TRANSACTION_FROM
        + where
        + " GROUP BY categories.id, transactions.currency"
        " ORDER BY transactions.currency, money_out_minor DESC, category_name",
        params,
    ).fetchall()
    return {"totals": totals, "by_month": by_month, "by_category": by_category}


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
        "SELECT id, name, region, is_default, excluded_from_spending FROM categories"
        " ORDER BY name = 'Uncategorized', name"
    ).fetchall()


def get_category(connection: sqlite3.Connection, category_id: int) -> sqlite3.Row | None:
    return connection.execute(
        "SELECT id, name, region, is_default, excluded_from_spending FROM categories WHERE id = ?",
        (category_id,),
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


def update_category(
    connection: sqlite3.Connection,
    category_id: int,
    *,
    name: str | None = None,
    excluded_from_spending: bool | None = None,
) -> None:
    """Raises sqlite3.IntegrityError if the new name exists."""
    with connection:
        if name is not None:
            connection.execute("UPDATE categories SET name = ? WHERE id = ?", (name, category_id))
        if excluded_from_spending is not None:
            connection.execute(
                "UPDATE categories SET excluded_from_spending = ? WHERE id = ?",
                (int(excluded_from_spending), category_id),
            )


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
