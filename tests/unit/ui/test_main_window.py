import csv
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QFileDialog,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTextEdit,
)

from molvault.infrastructure.migrations import migrate
from molvault.ui.main_window import MainWindow


def connected_window(qtbot, tmp_path: Path) -> MainWindow:
    db_path = tmp_path / "registry.db"
    migrate(db_path)
    window = MainWindow(
        registry_path=str(tmp_path), registry_connected=True, database_path=db_path
    )
    qtbot.addWidget(window)
    return window


def test_main_window_has_key_registry_identity_and_safe_unavailable_action(qtbot):
    window = MainWindow(registry_path=r"\\secure-drive\molkey", registry_connected=False)
    qtbot.addWidget(window)

    assert window.windowTitle() == "MolKey"
    assert window.minimumWidth() >= 1100
    button = window.findChild(QPushButton, "generateKeyButton")
    assert button.text() == "Generate key"
    assert button.accessibleName() == "Generate or retrieve a permanent patient key"
    assert not button.isEnabled()


def test_help_describes_key_registry_workflow(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)

    qtbot.mouseClick(window.findChild(QPushButton, "helpButton"), Qt.MouseButton.LeftButton)

    dialog = window.findChild(QDialog, "helpDialog")
    help_text = dialog.findChild(QLabel, "helpText").text()
    assert "database is created automatically" in help_text
    assert "Generate a key" in help_text
    assert "patient-to-key mapping" in help_text
    assert "encrypt" not in help_text.lower()


def test_dashboard_exposes_connection_and_privacy_status(qtbot):
    window = MainWindow(registry_path=r"\\secure-drive\molkey", registry_connected=True)
    qtbot.addWidget(window)

    assert window.connection_status.text() == "Registry connected"
    assert "secure-drive" in window.registry_path_label.text()
    assert "Patient identifiers stay inside the registry" in window.privacy_notice.text()


def test_sidebar_navigation_switches_to_batch_page(qtbot):
    window = MainWindow(registry_path=r"C:\MolKeyRegistry")
    qtbot.addWidget(window)

    batch_button = window.navigation_buttons[1]
    qtbot.mouseClick(batch_button, Qt.MouseButton.LeftButton)

    assert window.page_stack.currentIndex() == 1
    assert batch_button.property("active") is True
    assert window.navigation_buttons[0].property("active") is False
    assert window.page_title.text() == "Batch generation"


def test_single_generate_reuses_permanent_key(qtbot, tmp_path):
    window = connected_window(qtbot, tmp_path)
    button = window.findChild(QPushButton, "generateKeyButton")

    qtbot.mouseClick(button, Qt.MouseButton.LeftButton)
    dialog = window.findChild(QDialog, "generateKeyDialog")
    dialog.findChild(QLineEdit, "patientIdInput").setText("PAT-UI-001")
    qtbot.mouseClick(dialog.findChild(QPushButton, "confirmGenerateButton"), Qt.MouseButton.LeftButton)

    generated = dialog.findChild(QLineEdit, "generatedKeyOutput").text()
    assert generated.startswith("MK-")
    assert window.key_service.lookup_by_patient("PAT-UI-001").pseudonymous_key == generated

    dialog.close()
    qtbot.mouseClick(button, Qt.MouseButton.LeftButton)
    second = window.findChild(QDialog, "generateKeyDialog")
    second.findChild(QLineEdit, "patientIdInput").setText("PAT-UI-001")
    qtbot.mouseClick(second.findChild(QPushButton, "confirmGenerateButton"), Qt.MouseButton.LeftButton)
    assert second.findChild(QLineEdit, "generatedKeyOutput").text() == generated


def test_batch_paste_generates_review_and_keys_only_export(qtbot, tmp_path, monkeypatch):
    window = connected_window(qtbot, tmp_path)
    qtbot.mouseClick(window.navigation_buttons[1], Qt.MouseButton.LeftButton)
    batch_input = window.findChild(QTextEdit, "batchPatientIdsInput")
    batch_input.setPlainText("PAT-001\nPAT-002\nPAT-001\n")

    qtbot.mouseClick(
        window.findChild(QPushButton, "processBatchButton"), Qt.MouseButton.LeftButton
    )

    table = window.findChild(QTableWidget, "batchResultsTable")
    assert table.rowCount() == 2
    summary = window.findChild(QLabel, "batchSummary").text()
    assert "2 new" in summary
    assert "1 duplicate" in summary
    destination = tmp_path / "upload_keys.csv"
    monkeypatch.setattr(
        QFileDialog,
        "getSaveFileName",
        staticmethod(lambda *args, **kwargs: (str(destination), "CSV (*.csv)")),
    )
    qtbot.mouseClick(
        window.findChild(QPushButton, "exportBatchButton"), Qt.MouseButton.LeftButton
    )

    with destination.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert list(rows[0]) == ["molkey"]
    assert "PAT-001" not in destination.read_text(encoding="utf-8")


def test_lookup_works_in_both_directions(qtbot, tmp_path):
    window = connected_window(qtbot, tmp_path)
    record = window.key_service.get_or_create("PAT-LOOKUP")
    qtbot.mouseClick(window.navigation_buttons[2], Qt.MouseButton.LeftButton)
    lookup = window.findChild(QLineEdit, "lookupInput")

    lookup.setText("PAT-LOOKUP")
    qtbot.mouseClick(window.findChild(QPushButton, "lookupButton"), Qt.MouseButton.LeftButton)
    assert record.pseudonymous_key in window.findChild(QLabel, "lookupResult").text()

    lookup.setText(record.pseudonymous_key.lower())
    qtbot.mouseClick(window.findChild(QPushButton, "lookupButton"), Qt.MouseButton.LeftButton)
    assert "PAT-LOOKUP" in window.findChild(QLabel, "lookupResult").text()


def test_registry_page_lists_internal_mapping(qtbot, tmp_path):
    window = connected_window(qtbot, tmp_path)
    record = window.key_service.get_or_create("PAT-INTERNAL")

    qtbot.mouseClick(window.navigation_buttons[3], Qt.MouseButton.LeftButton)

    table = window.findChild(QTableWidget, "keyRegistryTable")
    visible = " ".join(table.item(0, column).text() for column in range(table.columnCount()))
    assert "PAT-INTERNAL" in visible
    assert record.pseudonymous_key in visible


def test_settings_copy_mentions_only_registry_data(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    qtbot.mouseClick(window.navigation_buttons[4], Qt.MouseButton.LeftButton)

    help_texts = [item.text() for item in window.findChildren(QLabel, "settingsHelp")]
    assert any("patient-to-key mappings" in text for text in help_texts)
    assert all("encrypted packages" not in text for text in help_texts)
