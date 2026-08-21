"""MolVault desktop application entry point."""

from __future__ import annotations

import os
import sys

from PyQt6.QtCore import QSettings
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QApplication

from molvault.config import ConfigError, RegistryConfig
from molvault.ui.main_window import MainWindow


def resolve_registry_config(settings: QSettings, *, validate_root: bool = True) -> RegistryConfig | None:
    """Resolve registry configuration, preferring managed environment settings."""
    try:
        if os.environ.get("MOLVAULT_REGISTRY_ROOT"):
            return RegistryConfig.from_env(validate_root=validate_root)
        saved_root = str(settings.value("registry/root", "")).strip()
        if saved_root:
            return RegistryConfig.from_root(saved_root, validate_root=validate_root)
    except ConfigError:
        return None
    return None


def main() -> int:
    """Start the MolVault desktop application."""
    application = QApplication(sys.argv)
    application.setApplicationName("MolVault")
    application.setOrganizationName("MolVault")
    application.setFont(QFont("Arial", 10))
    settings = QSettings()
    config = resolve_registry_config(settings)
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
    )
    window.show()
    return application.exec()


if __name__ == "__main__":
    raise SystemExit(main())
