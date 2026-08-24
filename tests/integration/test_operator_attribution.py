"""Operator attribution: every key records who made it, and creation is blocked without initials."""

import sqlite3
from pathlib import Path

import pytest

from molkey.application.patient_key_service import PatientKeyService
from molkey.infrastructure.migrations import MIGRATION_001, MIGRATION_002, SCHEMA_VERSION, migrate


def test_get_or_create_without_initials_raises_value_error(tmp_path: Path) -> None:
    db_path = tmp_path / "registry.db"
    migrate(db_path)
    service = PatientKeyService(db_path)

    with pytest.raises(ValueError, match="initials"):
        service.get_or_create("26OUM99999", initials="   ")


def test_generated_key_records_operator_initials(tmp_path: Path) -> None:
    db_path = tmp_path / "registry.db"
    migrate(db_path)
    service = PatientKeyService(db_path)

    record = service.get_or_create("26OUM99999", initials="cfb")

    assert record.created_by == "CFB"


def test_key_created_by_one_session_is_visible_to_another_with_initials(tmp_path: Path) -> None:
    """Simulates two workstations sharing the registry database file."""
    db_path = tmp_path / "registry.db"
    migrate(db_path)
    creator = PatientKeyService(db_path)

    created = creator.get_or_create("26OUM99999", initials="CFB")

    colleague = PatientKeyService(db_path)
    found = colleague.lookup_by_patient("26OUM99999")
    assert found is not None
    assert found.pseudonymous_key == created.pseudonymous_key
    assert found.created_by == "CFB"
    assert colleague.list_recent() == [found]


def test_batch_generation_also_requires_initials(tmp_path: Path) -> None:
    db_path = tmp_path / "registry.db"
    migrate(db_path)
    service = PatientKeyService(db_path)

    with pytest.raises(ValueError, match="initials"):
        service.process_batch(["PAT-001", "PAT-002"], initials="")


def test_existing_patient_lookup_still_works_without_initials(tmp_path: Path) -> None:
    """Initials gate creation only; reading existing mappings must stay friction-free."""
    db_path = tmp_path / "registry.db"
    migrate(db_path)
    creator = PatientKeyService(db_path)
    created = creator.get_or_create("26OUM99999", initials="CFB")

    reader = PatientKeyService(db_path)
    assert reader.lookup_by_patient("26OUM99999") == created
    assert reader.lookup_by_key(created.pseudonymous_key) == created


def test_schema_version_bumps_to_three(tmp_path: Path) -> None:
    db_path = tmp_path / "registry.db"

    migrate(db_path)

    assert SCHEMA_VERSION == 3
    conn = sqlite3.connect(db_path)
    try:
        version = conn.execute("SELECT version FROM schema_version").fetchone()[0]
        columns = {row[1] for row in conn.execute("PRAGMA table_info(patient_keys)").fetchall()}
    finally:
        conn.close()
    assert version == 3
    assert "created_by" in columns


def test_v2_database_upgrades_in_place_and_backfills_operator(tmp_path: Path) -> None:
    """A registry created by MolKey 0.2.0 must upgrade without losing keys."""
    db_path = tmp_path / "registry.db"
    legacy = sqlite3.connect(db_path)
    try:
        legacy.executescript(MIGRATION_001)
        legacy.executescript(MIGRATION_002)
        legacy.execute(
            "INSERT INTO patient_keys (patient_id, pseudonymous_key) VALUES (?, ?)",
            ("LEGACY-PATIENT", "MK-ABCDEF1234"),
        )
        legacy.execute("INSERT INTO schema_version (version) VALUES (2)")
        legacy.commit()
    finally:
        legacy.close()

    migrate(db_path)

    service = PatientKeyService(db_path)
    found = service.lookup_by_patient("LEGACY-PATIENT")
    assert found is not None
    assert found.pseudonymous_key == "MK-ABCDEF1234"
    assert found.created_by == "UKJENT"
