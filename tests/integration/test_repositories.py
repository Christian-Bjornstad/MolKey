"""Integration tests for SQLite repositories."""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from molvault.domain.models import CaseRecord, PackageRecord
from molvault.domain.states import PackageState
from molvault.infrastructure.migrations import migrate
from molvault.infrastructure.repositories import (
    CaseRepository,
    DuplicateRecordError,
    PackageRepository,
    RecordNotFoundError,
)


def _case(case_id: str = "CASE-ABC123") -> CaseRecord:
    return CaseRecord(
        case_id=case_id,
        patient_id="PAT-123",
        specimen_id="SPEC-26OUM12287",
        created_at=datetime(2026, 8, 20, tzinfo=UTC),
    )


def _package(package_id: str = "SPK-2026-ABCDEF1234567890ABCDEF12") -> PackageRecord:
    return PackageRecord(
        package_id=package_id,
        case_id="CASE-ABC123",
        key_id="KEY-PENDING",
        destination=None,
        destination_ref="ExternalLab",
        created_at=datetime(2026, 8, 20, tzinfo=UTC),
        updated_at=datetime(2026, 8, 20, tzinfo=UTC),
    )


def test_case_repository_adds_and_reads_case(tmp_path: Path) -> None:
    db_path = tmp_path / "registry.db"
    migrate(db_path)
    repository = CaseRepository(db_path)

    repository.add(_case())

    assert repository.get("CASE-ABC123") == _case()


def test_case_repository_rejects_duplicate_case(tmp_path: Path) -> None:
    db_path = tmp_path / "registry.db"
    migrate(db_path)
    repository = CaseRepository(db_path)
    repository.add(_case())

    with pytest.raises(DuplicateRecordError, match="CASE-ABC123"):
        repository.add(_case())


def test_case_repository_returns_none_for_unknown_case(tmp_path: Path) -> None:
    db_path = tmp_path / "registry.db"
    migrate(db_path)

    assert CaseRepository(db_path).get("CASE-UNKNOWN") is None


def test_package_repository_adds_and_reads_package(tmp_path: Path) -> None:
    db_path = tmp_path / "registry.db"
    migrate(db_path)
    CaseRepository(db_path).add(_case())
    repository = PackageRepository(db_path)

    repository.add(_package())

    assert repository.get(_package().package_id) == _package()


def test_package_repository_requires_existing_case(tmp_path: Path) -> None:
    db_path = tmp_path / "registry.db"
    migrate(db_path)

    with pytest.raises(RecordNotFoundError, match="CASE-ABC123"):
        PackageRepository(db_path).add(_package())


def test_package_repository_transitions_state(tmp_path: Path) -> None:
    db_path = tmp_path / "registry.db"
    migrate(db_path)
    CaseRepository(db_path).add(_case())
    repository = PackageRepository(db_path)
    repository.add(_package())

    updated = repository.transition(_package().package_id, PackageState.ENCRYPTING)

    assert updated.state is PackageState.ENCRYPTING
    assert updated.updated_at >= _package().updated_at
    assert repository.get(_package().package_id) == updated


def test_package_repository_rejects_invalid_transition(tmp_path: Path) -> None:
    db_path = tmp_path / "registry.db"
    migrate(db_path)
    CaseRepository(db_path).add(_case())
    repository = PackageRepository(db_path)
    repository.add(_package())

    with pytest.raises(ValueError, match="Cannot transition"):
        repository.transition(_package().package_id, PackageState.READY)


def test_package_repository_lists_packages_for_case(tmp_path: Path) -> None:
    db_path = tmp_path / "registry.db"
    migrate(db_path)
    CaseRepository(db_path).add(_case())
    repository = PackageRepository(db_path)
    first = _package("SPK-2026-111111111111111111111111")
    second = _package("SPK-2026-222222222222222222222222")
    repository.add(first)
    repository.add(second)

    assert repository.list_for_case("CASE-ABC123") == [first, second]


def test_package_repository_returns_none_for_unknown_package(tmp_path: Path) -> None:
    db_path = tmp_path / "registry.db"
    migrate(db_path)

    assert PackageRepository(db_path).get("SPK-2026-UNKNOWN") is None


def test_package_repository_raises_when_transitioning_unknown_package(tmp_path: Path) -> None:
    db_path = tmp_path / "registry.db"
    migrate(db_path)

    with pytest.raises(RecordNotFoundError, match="SPK-2026-UNKNOWN"):
        PackageRepository(db_path).transition("SPK-2026-UNKNOWN", PackageState.ENCRYPTING)
