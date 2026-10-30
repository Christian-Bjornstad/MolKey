"""Load branded icons from both an installed wheel and a source checkout."""

from importlib.resources import files
from pathlib import Path

from PyQt6.QtGui import QIcon, QPixmap


def load_icon(filename: str) -> QIcon:
    """Return an icon even when the current working directory is outside the repo."""
    packaged = files("molkey").joinpath("assets", filename)
    source = Path(__file__).resolve().parents[2] / "assets" / filename
    asset = packaged if packaged.is_file() else source
    if not asset.is_file():
        return QIcon()
    pixmap = QPixmap()
    try:
        data = asset.read_bytes()
    except OSError:
        return QIcon()
    if not pixmap.loadFromData(data):
        return QIcon()
    return QIcon(pixmap)
