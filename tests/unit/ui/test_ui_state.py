"""Keep displayed keys in sync with input and surface routine file errors."""

from pathlib import Path

from PyQt6.QtCore import QSettings
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import QDialog, QFileDialog, QLabel, QLineEdit, QPushButton

from molkey.infrastructure.migrations import migrate
from molkey.ui.main_window import MainWindow


def _window(qtbot, tmp_path: Path) -> MainWindow:  # noqa: ANN001
    db_path = tmp_path / "registry.db"
    migrate(db_path)
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    window = MainWindow(
        registry_path=str(tmp_path),
        registry_connected=True,
        database_path=db_path,
        settings=settings,
    )
    qtbot.addWidget(window)
    return window


def test_sidebar_uses_packaged_brand_icon(qtbot, tmp_path: Path) -> None:  # noqa: ANN001
    window = _window(qtbot, tmp_path)

    logo = window.findChild(QLabel, "brandIcon")
    assert logo is not None
    assert logo.accessibleName() == "MolKey logo"
    assert not logo.pixmap().isNull()


def test_batch_edit_clears_previous_export_and_results(qtbot, tmp_path: Path) -> None:  # noqa: ANN001
    window = _window(qtbot, tmp_path)
    window.operator_initials_input.setText("ABC")
    window.batch_input.setPlainText("26OUM12345")
    window._process_batch()
    assert window.batch_results.rowCount() == 1
    assert window.findChild(QPushButton, "exportBatchButton").isEnabled()

    window.batch_input.setPlainText("26OUM67890")

    assert window.current_batch is None
    assert window.batch_results.rowCount() == 0
    assert not window.findChild(QPushButton, "exportBatchButton").isEnabled()


def test_batch_shows_mapping_and_blocks_export_until_invalid_rows_are_fixed(qtbot, tmp_path: Path) -> None:  # noqa: ANN001
    window = _window(qtbot, tmp_path)
    window.operator_initials_input.setText("ABC")
    window.batch_input.setPlainText("26OUM12345\nBAD-ID\n26OUM67890")

    window._process_batch()

    assert window.batch_results.rowCount() == 0
    assert window.key_service.lookup_by_patient("26OUM12345") is None
    assert window.key_service.lookup_by_patient("26OUM67890") is None
    assert "no keys were created" in window.batch_summary.text().lower()
    assert "line 2" in window.batch_summary.text().lower()
    assert not window.findChild(QPushButton, "exportBatchButton").isEnabled()

    window.batch_input.setPlainText("26OUM12345\n26OUM67890")
    window._process_batch()

    assert window.batch_results.rowCount() == 2
    assert [window.batch_results.horizontalHeaderItem(column).text() for column in range(3)] == [
        "Patient ID",
        "MolKey",
        "Result",
    ]
    assert window.batch_results.item(0, 0).text() == "26OUM12345"
    assert window.batch_results.item(0, 1).text().startswith("MK")
    assert window.findChild(QPushButton, "exportBatchButton").isEnabled()


def test_lookup_edit_clears_previous_match_and_copy_actions(qtbot, tmp_path: Path) -> None:  # noqa: ANN001
    window = _window(qtbot, tmp_path)
    record = window.key_service.get_or_create("26OUM12345", "ABC")
    window.lookup_input.setText(record.patient_id)
    window._lookup()
    assert window.copy_lookup_key_button.isEnabled()

    window.lookup_input.setText("26OUM67890")

    assert window.lookup_result.text() == ""
    assert not window.copy_lookup_key_button.isEnabled()
    assert not window.copy_lookup_patient_button.isEnabled()


def test_generate_dialog_edit_clears_key_and_copy_action(qtbot, tmp_path: Path) -> None:  # noqa: ANN001
    window = _window(qtbot, tmp_path)
    window.generate_key_button.click()
    dialog = window.findChild(QDialog, "generateKeyDialog")
    patient_input = dialog.findChild(QLineEdit, "patientIdInput")
    dialog.findChild(QLineEdit, "dialogInitialsInput").setText("ABC")
    patient_input.setText("26OUM12345")
    dialog.findChild(QPushButton, "confirmGenerateButton").click()
    output = dialog.findChild(QLineEdit, "generatedKeyOutput")
    copy = dialog.findChild(QPushButton, "copyGeneratedKeyButton")
    assert output.text().startswith("MK")
    assert copy.isEnabled()

    patient_input.setText("26OUM67890")

    assert output.text() == ""
    assert not copy.isEnabled()


def test_bad_csv_import_reports_error_without_changing_input(qtbot, tmp_path: Path, monkeypatch) -> None:  # noqa: ANN001
    window = _window(qtbot, tmp_path)
    window.batch_input.setPlainText("26OUM12345")
    broken_csv = tmp_path / "broken.csv"
    broken_csv.write_bytes(b"\xff")
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *_args: (str(broken_csv), "CSV files (*.csv)"))

    window._import_batch_csv()

    assert window.batch_input.toPlainText() == "26OUM12345"
    assert "import" in window.batch_summary.text().lower()


def test_csv_import_accepts_excel_semicolon_separator_and_header(qtbot, tmp_path: Path, monkeypatch) -> None:  # noqa: ANN001
    window = _window(qtbot, tmp_path)
    source = tmp_path / "ids.csv"
    source.write_text("Pasient-ID;Kommentar\n26oum12345;test\n26OUM67890;test\n", encoding="utf-8")
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *_args: (str(source), "CSV files (*.csv)"))

    window._import_batch_csv()

    assert window.batch_input.toPlainText() == "26oum12345\n26OUM67890"


def test_empty_batch_explains_required_input(qtbot, tmp_path: Path) -> None:  # noqa: ANN001
    window = _window(qtbot, tmp_path)
    window.operator_initials_input.setText("ABC")

    window._process_batch()

    assert "at least one patient ID" in window.batch_summary.text()
    assert window.current_batch is None


def test_export_failure_reports_error(qtbot, tmp_path: Path, monkeypatch) -> None:  # noqa: ANN001
    window = _window(qtbot, tmp_path)
    window.operator_initials_input.setText("ABC")
    window.batch_input.setPlainText("26OUM12345")
    window._process_batch()
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *_args: (str(tmp_path / "out.csv"), "CSV (*.csv)"))

    def fail_export(*_args: object) -> None:
        raise PermissionError("locked")

    monkeypatch.setattr(window.key_service, "export_keys", fail_export)

    window._export_batch()

    assert "could not export" in window.batch_summary.text().lower()
    assert "locked" in window.batch_summary.text().lower()


def test_lookup_failure_reports_error_and_clears_previous_match(qtbot, tmp_path: Path, monkeypatch) -> None:  # noqa: ANN001
    window = _window(qtbot, tmp_path)
    record = window.key_service.get_or_create("26OUM12345", "ABC")
    window.lookup_input.setText(record.patient_id)
    window._lookup()

    def fail_lookup(*_args: object) -> None:
        raise OSError("offline")

    monkeypatch.setattr(window.key_service, "lookup_by_patient", fail_lookup)

    window._lookup()

    assert "unavailable" in window.lookup_result.text().lower()
    assert "offline" in window.lookup_result.text().lower()
    assert not window.copy_lookup_key_button.isEnabled()


def test_registry_detail_failure_reports_error(qtbot, tmp_path: Path, monkeypatch) -> None:  # noqa: ANN001
    window = _window(qtbot, tmp_path)
    window.key_service.get_or_create("26OUM12345", "ABC")
    window._refresh_registry()

    def fail_lookup(*_args: object) -> None:
        raise OSError("offline")

    monkeypatch.setattr(window.key_service, "lookup_by_patient", fail_lookup)
    window._open_registry_detail(0)

    assert "unavailable" in window.registry_count_label.text().lower()
    assert window.findChild(QDialog, "registryDetailDialog") is None


def test_open_excel_reports_when_windows_cannot_launch_it(qtbot, tmp_path: Path, monkeypatch) -> None:  # noqa: ANN001
    window = _window(qtbot, tmp_path)
    monkeypatch.setattr(QDesktopServices, "openUrl", lambda *_args: False)

    window._open_registry_workbook()

    assert "could not open" in window.registry_count_label.text().lower()
