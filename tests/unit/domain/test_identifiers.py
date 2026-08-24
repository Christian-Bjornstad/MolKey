import re
from datetime import date

import pytest

from molkey.domain.identifiers import generate_key_id, generate_package_id


def test_package_id_uses_injected_year_and_uppercase_random_component():
    package_id = generate_package_id(today=date(2031, 4, 9))

    assert re.fullmatch(r"SPK-2031-[0-9A-F]{24}", package_id)


def test_key_id_is_distinct_from_package_id():
    assert re.fullmatch(r"KEY-[0-9A-F]{12}", generate_key_id())


def test_ten_thousand_generated_package_ids_are_unique():
    generated = {generate_package_id(today=date(2026, 1, 1)) for _ in range(10_000)}

    assert len(generated) == 10_000


def test_patient_or_specimen_inputs_are_not_accepted():
    with pytest.raises(TypeError):
        generate_package_id(patient_id="PAT-123")
    with pytest.raises(TypeError):
        generate_package_id(specimen_id="SPEC-123")
