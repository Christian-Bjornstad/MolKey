import csv
import json
import re
from pathlib import Path
from unittest.mock import patch

from molkey.application.patient_key_service import PatientKeyService
from molkey.infrastructure.migrations import migrate


def test_generate_key_reuses_permanent_key_for_existing_patient(tmp_path: Path) -> None:
    db_path = tmp_path / "registry.db"
    migrate(db_path)
    service = PatientKeyService(db_path)

    first = service.get_or_create("12345678901", initials="CFB")
    second = service.get_or_create(" 12345678901 ", initials="CFB")

    assert first.patient_id == "12345678901"
    assert first.pseudonymous_key.startswith("MK")
    assert first.pseudonymous_key.isalnum()
    assert re.fullmatch(r"MK[0-9]{7}", first.pseudonymous_key)
    assert "12345678901" not in first.pseudonymous_key
    assert second == first
    assert service.lookup_by_patient("12345678901") == first
    assert service.lookup_by_key(first.pseudonymous_key.lower()) == first
    assert service.list_recent() == [first]


def test_patient_id_is_stored_upper_case_and_case_insensitive_at_lookup(tmp_path: Path) -> None:
    """DIT numbers typed as 26oum12345 / 26OUM12345 map to one stored row."""
    db_path = tmp_path / "registry.db"
    migrate(db_path)
    service = PatientKeyService(db_path)

    lower = service.get_or_create("26oum12345", initials="cfb")
    upper = service.get_or_create("26OUM12345", initials="CFB")
    mixed = service.get_or_create(" 26Oum12345 ", initials="CFB")

    assert lower == upper == mixed  # same stored record across spellings
    assert lower.patient_id == "26OUM12345"
    assert lower.created_by == "CFB"
    assert service.lookup_by_patient("26oum12345") == lower
    assert service.lookup_by_patient("26Oum12345") == lower

    row = PatientKeyService(db_path).repository.get_by_patient("26oum12345")
    assert row is not None and row.patient_id == "26OUM12345"


def test_batch_generation_deduplicates_across_case_spellings(tmp_path: Path) -> None:
    db_path = tmp_path / "registry.db"
    migrate(db_path)
    service = PatientKeyService(db_path)

    result = service.process_batch(
        ["26oum12345", "26OUM12345", "26Oum12345", "26oum99999"], initials="CFB"
    )

    assert [item.patient_id for item in result.items] == ["26OUM12345", "26OUM99999"]
    assert result.created_count == 2
    assert result.duplicate_count == 2
    assert result.invalid_count == 0


def test_process_batch_reuses_keys_and_deduplicates_in_input_order(tmp_path: Path) -> None:
    db_path = tmp_path / "registry.db"
    migrate(db_path)
    service = PatientKeyService(db_path)
    existing = service.get_or_create("PAT001", initials="CFB")

    result = service.process_batch(["PAT001", " PAT002 ", "PAT001", "", "PAT003"], initials="CFB")

    assert [item.patient_id for item in result.items] == ["PAT001", "PAT002", "PAT003"]
    assert result.items[0].pseudonymous_key == existing.pseudonymous_key
    assert result.reused_count == 1
    assert result.created_count == 2
    assert result.duplicate_count == 1
    assert result.invalid_count == 1


def test_export_contains_only_keys_in_batch_order(tmp_path: Path) -> None:
    db_path = tmp_path / "registry.db"
    migrate(db_path)
    service = PatientKeyService(db_path)
    result = service.process_batch(["PATIENTSECRETA", "PATIENTSECRETB"], initials="CFB")
    csv_path = tmp_path / "keys.csv"
    json_path = tmp_path / "keys.json"

    service.export_keys(result.items, csv_path)
    service.export_keys(result.items, json_path)

    with csv_path.open(newline="", encoding="utf-8") as handle:
        csv_rows = list(csv.DictReader(handle))
    json_rows = json.loads(json_path.read_text(encoding="utf-8"))
    expected = [{"molkey": item.pseudonymous_key} for item in result.items]
    assert csv_rows == expected
    assert json_rows == expected
    assert "PATIENTSECRET" not in csv_path.read_text(encoding="utf-8")
    assert "PATIENTSECRET" not in json_path.read_text(encoding="utf-8")


def test_new_patient_ids_reject_special_characters(tmp_path: Path) -> None:
    db_path = tmp_path / "registry.db"
    migrate(db_path)
    service = PatientKeyService(db_path)

    for invalid in ("PAT-001", "PAT_001", "PAT 001", "PAT/001", "PÁT001"):
        try:
            service.get_or_create(invalid, initials="CFB")
        except ValueError as exc:
            assert "letters A-Z and digits 0-9" in str(exc)
        else:
            raise AssertionError(f"Accepted invalid patient ID: {invalid}")

    result = service.process_batch(["PAT-001", "pat_002", "pat003"], initials="CFB")
    assert result.invalid_count == 2
    assert [item.patient_id for item in result.items] == ["PAT003"]


def test_short_numeric_key_collision_is_retried_without_changing_existing_key(tmp_path: Path) -> None:
    db_path = tmp_path / "registry.db"
    migrate(db_path)
    service = PatientKeyService(db_path)
    with patch("molkey.application.patient_key_service.secrets.randbelow", side_effect=[1234567, 1234567, 7654321]):
        first = service.get_or_create("26OUM12345", initials="CFB")
        second = service.get_or_create("26OUM12346", initials="CFB")

    assert first.pseudonymous_key == "MK1234567"
    assert second.pseudonymous_key == "MK7654321"
    assert service.lookup_by_patient("26OUM12345") == first
    assert service.lookup_by_patient("26OUM12346") == second
