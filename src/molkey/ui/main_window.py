"""Polished application shell for the MolKey patient pseudonym registry."""

from __future__ import annotations

import csv
from collections.abc import Callable
from pathlib import Path

from PyQt6.QtCore import QSettings, Qt, QTimer
from PyQt6.QtGui import QFont, QGuiApplication, QIcon, QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
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
        # When settings is None, QSettings picks up the org/app names that
        # __main__ sets on QApplication before constructing this window.
        self.settings = settings if settings is not None else QSettings()
        saved_registry_path = str(self.settings.value("registry/root", ""))
        self.registry_path = saved_registry_path or registry_path
        self.registry_connected = registry_connected
        self.database_path = database_path
        self.key_service = PatientKeyService(database_path) if database_path is not None else None
        self.current_batch: BatchResult | None = None
        self.operator_initials = str(self.settings.value("operator/initials", "")).strip().upper()
        self.page_metadata = [
            ("Dashboard", "Generate or retrieve a permanent patient key"),
            ("Batch generation", "Paste or import patient IDs and create keys in one batch"),
            ("Lookup", "Find a mapping by patient ID or MolKey"),
            ("Key registry", "Review protected internal patient-to-key mappings"),
            ("Settings", "Configure the secure shared registry folder"),
        ]
        self.navigation_buttons: list[QPushButton] = []
        self.setWindowTitle("MolKey")
        self._set_brand_icon()
        self.setFont(QFont("Arial", 10))
        self.setMinimumSize(1100, 700)
        self.resize(1360, 840)
        self.setStyleSheet(STYLESHEET)
        self._last_lookup_record: PatientKeyRecord | None = None
        self._build_ui()
        self._install_copy_shortcuts()

    def _install_copy_shortcuts(self) -> None:
        """Ctrl+C copies the selected rows' keys from registry or batch tables."""
        registry_copy = QShortcut(QKeySequence.StandardKey.Copy, self.registry_table)
        registry_copy.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        registry_copy.activated.connect(self._copy_registry_keys)
        batch_copy = QShortcut(QKeySequence.StandardKey.Copy, self.batch_results)
        batch_copy.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        batch_copy.activated.connect(self._copy_batch_keys)

    def _set_brand_icon(self) -> None:
        """Apply the MolKey brand icon (Designer master) from repo assets."""
        asset = Path(__file__).resolve().parents[3] / "assets" / "molkey_icon_256.png"
        if asset.is_file():
            self.setWindowIcon(QIcon(str(asset)))

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
        card_layout.addWidget(QLabel("Your initials", objectName="fieldLabel"))
        self.operator_initials_input = QLineEdit(objectName="operatorInitialsInput")
        self.operator_initials_input.setAccessibleName("Operator initials")
        self.operator_initials_input.setPlaceholderText("e.g. CFB")
        self.operator_initials_input.setMaxLength(4)
        self.operator_initials_input.setText(self.operator_initials)
        self.operator_initials_input.textChanged.connect(self._remember_initials)
        card_layout.addWidget(self.operator_initials_input)
        initials_help = QLabel(
            "Stored on this workstation and stamped onto every key you create, so colleagues can see who "
            "generated each key in the registry.",
            objectName="muted",
        )
        initials_help.setWordWrap(True)
        card_layout.addWidget(initials_help)
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

    def _remember_initials(self, text: str) -> None:
        self.operator_initials = text.strip().upper()
        self.settings.setValue("operator/initials", self.operator_initials)
        sender = self.sender()
        if isinstance(sender, QLineEdit) and sender.text() != self.operator_initials:
            sender.setText(self.operator_initials)

    def _open_generate_key_dialog(self) -> None:
        if self.key_service is None:
            return
        dialog = QDialog(self, objectName="generateKeyDialog")
        dialog.setWindowTitle("Generate or retrieve key")
        dialog.setMinimumWidth(480)
        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel("Your initials", objectName="fieldLabel"))
        initials_input = QLineEdit(objectName="dialogInitialsInput")
        initials_input.setMaxLength(4)
        initials_input.setPlaceholderText("e.g. CFB")
        initials_input.setText(self.operator_initials)
        layout.addWidget(initials_input)
        layout.addWidget(QLabel("Internal patient ID", objectName="fieldLabel"))
        patient_input = QLineEdit(objectName="patientIdInput")
        layout.addWidget(patient_input)
        feedback = QLabel("", objectName="generateFeedback")
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
                record = self.key_service.get_or_create(patient_input.text(), initials_input.text())
            except ValueError as exc:
                feedback.setText(str(exc))
                return
            self._remember_initials(initials_input.text())
            output.setText(record.pseudonymous_key)
            feedback.setText(
                f"Permanent key ready — created by {record.created_by}. The mapping is stored in the shared registry."
            )
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
        if not self.operator_initials:
            self.batch_summary.setText("Enter your initials on the Dashboard before generating keys.")
            return
        patient_ids = self.batch_input.toPlainText().splitlines()
        try:
            self.current_batch = self.key_service.process_batch(patient_ids, self.operator_initials)
        except ValueError as exc:
            self.batch_summary.setText(str(exc))
            return
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
        self.lookup_result.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        card_layout.addWidget(self.lookup_result)
        lookup_copy_row = QHBoxLayout()
        self.copy_lookup_key_button = QPushButton("Copy MolKey", objectName="copyLookupKeyButton")
        self.copy_lookup_key_button.setProperty("secondary", True)
        self.copy_lookup_key_button.setEnabled(False)
        self.copy_lookup_patient_button = QPushButton("Copy patient ID", objectName="copyLookupPatientButton")
        self.copy_lookup_patient_button.setProperty("secondary", True)
        self.copy_lookup_patient_button.setEnabled(False)
        lookup_copy_row.addWidget(self.copy_lookup_key_button)
        lookup_copy_row.addWidget(self.copy_lookup_patient_button)
        lookup_copy_row.addStretch()
        card_layout.addLayout(lookup_copy_row)
        self.copy_lookup_key_button.clicked.connect(
            lambda: QGuiApplication.clipboard().setText(self._last_lookup_record.pseudonymous_key)
            if self._last_lookup_record is not None
            else None
        )
        self.copy_lookup_patient_button.clicked.connect(
            lambda: QGuiApplication.clipboard().setText(self._last_lookup_record.patient_id)
            if self._last_lookup_record is not None
            else None
        )
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
        self._last_lookup_record = record
        has_match = record is not None
        self.copy_lookup_key_button.setEnabled(has_match)
        self.copy_lookup_patient_button.setEnabled(has_match)
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
        controls = QHBoxLayout()
        self.registry_search_input = QLineEdit(objectName="registrySearchInput")
        self.registry_search_input.setAccessibleName("Search the key registry")
        self.registry_search_input.setPlaceholderText("Search patient ID, MolKey, or initials…")
        self.registry_search_input.textChanged.connect(self._refresh_registry)
        controls.addWidget(self.registry_search_input, 1)
        refresh_button = QPushButton("Refresh", objectName="refreshRegistryButton")
        refresh_button.setProperty("secondary", True)
        refresh_button.clicked.connect(self._refresh_registry)
        controls.addWidget(refresh_button)
        card_layout.addLayout(controls)
        self.registry_count_label = QLabel("", objectName="registryCountLabel")
        card_layout.addWidget(self.registry_count_label)
        self.registry_table = QTableWidget(0, 4, objectName="keyRegistryTable")
        self.registry_table.setHorizontalHeaderLabels(["Patient ID", "MolKey", "Created", "By"])
        self.registry_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.registry_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.registry_table.setSelectionMode(QTableWidget.SelectionMode.ExtendedSelection)
        self.registry_table.doubleClicked.connect(self._open_registry_detail)
        self.registry_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.registry_table.customContextMenuRequested.connect(self._show_registry_context_menu)
        card_layout.addWidget(self.registry_table)
        layout.addWidget(card)
        self._refresh_registry()
        return page

    def _refresh_registry(self, *_args: object) -> None:
        """Reload every mapping from the shared database and apply the search filter."""
        if not hasattr(self, "registry_table"):
            return
        records = self.key_service.list_recent(500) if self.key_service is not None else []
        query = self.registry_search_input.text().strip().upper() if hasattr(self, "registry_search_input") else ""
        visible = [
            record
            for record in records
            if not query
            or query in record.patient_id.upper()
            or query in record.pseudonymous_key
            or query in record.created_by.upper()
        ]
        self.registry_table.setRowCount(len(visible))
        for row, record in enumerate(visible):
            for column, value in enumerate(
                (
                    record.patient_id,
                    record.pseudonymous_key,
                    record.created_at.strftime("%Y-%m-%d %H:%M"),
                    record.created_by,
                )
            ):
                self.registry_table.setItem(row, column, QTableWidgetItem(value))
        summary = f"Showing {len(visible)} of {len(records)} keys"
        if query:
            summary += f' matching "{query}"'
        self.registry_count_label.setText(summary)

    def _registry_record_for_row(self, row: int) -> PatientKeyRecord | None:
        """Map a table row back to its PatientKeyRecord (rows mirror list order)."""
        if self.key_service is None or not (0 <= row < self.registry_table.rowCount()):
            return None
        patient_id = self.registry_table.item(row, 0).text()
        key = self.registry_table.item(row, 1).text()
        return self.key_service.lookup_by_patient(patient_id) if key else None

    def _open_registry_detail(self, index: object) -> None:
        row = int(index.row()) if hasattr(index, "row") and not isinstance(index, int) else index
        record = self._registry_record_for_row(int(row))
        if record is None:
            return
        dialog = QDialog(self, objectName="registryDetailDialog")
        dialog.setWindowTitle("Registry entry")
        dialog.setMinimumWidth(460)
        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel("MolKey", objectName="fieldLabel"))

        key_row = QHBoxLayout()
        key_value = QLabel(record.pseudonymous_key, objectName="detailKeyValue")
        key_value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        key_row.addWidget(key_value, 1)
        key_row.addWidget(self._make_copy_button(record.pseudonymous_key, "copyDetailKeyButton"))
        layout.addLayout(key_row)

        layout.addWidget(QLabel("Patient ID (DIT number)", objectName="fieldLabel"))
        patient_row = QHBoxLayout()
        patient_value = QLabel(record.patient_id, objectName="detailPatientValue")
        patient_value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        patient_row.addWidget(patient_value, 1)
        patient_row.addWidget(self._make_copy_button(record.patient_id, "copyDetailPatientButton"))
        layout.addLayout(patient_row)

        meta = QLabel(
            f"Created {record.created_at.strftime('%Y-%m-%d %H:%M')}    By {record.created_by}",
            objectName="settingsHelp",
        )
        layout.addWidget(meta)
        close = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        close.rejected.connect(dialog.reject)
        layout.addWidget(close)
        dialog.setModal(True)
        dialog.show()

    def _make_copy_button(self, text: str, object_name: str) -> QPushButton:
        button = QPushButton("Copy", objectName=object_name)
        button.setProperty("secondary", True)

        def copy_with_feedback() -> None:
            QGuiApplication.clipboard().setText(text)
            button.setText("Copied ✓")
            QTimer.singleShot(1500, lambda: button.setText("Copy"))

        button.clicked.connect(copy_with_feedback)
        result: QPushButton = button
        return result

    def _selected_rows(self, table: QTableWidget) -> list[int]:
        return sorted({index.row() for index in table.selectionModel().selectedIndexes()})

    def _copy_registry_keys(self) -> None:
        rows = self._selected_rows(self.registry_table)
        keys = [self.registry_table.item(row, 1).text() for row in rows]
        if keys:
            QGuiApplication.clipboard().setText("\n".join(keys))

    def _copy_registry_patients(self) -> None:
        rows = self._selected_rows(self.registry_table)
        patients = [self.registry_table.item(row, 0).text() for row in rows]
        if patients:
            QGuiApplication.clipboard().setText("\n".join(patients))

    def _copy_selected_rows(self) -> None:
        self._copy_registry_keys()

    def _show_registry_context_menu(self, position: object) -> None:
        menu = QMenu(self.registry_table)
        menu.addAction("Copy MolKey", self._copy_registry_keys)
        menu.addAction("Copy patient ID", self._copy_registry_patients)
        menu.addAction(
            "Copy entire row",
            lambda: QGuiApplication.clipboard().setText("\t".join(
                self.registry_table.item(row, column).text()
                for row in self._selected_rows(self.registry_table)
                for column in range(self.registry_table.columnCount())
            )),
        )
        menu.exec(self.registry_table.viewport().mapToGlobal(position))

    def _copy_batch_keys(self) -> None:
        rows = self._selected_rows(self.batch_results)
        keys = [self.batch_results.item(row, 0).text() for row in rows if self.batch_results.item(row, 0)]
        if keys:
            QGuiApplication.clipboard().setText("\n".join(keys))

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
