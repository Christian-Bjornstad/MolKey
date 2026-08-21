"""MolKey visual design tokens and application stylesheet."""

COLORS = {
    "primary": "#847CBA",
    "primary_hover": "#A69ED6",
    "primary_dark": "#6B63A1",
    "primary_darker": "#4A4380",
    "sidebar_bg": "#3D356B",
    "sidebar_hover": "#4A4380",
    "sidebar_active": "#554DA8",
    "canvas": "#F5F3FA",
    "surface": "#FFFFFF",
    "border": "#D9D2EC",
    "text": "#3A346B",
    "muted": "#8A84B5",
    "success": "#4CAF7C",
    "warning": "#D4A843",
    "danger": "#D34A4A",
}

STYLESHEET = """
* {
    font-family: "Arial", sans-serif;
    font-size: 14px;
    color: #3A346B;
}
QMainWindow, QWidget#centralWidget { background: #F5F3FA; }
QFrame#sidebar { background: #3D356B; border: none; }
QLabel#brandMark {
    background: #847CBA; color: white; font-weight: 700; font-size: 18px;
    border-radius: 8px; min-width: 38px; max-width: 38px;
    min-height: 38px; max-height: 38px;
}
QLabel#brandName { color: white; font-size: 20px; font-weight: 700; }
QLabel#brandSubtitle { color: #C9C5E8; font-size: 12px; }
QPushButton[nav="true"] {
    background: transparent; color: #D9D2EC; border: none; border-radius: 7px;
    padding: 11px 14px; text-align: left; font-weight: 600;
}
QPushButton[nav="true"]:hover { background: #4A4380; color: white; }
QPushButton[nav="true"][active="true"] {
    background: #554DA8; color: white; border-left: 3px solid #A69ED6;
}
QLabel#environmentBadge {
    color: #E8E4FA; background: #4A4380; border: 1px solid #6B63A1;
    border-radius: 11px; padding: 4px 9px; font-size: 11px; font-weight: 700;
}
QFrame#topbar { background: white; border-bottom: 1px solid #D9D2EC; }
QLabel#pageTitle { font-size: 24px; font-weight: 700; color: #3D356B; }
QLabel#pageDescription { color: #8A84B5; }
QPushButton#primaryButton, QPushButton#createPackageButton {
    background: #847CBA; color: white; border: none; border-radius: 7px;
    padding: 10px 18px; font-weight: 700;
}
QPushButton#primaryButton:hover, QPushButton#createPackageButton:hover { background: #6B63A1; }
QPushButton#secondaryButton {
    background: white; color: #3A346B; border: 1px solid #C9C5E8;
    border-radius: 7px; padding: 9px 15px; font-weight: 600;
}
QPushButton#secondaryButton:hover { background: #EEEAF6; border-color: #A69ED6; }
QFrame.card, QFrame#metricCard, QFrame#contentCard, QFrame#privacyNotice {
    background: white; border: 1px solid #D9D2EC; border-radius: 10px;
}
QLabel#eyebrow { color: #8A84B5; font-size: 12px; font-weight: 700; }
QLabel#metricValue { color: #3D356B; font-size: 30px; font-weight: 700; }
QLabel#metricDetail { color: #8A84B5; font-size: 12px; }
QLabel#sectionTitle { color: #3D356B; font-size: 17px; font-weight: 700; }
QLabel#emptyStateTitle { color: #3A346B; font-size: 16px; font-weight: 700; }
QLabel#muted { color: #8A84B5; }
QFrame#privacyNotice { background: #EEEAF6; border-color: #C9C5E8; }
QLabel#privacyIcon { color: #847CBA; font-size: 17px; font-weight: 700; }
QLabel#privacyText { color: #5A548A; }
QFrame#statusBar { background: white; border-top: 1px solid #D9D2EC; }
QLabel#statusGood { color: #4CAF7C; font-weight: 700; }
QLabel#statusError { color: #D34A4A; font-weight: 700; }
QLabel#fieldLabel { color: #3A346B; font-weight: 700; }
QLabel#settingsHelp { color: #6A6491; line-height: 1.4; }
QLabel#statusPath { color: #8A84B5; font-family: "Cascadia Mono", "Consolas", monospace; }
QLineEdit {
    background: white; border: 1px solid #C9C5E8; border-radius: 7px;
    padding: 9px 12px; selection-background-color: #847CBA;
}
QLineEdit:focus { border: 2px solid #847CBA; }
QTableWidget { background: white; border: 1px solid #D9D2EC; border-radius: 8px; gridline-color: #E8E4FA; }
QHeaderView::section {
    background: #EEEAF6; padding: 9px; border: none;
    border-bottom: 1px solid #D9D2EC; font-weight: 700;
}
"""
