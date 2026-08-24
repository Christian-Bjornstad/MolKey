"""Registry browser shows everyone's keys with operator attribution, searchable; creation requires initials."""

from pathlib import Path

from PyQt6.QtCore import QSettings
from PyQt6.QtWidgets import QPushButton

from molkey.application.patient_key_service import PatientKeyService
from molkey.infrastructure.migrations import migrate
from molkey.ui.main_window import MainWindow


def _isolated_settings(tmp_path: Path) -> QSettings:
    """INI-backed settings in the test's temp dir; never touches real user state."""
    return QSettings(str(tmp_path / "molkey-test-settings.ini"), QSettings.Format.IniFormat)


def _build_window(qtbot, tmp_path: Path):  # noqa: ANN001
    db_path = tmp_path / "registry.db"
    migrate(db_path)
    window = MainWindow(
        registry_path=str(tmp_path),
        registry_connected=True,
        database_path=db_path,
        settings=_isolated_settings(tmp_path),
    )
    qtbot.addWidget(window)
    return window


def _navigate_to_registry(window) -> None:  # noqa: ANN001
    window._make_navigation_handler(3)()


def test_registry_page_shows_keys_created_by_other_workstations(qtbot, tmp_path: Path) -> None:
    window = _build_window(qtbot, tmp_path)
    # Two independent "workstations" share the same registry file.
    PatientKeyService(window.database_path).get_or_create("26OUM99999", initials="CFB")
    PatientKeyService(window.database_path).get_or_create("26OUM00001", initials="ANB")

    _navigate_to_registry(window)

    assert window.registry_table.rowCount() == 2
    headers = [window.registry_table.horizontalHeaderItem(i).text() for i in range(4)]
    assert headers == ["Patient ID", "MolKey", "Created", "By"]
    by_column = {window.registry_table.item(row, 3).text() for row in range(2)}
    assert by_column == {"CFB", "ANB"}


def test_registry_search_filters_by_patient_id_fragment(qtbot, tmp_path: Path) -> None:
    window = _build_window(qtbot, tmp_path)
    service = PatientKeyService(window.database_path)
    service.get_or_create("26OUM99999", initials="CFB")
    service.get_or_create("26OUM00001", initials="ANB")
    service.get_or_create("27ABD12345", initials="CFB")
    _navigate_to_registry(window)

    search = window.findChild(type(window.lookup_input), "registrySearchInput")
    search.setText("26OUM")

    assert window.registry_table.rowCount() == 2
    assert "Showing 2 of 3" in window.findChild(type(window.batch_summary), "registryCountLabel").text()


def test_registry_search_matches_molkey_and_initials(qtbot, tmp_path: Path) -> None:
    window = _build_window(qtbot, tmp_path)
    service = PatientKeyService(window.database_path)
    first = service.get_or_create("26OUM99999", initials="CFB")
    service.get_or_create("26OUM00001", initials="ANB")
    _navigate_to_registry(window)
    search = window.findChild(type(window.lookup_input), "registrySearchInput")

    search.setText(first.pseudonymous_key[-4:])
    assert window.registry_table.rowCount() == 1

    search.setText("anb")
    assert window.registry_table.rowCount() == 1
    assert window.registry_table.item(0, 0).text() == "26OUM00001"


def test_refresh_button_pulls_new_keys_from_shared_database(qtbot, tmp_path: Path) -> None:
    window = _build_window(qtbot, tmp_path)
    _navigate_to_registry(window)
    assert window.registry_table.rowCount() == 0

    PatientKeyService(window.database_path).get_or_create("26OUM99999", initials="TST")
    window.findChild(type(window.generate_key_button), "refreshRegistryButton").click()

    assert window.registry_table.rowCount() == 1
    assert window.registry_table.item(0, 0).text() == "26OUM99999"


def test_generate_dialog_refuses_without_initials_and_shows_error(qtbot, tmp_path: Path) -> None:
    window = _build_window(qtbot, tmp_path)
    window.generate_key_button.click()
    patient_input = window.findChild(type(window.lookup_input), "patientIdInput")
    confirm = window.findChild(type(window.generate_key_button), "confirmGenerateButton")
    output = window.findChild(type(window.lookup_input), "generatedKeyOutput")
    feedback = window.findChild(type(window.batch_summary), "generateFeedback")

    patient_input.setText("26OUM99999")
    confirm.click()

    assert output.text() == ""
    assert "initials" in feedback.text().lower()
    assert PatientKeyService(window.database_path).list_recent() == []


def test_initials_are_normalised_stored_and_remembered(qtbot, tmp_path: Path) -> None:
    window = _build_window(qtbot, tmp_path)
    initials_input = window.findChild(type(window.lookup_input), "operatorInitialsInput")
    initials_input.setText("cfb")

    window.generate_key_button.click()
    window.findChild(type(window.lookup_input), "patientIdInput").setText("26OUM99999")
    window.findChild(type(window.generate_key_button), "confirmGenerateButton").click()
    output = window.findChild(type(window.lookup_input), "generatedKeyOutput")

    assert output.text().startswith("MK-")
    assert initials_input.text() == "CFB"
    assert str(window.settings.value("operator/initials")) == "CFB"

    # A brand-new window (simulated restart) prefills the remembered initials.
    reopened = MainWindow(
        registry_path=str(tmp_path),
        registry_connected=True,
        database_path=window.database_path,
        settings=window.settings,
    )
    qtbot.addWidget(reopened)
    assert reopened.findChild(type(initials_input), "operatorInitialsInput").text() == "CFB"


def test_batch_generation_blocked_with_message_when_initials_missing(qtbot, tmp_path: Path) -> None:
    window = _build_window(qtbot, tmp_path)
    window.findChild(type(window.lookup_input), "operatorInitialsInput").setText("")
    window.batch_input.setPlainText("PAT-001\nPAT-002")

    batch_button = window.findChild(QPushButton, "processBatchButton")
    assert batch_button is not None
    batch_button.click()

    assert "initials" in window.batch_summary.text().lower()
    assert PatientKeyService(window.database_path).list_recent() == []
