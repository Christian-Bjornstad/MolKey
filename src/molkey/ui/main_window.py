"""Polished application shell for the MolKey patient pseudonym registry."""

from __future__ import annotations

import csv
from collections.abc import Callable
from pathlib import Path

from PyQt6.QtCore import QSettings, Qt
from PyQt6.QtGui import QFont, QGuiApplication
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
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from molkey.application.patient_key_service import BatchResult, PatientKeyService
from molkey.config import ConfigError, RegistryConfig, _is_mapped_drive
from molkey.infrastructure.migrations import migrate
from molkey.infrastructure.repositories import PatientKeyRecord
from molkey.ui.theme import STYLESHEET


class MainWindow(QMainWindow):
    """Main navigation shell for stable patient pseudonym management."""

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
        self.key_service = PatientKeyService(database_path) if database_path is not None else None
        self.current_batch: BatchResult | None = None
        self.page_metadata = [
            ("Dashboard", "Generate or retrieve a permanent patient key"),
            ("Batch generation", "Paste or import patient IDs and create keys in one batch"),
            ("Lookup", "Find a mapping by patient ID or MolKey"),
            ("Key registry", "Review protected internal patient-to-key mappings"),
            ("Settings", "Configure the secure shared registry folder"),
        ]
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
        self.page_stack.addWidget(self._build_batch_page())
        self.page_stack.addWidget(self._build_lookup_page())
        self.page_stack.addWidget(self._build_registry_page())
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
        brand_row.addWidget(QLabel("MK", objectName="brandMark", alignment=Qt.AlignmentFlag.AlignCenter))
        brand_text = QVBoxLayout()
        brand_text.setSpacing(0)
        brand_text.addWidget(QLabel("MolKey", objectName="brandName"))
        brand_text.addWidget(QLabel("Patient Key Registry", objectName="brandSubtitle"))
        brand_row.addLayout(brand_text)
        layout.addLayout(brand_row)
        layout.addSpacing(28)
        for index, label in enumerate(["Dashboard", "Batch generation", "Lookup", "Key registry"]):
            layout.addWidget(self._navigation_button(label, index))
        layout.addItem(QSpacerItem(1, 1, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding))
        layout.addWidget(self._navigation_button("Settings", 4))
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
        button.clicked.connect(self._make_navigation_handler(index))
        self.navigation_buttons.append(button)
        return button

    def _make_navigation_handler(self, index: int) -> Callable[[], None]:
        def navigate() -> None:
            if index == 3:
                self._refresh_registry()
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
        self.page_title = QLabel("Dashboard", objectName="pageTitle")
        self.page_description = QLabel(self.page_metadata[0][1], objectName="pageDescription")
        titles.addWidget(self.page_title)
        titles.addWidget(self.page_description)
        layout.addLayout(titles)
        layout.addStretch()
        help_button = QPushButton("Help", objectName="helpButton")
        help_button.setProperty("secondary", True)
        help_button.clicked.connect(self._open_help_dialog)
        layout.addWidget(help_button)
        self.generate_key_button = QPushButton("Generate key", objectName="generateKeyButton")
        self.generate_key_button.setAccessibleName("Generate or retrieve a permanent patient key")
        self.generate_key_button.setEnabled(self.key_service is not None and self.registry_connected)
        self.generate_key_button.clicked.connect(self._open_generate_key_dialog)
        layout.addWidget(self.generate_key_button)
        return topbar

    def _build_dashboard(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(20)
        notice = QFrame(objectName="privacyNotice")
        notice_layout = QHBoxLayout(notice)
        notice_layout.addWidget(QLabel("i", objectName="privacyIcon"))
        self.privacy_notice = QLabel(
            "Patient identifiers stay inside the registry. External exports contain generated MolKeys only.",
            objectName="privacyText",
        )
        notice_layout.addWidget(self.privacy_notice, 1)
        layout.addWidget(notice)
        card = QFrame(objectName="contentCard")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(28, 28, 28, 28)
        card_layout.addWidget(QLabel("Permanent patient pseudonyms", objectName="pageTitle"))
        description = QLabel(
            "Enter one patient ID to generate a new MolKey or retrieve the permanent key already assigned. "
            "Use Batch generation for lists from the clipboard or CSV files.",
            objectName="settingsHelp",
        )
        description.setWordWrap(True)
        card_layout.addWidget(description)
        card_layout.addSpacing(12)
        action = QPushButton("Generate or retrieve key", objectName="dashboardGenerateButton")
        action.setEnabled(self.key_service is not None and self.registry_connected)
        action.clicked.connect(self._open_generate_key_dialog)
        card_layout.addWidget(action)
        card_layout.addStretch()
        layout.addWidget(card, 1)
        return page

    def _open_help_dialog(self) -> None:
        dialog = QDialog(self, objectName="helpDialog")
        dialog.setWindowTitle("MolKey help")
        dialog.setMinimumWidth(580)
        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel("Getting started with MolKey", objectName="pageTitle"))
        help_text = QLabel(
            "<b>1. Configure the registry</b><br>Choose the approved secure shared folder in Settings. "
            "The database is created automatically.<br><br>"
            "<b>2. Generate a key</b><br>Enter an internal patient ID. MolKey reuses the existing permanent "
            "key or generates one for a new patient.<br><br>"
            "<b>3. Process a batch</b><br>Paste patient IDs or import a CSV, review the results, then export "
            "a CSV or JSON containing MolKeys only.<br><br>"
            "<b>Privacy</b><br>The patient-to-key mapping remains exclusively in the protected registry.",
            objectName="helpText",
        )
        help_text.setWordWrap(True)
        help_text.setTextFormat(Qt.TextFormat.RichText)
        layout.addWidget(help_text)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        dialog.setModal(True)
        dialog.show()

    def _open_generate_key_dialog(self) -> None:
        if self.key_service is None:
            return
        dialog = QDialog(self, objectName="generateKeyDialog")
        dialog.setWindowTitle("Generate or retrieve key")
        dialog.setMinimumWidth(480)
        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel("Internal patient ID", objectName="fieldLabel"))
        patient_input = QLineEdit(objectName="patientIdInput")
        layout.addWidget(patient_input)
        feedback = QLabel("", objectName="muted")
        layout.addWidget(feedback)
        layout.addWidget(QLabel("MolKey", objectName="fieldLabel"))
        output = QLineEdit(objectName="generatedKeyOutput")
        output.setReadOnly(True)
        layout.addWidget(output)
        actions = QHBoxLayout()
        generate = QPushButton("Generate or retrieve", objectName="confirmGenerateButton")
        copy = QPushButton("Copy key", objectName="copyGeneratedKeyButton")
        copy.setEnabled(False)
        actions.addWidget(generate)
        actions.addWidget(copy)
        layout.addLayout(actions)
        close = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        close.rejected.connect(dialog.reject)
        layout.addWidget(close)

        def create() -> None:
            try:
                record = self.key_service.get_or_create(patient_input.text())
            except ValueError as exc:
                feedback.setText(str(exc))
                return
            output.setText(record.pseudonymous_key)
            feedback.setText("Permanent key ready. The mapping is stored in the secure registry.")
            copy.setEnabled(True)
            self._refresh_registry()

        generate.clicked.connect(create)
        copy.clicked.connect(lambda: QGuiApplication.clipboard().setText(output.text()))
        dialog.setModal(True)
        dialog.show()

    def _build_batch_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(32, 28, 32, 28)
        card = QFrame(objectName="contentCard")
        card_layout = QVBoxLayout(card)
        card_layout.addWidget(QLabel("Batch key generation", objectName="sectionTitle"))
        guidance = QLabel(
            "Paste one patient ID per line, or import the first column of a CSV. Existing patients keep their "
            "permanent key. Exports contain only MolKeys in the reviewed order.",
            objectName="settingsHelp",
        )
        guidance.setWordWrap(True)
        card_layout.addWidget(guidance)
        self.batch_input = QTextEdit(objectName="batchPatientIdsInput")
        self.batch_input.setPlaceholderText("PAT-001\nPAT-002\nPAT-003")
        card_layout.addWidget(self.batch_input)
        action_row = QHBoxLayout()
        import_button = QPushButton("Import CSV", objectName="importBatchButton")
        process_button = QPushButton("Process batch", objectName="processBatchButton")
        export_button = QPushButton("Export keys", objectName="exportBatchButton")
        export_button.setEnabled(False)
        import_button.clicked.connect(self._import_batch_csv)
        process_button.clicked.connect(self._process_batch)
        export_button.clicked.connect(self._export_batch)
        action_row.addWidget(import_button)
        action_row.addWidget(process_button)
        action_row.addStretch()
        action_row.addWidget(export_button)
        card_layout.addLayout(action_row)
        self.batch_summary = QLabel("No batch processed", objectName="batchSummary")
        card_layout.addWidget(self.batch_summary)
        self.batch_results = QTableWidget(0, 2, objectName="batchResultsTable")
        self.batch_results.setHorizontalHeaderLabels(["MolKey", "Result"])
        self.batch_results.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        card_layout.addWidget(self.batch_results)
        layout.addWidget(card)
        return page

    def _import_batch_csv(self) -> None:
        selected, _filter = QFileDialog.getOpenFileName(self, "Import patient IDs", "", "CSV files (*.csv)")
        if not selected:
            return
        values: list[str] = []
        with Path(selected).open(newline="", encoding="utf-8-sig") as handle:
            for row in csv.reader(handle):
                if row:
                    values.append(row[0])
        self.batch_input.setPlainText("\n".join(values))

    def _process_batch(self) -> None:
        if self.key_service is None:
            return
        patient_ids = self.batch_input.toPlainText().splitlines()
        self.current_batch = self.key_service.process_batch(patient_ids)
        self.batch_results.setRowCount(len(self.current_batch.items))
        for row, item in enumerate(self.current_batch.items):
            self.batch_results.setItem(row, 0, QTableWidgetItem(item.pseudonymous_key))
            self.batch_results.setItem(row, 1, QTableWidgetItem("Ready"))
        self.batch_summary.setText(
            f"{self.current_batch.created_count} new · {self.current_batch.reused_count} reused · "
            f"{self.current_batch.duplicate_count} duplicate · {self.current_batch.invalid_count} invalid"
        )
        self.findChild(QPushButton, "exportBatchButton").setEnabled(bool(self.current_batch.items))
        self._refresh_registry()

    def _export_batch(self) -> None:
        if self.key_service is None or self.current_batch is None:
            return
        selected, selected_filter = QFileDialog.getSaveFileName(
            self, "Export MolKeys only", "molkeys.csv", "CSV (*.csv);;JSON (*.json)"
        )
        if not selected:
            return
        destination = Path(selected)
        if not destination.suffix:
            destination = destination.with_suffix(".json" if "JSON" in selected_filter else ".csv")
        self.key_service.export_keys(self.current_batch.items, destination)
        self.batch_summary.setText(f"Keys-only export saved to {destination}")

    def _build_lookup_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(32, 28, 32, 28)
        card = QFrame(objectName="contentCard")
        card_layout = QVBoxLayout(card)
        card_layout.addWidget(QLabel("Find patient or MolKey", objectName="sectionTitle"))
        card_layout.addWidget(QLabel("Enter an internal patient ID or a generated MolKey.", objectName="settingsHelp"))
        self.lookup_input = QLineEdit(objectName="lookupInput")
        card_layout.addWidget(self.lookup_input)
        lookup_button = QPushButton("Lookup", objectName="lookupButton")
        lookup_button.clicked.connect(self._lookup)
        card_layout.addWidget(lookup_button)
        self.lookup_result = QLabel("", objectName="lookupResult")
        self.lookup_result.setWordWrap(True)
        card_layout.addWidget(self.lookup_result)
        card_layout.addStretch()
        layout.addWidget(card)
        return page

    def _lookup(self) -> None:
        if self.key_service is None:
            return
        value = self.lookup_input.text().strip()
        record = (
            self.key_service.lookup_by_key(value)
            if value.upper().startswith("MK-")
            else self.key_service.lookup_by_patient(value)
        )
        self.lookup_result.setText(
            f"Patient ID: {record.patient_id}    MolKey: {record.pseudonymous_key}"
            if record is not None
            else "No matching mapping found."
        )

    def _build_registry_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(32, 28, 32, 28)
        card = QFrame(objectName="contentCard")
        card_layout = QVBoxLayout(card)
        card_layout.addWidget(QLabel("Internal key registry", objectName="sectionTitle"))
        warning = QLabel(
            "Sensitive internal view: patient IDs shown here must never be copied into external exports.",
            objectName="settingsHelp",
        )
        warning.setWordWrap(True)
        card_layout.addWidget(warning)
        self.registry_table = QTableWidget(0, 3, objectName="keyRegistryTable")
        self.registry_table.setHorizontalHeaderLabels(["Patient ID", "MolKey", "Created"])
        self.registry_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        card_layout.addWidget(self.registry_table)
        layout.addWidget(card)
        self._refresh_registry()
        return page

    def _refresh_registry(self) -> None:
        if not hasattr(self, "registry_table"):
            return
        records = self.key_service.list_recent(500) if self.key_service is not None else []
        self.registry_table.setRowCount(len(records))
        for row, record in enumerate(records):
            for column, value in enumerate(
                (record.patient_id, record.pseudonymous_key, record.created_at.strftime("%Y-%m-%d %H:%M"))
            ):
                self.registry_table.setItem(row, column, QTableWidgetItem(value))

    def _build_settings_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(32, 28, 32, 28)
        card = QFrame(objectName="contentCard")
        card_layout = QVBoxLayout(card)
        card_layout.addWidget(QLabel("Shared registry", objectName="sectionTitle"))
        help_text = QLabel(
            "Choose the hospital's approved secure shared folder. MolKey stores the SQLite database, "
            "patient-to-key mappings, writer locks, and backups below this location.",
            objectName="settingsHelp",
        )
        help_text.setWordWrap(True)
        card_layout.addWidget(help_text)
        card_layout.addWidget(QLabel("Hospital registry folder", objectName="fieldLabel"))
        path_row = QHBoxLayout()
        self.registry_path_input = QLineEdit()
        self.registry_path_input.setAccessibleName("Hospital registry folder")
        self.registry_path_input.setPlaceholderText(r"\\server\secure-share\MolKey")
        self.registry_path_input.setText(self.registry_path if self.registry_path.startswith((r"\\", "//")) else "")
        path_row.addWidget(self.registry_path_input, 1)
        browse = QPushButton("Browse", objectName="browseRegistryButton")
        browse.setProperty("secondary", True)
        browse.clicked.connect(self._browse_registry_folder)
        path_row.addWidget(browse)
        card_layout.addLayout(path_row)
        hint = QLabel(
            "Production requires a UNC path beginning with \\\\ or //, or an active mapped network drive.",
            objectName="muted",
        )
        hint.setWordWrap(True)
        card_layout.addWidget(hint)
        action_row = QHBoxLayout()
        self.settings_feedback = QLabel("", objectName="muted")
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
            self._set_settings_feedback("Enter an approved UNC network path or mapped network drive.", error=True)
            return
        self.settings.setValue("registry/root", registry_path)
        self.settings.sync()
        self.registry_path = registry_path
        self.registry_path_label.setText(registry_path)
        try:
            config = RegistryConfig.from_root(registry_path)
            config.locks_dir.mkdir(parents=True, exist_ok=True)
            config.packages_dir.mkdir(parents=True, exist_ok=True)
            config.staging_dir.mkdir(parents=True, exist_ok=True)
            config.backups_dir.mkdir(parents=True, exist_ok=True)
            migrate(config.database_path)
        except (ConfigError, OSError, RuntimeError) as exc:
            self._set_settings_feedback(f"Folder saved, but MolKey could not connect: {exc}", error=True)
            return
        self.database_path = config.database_path
        self.key_service = PatientKeyService(config.database_path)
        self.registry_connected = True
        self.connection_status.setText("Registry connected")
        self.connection_status.setObjectName("statusGood")
        self.connection_status.style().unpolish(self.connection_status)
        self.connection_status.style().polish(self.connection_status)
        self.generate_key_button.setEnabled(True)
        self.findChild(QPushButton, "dashboardGenerateButton").setEnabled(True)
        self._set_settings_feedback("Registry connected and ready.", error=False)

    def _set_settings_feedback(self, text: str, *, error: bool) -> None:
        self.settings_feedback.setText(text)
        self.settings_feedback.setObjectName("statusError" if error else "statusGood")
        self.settings_feedback.style().unpolish(self.settings_feedback)
        self.settings_feedback.style().polish(self.settings_feedback)

    def _build_status_bar(self) -> QFrame:
        status = QFrame(objectName="statusBar")
        layout = QHBoxLayout(status)
        layout.setContentsMargins(32, 10, 32, 10)
        connected = self.registry_connected
        self.connection_status = QLabel(
            "Registry connected" if connected else "Registry not connected",
            objectName="statusGood" if connected else "muted",
        )
        layout.addWidget(self.connection_status)
        layout.addStretch()
        layout.addWidget(QLabel("Registry:", objectName="muted"))
        self.registry_path_label = QLabel(self.registry_path, objectName="statusPath")
        layout.addWidget(self.registry_path_label)
        return status


def _keys_only(records: list[PatientKeyRecord]) -> list[str]:
    """Return generated keys without exposing patient IDs."""
    return [record.pseudonymous_key for record in records]
