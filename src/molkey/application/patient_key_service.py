"""Application service for permanent patient pseudonyms."""

import csv
import json
import secrets
from dataclasses import dataclass
from pathlib import Path

from molkey.infrastructure.repositories import PatientKeyRecord, PatientKeyRepository


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

    def get_or_create(self, patient_id: str) -> PatientKeyRecord:
        normalised = patient_id.strip()
        if not normalised:
            raise ValueError("Patient ID is required")
        existing = self.repository.get_by_patient(normalised)
        if existing is not None:
            return existing
        return self.repository.get_or_create(normalised, f"MK-{secrets.token_hex(5).upper()}")

    def lookup_by_patient(self, patient_id: str) -> PatientKeyRecord | None:
        normalised = patient_id.strip()
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

    def process_batch(self, patient_ids: list[str]) -> BatchResult:
        items: list[PatientKeyRecord] = []
        seen: set[str] = set()
        reused_count = 0
        created_count = 0
        duplicate_count = 0
        invalid_count = 0

        for patient_id in patient_ids:
            normalised = patient_id.strip()
            if not normalised:
                invalid_count += 1
                continue
            if normalised in seen:
                duplicate_count += 1
                continue
            seen.add(normalised)
            existing = self.repository.get_by_patient(normalised)
            if existing is not None:
                items.append(existing)
                reused_count += 1
            else:
                items.append(self.get_or_create(normalised))
                created_count += 1

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
