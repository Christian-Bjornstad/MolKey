"""MolVault desktop application entry point."""

from __future__ import annotations

import sys

from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QApplication

from molvault.config import ConfigError, RegistryConfig
from molvault.ui.main_window import MainWindow


def main() -> int:
    """Start the MolVault desktop application."""
    application = QApplication(sys.argv)
    application.setApplicationName("MolVault")
    application.setOrganizationName("MolVault")
    application.setFont(QFont("Arial", 10))
    try:
        config = RegistryConfig.from_env()
    except ConfigError:
        registry_path = "Registry not configured or inaccessible"
        registry_connected = False
    else:
        registry_path = str(config.root)
        registry_connected = True
    window = MainWindow(registry_path=registry_path, registry_connected=registry_connected)
    window.show()
    return application.exec()


if __name__ == "__main__":
    raise SystemExit(main())
