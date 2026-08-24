"""Capture the MolKey dashboard for visual verification."""

import os
from pathlib import Path

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication

from molkey.ui.main_window import MainWindow


def main() -> None:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QApplication([])
    window = MainWindow(
        registry_path=r"\\hospital-secure-drive\molecular-pathology\MolKey",
        registry_connected=True,
    )
    window.show()

    output = Path(__file__).resolve().parents[1] / "artifacts" / "molkey-dashboard.png"
    output.parent.mkdir(parents=True, exist_ok=True)

    def capture() -> None:
        window.grab().save(str(output))
        app.quit()

    QTimer.singleShot(400, capture)
    app.exec()
    print(output)


if __name__ == "__main__":
    main()
