from dataclasses import fields

import pytest

from molvault.domain.errors import InvalidStateTransition
from molvault.domain.models import CaseRecord, PackageRecord
from molvault.domain.states import PackageState


@pytest.mark.parametrize(
    ("current", "next_state"),
    [
        (PackageState.DRAFT, PackageState.ENCRYPTING),
        (PackageState.ENCRYPTING, PackageState.VERIFIED),
        (PackageState.VERIFIED, PackageState.FINALIZING),
        (PackageState.FINALIZING, PackageState.READY),
        (PackageState.READY, PackageState.EXPORTED),
    ],
)
def test_valid_package_state_transitions(current, next_state):
    assert current.can_transition_to(next_state)


@pytest.mark.parametrize(
    "current",
    [
        PackageState.DRAFT,
        PackageState.ENCRYPTING,
        PackageState.VERIFIED,
        PackageState.FINALIZING,
    ],
)
def test_active_states_can_transition_to_failed(current):
    assert current.can_transition_to(PackageState.FAILED)


def test_ready_cannot_return_to_draft():
    with pytest.raises(InvalidStateTransition):
        PackageState.READY.require_transition_to(PackageState.DRAFT)


def test_domain_records_distinguish_identifiers():
    case = CaseRecord(case_id="CASE-1", patient_id="PAT-1", specimen_id="SPEC-1")
    package = PackageRecord(
        package_id="SPK-2026-ABCDEF12",
        case_id=case.case_id,
        key_id="KEY-ABCDEF12",
        destination_ref="External lab",
        state=PackageState.DRAFT,
    )

    assert case.patient_id != package.package_id
    assert package.key_id != package.package_id
    assert package.destination_ref == "External lab"


def test_record_timestamps_use_factories_instead_of_import_time_values():
    case_created = next(field for field in fields(CaseRecord) if field.name == "created_at")
    package_created = next(field for field in fields(PackageRecord) if field.name == "created_at")
    package_updated = next(field for field in fields(PackageRecord) if field.name == "updated_at")

    assert case_created.default_factory is not None
    assert package_created.default_factory is not None
    assert package_updated.default_factory is not None


@pytest.mark.parametrize(
    ("field_name", "value"),
    [("case_id", "CASE-"), ("patient_id", "PAT-"), ("specimen_id", "SPEC-")],
)
def test_case_rejects_empty_identifier_suffixes(field_name, value):
    values = {"case_id": "CASE-1", "patient_id": "PAT-1", "specimen_id": "SPEC-1"}
    values[field_name] = value
    with pytest.raises(ValueError):
        CaseRecord(**values)


def test_package_validates_its_case_identifier():
    with pytest.raises(ValueError, match="case_id"):
        PackageRecord(
            package_id="SPK-2026-ABCDEF12",
            case_id="PAT-1",
            key_id="KEY-ABCDEF12",
            destination_ref="External lab",
        )


@pytest.mark.parametrize("destination_ref", ["", "   ", "x" * 201])
def test_package_rejects_invalid_destination_reference(destination_ref):
    with pytest.raises(ValueError, match="destination_ref"):
        PackageRecord(
            package_id="SPK-2026-ABCDEF12",
            case_id="CASE-1",
            key_id="KEY-ABCDEF12",
            destination_ref=destination_ref,
        )
