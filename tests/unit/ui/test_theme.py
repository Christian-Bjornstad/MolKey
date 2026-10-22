"""MolKey must stay readable regardless of the Windows system color scheme."""

from PyQt6.QtGui import QColor

from molkey.ui.theme import COLORS, apply_palette, build_palette


def _contrast(foreground: str, background: str) -> float:
    def luminance(hex_color: str) -> float:
        channels = [int(hex_color[index : index + 2], 16) / 255 for index in (1, 3, 5)]
        linear = [channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4 for channel in channels]
        return sum(channel * weight for channel, weight in zip(linear, (0.2126, 0.7152, 0.0722), strict=True))

    brighter, darker = sorted((luminance(foreground), luminance(background)), reverse=True)
    return (brighter + 0.05) / (darker + 0.05)


def test_brand_and_status_text_meet_normal_text_contrast() -> None:
    assert _contrast("#FFFFFF", COLORS["primary"]) >= 4.5
    for token in ("muted", "success"):
        assert _contrast(COLORS[token], COLORS["surface"]) >= 4.5
        assert _contrast(COLORS[token], COLORS["canvas"]) >= 4.5


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
    assert palette.color(palette.ColorRole.Highlight) == QColor(COLORS["primary"])


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
