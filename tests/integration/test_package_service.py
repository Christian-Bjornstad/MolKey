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


def test_add_source_files_stages_safe_names_without_patient_data(tmp_path: Path) -> None:
    db_path = tmp_path / "registry.db"
    migrate(db_path)
    service = PackageService(db_path)
    package = service.create_draft(patient_id="PAT-SECRET", case_number="CASE-987")
    source_a = tmp_path / "patient-secret-report.txt"
    source_b = tmp_path / "analysis.vcf"
    source_a.write_text("report", encoding="utf-8")
    source_b.write_text("variants", encoding="utf-8")

    staged = service.add_source_files(package.package_id, [source_a, source_b])

    assert [item.source_path for item in staged] == [source_a, source_b]
    assert [item.export_name for item in staged] == [
        f"{package.package_id}-001.txt",
        f"{package.package_id}-002.vcf",
    ]
    assert "SECRET" not in " ".join(item.export_name for item in staged)
    assert service.list_source_files(package.package_id) == staged


def test_encrypt_and_verify_creates_authenticated_phi_free_artifacts(tmp_path: Path) -> None:
    db_path = tmp_path / "registry.db"
    migrate(db_path)
    service = PackageService(db_path)
    package = service.create_draft(patient_id="PAT-SECRET", case_number="CASE-987")
    source = tmp_path / "patient-secret-result.vcf"
    source.write_bytes(b"sensitive variant result")
    service.add_source_files(package.package_id, [source])

    result = service.encrypt_and_verify(package.package_id)

    assert result.package_id == package.package_id
    assert result.workspace.is_dir()
    assert result.manifest_path.name == "manifest.json"
    assert result.manifest_path.is_file()
    encrypted_files = list(result.workspace.glob("*.enc"))
    assert [path.name for path in encrypted_files] == [
        f"{package.package_id}-001.vcf.enc"
    ]
    assert b"sensitive variant result" not in encrypted_files[0].read_bytes()
    manifest = result.manifest_path.read_text(encoding="utf-8")
    assert "PAT-SECRET" not in manifest
    assert "patient-secret-result" not in manifest
    assert service.packages.get(package.package_id).state.value == "Ready"


def test_export_ready_package_copies_verified_artifacts_and_marks_exported(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "registry.db"
    migrate(db_path)
    service = PackageService(db_path)
    package = service.create_draft(patient_id="PAT-SECRET", case_number="CASE-987")
    source = tmp_path / "result.txt"
    source.write_text("sensitive", encoding="utf-8")
    service.add_source_files(package.package_id, [source])
    service.encrypt_and_verify(package.package_id)
    destination = tmp_path / "delivery"

    exported = service.export_package(package.package_id, destination)

    assert exported == destination / package.package_id
    assert (exported / "manifest.json").is_file()
    assert (exported / f"{package.package_id}-001.txt.enc").is_file()
    assert service.packages.get(package.package_id).state.value == "Exported"


def test_ready_package_can_be_exported_after_application_restart(tmp_path: Path) -> None:
    db_path = tmp_path / "registry.db"
    migrate(db_path)
    service = PackageService(db_path)
    package = service.create_draft(patient_id="PAT-SECRET", case_number="CASE-987")
    source = tmp_path / "result.txt"
    source.write_text("sensitive", encoding="utf-8")
    service.add_source_files(package.package_id, [source])
    service.encrypt_and_verify(package.package_id)

    restarted_service = PackageService(db_path)
    exported = restarted_service.export_package(package.package_id, tmp_path / "delivery")

    assert (exported / "manifest.json").is_file()
    assert restarted_service.packages.get(package.package_id).state.value == "Exported"
