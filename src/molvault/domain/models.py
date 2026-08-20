"""Domain models for MolVault."""

from dataclasses import dataclass, field
from datetime import UTC, datetime

from molvault.domain.states import PackageState


@dataclass(frozen=True)
class CaseRecord:
    """Internal case record linking patient/specimen to packages."""

    case_id: str
    patient_id: str
    specimen_id: str
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        _require_identifier(self.case_id, "CASE-", "case_id")
        _require_identifier(self.patient_id, "PAT-", "patient_id")
        _require_identifier(self.specimen_id, "SPEC-", "specimen_id")


@dataclass(frozen=True)
class PackageRecord:
    """Pseudonymous package record for export/transfer."""

    package_id: str
    case_id: str
    key_id: str
    destination_ref: str
    state: PackageState = PackageState.DRAFT
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        _require_identifier(self.package_id, "SPK-", "package_id")
        _require_identifier(self.case_id, "CASE-", "case_id")
        _require_identifier(self.key_id, "KEY-", "key_id")
        if not self.destination_ref.strip() or len(self.destination_ref) > 200:
            raise ValueError("destination_ref must be between 1 and 200 characters")


def _require_identifier(value: str, prefix: str, field_name: str) -> None:
    if not value.startswith(prefix) or not value.removeprefix(prefix).strip():
        raise ValueError(f"{field_name} must start with '{prefix}' and include a value")
