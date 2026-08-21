"""Polished application shell for MolKey."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from PyQt6.QtCore import QSettings, Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QSizePolicy,
    QSpacerItem,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from molvault.application.package_service import PackageService
from molvault.config import _is_mapped_drive
from molvault.ui.theme import STYLESHEET


class MainWindow(QMainWindow):
    """Main navigation shell and privacy-conscious dashboard."""

    def __init__(
        self,
        registry_path: str = "Not configured",
        *,
        registry_connected: bool = False,
        settings: QSettings | None = None,
        database_path: Path | None = None,
    ) -> None:
        super().__init__()
        self.settings = settings or QSettings()
        saved_registry_path = str(self.settings.value("registry/root", ""))
        self.registry_path = saved_registry_path or registry_path
        self.registry_connected = registry_connected
        self.database_path = database_path
        self.package_service = PackageService(database_path) if database_path is not None else None
        self.page_metadata = [
            ("Dashboard", "Secure package activity at a glance"),
            ("Packages", "Search, review, and export secure packages"),
            ("Cases", "Manage internal case and specimen links"),
            ("Key management", "Review protected key material and recovery readiness"),
            ("Settings", "Configure the secure shared registry folder"),
        ]
        self.metric_values = {"ready": "0", "processing": "0", "attention": "0"}
        self.navigation_buttons: list[QPushButton] = []
        self.setWindowTitle("MolKey")
        self.setFont(QFont("Arial", 10))
        self.setMinimumSize(1100, 700)
        self.resize(1360, 840)
        self.setStyleSheet(STYLESHEET)
        self._build_ui()

    def _build_ui(self) -> None:
        central = QWidget(objectName="centralWidget")
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._build_sidebar())

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)
        content_layout.addWidget(self._build_topbar())

        self.page_stack = QStackedWidget()
        self.page_stack.addWidget(self._build_dashboard())
        self.page_stack.addWidget(self._build_packages_page())
        self.page_stack.addWidget(self._build_cases_page())
        self.page_stack.addWidget(
            self._build_placeholder_page("Key management", "Review protected key material and recovery readiness.")
        )
        self.page_stack.addWidget(self._build_settings_page())
        content_layout.addWidget(self.page_stack, 1)
        content_layout.addWidget(self._build_status_bar())
        root.addWidget(content, 1)
        self.setCentralWidget(central)

    def _build_sidebar(self) -> QFrame:
        sidebar = QFrame(objectName="sidebar")
        sidebar.setFixedWidth(242)
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(20, 24, 20, 18)
        layout.setSpacing(8)

        brand_row = QHBoxLayout()
        mark = QLabel("MK", objectName="brandMark", alignment=Qt.AlignmentFlag.AlignCenter)
        brand_row.addWidget(mark)
        brand_text = QVBoxLayout()
        brand_text.setSpacing(0)
        brand_text.addWidget(QLabel("MolKey", objectName="brandName"))
        brand_text.addWidget(QLabel("Secure Package Registry", objectName="brandSubtitle"))
        brand_row.addLayout(brand_text)
        layout.addLayout(brand_row)
        layout.addSpacing(28)

        for index, label in enumerate(["Dashboard", "Packages", "Cases", "Key management"]):
            button = self._navigation_button(label, index)
            layout.addWidget(button)

        layout.addItem(QSpacerItem(1, 1, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding))
        settings_button = self._navigation_button("Settings", 4)
        layout.addWidget(settings_button)
        layout.addSpacing(14)
        badge = QLabel("SECURE WORKSPACE", objectName="environmentBadge")

        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(badge)
        layout.addSpacing(8)
        layout.addWidget(QLabel("MolKey 0.1.0", objectName="brandSubtitle"))
        return sidebar

    def _navigation_button(self, label: str, index: int) -> QPushButton:
        button = QPushButton(label)
        button.setProperty("nav", True)
        button.setProperty("active", index == 0)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.clicked.connect(self._make_navigation_handler(index))
        self.navigation_buttons.append(button)
        return button

    def _make_navigation_handler(self, index: int) -> Callable[[], None]:
        def navigate() -> None:
            if index == 1:
                self._refresh_packages()
            elif index == 2:
                self._refresh_cases()
            self.page_stack.setCurrentIndex(index)
            self.page_title.setText(self.page_metadata[index][0])
            self.page_description.setText(self.page_metadata[index][1])
            for item_index, button in enumerate(self.navigation_buttons):
                button.setProperty("active", item_index == index)
                button.style().unpolish(button)
                button.style().polish(button)

        return navigate

    def _build_topbar(self) -> QFrame:
        topbar = QFrame(objectName="topbar")
        layout = QHBoxLayout(topbar)
        layout.setContentsMargins(32, 18, 32, 18)
        titles = QVBoxLayout()
        titles.setSpacing(2)
        self.page_title = QLabel("Dashboard", objectName="pageTitle")
        self.page_description = QLabel("Secure package activity at a glance", objectName="pageDescription")
        titles.addWidget(self.page_title)
        titles.addWidget(self.page_description)
        layout.addLayout(titles)
        layout.addStretch()
        help_button = QPushButton("Help")
        help_button.setObjectName("secondaryButton")
        help_button.setEnabled(False)
        help_button.setToolTip("Help is not available in this prototype")
        layout.addWidget(help_button)
        self.create_package_button = QPushButton("Create package", objectName="createPackageButton")
        self.create_package_button.setAccessibleName("Create a secure package")
        self.create_package_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.create_package_button.setEnabled(self.package_service is not None and self.registry_connected)
        self.create_package_button.setToolTip("Create a pseudonymous package draft")
        self.create_package_button.clicked.connect(self._open_create_package_dialog)
        layout.addWidget(self.create_package_button)
        return topbar

    def _open_create_package_dialog(self) -> None:
        if self.package_service is None:
            return
        dialog = QDialog(self, objectName="createPackageDialog")
        dialog.setWindowTitle("Create package")
        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel("Patient ID", objectName="fieldLabel"))
        patient_id = QLineEdit(objectName="patientIdInput")
        layout.addWidget(patient_id)
        layout.addWidget(QLabel("DIT / case number", objectName="fieldLabel"))
        case_number = QLineEdit(objectName="ditInput")
        layout.addWidget(case_number)
        feedback = QLabel("", objectName="statusError")
        layout.addWidget(feedback)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        save = buttons.addButton("Save draft", QDialogButtonBox.ButtonRole.AcceptRole)
        save.setObjectName("saveDraftButton")
        buttons.rejected.connect(dialog.reject)

        def save_draft() -> None:
            try:
                self.package_service.create_draft(
                    patient_id=patient_id.text(), case_number=case_number.text()
                )
            except ValueError as exc:
                feedback.setText(str(exc))
                return
            dialog.accept()
            self._refresh_packages()
            self.page_stack.setCurrentIndex(1)
            self.page_title.setText("Packages")

        save.clicked.connect(save_draft)
        layout.addWidget(buttons)
        dialog.setModal(True)
        dialog.show()

    def _build_packages_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(32, 28, 32, 28)
        card = QFrame(objectName="contentCard")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(22, 20, 22, 22)
        card_layout.addWidget(QLabel("Secure packages", objectName="sectionTitle"))
        self.packages_table = QTableWidget(0, 4, objectName="packagesTable")
        self.packages_table.setHorizontalHeaderLabels(
            ["Package ID", "State", "Destination", "Created"]
        )
        self.packages_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.packages_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        card_layout.addWidget(self.packages_table)
        layout.addWidget(card)
        self._refresh_packages()
        return page

    def _refresh_packages(self) -> None:
        if not hasattr(self, "packages_table"):
            return
        packages = self.package_service.packages.list_recent() if self.package_service is not None else []
        self.packages_table.setRowCount(len(packages))
        for row, package in enumerate(packages):
            values = (
                package.package_id,
                package.state.value,
                package.destination or "Not set",
                package.created_at.astimezone().strftime("%Y-%m-%d %H:%M"),
            )
            for column, value in enumerate(values):
                self.packages_table.setItem(row, column, QTableWidgetItem(value))

    def _build_cases_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(32, 28, 32, 28)
        card = QFrame(objectName="contentCard")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(22, 20, 22, 22)
        card_layout.addWidget(QLabel("Internal case mappings", objectName="sectionTitle"))
        self.cases_table = QTableWidget(0, 4, objectName="casesTable")
        self.cases_table.setHorizontalHeaderLabels(
            ["Case ID", "Patient ID", "Specimen ID", "Created"]
        )
        self.cases_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.cases_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        card_layout.addWidget(self.cases_table)
        layout.addWidget(card)
        self._refresh_cases()
        return page

    def _refresh_cases(self) -> None:
        if not hasattr(self, "cases_table"):
            return
        cases = self.package_service.cases.list_recent() if self.package_service is not None else []
        self.cases_table.setRowCount(len(cases))
        for row, case in enumerate(cases):
            values = (
                case.case_id,
                case.patient_id,
                case.specimen_id,
                case.created_at.astimezone().strftime("%Y-%m-%d %H:%M"),
            )
            for column, value in enumerate(values):
                self.cases_table.setItem(row, column, QTableWidgetItem(value))

    def _build_dashboard(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(32, 28, 32, 26)
        layout.setSpacing(20)

        notice = QFrame(objectName="privacyNotice")
        notice_layout = QHBoxLayout(notice)
        notice_layout.setContentsMargins(16, 12, 16, 12)
        notice_layout.addWidget(QLabel("i", objectName="privacyIcon"))
        self.privacy_notice = QLabel(
            "Patient identifiers stay inside the registry. Exported package names contain only pseudonymous IDs.",
            objectName="privacyText",
        )
        self.privacy_notice.setWordWrap(True)
        notice_layout.addWidget(self.privacy_notice, 1)
        layout.addWidget(notice)

        metrics = QHBoxLayout()
        metrics.setSpacing(16)
        metrics.addWidget(
            self._metric_card("READY TO EXPORT", self.metric_values["ready"], "Verified packages", "#217A58")
        )
        metrics.addWidget(
            self._metric_card("IN PROCESS", self.metric_values["processing"], "Draft or encrypting", "#167D86")
        )
        metrics.addWidget(
            self._metric_card("NEEDS ATTENTION", self.metric_values["attention"], "Failed or interrupted", "#A35C00")
        )
        layout.addLayout(metrics)

        activity = QFrame(objectName="contentCard")
        activity_layout = QVBoxLayout(activity)
        activity_layout.setContentsMargins(22, 20, 22, 22)
        activity_layout.setSpacing(12)
        header = QHBoxLayout()
        header.addWidget(QLabel("Recent packages", objectName="sectionTitle"))
        header.addStretch()
        search = QLineEdit()
        search.setPlaceholderText("Search package ID…")
        search.setAccessibleName("Search packages")
        search.setFixedWidth(230)
        header.addWidget(search)
        activity_layout.addLayout(header)
        activity_layout.addSpacing(24)
        empty_symbol = QLabel("MV", objectName="privacyIcon", alignment=Qt.AlignmentFlag.AlignCenter)
        activity_layout.addWidget(empty_symbol)
        self.empty_state_title = QLabel(
            "No packages yet", objectName="emptyStateTitle", alignment=Qt.AlignmentFlag.AlignCenter
        )
        activity_layout.addWidget(self.empty_state_title)
        empty_detail = QLabel(
            "Create the first secure package to begin the protected transfer workflow.",
            objectName="muted",
            alignment=Qt.AlignmentFlag.AlignCenter,
        )
        activity_layout.addWidget(empty_detail)
        activity_layout.addStretch()
        layout.addWidget(activity, 1)
        return page

    @staticmethod
    def _metric_card(title: str, value: str, detail: str, accent: str) -> QFrame:
        card = QFrame(objectName="metricCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 17, 20, 17)
        title_label = QLabel(title, objectName="eyebrow")
        title_label.setStyleSheet(f"color: {accent};")
        layout.addWidget(title_label)
        layout.addWidget(QLabel(value, objectName="metricValue"))
        layout.addWidget(QLabel(detail, objectName="metricDetail"))
        return card

    @staticmethod
    def _build_placeholder_page(title: str, description: str) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(32, 32, 32, 32)
        card = QFrame(objectName="contentCard")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(28, 26, 28, 26)
        card_layout.addWidget(QLabel(title, objectName="pageTitle"))
        card_layout.addWidget(QLabel(description, objectName="pageDescription"))
        card_layout.addStretch()
        layout.addWidget(card)
        return page

    def _build_settings_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(18)

        card = QFrame(objectName="contentCard")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(26, 24, 26, 26)
        card_layout.setSpacing(12)
        card_layout.addWidget(QLabel("Shared registry", objectName="sectionTitle"))
        help_text = QLabel(
            "Choose the hospital's approved secure shared folder. MolVault stores the registry database, "
            "encrypted packages, locks, and backups below this location.",
            objectName="settingsHelp",
        )
        help_text.setWordWrap(True)
        card_layout.addWidget(help_text)
        card_layout.addSpacing(6)
        card_layout.addWidget(QLabel("Hospital registry folder", objectName="fieldLabel"))

        path_row = QHBoxLayout()
        self.registry_path_input = QLineEdit()
        self.registry_path_input.setAccessibleName("Hospital registry folder")
        self.registry_path_input.setPlaceholderText(r"\\server\secure-share\MolVault")
        self.registry_path_input.setText(self.registry_path if self.registry_path.startswith((r"\\", "//")) else "")
        path_row.addWidget(self.registry_path_input, 1)
        browse = QPushButton("Browse", objectName="browseRegistryButton")
        browse.setProperty("secondary", True)
        browse.clicked.connect(self._browse_registry_folder)
        path_row.addWidget(browse)
        card_layout.addLayout(path_row)

        hint = QLabel(
            "Production requires a UNC path beginning with \\\\ or //, or a mapped "
            "network drive (X:\\...). Do not select a personal or local folder.",
            objectName="muted",
        )
        hint.setWordWrap(True)
        card_layout.addWidget(hint)

        action_row = QHBoxLayout()
        self.settings_feedback = QLabel("", objectName="muted")
        self.settings_feedback.setWordWrap(True)
        action_row.addWidget(self.settings_feedback, 1)
        save = QPushButton("Save settings", objectName="saveRegistryButton")
        save.clicked.connect(self._save_registry_folder)
        action_row.addWidget(save)
        card_layout.addLayout(action_row)
        layout.addWidget(card)
        layout.addStretch()
        return page

    def _browse_registry_folder(self) -> None:
        selected = QFileDialog.getExistingDirectory(
            self, "Choose hospital registry folder", self.registry_path_input.text()
        )
        if selected:
            self.registry_path_input.setText(selected)

    def _save_registry_folder(self) -> None:
        registry_path = self.registry_path_input.text().strip()
        if not (registry_path.startswith((r"\\", "//")) or _is_mapped_drive(registry_path)):
            self._set_settings_feedback(
                "Enter an approved UNC network path or mapped network drive.", error=True
            )
            return
        self.settings.setValue("registry/root", registry_path)
        self.settings.sync()
        self.registry_path = registry_path
        self.registry_path_label.setText(registry_path)
        self._set_settings_feedback("Registry folder saved.", error=False)

    def _set_settings_feedback(self, text: str, *, error: bool) -> None:
        self.settings_feedback.setText(text)
        self.settings_feedback.setObjectName("statusError" if error else "statusGood")
        self.settings_feedback.style().unpolish(self.settings_feedback)
        self.settings_feedback.style().polish(self.settings_feedback)

    def _build_status_bar(self) -> QFrame:
        status = QFrame(objectName="statusBar")
        layout = QHBoxLayout(status)
        layout.setContentsMargins(32, 10, 32, 10)
        status_text = "Registry connected" if self.registry_connected else "Registry not connected"
        status_object = "statusGood" if self.registry_connected else "muted"
        self.connection_status = QLabel(status_text, objectName=status_object)
        layout.addWidget(self.connection_status)
        layout.addStretch()
        layout.addWidget(QLabel("Registry:", objectName="muted"))
        self.registry_path_label = QLabel(self.registry_path, objectName="statusPath")
        layout.addWidget(self.registry_path_label)
        return status
