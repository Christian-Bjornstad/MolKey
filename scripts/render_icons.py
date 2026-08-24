"""Render assets/molkey_icon.svg to the full PNG set and a multi-resolution .ico.

Uses Qt's SVG renderer (no extra project dependencies). Writes:
  assets/molkey_icon_512.png / _256 / _64 / _32 / _16
  assets/molkey_icon.ico  (256, 64, 32, 16 embedded)
"""

from pathlib import Path

from PyQt6.QtCore import QByteArray, Qt
from PyQt6.QtGui import QIcon, QImage, QPainter, QPixmap
from PyQt6.QtSvg import QSvgRenderer
from PyQt6.QtWidgets import QApplication

ROOT = Path(__file__).resolve().parents[1]
SVG_PATH = ROOT / "assets" / "molkey_icon.svg"
SVG_SMALL_PATH = ROOT / "assets" / "molkey_icon_small.svg"
SIZES = [512, 256, 64, 32, 16]
SMALL_SIZES = {64, 32, 16}


def render_png(renderer: QSvgRenderer, size: int) -> QImage:
    """Render the SVG master at the requested pixel size."""
    image = QImage(size, size, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    renderer.render(painter)
    painter.end()
    return image


def main() -> None:
    _app = QApplication([])  # QPixmap/QIcon require a QGuiApplication instance
    master_renderer = QSvgRenderer(QByteArray(SVG_PATH.read_bytes()))
    small_renderer = QSvgRenderer(QByteArray(SVG_SMALL_PATH.read_bytes()))

    images = {}
    for size in SIZES:
        renderer = small_renderer if size in SMALL_SIZES else master_renderer
        if not renderer.isValid():
            raise SystemExit(f"Invalid SVG asset for size {size}")
        image = render_png(renderer, size)
        out = ROOT / "assets" / f"molkey_icon_{size}.png"
        if not image.save(str(out), "PNG"):
            raise SystemExit(f"Failed to write {out}")
        images[size] = image
        print(f"wrote {out.relative_to(ROOT)}")

    icon = QIcon()
    for size in (256, 64, 32, 16):
        icon.addPixmap(QPixmap.fromImage(images[size]))
    ico_path = ROOT / "assets" / "molkey_icon.ico"
    if not icon.pixmap(256, 256).save(str(ico_path), "ICO"):
        raise SystemExit(f"Failed to write {ico_path}")
    print(f"wrote {ico_path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
