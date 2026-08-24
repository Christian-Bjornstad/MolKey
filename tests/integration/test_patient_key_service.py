import csv
import json
from pathlib import Path

from molkey.application.patient_key_service import PatientKeyService
from molkey.infrastructure.migrations import migrate


def test_generate_key_reuses_permanent_key_for_existing_patient(tmp_path: Path) -> None:
    db_path = tmp_path / "registry.db"
    migrate(db_path)
    service = PatientKeyService(db_path)

    first = service.get_or_create("12345678901")
    second = service.get_or_create(" 12345678901 ")

    assert first.patient_id == "12345678901"
    assert first.pseudonymous_key.startswith("MK-")
    assert "12345678901" not in first.pseudonymous_key
    assert second == first
    assert service.lookup_by_patient("12345678901") == first
    assert service.lookup_by_key(first.pseudonymous_key.lower()) == first
    assert service.list_recent() == [first]


def test_process_batch_reuses_keys_and_deduplicates_in_input_order(tmp_path: Path) -> None:
    db_path = tmp_path / "registry.db"
    migrate(db_path)
    service = PatientKeyService(db_path)
    existing = service.get_or_create("PAT-001")

    result = service.process_batch(["PAT-001", " PAT-002 ", "PAT-001", "", "PAT-003"])

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
    result = service.process_batch(["PATIENT-SECRET-A", "PATIENT-SECRET-B"])
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
