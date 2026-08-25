"""MolKey visual design tokens and application stylesheet."""

from PyQt6.QtGui import QColor, QPalette
from PyQt6.QtWidgets import QApplication

COLORS = {
    "primary": "#847CBA",
    "primary_hover": "#746CA8",
    "primary_dark": "#5E5794",
    "primary_darker": "#46407A",
    "sidebar_bg": "#2D2950",
    "sidebar_hover": "#3D3868",
    "sidebar_active": "#4A4480",
    "canvas": "#F7F6FA",
    "surface": "#FFFFFF",
    "border": "#D0CEE8",
    "text": "#2D2950",
    "muted": "#7A76A3",
    "success": "#3A8F6B",
    "warning": "#B88A2E",
    "danger": "#C04040",
}

STYLESHEET = """
* {
    font-family: "Arial", sans-serif;
    font-size: 14px;
    color: #2D2950;
}
QMainWindow, QWidget#centralWidget { background: #F7F6FA; }
QFrame#sidebar { background: #2D2950; border: none; }
QLabel#brandMark {
    background: #847CBA; color: white; font-weight: 700; font-size: 18px;
    border-radius: 8px; min-width: 38px; max-width: 38px;
    min-height: 38px; max-height: 38px;
}
QLabel#brandName { color: white; font-size: 20px; font-weight: 700; }
QLabel#brandSubtitle { color: #A8A4D0; font-size: 12px; }
QPushButton[nav="true"] {
    background: transparent; color: #C8C4E0; border: none; border-radius: 7px;
    padding: 11px 14px; text-align: left; font-weight: 600;
}
QPushButton[nav="true"]:hover { background: #3D3868; color: white; }
QPushButton[nav="true"][active="true"] {
    background: #4A4480; color: white; border-left: 3px solid #746CA8;
}
QLabel#environmentBadge {
    color: #D8D4F0; background: #3D3868; border: 1px solid #5E5794;
    border-radius: 11px; padding: 4px 9px; font-size: 11px; font-weight: 700;
}
QFrame#topbar { background: white; border-bottom: 1px solid #D0CEE8; }
QLabel#pageTitle { font-size: 24px; font-weight: 700; color: #2D2950; }
QLabel#pageDescription { color: #7A76A3; }
QPushButton#primaryButton, QPushButton#generateKeyButton, QPushButton#dashboardGenerateButton {
    background: #847CBA; color: white; border: none; border-radius: 7px;
    padding: 10px 18px; font-weight: 700;
}
QPushButton#primaryButton:hover, QPushButton#generateKeyButton:hover,
QPushButton#dashboardGenerateButton:hover { background: #5E5794; }
QPushButton#secondaryButton, QPushButton[secondary="true"] {
    background: white; color: #2D2950; border: 1px solid #B8B4D8;
    border-radius: 7px; padding: 9px 15px; font-weight: 600;
}
QPushButton#secondaryButton:hover, QPushButton[secondary="true"]:hover {
    background: #EFEEF6; border-color: #9894C0;
}
QFrame.card, QFrame#metricCard, QFrame#contentCard, QFrame#privacyNotice {
    background: white; border: 1px solid #D0CEE8; border-radius: 10px;
}
QLabel#eyebrow { color: #7A76A3; font-size: 12px; font-weight: 700; }
QLabel#metricValue { color: #2D2950; font-size: 30px; font-weight: 700; }
QLabel#metricDetail { color: #7A76A3; font-size: 12px; }
QLabel#sectionTitle { color: #2D2950; font-size: 17px; font-weight: 700; }
QLabel#emptyStateTitle { color: #2D2950; font-size: 16px; font-weight: 700; }
QLabel#muted { color: #7A76A3; }
QFrame#privacyNotice { background: #EFEEF6; border-color: #B8B4D8; }
QLabel#privacyIcon { color: #847CBA; font-size: 17px; font-weight: 700; }
QLabel#privacyText { color: #4E4A7A; }
QFrame#statusBar { background: white; border-top: 1px solid #D0CEE8; }
QLabel#statusGood { color: #3A8F6B; font-weight: 700; }
QLabel#statusError { color: #C04040; font-weight: 700; }
QLabel#fieldLabel { color: #2D2950; font-weight: 700; }
QLabel#settingsHelp { color: #5A5688; line-height: 1.4; }
QLabel#statusPath, QLabel#detailKeyValue { color: #7A76A3; font-family: "Cascadia Mono", "Consolas", monospace; }
QLineEdit {
    background: white; border: 1px solid #B8B4D8; border-radius: 7px;
    padding: 9px 12px; selection-background-color: #847CBA;
}
QLineEdit:focus { border: 2px solid #847CBA; }
QTableWidget { background: white; border: 1px solid #D0CEE8; border-radius: 8px; gridline-color: #E8E6F0; }
QHeaderView::section {
    background: #EFEEF6; padding: 9px; border: none;
    border-bottom: 1px solid #D0CEE8; font-weight: 700;
}
QDialog, QMessageBox {
    background: #F7F6FA;
    color: #2D2950;
}
QDialog QLabel { color: #2D2950; background: transparent; }
QMessageBox QLabel { color: #2D2950; background: transparent; }
QDialog QPushButton, QMessageBox QPushButton {
    background: white; color: #2D2950; border: 1px solid #B8B4D8;
    border-radius: 7px; padding: 8px 16px; font-weight: 600; min-width: 72px;
}
QDialog QPushButton:hover, QMessageBox QPushButton:hover {
    background: #EFEEF6; border-color: #9894C0;
}
QDialog QLineEdit, QDialog QPlainTextEdit, QDialog QTextEdit {
    background: white; color: #2D2950; border: 1px solid #B8B4D8;
    border-radius: 7px; padding: 9px 12px;
}
QToolTip {
    background: white; color: #2D2950; border: 1px solid #B8B4D8;
    padding: 5px; border-radius: 4px;
}
"""

def build_palette() -> QPalette:
    """Return a fixed light palette so dark system schemes never bleed through."""
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor(COLORS["canvas"]))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(COLORS["text"]))
    palette.setColor(QPalette.ColorRole.Base, QColor("#FFFFFF"))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor("#EFEEF6"))
    palette.setColor(QPalette.ColorRole.Text, QColor(COLORS["text"]))
    palette.setColor(QPalette.ColorRole.Button, QColor("#FFFFFF"))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor(COLORS["text"]))
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor("#FFFFFF"))
    palette.setColor(QPalette.ColorRole.ToolTipText, QColor(COLORS["text"]))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(COLORS["primary"]))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#FFFFFF"))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, QColor("#A6A3B8"))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, QColor("#A6A3B8"))
    return palette


def apply_palette(app: QApplication) -> None:
    """Install the fixed light palette on the application."""
    app.setPalette(build_palette())

