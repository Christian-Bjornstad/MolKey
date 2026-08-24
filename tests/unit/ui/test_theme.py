"""MolKey must stay readable regardless of the Windows system color scheme."""

from PyQt6.QtGui import QColor

from molkey.ui.theme import apply_palette, build_palette


def test_stylesheet_styles_dialogs_independently_of_system_theme() -> None:
    from molkey.ui.theme import STYLESHEET

    dialog_block = STYLESHEET.split("QDialog, QMessageBox {", 1)[1].split("}", 1)[0]
    assert "#F7F6FA" in dialog_block
    assert "QToolTip {" in STYLESHEET


def test_build_palette_uses_light_canvas_and_brand_text() -> None:
    palette = build_palette()

    assert palette.color(palette.ColorRole.Window) == QColor("#F7F6FA")
    assert palette.color(palette.ColorRole.WindowText) == QColor("#2D2950")
    assert palette.color(palette.ColorRole.Base) == QColor("#FFFFFF")
    assert palette.color(palette.ColorRole.ToolTipBase) == QColor("#FFFFFF")
    assert palette.color(palette.ColorRole.ToolTipText) == QColor("#2D2950")
    assert palette.color(palette.ColorRole.Highlight) == QColor("#847CBA")


def test_apply_palette_overrides_dark_system_scheme(qtbot) -> None:
    from PyQt6.QtWidgets import QApplication

    app = QApplication.instance()
    assert app is not None
    previous = app.palette()
    try:
        dark = build_palette()
        dark.setColor(dark.ColorRole.Window, QColor("#101010"))
        app.setPalette(dark)

        apply_palette(app)

        assert app.palette().color(app.palette().ColorRole.Window) == QColor("#F7F6FA")
    finally:
        app.setPalette(previous)
