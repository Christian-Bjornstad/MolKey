"""Application service for creating package drafts."""

from __future__ import annotations

import secrets
from pathlib import Path

from molvault.domain.identifiers import generate_package_id
from molvault.domain.models import CaseRecord, PackageRecord
from molvault.infrastructure.database import connect
from molvault.infrastructure.repositories import CaseRepository, PackageRepository


class PackageService:
    """Coordinate case mapping and pseudonymous package creation."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.cases = CaseRepository(db_path)
        self.packages = PackageRepository(db_path)

    def create_draft(
        self,
        *,
        patient_id: str,
        case_number: str,
        destination: str | None = None,
        notes: str = "",
    ) -> PackageRecord:
        patient_value = patient_id.strip()
        case_value = case_number.strip()
        if not patient_value:
            raise ValueError("Patient ID is required")
        if not case_value:
            raise ValueError("Case number is required")

        internal_patient_id = _with_prefix(patient_value, "PAT-")
        case = self._find_case(internal_patient_id, case_value)
        if case is None:
            case = CaseRecord(
                case_id=f"CASE-{secrets.token_hex(6).upper()}",
                patient_id=internal_patient_id,
                specimen_id=_with_prefix(case_value, "SPEC-"),
            )
            self.cases.add(case)

        package = PackageRecord(
            package_id=generate_package_id(),
            case_id=case.case_id,
            key_id="KEY-PENDING",
            destination=destination.strip() if destination and destination.strip() else None,
            notes=notes.strip(),
        )
        self.packages.add(package)
        return package

    def _find_case(self, patient_id: str, case_number: str) -> CaseRecord | None:
        conn = connect(self.db_path)
        try:
            row = conn.execute(
                "SELECT id FROM cases WHERE patient_id = ? AND case_number = ?",
                (patient_id, case_number),
            ).fetchone()
        finally:
            conn.close()
        return self.cases.get(str(row["id"])) if row is not None else None


def _with_prefix(value: str, prefix: str) -> str:
    return value if value.startswith(prefix) else f"{prefix}{value}"
