"""Schema upgrades must be safe: existing shared-database rows survive v2 -> v3."""

import sqlite3
from pathlib import Path

from molkey.infrastructure.migrations import migrate


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
            VALUES ('26OUM99999', 'MK-2026-DEADBEEF', '2026-08-20 10:00:00');
        """
    )
    conn.commit()
    conn.close()


def test_v2_database_upgrades_to_v3_preserving_rows(tmp_path: Path) -> None:
    db_path = tmp_path / "registry.db"
    _make_v2_database(db_path)

    migrate(db_path)

    conn = sqlite3.connect(db_path)
    version = int(conn.execute("SELECT MAX(version) FROM schema_version").fetchone()[0])
    row = conn.execute(
        "SELECT patient_id, pseudonymous_key, created_by FROM patient_keys WHERE patient_id = '26OUM99999'"
    ).fetchone()
    conn.close()

    assert version == 3
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
