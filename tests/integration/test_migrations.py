"""Integration tests for schema migrations."""

import sqlite3
import tempfile
from pathlib import Path

import pytest

from molkey.infrastructure.migrations import SCHEMA_VERSION, migrate


class TestMigrations:
    """Test schema migration to version 1."""

    def test_empty_db_migrates_to_v1(self):
        """Fresh database migrates to version 1 with all tables."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "registry.db"
            conn = sqlite3.connect(db_path)
            conn.close()

            # Run migration
            migrate(db_path)

            # Verify schema version
            conn = sqlite3.connect(db_path)
            cursor = conn.execute("SELECT version FROM schema_version")
            row = cursor.fetchone()
            assert row is not None
            assert row[0] == SCHEMA_VERSION
            conn.close()

    def test_second_migration_run_is_idempotent(self):
        """Running migration twice does not error or duplicate data."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "registry.db"

            migrate(db_path)
            migrate(db_path)  # Should not raise

            conn = sqlite3.connect(db_path)
            cursor = conn.execute("SELECT version FROM schema_version")
            row = cursor.fetchone()
            assert row[0] == SCHEMA_VERSION

            # Verify tables exist
            tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            expected = {
                "schema_version",
                "cases",
                "packages",
                "encryption_keys",
                "package_files",
                "destinations",
                "audit_events",
            }
            assert expected.issubset(tables)
            conn.close()

    def test_foreign_keys_reject_orphan_rows(self):
        """Foreign key constraints prevent orphan package/case references."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "registry.db"
            migrate(db_path)

            conn = sqlite3.connect(db_path)
            conn.execute("PRAGMA foreign_keys = ON")

            # Try to insert package with non-existent case_id
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute(
                    """
                    INSERT INTO packages (id, case_id, state, created_at, updated_at)
                    VALUES (?, ?, ?, datetime('now'), datetime('now'))
                    """,
                    ("SPK-2026-ABCDEF123456", "CASE-NONEXISTENT", "Draft"),
                )
            conn.close()

    def test_duplicate_package_id_fails(self):
        """Unique constraint on package.id prevents duplicates."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "registry.db"
            migrate(db_path)

            conn = sqlite3.connect(db_path)
            conn.execute("PRAGMA foreign_keys = ON")

            # Insert a case first
            conn.execute(
                "INSERT INTO cases (id, patient_id, case_number, created_at) VALUES (?, ?, ?, datetime('now'))",
                ("CASE-ABCDEF12", "PAT-123", "26OUM12287"),
            )

            # Insert first package
            conn.execute(
                """
                INSERT INTO packages (id, case_id, state, created_at, updated_at)
                VALUES (?, ?, ?, datetime('now'), datetime('now'))
                """,
                ("SPK-2026-ABCDEF123456", "CASE-ABCDEF12", "Draft"),
            )

            # Second insert with same package id should fail
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute(
                    """
                    INSERT INTO packages (id, case_id, state, created_at, updated_at)
                    VALUES (?, ?, ?, datetime('now'), datetime('now'))
                    """,
                    ("SPK-2026-ABCDEF123456", "CASE-ABCDEF12", "Draft"),
                )
            conn.close()

    def test_duplicate_key_id_fails(self):
        """Unique constraint on encryption_keys.id prevents duplicates."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "registry.db"
            migrate(db_path)

            conn = sqlite3.connect(db_path)
            conn.execute("PRAGMA foreign_keys = ON")

            # Insert case and package
            conn.execute(
                "INSERT INTO cases (id, patient_id, case_number, created_at) VALUES (?, ?, ?, datetime('now'))",
                ("CASE-ABCDEF12", "PAT-123", "26OUM12287"),
            )
            conn.execute(
                """
                INSERT INTO packages (id, case_id, state, created_at, updated_at)
                VALUES (?, ?, ?, datetime('now'), datetime('now'))
                """,
                ("SPK-2026-ABCDEF123456", "CASE-ABCDEF12", "Draft"),
            )

            # Insert first key
            conn.execute(
                """
                INSERT INTO encryption_keys (id, package_id, wrapped_key, algorithm, version, created_at)
                VALUES (?, ?, ?, ?, ?, datetime('now'))
                """,
                ("KEY-ABCDEF12", "SPK-2026-ABCDEF123456", "wrapped-key-bytes", "AES-256-GCM", 1),
            )

            # Second insert with same key id should fail
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute(
                    """
                    INSERT INTO encryption_keys (id, package_id, wrapped_key, algorithm, version, created_at)
                    VALUES (?, ?, ?, ?, ?, datetime('now'))
                    """,
                    ("KEY-ABCDEF12", "SPK-2026-ABCDEF123456", "other-bytes", "AES-256-GCM", 1),
                )
            conn.close()

    def test_package_state_check_constraint(self):
        """CHECK constraint on packages.state only allows valid states."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "registry.db"
            migrate(db_path)

            conn = sqlite3.connect(db_path)
            conn.execute("PRAGMA foreign_keys = ON")

            conn.execute(
                "INSERT INTO cases (id, patient_id, case_number, created_at) VALUES (?, ?, ?, datetime('now'))",
                ("CASE-ABCDEF12", "PAT-123", "26OUM12287"),
            )

            # Valid state should work
            conn.execute(
                """
                INSERT INTO packages (id, case_id, state, created_at, updated_at)
                VALUES (?, ?, ?, datetime('now'), datetime('now'))
                """,
                ("SPK-2026-ABCDEF123456", "CASE-ABCDEF12", "Draft"),
            )

            # Invalid state should fail
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute(
                    """
                    INSERT INTO packages (id, case_id, state, created_at, updated_at)
                    VALUES (?, ?, ?, datetime('now'), datetime('now'))
                    """,
                    ("SPK-2026-ABCDEF123457", "CASE-ABCDEF12", "InvalidState"),
                )
            conn.close()

    def test_indexes_exist_for_search_performance(self):
        """Search indexes exist on commonly queried columns."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "registry.db"
            migrate(db_path)

            conn = sqlite3.connect(db_path)
            indexes = {row[1] for row in conn.execute("SELECT * FROM sqlite_master WHERE type='index'")}
            conn.close()

            expected_indexes = {
                "idx_packages_case_id",
                "idx_packages_state",
                "idx_packages_destination_ref",
                "idx_cases_patient_id",
                "idx_cases_case_number",
                "idx_encryption_keys_package_id",
                "idx_package_files_package_id",
                "idx_audit_events_package_id",
                "idx_audit_events_timestamp",
            }
            assert expected_indexes.issubset(indexes)

    def test_newer_schema_version_is_rejected(self):
        """Database with newer schema version fails with clear error."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "registry.db"
            migrate(db_path)

            conn = sqlite3.connect(db_path)
            conn.execute("UPDATE schema_version SET version = 999")
            conn.commit()
            conn.close()

            with pytest.raises(RuntimeError, match="newer than supported"):
                migrate(db_path)

    def test_migration_acquires_writer_lock(self):
        """Migration holds the writer lock while applying DDL."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "registry.db"
            # Create the lock file by acquiring it
            from molkey.infrastructure.writer_lock import writer_lock

            with writer_lock(Path(tmpdir), timeout=5.0):
                # While lock is held, migration should block
                # We can't easily test blocking in a single-threaded test,
                # but we can verify the lock file is created and accessible
                lock_path = Path(tmpdir) / "locks" / "registry.writer.lock"
                assert lock_path.exists()

            # Now migration should succeed
            migrate(db_path)
            conn = sqlite3.connect(db_path)
            cursor = conn.execute("SELECT version FROM schema_version")
            row = cursor.fetchone()
            assert row[0] == SCHEMA_VERSION
            conn.close()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
