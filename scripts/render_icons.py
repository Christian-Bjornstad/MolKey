"""Render the MolKey brand icon (Designer master) to the full PNG set + .ico.

Source of truth: assets/molkey_icon_designer.png — the hand-drawn master
(navy squircle tile: key + database + molecular network) exported on a
white canvas. This script:

  1. Crops to the tile (bounding box of non-white content, safety inset).
  2. Re-masks the tile with a clean anti-aliased rounded rectangle so the
     corners are truly transparent (the Designer export ships white
     corners, not alpha).
  3. Writes assets/molkey_icon_512.png / _256 / _64 / _32 / _16 (all with
     transparent corners) and assets/molkey_icon.ico (256, 64, 32, 16).

Requires only the project's existing PyQt6 dependency (QImage/QPainter).
"""

from pathlib import Path

from PyQt6.QtCore import QPointF, QSize, Qt
from PyQt6.QtGui import QColor, QIcon, QImage, QPainterPath, QPixmap
from PyQt6.QtWidgets import QApplication

ROOT = Path(__file__).resolve().parents[1]
MASTER = ROOT / "assets" / "molkey_icon_designer.png"
SIZES = [512, 256, 64, 32, 16]
CORNER_RADIUS_RATIO = 0.225  # ≈ tile radius measured from the Designer master
WHITE_THRESHOLD = 238  # rgb components above this count as margin white
INSET = 6  # px trimmed from the measured tile box (anti-aliasing safety)


def _is_margin_white(color: QColor) -> bool:
    return (
        color.red() > WHITE_THRESHOLD
        and color.green() > WHITE_THRESHOLD
        and color.blue() > WHITE_THRESHOLD
    )


def _rounded_path(size: float, radius: float) -> QPainterPath:
    path = QPainterPath()
    path.addRoundedRect(0.0, 0.0, size, size, radius, radius)
    return path


def build_master() -> QImage:
    """Crop the tile out of the white-canvas export and re-mask its corners."""
    source = QImage(str(MASTER))
    if source.isNull():
        raise SystemExit(f"Cannot read {MASTER}")

    width, height = source.width(), source.height()

    # 1. Bounding box of non-white content (the tile).
    min_x, min_y, max_x, max_y = width, height, -1, -1
    for y in range(height):
        for x in range(width):
            if not _is_margin_white(source.pixelColor(x, y)):
                min_x, min_y = min(min_x, x), min(min_y, y)
                max_x, max_y = max(max_x, x), max(max_y, y)
    if max_x < 0:
        raise SystemExit("Master appears blank — no non-white content found")

    tile_box = source.copy(
        min_x + INSET,
        min_y + INSET,
        max_x - min_x - 2 * INSET,
        max_y - min_y - 2 * INSET,
    )
    # The Designer export is not pixel-perfect square; take a centred square
    # crop of the shorter side (sub-2 px difference is imperceptible).
    side = min(tile_box.width(), tile_box.height())
    off_x = (tile_box.width() - side) // 2
    off_y = (tile_box.height() - side) // 2
    tile = tile_box.copy(off_x, off_y, side, side)

    # 2. Copy tile pixels that fall inside the rounded-rect mask; the rest
    #    (the Designer export's white corner fill) becomes transparent.
    size = tile.width()
    path = _rounded_path(float(size), float(size) * CORNER_RADIUS_RATIO)
    result = QImage(size, size, QImage.Format.Format_ARGB32)
    result.fill(Qt.GlobalColor.transparent)
    for y in range(size):
        for x in range(size):
            if path.contains(QPointF(x + 0.5, y + 0.5)):
                result.setPixelColor(x, y, tile.pixelColor(x, y))
    return result


def _scale_and_remask(master: QImage, size_px: int) -> QImage:
    """Smooth-scale the master, then re-apply the rounded mask at target size.

    Scaling alone leaves the corners correct (master already masked), but
    re-masking guarantees crisp corner alpha even if resampling bleeds a
    few semi-transparent pixels outside the arc.
    """
    scaled = master.scaled(
        size_px,
        size_px,
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )
    cleaned = QImage(size_px, size_px, QImage.Format.Format_ARGB32)
    cleaned.fill(Qt.GlobalColor.transparent)
    radius = max(2.0, size_px * CORNER_RADIUS_RATIO)
    path = _rounded_path(float(size_px), radius)
    for y in range(size_px):
        for x in range(size_px):
            if path.contains(QPointF(x + 0.5, y + 0.5)):
                cleaned.setPixelColor(x, y, scaled.pixelColor(x, y))
    return cleaned


def main() -> None:
    _app = QApplication([])  # QImage/QIcon require a QGuiApplication instance

    master = build_master()
    out_dir = ROOT / "assets"

    images: dict[int, QImage] = {}
    for size_px in SIZES:
        image = _scale_and_remask(master, size_px)
        out = out_dir / f"molkey_icon_{size_px}.png"
        if not image.save(str(out), "PNG"):
            raise SystemExit(f"Failed to write {out}")
        images[size_px] = image
        print(f"wrote {out.relative_to(ROOT)}")

    icon = QIcon()
    for size_px in (256, 64, 32, 16):
        icon.addPixmap(QPixmap.fromImage(images[size_px]))
    ico_path = out_dir / "molkey_icon.ico"
    if not icon.pixmap(QSize(256, 256)).save(str(ico_path), "ICO"):
        raise SystemExit(f"Failed to write {ico_path}")
    print(f"wrote {ico_path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
