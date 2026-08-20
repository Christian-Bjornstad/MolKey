"""MolVault visual design tokens and application stylesheet."""

COLORS = {
    "navy": "#102A43",
    "navy_hover": "#163D5C",
    "teal": "#167D86",
    "teal_hover": "#116A72",
    "canvas": "#F4F7FA",
    "surface": "#FFFFFF",
    "border": "#D9E2EC",
    "text": "#243B53",
    "muted": "#627D98",
    "success": "#217A58",
    "warning": "#A35C00",
    "danger": "#B42318",
}

STYLESHEET = """
* {
    font-family: "Arial", sans-serif;
    font-size: 14px;
    color: #243B53;
}
QMainWindow, QWidget#centralWidget { background: #F4F7FA; }
QFrame#sidebar { background: #102A43; border: none; }
QLabel#brandMark {
    background: #167D86; color: white; font-weight: 700; font-size: 18px;
    border-radius: 8px; min-width: 38px; max-width: 38px;
    min-height: 38px; max-height: 38px;
}
QLabel#brandName { color: white; font-size: 20px; font-weight: 700; }
QLabel#brandSubtitle { color: #BCCCDC; font-size: 12px; }
QPushButton[nav="true"] {
    background: transparent; color: #D9E2EC; border: none; border-radius: 7px;
    padding: 11px 14px; text-align: left; font-weight: 600;
}
QPushButton[nav="true"]:hover { background: #163D5C; color: white; }
QPushButton[nav="true"][active="true"] {
    background: #1F4D6B; color: white; border-left: 3px solid #40C4C8;
}
QLabel#environmentBadge {
    color: #B8F1E9; background: #163D5C; border: 1px solid #286983;
    border-radius: 11px; padding: 4px 9px; font-size: 11px; font-weight: 700;
}
QFrame#topbar { background: white; border-bottom: 1px solid #D9E2EC; }
QLabel#pageTitle { font-size: 24px; font-weight: 700; color: #102A43; }
QLabel#pageDescription { color: #627D98; }
QPushButton#primaryButton, QPushButton#createPackageButton {
    background: #167D86; color: white; border: none; border-radius: 7px;
    padding: 10px 18px; font-weight: 700;
}
QPushButton#primaryButton:hover, QPushButton#createPackageButton:hover { background: #116A72; }
QPushButton#secondaryButton {
    background: white; color: #243B53; border: 1px solid #BCCCDC;
    border-radius: 7px; padding: 9px 15px; font-weight: 600;
}
QPushButton#secondaryButton:hover { background: #EDF2F7; border-color: #829AB1; }
QFrame.card, QFrame#metricCard, QFrame#contentCard, QFrame#privacyNotice {
    background: white; border: 1px solid #D9E2EC; border-radius: 10px;
}
QLabel#eyebrow { color: #627D98; font-size: 12px; font-weight: 700; }
QLabel#metricValue { color: #102A43; font-size: 30px; font-weight: 700; }
QLabel#metricDetail { color: #627D98; font-size: 12px; }
QLabel#sectionTitle { color: #102A43; font-size: 17px; font-weight: 700; }
QLabel#emptyStateTitle { color: #243B53; font-size: 16px; font-weight: 700; }
QLabel#muted { color: #627D98; }
QFrame#privacyNotice { background: #F0F8F8; border-color: #B8DDDF; }
QLabel#privacyIcon { color: #167D86; font-size: 17px; font-weight: 700; }
QLabel#privacyText { color: #315A60; }
QFrame#statusBar { background: white; border-top: 1px solid #D9E2EC; }
QLabel#statusGood { color: #217A58; font-weight: 700; }
QLabel#statusPath { color: #627D98; font-family: "Cascadia Mono", "Consolas", monospace; }
QLineEdit {
    background: white; border: 1px solid #BCCCDC; border-radius: 7px;
    padding: 9px 12px; selection-background-color: #167D86;
}
QLineEdit:focus { border: 2px solid #167D86; }
QTableWidget { background: white; border: 1px solid #D9E2EC; border-radius: 8px; gridline-color: #E8EEF3; }
QHeaderView::section {
    background: #EDF2F7; padding: 9px; border: none;
    border-bottom: 1px solid #D9E2EC; font-weight: 700;
}
"""
