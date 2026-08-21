"""Integration tests for short write transactions."""

import sqlite3
from pathlib import Path

import pytest

from molvault.infrastructure.database import DatabaseError, connect, transaction
from molvault.infrastructure.migrations import migrate


def test_transaction_commits_successful_write(tmp_path: Path) -> None:
    db_path = tmp_path / "registry.db"
    migrate(db_path)

    with transaction(db_path) as conn:
        assert conn.in_transaction
        conn.execute(
            "INSERT INTO cases (id, patient_id, case_number) VALUES (?, ?, ?)",
            ("CASE-COMMIT", "PAT-1", "26OUM00001"),
        )

    conn = connect(db_path)
    try:
        count = conn.execute("SELECT COUNT(*) FROM cases WHERE id = ?", ("CASE-COMMIT",)).fetchone()[0]
        assert count == 1
    finally:
        conn.close()


def test_transaction_rolls_back_failed_write(tmp_path: Path) -> None:
    db_path = tmp_path / "registry.db"
    migrate(db_path)

    with pytest.raises(RuntimeError, match="stop"), transaction(db_path) as conn:
        conn.execute(
            "INSERT INTO cases (id, patient_id, case_number) VALUES (?, ?, ?)",
            ("CASE-ROLLBACK", "PAT-2", "26OUM00002"),
        )
        raise RuntimeError("stop")

    conn = connect(db_path)
    try:
        count = conn.execute("SELECT COUNT(*) FROM cases WHERE id = ?", ("CASE-ROLLBACK",)).fetchone()[0]
        assert count == 0
    finally:
        conn.close()


def test_transaction_uses_begin_immediate(tmp_path: Path) -> None:
    db_path = tmp_path / "registry.db"
    migrate(db_path)

    with transaction(db_path) as conn:
        assert conn.in_transaction
        competing = sqlite3.connect(db_path, timeout=0)
        try:
            competing.execute("PRAGMA busy_timeout = 0")
            with pytest.raises(sqlite3.OperationalError, match="locked"):
                competing.execute("BEGIN IMMEDIATE")
        finally:
            competing.close()


def test_non_retryable_sql_error_is_reported(tmp_path: Path) -> None:
    db_path = tmp_path / "registry.db"
    migrate(db_path)

    with pytest.raises(DatabaseError, match="Database operation failed"), transaction(db_path) as conn:
        conn.execute("INSERT INTO missing_table VALUES (1)")


def test_max_retries_must_not_be_negative(tmp_path: Path) -> None:
    db_path = tmp_path / "registry.db"
    migrate(db_path)

    with pytest.raises(ValueError, match="max_retries"), transaction(db_path, max_retries=-1):
        pass


def test_retry_on_busy_can_be_disabled(tmp_path: Path) -> None:
    db_path = tmp_path / "registry.db"
    migrate(db_path)

    blocker = connect(db_path)
    blocker.execute("BEGIN IMMEDIATE")
    try:
        with pytest.raises(DatabaseError, match="busy"), transaction(db_path, retry_on_busy=False):
            pass
    finally:
        blocker.rollback()
        blocker.close()


def test_busy_retry_exhaustion_has_clear_message(tmp_path: Path) -> None:
    db_path = tmp_path / "registry.db"
    migrate(db_path)

    blocker = connect(db_path)
    blocker.execute("PRAGMA busy_timeout = 0")
    blocker.execute("BEGIN IMMEDIATE")
    try:
        with pytest.raises(DatabaseError, match="busy after 2 attempts"), transaction(db_path, max_retries=1):
            pass
    finally:
        blocker.rollback()
        blocker.close()


def test_connection_is_closed_after_context(tmp_path: Path) -> None:
    db_path = tmp_path / "registry.db"
    migrate(db_path)

    with transaction(db_path) as conn:
        conn.execute("SELECT 1")

    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        conn.execute("SELECT 1")
