"""Render the SVG MolKey icon to the PNG sizes and Windows ICO asset."""

from pathlib import Path
from struct import pack

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QImage, QPainter
from PyQt6.QtSvg import QSvgRenderer
from PyQt6.QtWidgets import QApplication

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "assets" / "molkey_icon.svg"
SIZES = (512, 256, 64, 32, 16)
ICO_SIZES = (16, 32, 64, 256)


def render_icon(renderer: QSvgRenderer, size: int) -> QImage:
    """Rasterize the vector artwork with transparent rounded corners."""
    image = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    renderer.render(painter)
    painter.end()
    return image


def write_ico(png_files: dict[int, Path], destination: Path) -> None:
    """Bundle PNG images at native sizes into a Windows ICO container."""
    images = [(size, png_files[size].read_bytes()) for size in ICO_SIZES]
    directory = bytearray(pack("<HHH", 0, 1, len(images)))
    offset = len(directory) + 16 * len(images)
    for size, png in images:
        encoded_size = size if size < 256 else 0
        directory.extend(pack("<BBBBHHII", encoded_size, encoded_size, 0, 0, 1, 32, len(png), offset))
        offset += len(png)
    destination.write_bytes(bytes(directory) + b"".join(png for _, png in images))


def main() -> None:
    _app = QApplication([])
    renderer = QSvgRenderer(str(SOURCE))
    if not renderer.isValid():
        raise SystemExit(f"Cannot render {SOURCE}")

    png_files: dict[int, Path] = {}
    for size in SIZES:
        image = render_icon(renderer, size)
        output = ROOT / "assets" / f"molkey_icon_{size}.png"
        if not image.save(str(output), "PNG"):
            raise SystemExit(f"Failed to write {output}")
        png_files[size] = output
        print(f"wrote {output.relative_to(ROOT)}")

    ico_path = ROOT / "assets" / "molkey_icon.ico"
    write_ico(png_files, ico_path)
    print(f"wrote {ico_path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
