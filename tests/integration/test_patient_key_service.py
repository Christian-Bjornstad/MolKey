import csv
import json
from pathlib import Path

from molkey.application.patient_key_service import PatientKeyService
from molkey.infrastructure.migrations import migrate


def test_generate_key_reuses_permanent_key_for_existing_patient(tmp_path: Path) -> None:
    db_path = tmp_path / "registry.db"
    migrate(db_path)
    service = PatientKeyService(db_path)

    first = service.get_or_create("12345678901", initials="CFB")
    second = service.get_or_create(" 12345678901 ", initials="CFB")

    assert first.patient_id == "12345678901"
    assert first.pseudonymous_key.startswith("MK-")
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
    existing = service.get_or_create("PAT-001", initials="CFB")

    result = service.process_batch(["PAT-001", " PAT-002 ", "PAT-001", "", "PAT-003"], initials="CFB")

    assert [item.patient_id for item in result.items] == ["PAT-001", "PAT-002", "PAT-003"]
    assert result.items[0].pseudonymous_key == existing.pseudonymous_key
    assert result.reused_count == 1
    assert result.created_count == 2
    assert result.duplicate_count == 1
    assert result.invalid_count == 1


def test_export_contains_only_keys_in_batch_order(tmp_path: Path) -> None:
    db_path = tmp_path / "registry.db"
    migrate(db_path)
    service = PatientKeyService(db_path)
    result = service.process_batch(["PATIENT-SECRET-A", "PATIENT-SECRET-B"], initials="CFB")
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
    assert "PATIENT-SECRET" not in csv_path.read_text(encoding="utf-8")
    assert "PATIENT-SECRET" not in json_path.read_text(encoding="utf-8")
