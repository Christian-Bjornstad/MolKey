from __future__ import annotations

from pathlib import Path

from molvault.application.package_service import PackageService
from molvault.infrastructure.migrations import migrate
from molvault.infrastructure.repositories import CaseRepository, PackageRepository


def test_create_draft_persists_case_and_pseudonymous_package(tmp_path: Path) -> None:
    db_path = tmp_path / "registry.db"
    migrate(db_path)
    service = PackageService(db_path)

    package = service.create_draft(
        patient_id="12345678901",
        case_number="26OUM12287",
        destination="External laboratory",
        notes="Priority analysis",
    )

    assert package.package_id.startswith("SPK-")
    assert "12345678901" not in package.package_id
    assert package.destination == "External laboratory"
    assert package.notes == "Priority analysis"
    assert PackageRepository(db_path).get(package.package_id) == package
    case = CaseRepository(db_path).get(package.case_id)
    assert case is not None
    assert case.patient_id == "PAT-12345678901"
    assert case.specimen_id == "SPEC-26OUM12287"


def test_create_draft_reuses_existing_patient_case_mapping(tmp_path: Path) -> None:
    db_path = tmp_path / "registry.db"
    migrate(db_path)
    service = PackageService(db_path)

    first = service.create_draft(patient_id="123", case_number="26OUM12287")
    second = service.create_draft(patient_id="123", case_number="26OUM12287")

    assert second.case_id == first.case_id
    assert second.package_id != first.package_id
    assert len(CaseRepository(db_path).list_recent()) == 1
    assert len(PackageRepository(db_path).list_for_case(first.case_id)) == 2


def test_create_draft_rejects_missing_required_identifiers(tmp_path: Path) -> None:
    db_path = tmp_path / "registry.db"
    migrate(db_path)
    service = PackageService(db_path)

    try:
        service.create_draft(patient_id=" ", case_number="26OUM12287")
    except ValueError as exc:
        assert str(exc) == "Patient ID is required"
    else:
        raise AssertionError("Expected a missing patient ID to be rejected")
