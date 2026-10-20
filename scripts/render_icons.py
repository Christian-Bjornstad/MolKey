"""Render the SVG MolKey icon to the PNG sizes and Windows ICO asset."""

from pathlib import Path

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QIcon, QImage, QPainter, QPixmap
from PyQt6.QtSvg import QSvgRenderer
from PyQt6.QtWidgets import QApplication

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "assets" / "molkey_icon.svg"
SIZES = (512, 256, 64, 32, 16)


def render_icon(renderer: QSvgRenderer, size: int) -> QImage:
    """Rasterize the vector artwork with transparent rounded corners."""
    image = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    renderer.render(painter)
    painter.end()
    return image


def main() -> None:
    _app = QApplication([])
    renderer = QSvgRenderer(str(SOURCE))
    if not renderer.isValid():
        raise SystemExit(f"Cannot render {SOURCE}")

    icon = QIcon()
    for size in SIZES:
        image = render_icon(renderer, size)
        output = ROOT / "assets" / f"molkey_icon_{size}.png"
        if not image.save(str(output), "PNG"):
            raise SystemExit(f"Failed to write {output}")
        icon.addPixmap(QPixmap.fromImage(image))
        print(f"wrote {output.relative_to(ROOT)}")

    ico_path = ROOT / "assets" / "molkey_icon.ico"
    if not icon.pixmap(QSize(256, 256)).save(str(ico_path), "ICO"):
        raise SystemExit(f"Failed to write {ico_path}")
    print(f"wrote {ico_path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
