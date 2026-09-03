"""SQLite repositories for MolKey domain records."""

import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from molkey.domain.models import CaseRecord, PackageRecord
from molkey.domain.states import PackageState
from molkey.infrastructure.database import connect, transaction


def normalise_external_id(value: str) -> str:
    """Normalise an externally-typed identifier (DIT number, patient key) for storage.

    DIT numbers and other hospital-style identifiers are routinely typed in
    mixed case (e.g. ``26oum12345`` vs. ``26OUM12345``). We persist a single
    canonical upper-case form so the database never contains duplicates that
    differ only by case, and every lookup is case-insensitive.
    """
    return value.strip().upper()


class RepositoryError(Exception):
    """Base error for repository operations."""


class DuplicateRecordError(RepositoryError):
    """Raised when a record violates a uniqueness constraint."""


class RecordNotFoundError(RepositoryError):
    """Raised when a required record does not exist."""


@dataclass(frozen=True)
class EncryptionKeyRecord:
    """Wrapped data-encryption key metadata."""

    key_id: str
    package_id: str
    wrapped_key: bytes
    algorithm: str
    version: int


@dataclass(frozen=True)
class PackageFileRecord:
    """Export-safe encrypted file metadata."""

    package_id: str
    export_name: str
    original_size: int
    encrypted_size: int
    nonce: bytes
    checksum: str


@dataclass(frozen=True)
class DestinationRecord:
    """Destination metadata without credentials or secret material."""

    name: str
    destination_type: str
    config_json: str
    is_active: bool


@dataclass(frozen=True)
class PatientKeyRecord:
    """Permanent pseudonymous key assigned to one internal patient."""

    patient_id: str
    pseudonymous_key: str
    created_at: datetime
    created_by: str = "UKJENT"


class PatientKeyRepository:
    """Persistence operations for permanent patient-to-key mappings."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path

    def get_or_create(self, patient_id: str, pseudonymous_key: str, created_by: str) -> PatientKeyRecord:
        normalised_id = normalise_external_id(patient_id)
        with transaction(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO patient_keys (patient_id, pseudonymous_key, created_by)
                VALUES (?, ?, ?)
                ON CONFLICT(patient_id) DO NOTHING
                """,
                (normalised_id, pseudonymous_key, created_by),
            )
            row = conn.execute(
                """
                SELECT patient_id, pseudonymous_key, created_at, created_by
                FROM patient_keys WHERE patient_id = ?
                """,
                (normalised_id,),
            ).fetchone()
        if row is None:  # pragma: no cover - guarded by insert/select transaction
            raise RepositoryError(f"Patient key was not saved: {normalised_id}")
        return _patient_key_from_row(row)

    def get_by_patient(self, patient_id: str) -> PatientKeyRecord | None:
        conn = connect(self.db_path)
        try:
            row = conn.execute(
                """
                SELECT patient_id, pseudonymous_key, created_at, created_by
                FROM patient_keys WHERE patient_id = ?
                """,
                (normalise_external_id(patient_id),),
            ).fetchone()
        finally:
            conn.close()
        return _patient_key_from_row(row) if row is not None else None

    def get_by_key(self, pseudonymous_key: str) -> PatientKeyRecord | None:
        conn = connect(self.db_path)
        try:
            row = conn.execute(
                """
                SELECT patient_id, pseudonymous_key, created_at, created_by
                FROM patient_keys WHERE pseudonymous_key = ?
                """,
                (normalise_external_id(pseudonymous_key),),
            ).fetchone()
        finally:
            conn.close()
        return _patient_key_from_row(row) if row is not None else None

    def list_recent(self, limit: int = 50) -> list[PatientKeyRecord]:
        conn = connect(self.db_path)
        try:
            rows = conn.execute(
                """
                SELECT patient_id, pseudonymous_key, created_at, created_by
                FROM patient_keys ORDER BY created_at DESC, patient_id LIMIT ?
                """,
                (limit,),
            ).fetchall()
        finally:
            conn.close()
        return [_patient_key_from_row(row) for row in rows]


class CaseRepository:
    """Persistence operations for internal cases."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path

    def add(self, record: CaseRecord) -> None:
        try:
            with transaction(self.db_path) as conn:
                conn.execute(
                    """
                    INSERT INTO cases (id, patient_id, case_number, created_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        record.case_id,
                        normalise_external_id(record.patient_id),
                        normalise_external_id(record.specimen_id.removeprefix("SPEC-")),
                        record.created_at.isoformat(),
                    ),
                )
        except Exception as exc:
            if isinstance(exc.__cause__, sqlite3.IntegrityError):
                raise DuplicateRecordError(f"Case already exists: {record.case_id}") from exc
            raise

    def get(self, case_id: str) -> CaseRecord | None:
        conn = connect(self.db_path)
        try:
            row = conn.execute(
                "SELECT id, patient_id, case_number, created_at FROM cases WHERE id = ?",
                (case_id,),
            ).fetchone()
        finally:
            conn.close()
        if row is None:
            return None
        return _case_from_row(row)

    def get_by_case_number(self, case_number: str) -> CaseRecord | None:
        """Look up a case by its DIT case number, case-insensitively."""
        conn = connect(self.db_path)
        try:
            row = conn.execute(
                "SELECT id, patient_id, case_number, created_at FROM cases WHERE case_number = ?",
                (normalise_external_id(case_number),),
            ).fetchone()
        finally:
            conn.close()
        if row is None:
            return None
        return _case_from_row(row)

    def list_recent(self, limit: int = 50) -> list[CaseRecord]:
        conn = connect(self.db_path)
        try:
            rows = conn.execute(
                "SELECT id, patient_id, case_number, created_at FROM cases ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        finally:
            conn.close()
        return [_case_from_row(row) for row in rows]


class PackageRepository:
    """Persistence operations for packages and workflow transitions."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path

    def add(self, record: PackageRecord) -> None:
        if CaseRepository(self.db_path).get(record.case_id) is None:
            raise RecordNotFoundError(f"Case not found: {record.case_id}")
        try:
            with transaction(self.db_path) as conn:
                conn.execute(
                    """
                    INSERT INTO packages (
                        id, case_id, state, destination, destination_ref, notes,
                        created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        record.package_id,
                        record.case_id,
                        record.state.value,
                        record.destination,
                        record.destination_ref,
                        record.notes,
                        record.created_at.isoformat(),
                        record.updated_at.isoformat(),
                    ),
                )
        except Exception as exc:
            if isinstance(exc.__cause__, sqlite3.IntegrityError):
                raise DuplicateRecordError(f"Package already exists: {record.package_id}") from exc
            raise

    def get(self, package_id: str) -> PackageRecord | None:
        conn = connect(self.db_path)
        try:
            row = conn.execute(
                """
                SELECT id, case_id, state, destination, destination_ref, key_id, notes, created_at, updated_at
                FROM packages WHERE id = ?
                """,
                (package_id,),
            ).fetchone()
        finally:
            conn.close()
        if row is None:
            return None
        return _package_from_row(row)

    def list_for_case(self, case_id: str) -> list[PackageRecord]:
        conn = connect(self.db_path)
        try:
            rows = conn.execute(
                """
                SELECT id, case_id, state, destination, destination_ref, key_id, notes, created_at, updated_at
                FROM packages WHERE case_id = ? ORDER BY created_at, id
                """,
                (case_id,),
            ).fetchall()
        finally:
            conn.close()
        return [_package_from_row(row) for row in rows]

    def list_recent(self, limit: int = 50) -> list[PackageRecord]:
        conn = connect(self.db_path)
        try:
            rows = conn.execute(
                """
                SELECT id, case_id, state, destination, destination_ref, key_id, notes, created_at, updated_at
                FROM packages ORDER BY created_at DESC LIMIT ?
                """,
                (limit,),
            ).fetchall()
        finally:
            conn.close()
        return [_package_from_row(row) for row in rows]

    def transition(self, package_id: str, next_state: PackageState) -> PackageRecord:
        current = self.get(package_id)
        if current is None:
            raise RecordNotFoundError(f"Package not found: {package_id}")
        if not current.state.can_transition_to(next_state):
            raise ValueError(f"Cannot transition from {current.state.value} to {next_state.value}")

        updated_at = datetime.now(UTC)
        with transaction(self.db_path) as conn:
            cursor = conn.execute(
                """
                UPDATE packages SET state = ?, updated_at = ?
                WHERE id = ? AND state = ?
                """,
                (next_state.value, updated_at.isoformat(), package_id, current.state.value),
            )
            if cursor.rowcount != 1:
                raise RepositoryError(f"Package changed concurrently: {package_id}")

        updated = self.get(package_id)
        if updated is None:  # pragma: no cover - guarded by the successful update
            raise RecordNotFoundError(f"Package not found: {package_id}")
        return updated


class EncryptionKeyRepository:
    """Persistence operations for wrapped package keys."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path

    def add(self, record: EncryptionKeyRecord) -> None:
        if PackageRepository(self.db_path).get(record.package_id) is None:
            raise RecordNotFoundError(f"Package not found: {record.package_id}")
        with transaction(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO encryption_keys (id, package_id, wrapped_key, algorithm, version)
                VALUES (?, ?, ?, ?, ?)
                """,
                (record.key_id, record.package_id, record.wrapped_key, record.algorithm, record.version),
            )
            conn.execute(
                "UPDATE packages SET key_id = ? WHERE id = ?",
                (record.key_id, record.package_id),
            )

    def get(self, key_id: str) -> EncryptionKeyRecord | None:
        conn = connect(self.db_path)
        try:
            row = conn.execute(
                "SELECT id, package_id, wrapped_key, algorithm, version FROM encryption_keys WHERE id = ?",
                (key_id,),
            ).fetchone()
        finally:
            conn.close()
        if row is None:
            return None
        return EncryptionKeyRecord(
            str(row["id"]),
            str(row["package_id"]),
            bytes(row["wrapped_key"]),
            str(row["algorithm"]),
            int(row["version"]),
        )


class PackageFileRepository:
    """Persistence operations for encrypted package-file metadata."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path

    def add(self, record: PackageFileRecord) -> None:
        if PackageRepository(self.db_path).get(record.package_id) is None:
            raise RecordNotFoundError(f"Package not found: {record.package_id}")
        with transaction(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO package_files (
                    package_id, export_name, original_size, encrypted_size, nonce, checksum
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    record.package_id,
                    record.export_name,
                    record.original_size,
                    record.encrypted_size,
                    record.nonce,
                    record.checksum,
                ),
            )

    def list_for_package(self, package_id: str) -> list[PackageFileRecord]:
        conn = connect(self.db_path)
        try:
            rows = conn.execute(
                """
                SELECT package_id, export_name, original_size, encrypted_size, nonce, checksum
                FROM package_files WHERE package_id = ? ORDER BY id
                """,
                (package_id,),
            ).fetchall()
        finally:
            conn.close()
        return [
            PackageFileRecord(
                str(row["package_id"]),
                str(row["export_name"]),
                int(row["original_size"]),
                int(row["encrypted_size"]),
                bytes(row["nonce"]),
                str(row["checksum"]),
            )
            for row in rows
        ]


class DestinationRepository:
    """Persistence operations for destination metadata."""

    _SECRET_KEYS = {
        "password",
        "secret",
        "token",
        "apikey",
        "accesstoken",
        "clientsecret",
        "privatekey",
        "authtoken",
        "bearer",
        "secretkey",
    }

    @staticmethod
    def _normalise_key(key: str) -> str:
        return "".join(ch.lower() for ch in key if ch.isalnum())

    @classmethod
    def _collect_keys(cls, obj: object, prefix: str = "") -> set[str]:
        """Recursively collect all key names from JSON objects/lists, normalised."""
        keys: set[str] = set()
        if isinstance(obj, dict):
            for k, v in obj.items():
                norm = cls._normalise_key(str(k))
                if prefix:
                    keys.add(f"{prefix}.{norm}")
                keys.add(norm)
                keys.update(cls._collect_keys(v, norm))
        elif isinstance(obj, list):
            for item in obj:
                keys.update(cls._collect_keys(item, prefix))
        return keys

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path

    def add(self, record: DestinationRecord) -> None:
        config = json.loads(record.config_json)
        if not isinstance(config, dict):
            raise ValueError("Destination configuration must be a JSON object")
        present_keys = DestinationRepository._collect_keys(config)
        if present_keys & self._SECRET_KEYS:
            raise ValueError("Destination configuration must not contain secret credentials")
        with transaction(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO destinations (name, type, config_json, is_active)
                VALUES (?, ?, ?, ?)
                """,
                (record.name, record.destination_type, record.config_json, int(record.is_active)),
            )

    def get(self, name: str) -> DestinationRecord | None:
        conn = connect(self.db_path)
        try:
            row = conn.execute(
                "SELECT name, type, config_json, is_active FROM destinations WHERE name = ?",
                (name,),
            ).fetchone()
        finally:
            conn.close()
        if row is None:
            return None
        return DestinationRecord(
            str(row["name"]),
            str(row["type"]),
            str(row["config_json"]),
            bool(row["is_active"]),
        )


def _patient_key_from_row(row: sqlite3.Row) -> PatientKeyRecord:
    return PatientKeyRecord(
        patient_id=str(row["patient_id"]),
        pseudonymous_key=str(row["pseudonymous_key"]),
        created_at=datetime.fromisoformat(str(row["created_at"])),
        created_by=str(row["created_by"]) if row["created_by"] else "UKJENT",
    )


def _case_from_row(row: sqlite3.Row) -> CaseRecord:
    return CaseRecord(
        case_id=str(row["id"]),
        patient_id=str(row["patient_id"]),
        specimen_id=f"SPEC-{row['case_number']}",
        created_at=datetime.fromisoformat(str(row["created_at"])),
    )


def _package_from_row(row: sqlite3.Row) -> PackageRecord:
    key_id = str(row["key_id"]) if row["key_id"] else "KEY-PENDING"
    destination = str(row["destination"]) if row["destination"] else None
    destination_ref = str(row["destination_ref"]) if row["destination_ref"] else "Pending"
    return PackageRecord(
        package_id=str(row["id"]),
        case_id=str(row["case_id"]),
        key_id=key_id,
        destination=destination,
        destination_ref=destination_ref,
        notes=str(row["notes"]) if row["notes"] else "",
        state=PackageState(str(row["state"])),
        created_at=datetime.fromisoformat(str(row["created_at"])),
        updated_at=datetime.fromisoformat(str(row["updated_at"])),
    )
