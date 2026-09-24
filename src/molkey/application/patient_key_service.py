"""Application service for permanent patient pseudonyms."""

import csv
import json
import secrets
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from molkey.infrastructure.database import DatabaseError
from molkey.infrastructure.registry_workbook import WORKBOOK_NAME, write_registry_workbook
from molkey.infrastructure.repositories import PatientKeyRecord, PatientKeyRepository
from molkey.infrastructure.writer_lock import RegistryBusyError, writer_lock


@dataclass(frozen=True)
class BatchResult:
    """Summary and ordered mappings produced by a batch."""

    items: list[PatientKeyRecord]
    reused_count: int
    created_count: int
    duplicate_count: int
    invalid_count: int


class PatientKeyService:
    """Generate and retrieve stable pseudonymous patient keys."""

    def __init__(self, db_path: Path) -> None:
        self.repository = PatientKeyRepository(db_path)
        self.workbook_path = db_path.parent / WORKBOOK_NAME
        self.workbook_error: str | None = None

    def refresh_registry_workbook(self) -> bool:
        """Refresh the protected Excel copy; preserve key creation if Excel locks it."""
        try:
            with writer_lock(self.repository.db_path.parent):
                write_registry_workbook(self.repository.list_all(), self.workbook_path)
        except (OSError, ValueError, sqlite3.Error, DatabaseError, RegistryBusyError, RuntimeError) as exc:
            self.workbook_error = str(exc)
            return False
        self.workbook_error = None
        return True

    @staticmethod
    def _normalise_initials(initials: str) -> str:
        raw = initials.strip()
        normalised = raw.upper()
        if not raw.isascii() or not raw.isalpha():
            raise ValueError("Operator initials are required (2-4 letters) before any key can be created")
        if not 2 <= len(normalised) <= 4:
            raise ValueError("Operator initials must be 2-4 letters")
        return normalised

    def get_or_create(self, patient_id: str, initials: str) -> PatientKeyRecord:
        raw = patient_id.strip()
        if not raw:
            raise ValueError("Patient ID is required")
        if not raw.isascii() or not raw.isalnum():
            raise ValueError("Patient ID must contain only letters A-Z and digits 0-9")
        normalised = raw.upper()
        existing = self.repository.get_by_patient(normalised)
        if existing is not None:
            return existing
        operator = self._normalise_initials(initials)
        record = self.repository.get_or_create(normalised, f"MK{secrets.token_hex(8).upper()}", operator)
        self.refresh_registry_workbook()
        return record

    def lookup_by_patient(self, patient_id: str) -> PatientKeyRecord | None:
        normalised = patient_id.strip().upper()
        if not normalised:
            return None
        return self.repository.get_by_patient(normalised)

    def lookup_by_key(self, pseudonymous_key: str) -> PatientKeyRecord | None:
        normalised = pseudonymous_key.strip().upper()
        if not normalised:
            return None
        return self.repository.get_by_key(normalised)

    def list_recent(self, limit: int = 50) -> list[PatientKeyRecord]:
        return self.repository.list_recent(limit)

    def search_registry(self, query: str = "", limit: int = 500) -> tuple[list[PatientKeyRecord], int, int]:
        return self.repository.search_registry(query, limit)

    def process_batch(self, patient_ids: list[str], initials: str) -> BatchResult:
        operator = self._normalise_initials(initials)
        items: list[PatientKeyRecord] = []
        seen: set[str] = set()
        reused_count = 0
        created_count = 0
        duplicate_count = 0
        invalid_count = 0

        for patient_id in patient_ids:
            raw = patient_id.strip()
            if not raw or not raw.isascii() or not raw.isalnum():
                invalid_count += 1
                continue
            normalised = raw.upper()
            if normalised in seen:
                duplicate_count += 1
                continue
            seen.add(normalised)
            existing = self.repository.get_by_patient(normalised)
            if existing is not None:
                items.append(existing)
                reused_count += 1
            else:
                try:
                    record = self.repository.get_or_create(normalised, f"MK{secrets.token_hex(8).upper()}", operator)
                except Exception:
                    if created_count:
                        self.refresh_registry_workbook()
                    raise
                items.append(record)
                created_count += 1

        if created_count:
            self.refresh_registry_workbook()

        return BatchResult(
            items=items,
            reused_count=reused_count,
            created_count=created_count,
            duplicate_count=duplicate_count,
            invalid_count=invalid_count,
        )

    def export_keys(self, items: list[PatientKeyRecord], destination: Path) -> None:
        rows = [{"molkey": item.pseudonymous_key} for item in items]
        if destination.suffix.lower() == ".csv":
            with destination.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=["molkey"])
                writer.writeheader()
                writer.writerows(rows)
            return
        if destination.suffix.lower() == ".json":
            destination.write_text(json.dumps(rows, indent=2), encoding="utf-8")
            return
        raise ValueError("Export destination must end with .csv or .json")
