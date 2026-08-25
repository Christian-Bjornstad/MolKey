"""Copy affordances: double-click detail card, context menu, Ctrl+C, selectable lookup text."""

from pathlib import Path

from PyQt6.QtCore import QSettings, Qt
from PyQt6.QtGui import QGuiApplication
from PyQt6.QtWidgets import (
    QDialog,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
)

from molkey.application.patient_key_service import PatientKeyService
from molkey.infrastructure.migrations import migrate
from molkey.ui.main_window import MainWindow


def _isolated_settings(tmp_path: Path) -> QSettings:
    return QSettings(str(tmp_path / "molkey-test-settings.ini"), QSettings.Format.IniFormat)


def _build_window(qtbot, tmp_path: Path, seed: int = 0):  # noqa: ANN001
    db_path = tmp_path / "registry.db"
    migrate(db_path)
    window = MainWindow(
        registry_path=str(tmp_path),
        registry_connected=True,
        database_path=db_path,
        settings=_isolated_settings(tmp_path),
    )
    qtbot.addWidget(window)
    service = PatientKeyService(db_path)
    records = [service.get_or_create(f"26OUM{i:05d}", initials="CFB") for i in range(seed)]
    if hasattr(window, "_refresh_registry"):
        window._refresh_registry()
    return window, service, records


def _clipboard_text() -> str:
    return QGuiApplication.clipboard().text()


# --- Slice 1: double-click opens detail card -------------------------------


def test_double_click_registry_row_opens_detail_dialog(qtbot, tmp_path: Path) -> None:
    window, _, [record] = _build_window(qtbot, tmp_path, seed=1)

    index = window.registry_table.model().index(0, 0)
    window.registry_table.doubleClicked.emit(index)

    dialog = window.findChild(QDialog, "registryDetailDialog")
    assert dialog is not None
    texts = " ".join(label.text() for label in dialog.findChildren(QLabel))
    assert record.pseudonymous_key in texts
    assert record.patient_id in texts


def test_detail_dialog_copy_buttons_fill_clipboard_with_feedback(qtbot, tmp_path: Path) -> None:
    window, _, [record] = _build_window(qtbot, tmp_path, seed=1)
    window._open_registry_detail(0)
    dialog = window.findChild(QDialog, "registryDetailDialog")

    key_button = dialog.findChild(QPushButton, "copyDetailKeyButton")
    patient_button = dialog.findChild(QPushButton, "copyDetailPatientButton")
    QGuiApplication.clipboard().clear()
    key_button.click()
    assert _clipboard_text() == record.pseudonymous_key
    assert "copied" in key_button.text().lower()
    patient_button.click()
    assert _clipboard_text() == record.patient_id


def test_detail_dialog_values_are_mouse_selectable(qtbot, tmp_path: Path) -> None:
    window, _, _record = _build_window(qtbot, tmp_path, seed=1)
    window._open_registry_detail(0)
    dialog = window.findChild(QDialog, "registryDetailDialog")

    value_labels = dialog.findChildren(QLabel, "detailKeyValue") + dialog.findChildren(
        QLabel, "detailPatientValue"
    )
    assert len(value_labels) >= 2
    for label in value_labels:
        interaction = label.textInteractionFlags()
        assert interaction & Qt.TextInteractionFlag.TextSelectableByMouse


# --- Slice 2: right-click menu + Ctrl+C ------------------------------------


def test_copy_actions_take_key_and_patient_from_selected_row(qtbot, tmp_path: Path) -> None:
    window, _, [record] = _build_window(qtbot, tmp_path, seed=1)
    window.registry_table.selectRow(0)

    QGuiApplication.clipboard().clear()
    window._copy_registry_keys()
    assert _clipboard_text() == record.pseudonymous_key

    window._copy_registry_patients()
    assert _clipboard_text() == record.patient_id


def test_ctrl_c_on_registry_copies_every_selected_key(qtbot, tmp_path: Path) -> None:
    window, _, records = _build_window(qtbot, tmp_path, seed=3)

    for row in range(window.registry_table.rowCount()):
        window.registry_table.item(row, 0).setSelected(True)

    QGuiApplication.clipboard().clear()
    window._copy_selected_rows()
    expected = "\n".join(
        window.registry_table.item(row, 1).text()
        for row in range(window.registry_table.rowCount())
    )
    assert _clipboard_text() == expected


def test_batch_results_table_also_copies_selected_keys(qtbot, tmp_path: Path) -> None:
    window, _, _records = _build_window(qtbot, tmp_path, seed=0)
    window.operator_initials = "CFB"
    window.batch_input.setPlainText("26OUM00001\n26OUM00002\n")
    window._process_batch()
    table = window.findChild(QTableWidget, "batchResultsTable")
    assert table.rowCount() == 2

    for row in range(table.rowCount()):
        table.item(row, 0).setSelected(True)
    QGuiApplication.clipboard().clear()
    window._copy_batch_keys()

    copied = [line for line in _clipboard_text().splitlines() if line.startswith("MK-")]
    assert len(copied) == 2


# --- Slice 3: lookup page ---------------------------------------------------


def test_lookup_result_is_selectable_and_has_copy_buttons(qtbot, tmp_path: Path) -> None:
    window, _, [record] = _build_window(qtbot, tmp_path, seed=1)
    window.navigation_buttons[2].click()
    window.lookup_input.setText(record.patient_id)
    window.findChild(QPushButton, "lookupButton").click()

    result = window.findChild(QLabel, "lookupResult")
    assert result.textInteractionFlags() & Qt.TextInteractionFlag.TextSelectableByMouse
    assert record.pseudonymous_key in result.text()

    QGuiApplication.clipboard().clear()
    window.findChild(QPushButton, "copyLookupKeyButton").click()
    assert _clipboard_text() == record.pseudonymous_key
    window.findChild(QPushButton, "copyLookupPatientButton").click()
    assert _clipboard_text() == record.patient_id


# --- Bonus: generated-key field ----------------------------------------------


def test_generate_dialog_offers_copy_of_new_key(qtbot, tmp_path: Path) -> None:
    window, _, _records = _build_window(qtbot, tmp_path, seed=0)
    window.findChild(QPushButton, "generateKeyButton").click()
    dialog = window.findChild(QDialog, "generateKeyDialog")
    dialog.findChild(QLineEdit, "dialogInitialsInput").setText("CFB")
    dialog.findChild(QLineEdit, "patientIdInput").setText("26OUM42424")

    confirm = dialog.findChild(QPushButton, "confirmGenerateButton")
    assert confirm is not None
    confirm.click()

    output = dialog.findChild(QLineEdit, "generatedKeyOutput")
    copy_button = dialog.findChild(QPushButton, "copyGeneratedKeyButton")
    assert copy_button is not None
    QGuiApplication.clipboard().clear()
    copy_button.click()
    assert _clipboard_text() == output.text()
    assert output.text().startswith("MK-")
