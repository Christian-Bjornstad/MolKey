"""Integration tests for package security and export metadata repositories."""

import json
from pathlib import Path

import pytest

from molkey.domain.models import CaseRecord, PackageRecord
from molkey.infrastructure.migrations import migrate
from molkey.infrastructure.repositories import (
    CaseRepository,
    DestinationRecord,
    DestinationRepository,
    EncryptionKeyRecord,
    EncryptionKeyRepository,
    PackageFileRecord,
    PackageFileRepository,
    PackageRepository,
)


def _seed_package(db_path: Path) -> str:
    case = CaseRecord("CASE-META", "PAT-1", "SPEC-26OUM00001")
    package = PackageRecord("SPK-2026-AAAAAAAAAAAAAAAAAAAAAAAA", case.case_id, "KEY-PENDING", "ExternalLab")
    CaseRepository(db_path).add(case)
    PackageRepository(db_path).add(package)
    return package.package_id


def test_wrapped_key_round_trip_and_package_link(tmp_path: Path) -> None:
    db_path = tmp_path / "registry.db"
    migrate(db_path)
    package_id = _seed_package(db_path)
    record = EncryptionKeyRecord("KEY-ABCDEF12", package_id, b"wrapped-secret", "AES-256-GCM", 1)

    EncryptionKeyRepository(db_path).add(record)

    assert EncryptionKeyRepository(db_path).get(record.key_id) == record
    assert PackageRepository(db_path).get(package_id).key_id == record.key_id  # type: ignore[union-attr]


def test_package_file_metadata_round_trip(tmp_path: Path) -> None:
    db_path = tmp_path / "registry.db"
    migrate(db_path)
    package_id = _seed_package(db_path)
    record = PackageFileRecord(package_id, "file-001.enc", 10, 38, b"123456789012", "a" * 64)

    PackageFileRepository(db_path).add(record)

    assert PackageFileRepository(db_path).list_for_package(package_id) == [record]


def test_destination_round_trip_without_secrets(tmp_path: Path) -> None:
    db_path = tmp_path / "registry.db"
    migrate(db_path)
    record = DestinationRecord("External laboratory", "filesystem", '{"path":"outbound"}', True)

    DestinationRepository(db_path).add(record)

    assert DestinationRepository(db_path).get(record.name) == record


def test_destination_rejects_secret_like_configuration(tmp_path: Path) -> None:
    db_path = tmp_path / "registry.db"
    migrate(db_path)
    repo = DestinationRepository(db_path)

    repo.add(DestinationRecord("valid", "sftp", json.dumps({"host": "sftp.example.com", "path": "/uploads"}), True))

    secret_cases = [
        ("password", json.dumps({"password": "secret"})),
        ("secret", json.dumps({"secret": "abc"})),
        ("token", json.dumps({"token": "xyz"})),
        ("api_key", json.dumps({"api_key": "key"})),
        ("private_key", json.dumps({"private_key": "pem"})),
        ("nested_password", json.dumps({"auth": {"password": "pw"}})),
        ("access_token", json.dumps({"auth": {"access_token": "tok"}})),
        ("client_secret", json.dumps({"oauth": {"client_secret": "sec"}})),
        ("privatekey_nospace", json.dumps({"privatekey": "pem"})),
        ("apiKey_camel", json.dumps({"apiKey": "key"})),
        ("apikey_lower", json.dumps({"apikey": "key"})),
        ("authtoken_lower", json.dumps({"authtoken": "tok"})),
        ("bearer_token", json.dumps({"bearer": "tok"})),
        ("secretkey_compound", json.dumps({"secretkey": "sec"})),
        ("deep_nested", json.dumps({"config": {"credentials": {"password": "pw"}}})),
        ("list_of_secrets", json.dumps({"accounts": [{"password": "a"}, {"password": "b"}]})),
    ]

    for label, config in secret_cases:
        with pytest.raises(ValueError, match="secret credentials"):
            repo.add(DestinationRecord(label, "test", config, True))

    assert repo.get("valid") is not None