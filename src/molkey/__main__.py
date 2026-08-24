"""MolKey desktop application entry point."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from PyQt6.QtCore import QSettings
from PyQt6.QtGui import QFont, QIcon
from PyQt6.QtWidgets import QApplication

from molkey.config import ConfigError, RegistryConfig
from molkey.infrastructure.migrations import migrate
from molkey.ui.main_window import MainWindow
from molkey.ui.theme import STYLESHEET, apply_palette


def resolve_registry_config(settings: QSettings, *, validate_root: bool = True) -> RegistryConfig | None:
    """Resolve registry configuration, preferring managed environment settings."""
    try:
        if os.environ.get("MOLKEY_REGISTRY_ROOT"):
            return RegistryConfig.from_env(validate_root=validate_root)
        saved_root = str(settings.value("registry/root", "")).strip()
        if saved_root:
            return RegistryConfig.from_root(saved_root, validate_root=validate_root)
    except ConfigError:
        return None
    return None


def initialize_registry(config: RegistryConfig) -> None:
    """Create required registry folders and migrate the shared database."""
    config.locks_dir.mkdir(parents=True, exist_ok=True)
    config.packages_dir.mkdir(parents=True, exist_ok=True)
    config.staging_dir.mkdir(parents=True, exist_ok=True)
    config.backups_dir.mkdir(parents=True, exist_ok=True)
    migrate(config.database_path)


def main() -> int:
    """Start the MolKey desktop application."""
    application = QApplication(sys.argv)
    application.setApplicationName("MolKey")
    application.setOrganizationName("MolKey")
    brand_icon = Path(__file__).resolve().parents[2] / "assets" / "molkey_icon.ico"
    if brand_icon.is_file():
        application.setWindowIcon(QIcon(str(brand_icon)))
    apply_palette(application)
    application.setStyleSheet(STYLESHEET)
    application.setFont(QFont("Arial", 10))
    settings = QSettings()
    config = resolve_registry_config(settings)
    if config is not None:
        try:
            initialize_registry(config)
        except (OSError, RuntimeError):
            config = None
    if config is None:
        registry_path = str(settings.value("registry/root", "Registry not configured or inaccessible"))
        registry_connected = False
    else:
        registry_path = str(config.root)
        registry_connected = True
    window = MainWindow(
        registry_path=registry_path,
        registry_connected=registry_connected,
        settings=settings,
        database_path=config.database_path if config is not None else None,
    )
    window.show()
    return application.exec()


if __name__ == "__main__":
    raise SystemExit(main())
