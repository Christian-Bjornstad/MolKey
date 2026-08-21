from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QDialog, QLabel, QLineEdit, QPushButton, QTableWidget

from molvault.infrastructure.migrations import migrate
from molvault.infrastructure.repositories import PackageRepository
from molvault.ui.main_window import MainWindow


def test_main_window_has_product_identity_and_safe_unavailable_actions(qtbot):
    window = MainWindow(registry_path=r"\\secure-drive\molvault", registry_connected=True)
    qtbot.addWidget(window)

    assert window.windowTitle() == "MolKey"
    assert window.minimumWidth() >= 1100
    assert window.findChild(QPushButton, "createPackageButton").text() == "Create package"
    assert window.findChild(QPushButton, "createPackageButton").accessibleName() == "Create a secure package"
    assert not window.findChild(QPushButton, "createPackageButton").isEnabled()


def test_help_button_opens_getting_started_dialog(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)

    help_button = window.findChild(QPushButton, "helpButton")
    assert help_button is not None
    assert help_button.isEnabled()
    qtbot.mouseClick(help_button, Qt.MouseButton.LeftButton)

    dialog = window.findChild(QDialog, "helpDialog")
    assert dialog is not None
    help_text = dialog.findChild(QLabel, "helpText").text()
    assert "database is created automatically" in help_text
    assert "Create package" in help_text


def test_dashboard_exposes_connection_and_privacy_status(qtbot):
    window = MainWindow(registry_path=r"\\secure-drive\molvault", registry_connected=True)
    qtbot.addWidget(window)

    assert window.connection_status.text() == "Registry connected"
    assert "secure-drive" in window.registry_path_label.text()
    assert "Patient identifiers stay inside the registry" in window.privacy_notice.text()


def test_sidebar_navigation_switches_pages(qtbot):
    window = MainWindow(registry_path=r"C:\MolVaultRegistry")
    qtbot.addWidget(window)

    packages_button = window.navigation_buttons[1]
    qtbot.mouseClick(packages_button, Qt.MouseButton.LeftButton)

    assert window.page_stack.currentIndex() == 1
    assert packages_button.property("active") is True
    assert window.navigation_buttons[0].property("active") is False
    assert window.page_title.text() == "Packages"


def test_unconfigured_registry_is_never_reported_as_connected(qtbot):
    window = MainWindow(registry_path="Registry not configured", registry_connected=False)
    qtbot.addWidget(window)

    assert window.connection_status.text() == "Registry not connected"


def test_dashboard_summary_is_seeded_with_safe_placeholder_counts(qtbot):
    window = MainWindow(registry_path=r"C:\MolVaultRegistry")
    qtbot.addWidget(window)

    assert window.metric_values == {"ready": "0", "processing": "0", "attention": "0"}
    assert "No packages yet" in window.empty_state_title.text()


def test_create_package_dialog_persists_draft(qtbot, tmp_path):
    db_path = tmp_path / "registry.db"
    migrate(db_path)
    window = MainWindow(
        registry_path=str(tmp_path),
        registry_connected=True,
        database_path=db_path,
    )
    qtbot.addWidget(window)

    create_button = window.findChild(QPushButton, "createPackageButton")
    assert create_button.isEnabled()
    qtbot.mouseClick(create_button, Qt.MouseButton.LeftButton)

    dialog = window.findChild(QDialog, "createPackageDialog")
    assert dialog is not None
    dialog.findChild(QLineEdit, "patientIdInput").setText("PAT-UI-001")
    dialog.findChild(QLineEdit, "ditInput").setText("26OUM12287")
    qtbot.mouseClick(dialog.findChild(QPushButton, "saveDraftButton"), Qt.MouseButton.LeftButton)

    packages = PackageRepository(db_path).list_recent()
    assert len(packages) == 1
    assert packages[0].package_id.startswith("SPK-")
    assert window.page_stack.currentIndex() == 1


def test_packages_page_lists_persisted_package_without_patient_identifier(qtbot, tmp_path):
    db_path = tmp_path / "registry.db"
    migrate(db_path)
    window = MainWindow(
        registry_path=str(tmp_path), registry_connected=True, database_path=db_path
    )
    qtbot.addWidget(window)
    package = window.package_service.create_draft(
        patient_id="PAT-SECRET-001", case_number="26OUM12287"
    )

    qtbot.mouseClick(window.navigation_buttons[1], Qt.MouseButton.LeftButton)

    table = window.findChild(QTableWidget, "packagesTable")
    assert table is not None
    assert table.rowCount() == 1
    visible_text = " ".join(
        table.item(0, column).text() for column in range(table.columnCount())
    )
    assert package.package_id in visible_text
    assert "PAT-SECRET-001" not in visible_text


def test_cases_page_lists_internal_patient_and_case_mapping(qtbot, tmp_path):
    db_path = tmp_path / "registry.db"
    migrate(db_path)
    window = MainWindow(
        registry_path=str(tmp_path), registry_connected=True, database_path=db_path
    )
    qtbot.addWidget(window)
    window.package_service.create_draft(
        patient_id="12345678901", case_number="26OUM12287"
    )

    qtbot.mouseClick(window.navigation_buttons[2], Qt.MouseButton.LeftButton)

    table = window.findChild(QTableWidget, "casesTable")
    assert table is not None
    assert table.rowCount() == 1
    visible_text = " ".join(
        table.item(0, column).text() for column in range(table.columnCount())
    )
    assert "PAT-12345678901" in visible_text
    assert "SPEC-26OUM12287" in visible_text
