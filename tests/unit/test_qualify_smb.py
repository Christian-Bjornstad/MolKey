"""Safety checks for the synthetic SMB qualification workload."""

from pathlib import Path

import pytest
from scripts.qualify_smb import _prepare_qualification_root, qualify

from molkey.__main__ import initialize_registry
from molkey.application.patient_key_service import PatientKeyService
from molkey.config import REGISTRY_DB_NAME, RegistryConfig


def test_qualification_rejects_existing_registry_without_marker(tmp_path: Path) -> None:
    root = tmp_path / "MolKey-qualification"
    root.mkdir()
    (root / "registry.db").write_bytes(b"existing patient registry")

    with pytest.raises(ValueError, match="dedicated qualification"):
        _prepare_qualification_root(root)

    assert (root / "registry.db").read_bytes() == b"existing patient registry"


def test_qualification_rejects_nonqualification_directory(tmp_path: Path) -> None:
    root = tmp_path / "MolKey-production"

    with pytest.raises(ValueError, match="qualification"):
        _prepare_qualification_root(root)

    assert not root.exists()


def test_qualification_marks_only_empty_root_and_can_reuse_it(tmp_path: Path) -> None:
    root = tmp_path / "MolKey-qualification"
    _prepare_qualification_root(root)
    (root / REGISTRY_DB_NAME).write_bytes(b"synthetic registry")
    (root / "MolKey-register.xlsx").write_bytes(b"snapshot")

    _prepare_qualification_root(root)

    assert (root / REGISTRY_DB_NAME).read_bytes() == b"synthetic registry"


def test_qualification_and_app_use_same_database(tmp_path: Path) -> None:
    root = tmp_path / "MolKey-qualification"
    _prepare_qualification_root(root)
    config = RegistryConfig.from_root(root, test_mode=True)
    initialize_registry(config)

    _prepare_qualification_root(root)

    assert config.database_path == root / REGISTRY_DB_NAME
    assert config.database_path.exists()
    assert not (root / "registry.db").exists()


def test_qualification_rejects_unrelated_files_even_with_marker(tmp_path: Path) -> None:
    root = tmp_path / "MolKey-qualification"
    _prepare_qualification_root(root)
    (root / "patient-list.csv").write_bytes(b"patient data")

    with pytest.raises(ValueError, match="unexpected content"):
        _prepare_qualification_root(root)


def test_qualification_rejects_nonpositive_workload_before_writing(tmp_path: Path) -> None:
    root = tmp_path / "MolKey-qualification"

    with pytest.raises(ValueError, match="positive"):
        qualify(root, workers=0)

    assert not root.exists()


def test_qualification_exercises_patient_key_writes_and_excel(tmp_path: Path) -> None:
    root = tmp_path / "MolKey-qualification"

    report = qualify(root, workers=2, writes=2)

    assert report["passed"] is True
    assert report["observed_synthetic_rows"] == 4
    assert report["integrity_check"] == "ok"
    assert (root / "MolKey-register.xlsx").is_file()


def test_qualification_rejects_nonsynthetic_patient_keys(tmp_path: Path) -> None:
    root = tmp_path / "MolKey-qualification"
    _prepare_qualification_root(root)
    config = RegistryConfig.from_root(root, test_mode=True)
    initialize_registry(config)
    PatientKeyService(config.database_path).get_or_create("REAL001", "AB")

    with pytest.raises(ValueError, match="non-synthetic records"):
        qualify(root, workers=1, writes=1)
