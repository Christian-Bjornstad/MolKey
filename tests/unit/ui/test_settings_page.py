"""Tests for configuring the shared registry from Settings."""

from pathlib import Path

from PyQt6.QtCore import QSettings, Qt
from PyQt6.QtWidgets import QLabel, QLineEdit, QPushButton

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
    assert window.settings_feedback.text() == "Registry folder saved."
    assert window.settings_feedback.objectName() == "statusGood"
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
