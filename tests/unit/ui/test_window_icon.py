"""The MolKey window must carry the Designer brand icon."""

from pathlib import Path

from PyQt6.QtGui import QIcon, QImage


def test_main_window_sets_molkey_brand_icon(qtbot) -> None:
    from molkey.ui.main_window import MainWindow

    window = MainWindow(registry_path=r"\\server\MolKey", registry_connected=True)
    qtbot.addWidget(window)

    icon = window.windowIcon()
    assert not icon.isNull()
    assert icon.availableSizes(), "brand icon has no rendered sizes"


def test_brand_icon_asset_exists_in_repo() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    assert (repo_root / "assets" / "molkey_icon_designer.png").is_file()
    assert (repo_root / "assets" / "molkey_icon_256.png").is_file()
    assert (repo_root / "assets" / "molkey_icon.ico").is_file()


def test_brand_icon_corners_are_transparent() -> None:
    """The Designer master ships white corners; the rendered set must not."""
    repo_root = Path(__file__).resolve().parents[3]
    image = QImage(str(repo_root / "assets" / "molkey_icon_256.png"))
    assert image.format() in (
        QImage.Format.Format_ARGB32,
        QImage.Format.Format_ARGB32_Premultiplied,
        QImage.Format.Format_RGBA8888,
    ), "icon must carry an alpha channel"
    last = image.width() - 2
    for corner in ((1, 1), (last, 1), (1, last), (last, last)):
        assert image.pixelColor(*corner).alpha() == 0, f"corner {corner} not transparent"


def test_window_icon_matches_brand_asset(qtbot) -> None:
    from molkey.ui.main_window import MainWindow

    window = MainWindow(registry_path=r"\\server\MolKey", registry_connected=True)
    qtbot.addWidget(window)

    asset = Path(__file__).resolve().parents[3] / "assets" / "molkey_icon_256.png"
    expected = QIcon(str(asset))
    actual = window.windowIcon()
    assert not actual.isNull()
    assert actual.pixmap(64, 64).toImage() == expected.pixmap(64, 64).toImage()
