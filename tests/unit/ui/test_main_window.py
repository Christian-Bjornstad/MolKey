from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QPushButton

from molvault.ui.main_window import MainWindow


def test_main_window_has_product_identity_and_safe_unavailable_actions(qtbot):
    window = MainWindow(registry_path=r"\\secure-drive\molvault", registry_connected=True)
    qtbot.addWidget(window)

    assert window.windowTitle() == "MolVault"
    assert window.minimumWidth() >= 1100
    assert window.findChild(QPushButton, "createPackageButton").text() == "Create package"
    assert window.findChild(QPushButton, "createPackageButton").accessibleName() == "Create a secure package"
    assert not window.findChild(QPushButton, "createPackageButton").isEnabled()


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
