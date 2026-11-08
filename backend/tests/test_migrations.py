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
