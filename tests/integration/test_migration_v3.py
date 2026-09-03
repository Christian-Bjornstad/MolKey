"""Schema upgrades must be safe: existing shared-database rows survive v3 -> v4."""

import sqlite3
from pathlib import Path

from molkey.infrastructure.migrations import SCHEMA_VERSION, migrate


def _make_v2_database(db_path: Path) -> None:
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        CREATE TABLE schema_version (
            version INTEGER PRIMARY KEY,
            applied_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        INSERT INTO schema_version (version) VALUES (2);
        CREATE TABLE patient_keys (
            patient_id TEXT PRIMARY KEY,
            pseudonymous_key TEXT NOT NULL UNIQUE,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE TABLE key_audit (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id TEXT NOT NULL,
            action TEXT NOT NULL,
            details TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        INSERT INTO patient_keys (patient_id, pseudonymous_key, created_at)
            VALUES ('26oum99999', 'MK-2026-DEADBEEF', '2026-08-20 10:00:00');
        -- cases exists since schema v1; a v2 registry has it, so the fixture must too.
        CREATE TABLE cases (
            id TEXT PRIMARY KEY,
            patient_id TEXT NOT NULL,
            case_number TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            UNIQUE(patient_id, case_number)
        );
        INSERT INTO cases (id, patient_id, case_number, created_at)
            VALUES ('CASE-1', 'pat-legacy', '26oum99999', '2026-08-20 10:00:00');
        """
    )
    conn.commit()
    conn.close()


def test_v2_database_upgrades_to_current_preserving_rows(tmp_path: Path) -> None:
    db_path = tmp_path / "registry.db"
    _make_v2_database(db_path)

    migrate(db_path)

    conn = sqlite3.connect(db_path)
    version = int(conn.execute("SELECT MAX(version) FROM schema_version").fetchone()[0])
    row = conn.execute(
        "SELECT patient_id, pseudonymous_key, created_by FROM patient_keys WHERE patient_id = '26OUM99999'"
    ).fetchone()
    conn.close()

    assert version == SCHEMA_VERSION
    # Legacy lower-case row was upper-cased in place by MIGRATION_004.
    assert row == ("26OUM99999", "MK-2026-DEADBEEF", "UKJENT")


def test_migrate_is_idempotent_across_repeated_runs(tmp_path: Path) -> None:
    db_path = tmp_path / "registry.db"
    _make_v2_database(db_path)

    migrate(db_path)
    migrate(db_path)
    migrate(db_path)

    conn = sqlite3.connect(db_path)
    count = int(conn.execute("SELECT COUNT(*) FROM patient_keys").fetchone()[0])
    conn.close()
    assert count == 1


def test_new_keys_written_after_upgrade_carry_operator(tmp_path: Path) -> None:
    from molkey.application.patient_key_service import PatientKeyService

    db_path = tmp_path / "registry.db"
    _make_v2_database(db_path)
    migrate(db_path)

    service = PatientKeyService(db_path)
    record = service.get_or_create("27NEW00001", initials="CFB")
    legacy = service.lookup_by_patient("26OUM99999")

    assert record.created_by == "CFB"
    assert legacy.created_by == "UKJENT"


def _make_v3_database(db_path: Path) -> None:
    """A database exactly as MolKey 0.2.0 (schema v3) left it — mixed-case IDs."""
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        CREATE TABLE schema_version (
            version INTEGER PRIMARY KEY,
            applied_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        INSERT INTO schema_version (version) VALUES (3);
        CREATE TABLE patient_keys (
            patient_id TEXT PRIMARY KEY,
            pseudonymous_key TEXT NOT NULL UNIQUE,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            created_by TEXT NOT NULL DEFAULT 'UKJENT'
        );
        INSERT INTO patient_keys (patient_id, pseudonymous_key, created_at, created_by)
            VALUES ('26oum99999', 'MK-2026-DEADBEEF', '2026-08-20 10:00:00', 'CFB');
        CREATE TABLE cases (
            id TEXT PRIMARY KEY,
            patient_id TEXT NOT NULL,
            case_number TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            UNIQUE(patient_id, case_number)
        );
        INSERT INTO cases (id, patient_id, case_number, created_at)
            VALUES ('CASE-1', 'pat-legacy', '26oum99999', '2026-08-20 10:00:00');
        """
    )
    conn.commit()
    conn.close()


def test_v3_database_uppercases_existing_rows_in_place(tmp_path: Path) -> None:
    db_path = tmp_path / "registry.db"
    _make_v3_database(db_path)

    migrate(db_path)

    conn = sqlite3.connect(db_path)
    try:
        version = int(conn.execute("SELECT MAX(version) FROM schema_version").fetchone()[0])
        patient_rows = conn.execute("SELECT patient_id, created_by FROM patient_keys").fetchall()
        case_rows = conn.execute("SELECT patient_id, case_number FROM cases").fetchall()
    finally:
        conn.close()

    assert version == SCHEMA_VERSION
    assert patient_rows == [("26OUM99999", "CFB")]
    assert case_rows == [("PAT-LEGACY", "26OUM99999")]


def test_uppercased_rows_resolve_from_any_case_after_upgrade(tmp_path: Path) -> None:
    """After migrating a v3 database, lookups in any case spelling hit the row."""
    from molkey.application.patient_key_service import PatientKeyService

    db_path = tmp_path / "registry.db"
    _make_v3_database(db_path)
    migrate(db_path)

    service = PatientKeyService(db_path)
    for spelling in ("26oum99999", "26OUM99999", "26Oum99999"):
        record = service.lookup_by_patient(spelling)
        assert record is not None, spelling
        assert record.patient_id == "26OUM99999"
        assert record.pseudonymous_key == "MK-2026-DEADBEEF"
