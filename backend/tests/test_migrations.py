import sqlite3

import pytest

from app import db


def write_migrations(directory, files: dict[str, str]):
    directory.mkdir()
    for name, sql in files.items():
        (directory / name).write_text(sql)
    return directory


def test_migrations_apply_in_order_and_set_user_version(tmp_path):
    migrations = write_migrations(
        tmp_path / "migrations",
        {
            "0002_add_note.sql": "ALTER TABLE thing ADD COLUMN note TEXT;",
            "0001_create_thing.sql": "CREATE TABLE thing (id INTEGER PRIMARY KEY);",
        },
    )
    connection = db.connect(tmp_path / "app.db")

    version = db.migrate(connection, migrations)

    assert version == 2
    assert db.schema_version(connection) == 2
    columns = [row["name"] for row in connection.execute("PRAGMA table_info(thing)")]
    assert columns == ["id", "note"]


def test_rerunning_migrations_applies_nothing_new(tmp_path):
    migrations = write_migrations(
        tmp_path / "migrations",
        {"0001_create_thing.sql": "CREATE TABLE thing (id INTEGER PRIMARY KEY);"},
    )
    connection = db.connect(tmp_path / "app.db")
    db.migrate(connection, migrations)

    assert db.migrate(connection, migrations) == 1


def test_failing_migration_leaves_previous_version_and_no_partial_changes(tmp_path):
    migrations = write_migrations(
        tmp_path / "migrations",
        {
            "0001_create_thing.sql": "CREATE TABLE thing (id INTEGER PRIMARY KEY);",
            "0002_broken.sql": "CREATE TABLE half_done (id INTEGER); SELECT * FROM missing;",
        },
    )
    connection = db.connect(tmp_path / "app.db")

    with pytest.raises(sqlite3.OperationalError, match="no such table: missing"):
        db.migrate(connection, migrations)

    connection.rollback()
    assert db.schema_version(connection) == 1
    tables = {row["name"] for row in connection.execute("SELECT name FROM sqlite_master")}
    assert "half_done" not in tables


def test_gap_in_migration_numbers_is_refused(tmp_path):
    migrations = write_migrations(
        tmp_path / "migrations",
        {
            "0001_create_thing.sql": "CREATE TABLE thing (id INTEGER PRIMARY KEY);",
            "0003_skipped_two.sql": "CREATE TABLE other (id INTEGER);",
        },
    )
    connection = db.connect(tmp_path / "app.db")

    with pytest.raises(RuntimeError, match="skips version 2"):
        db.migrate(connection, migrations)
    assert db.schema_version(connection) == 1


def test_statement_table_rebuild_keeps_existing_statements_and_transactions(tmp_path):
    from app.db import MIGRATIONS_DIR

    before = tmp_path / "before"
    before.mkdir()
    for path in sorted(MIGRATIONS_DIR.glob("000[1-5]_*.sql")):
        (before / path.name).write_text(path.read_text())
    connection = db.connect(tmp_path / "data.db")
    db.migrate(connection, before)
    connection.executescript(
        """
        INSERT INTO accounts (id, bank_id, type, name) VALUES (1, 'chase', 'bank', 'Main');
        INSERT INTO statement_files (id, sha256, filename, mime, bytes)
            VALUES (1, 'abc', 'a.csv', 'text/csv', x'00');
        INSERT INTO statements (id, file_id, account_id, currency, reconciliation_status,
            row_count, imported_count, duplicate_count)
            VALUES (7, 1, 1, 'USD', 'reconciled', 1, 1, 0);
        INSERT INTO transactions (statement_id, account_id, row_index, date, amount_minor,
            currency, description, normalized_description, raw_row, fingerprint)
            VALUES (7, 1, 0, '2026-03-04', -4210, 'USD', 'SHOP', 'shop', '{}', 'f1');
        """
    )

    db.migrate(connection)

    assert db.schema_version(connection) >= 6
    assert db.get_statement(connection, 7)["reconciliation_status"] == "reconciled"
    assert [row["amount_minor"] for row in db.list_transactions(connection)] == [-4210]
    assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
