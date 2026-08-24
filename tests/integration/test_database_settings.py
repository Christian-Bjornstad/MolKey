"""Integration tests for SQLite connection settings."""

import tempfile
from pathlib import Path

import pytest

from molkey.infrastructure.database import DatabaseError, connect
from molkey.infrastructure.migrations import migrate


class TestDatabaseSettings:
    """Test safe SQLite connection configuration."""

    def test_connection_enables_foreign_keys(self):
        """Each connection has foreign_keys=ON."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "registry.db"
            migrate(db_path)
            conn = connect(db_path)
            try:
                cursor = conn.execute("PRAGMA foreign_keys")
                row = cursor.fetchone()
                assert row[0] == 1
            finally:
                conn.close()

    def test_connection_uses_delete_journal_mode(self):
        """Journal mode is DELETE (not WAL) for SMB safety."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "registry.db"
            migrate(db_path)
            conn = connect(db_path)
            try:
                cursor = conn.execute("PRAGMA journal_mode")
                row = cursor.fetchone()
                assert row[0].upper() == "DELETE"
            finally:
                conn.close()

    def test_connection_uses_synchronous_full(self):
        """Synchronous mode is FULL (3) for durability."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "registry.db"
            migrate(db_path)
            conn = connect(db_path)
            try:
                cursor = conn.execute("PRAGMA synchronous")
                row = cursor.fetchone()
                assert row[0] == 3  # FULL = 3
            finally:
                conn.close()

    def test_connection_has_bounded_busy_timeout(self):
        """Busy timeout is set to 5000ms."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "registry.db"
            migrate(db_path)
            conn = connect(db_path)
            try:
                cursor = conn.execute("PRAGMA busy_timeout")
                row = cursor.fetchone()
                assert row[0] == 5000
            finally:
                conn.close()

    def test_connection_uses_memory_temp_store(self):
        """Temp store is MEMORY to avoid disk I/O on SMB."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "registry.db"
            migrate(db_path)
            conn = connect(db_path)
            try:
                cursor = conn.execute("PRAGMA temp_store")
                row = cursor.fetchone()
                assert row[0] == 2  # MEMORY = 2
            finally:
                conn.close()

    def test_connection_closes_after_operations(self):
        """Connections are not held globally; each call returns a new connection."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "registry.db"
            migrate(db_path)
            conn1 = connect(db_path)
            conn2 = connect(db_path)
            try:
                assert conn1 is not conn2
            finally:
                conn1.close()
                conn2.close()

    def test_connect_raises_on_missing_database(self):
        """Connecting to non-existent path without migration raises DatabaseError."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "nonexistent.db"
            with pytest.raises(DatabaseError):
                connect(db_path, require_existing=True)

    def test_connect_creates_database_when_allowed(self):
        """Connecting with require_existing=False creates the database."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "new.db"
            conn = connect(db_path, require_existing=False)
            try:
                assert db_path.exists()
                cursor = conn.execute("SELECT 1")
                assert cursor.fetchone()[0] == 1
            finally:
                conn.close()

    def test_explicit_transaction_control(self):
        """Connection does not autocommit; transactions are explicit."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "registry.db"
            migrate(db_path)
            conn = connect(db_path)
            try:
                # Should be in manual transaction mode
                assert conn.in_transaction is False
                conn.execute(
                    "INSERT INTO cases (id, patient_id, case_number) VALUES (?, ?, ?)",
                    ("CASE-TEST123", "PAT-1", "26OUM00001"),
                )
                conn.rollback()
                cursor = conn.execute("SELECT * FROM cases WHERE id = ?", ("CASE-TEST123",))
                assert cursor.fetchone() is None
            finally:
                conn.close()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
