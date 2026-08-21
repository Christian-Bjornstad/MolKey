"""Tests for configuring the shared registry from Settings."""

from pathlib import Path

from PyQt6.QtCore import QSettings, Qt
from PyQt6.QtWidgets import QLabel, QLineEdit, QPushButton

from molvault.config import RegistryConfig
from molvault.ui.main_window import MainWindow


def test_settings_page_contains_registry_path_controls(qtbot, tmp_path: Path) -> None:
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    window = MainWindow(settings=settings)
    qtbot.addWidget(window)

    qtbot.mouseClick(window.navigation_buttons[4], Qt.MouseButton.LeftButton)

    assert window.registry_path_input.accessibleName() == "Hospital registry folder"
    assert window.registry_path_input.placeholderText().startswith(r"\\server")
    assert window.findChild(QPushButton, "browseRegistryButton").text() == "Browse"
    assert window.findChild(QPushButton, "saveRegistryButton").text() == "Save settings"
    assert window.page_title.text() == "Settings"


def test_save_registry_path_persists_valid_unc(qtbot, tmp_path: Path) -> None:
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    window = MainWindow(settings=settings)
    qtbot.addWidget(window)
    unc = r"\\hospital-server\secure-share\MolVault"
    window.registry_path_input.setText(unc)

    qtbot.mouseClick(window.findChild(QPushButton, "saveRegistryButton"), Qt.MouseButton.LeftButton)

    assert settings.value("registry/root") == unc
    assert window.settings_feedback.text().startswith("Folder saved, but MolKey could not connect:")
    assert window.settings_feedback.objectName() == "statusError"
    assert not window.create_package_button.isEnabled()
    assert window.registry_path_label.text() == unc


def test_save_registry_path_rejects_local_path(qtbot, tmp_path: Path) -> None:
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    window = MainWindow(settings=settings)
    qtbot.addWidget(window)
    window.registry_path_input.setText(r"C:\MolVault")

    qtbot.mouseClick(window.findChild(QPushButton, "saveRegistryButton"), Qt.MouseButton.LeftButton)

    assert settings.value("registry/root") is None
    assert "UNC" in window.settings_feedback.text()
    assert window.settings_feedback.objectName() == "statusError"


def test_saved_registry_path_is_loaded_on_next_window(qtbot, tmp_path: Path) -> None:
    settings_path = tmp_path / "settings.ini"
    first_settings = QSettings(str(settings_path), QSettings.Format.IniFormat)
    first_settings.setValue("registry/root", r"\\server\share\MolVault")
    first_settings.sync()

    window = MainWindow(settings=QSettings(str(settings_path), QSettings.Format.IniFormat))
    qtbot.addWidget(window)

    assert window.registry_path_input.text() == r"\\server\share\MolVault"
    assert window.registry_path_label.text() == r"\\server\share\MolVault"
    assert window.findChild(QLabel, "settingsHelp") is not None
    assert isinstance(window.registry_path_input, QLineEdit)


def test_saving_accessible_registry_connects_without_restart(qtbot, tmp_path: Path, monkeypatch) -> None:
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    registry_root = tmp_path / "shared-registry"
    registry_root.mkdir()
    config = RegistryConfig.from_root(registry_root, test_mode=True)
    monkeypatch.setattr(
        "molvault.ui.main_window.RegistryConfig.from_root",
        lambda *_args, **_kwargs: config,
    )
    window = MainWindow(settings=settings)
    qtbot.addWidget(window)
    window.registry_path_input.setText(r"\\hospital-server\secure-share\MolKey")

    qtbot.mouseClick(window.findChild(QPushButton, "saveRegistryButton"), Qt.MouseButton.LeftButton)

    assert config.database_path.exists()
    assert window.registry_connected
    assert window.create_package_button.isEnabled()
    assert window.connection_status.text() == "Registry connected"
    assert window.settings_feedback.text() == "Registry connected and ready."
