from __future__ import annotations

from typing import Callable, Optional

from PyQt6.QtCore import Qt, QThread, QTimer, pyqtSignal
from PyQt6.QtGui import QShowEvent
from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from services.settings_import_service import (
    CopyResult,
    IMPORT_ITEMS,
    ItemAvailability,
    TranslatorLayout,
    collect_copy_jobs,
    current_dest_layout,
    execute_copy_jobs,
    inspect_item_availability,
    inspect_translator_folder,
    is_same_install,
)
from ui.styles import secondary_editor_dialog_stylesheet as _dialog_stylesheet
from ui.theme import apply_widget_stylesheet
from ui.secondary_pages.themed_message_box import themed_question, themed_warning
from ui.secondary_pages.themed_progress_dialog import create_progress_dialog
from utils.resource_helper import apply_app_icon_to_window


class _CopyWorker(QThread):
    progress = pyqtSignal(int, int, str)
    finished_ok = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(self, source, dest, item_ids: list[str], parent=None):
        super().__init__(parent)
        self._source = source
        self._dest = dest
        self._item_ids = item_ids

    def run(self) -> None:
        try:
            self.progress.emit(0, 0, "")
            jobs = collect_copy_jobs(self._source, self._dest, self._item_ids)
            if self.isInterruptionRequested():
                result = CopyResult(cancelled=True)
                self.finished_ok.emit(result)
                return
            if not jobs:
                self.finished_ok.emit(CopyResult())
                return
            result = execute_copy_jobs(
                jobs,
                progress=self.progress.emit,
                should_cancel=self.isInterruptionRequested,
            )
            self.finished_ok.emit(result)
        except Exception as exc:
            self.failed.emit(str(exc))


class SettingsImportDialog(QDialog):
    def __init__(
        self,
        parent=None,
        *,
        t_func: Callable[..., str],
        config_service,
    ):
        super().__init__(parent)
        self._t = t_func
        self._config_service = config_service
        self._dest = current_dest_layout(config_service)
        self._source: Optional[TranslatorLayout] = None
        self._availability: list[ItemAvailability] = []
        self._checkboxes: dict[str, QCheckBox] = {}
        self._copy_result: Optional[CopyResult] = None
        self._worker: Optional[_CopyWorker] = None
        self._progress = None

        self.setWindowTitle(self._t("Import Config"))
        self.setModal(True)
        self.setMinimumWidth(520)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setWindowFlag(Qt.WindowType.WindowContextHelpButtonHint, False)
        apply_widget_stylesheet(self, _dialog_stylesheet(include_tables=False))
        self._build_ui()
        self._validate_path()

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        apply_app_icon_to_window(self)

    def imported_result(self) -> Optional[CopyResult]:
        return self._copy_result

    def source_path(self) -> str:
        return self.path_edit.text().strip()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 14)
        root.setSpacing(10)

        title = QLabel(self._t("Import Config"))
        title.setObjectName("dialog_title")
        root.addWidget(title)

        subtitle = QLabel(self._t("import_settings_description"))
        subtitle.setObjectName("dialog_subtitle")
        subtitle.setWordWrap(True)
        root.addWidget(subtitle)

        divider = QFrame()
        divider.setObjectName("divider")
        divider.setFrameShape(QFrame.Shape.HLine)
        root.addWidget(divider)

        path_card = QWidget()
        path_card.setObjectName("dialog_card")
        path_layout = QVBoxLayout(path_card)
        path_layout.setContentsMargins(14, 14, 14, 14)
        path_layout.setSpacing(8)

        path_label = QLabel(self._t("import_settings_folder_label"))
        path_label.setObjectName("dialog_prompt")
        path_label.setWordWrap(True)
        path_layout.addWidget(path_label)

        path_row = QHBoxLayout()
        path_row.setContentsMargins(0, 0, 0, 0)
        path_row.setSpacing(8)
        self.path_edit = QLineEdit()
        self.path_edit.setPlaceholderText(self._t("import_settings_folder_placeholder"))
        self.path_edit.textChanged.connect(self._on_path_edited)
        browse_button = QPushButton(self._t("Browse..."))
        browse_button.clicked.connect(self._browse_folder)
        path_row.addWidget(self.path_edit, 1)
        path_row.addWidget(browse_button)
        path_layout.addLayout(path_row)
        root.addWidget(path_card)

        items_label = QLabel(self._t("import_settings_items_label"))
        items_label.setObjectName("section_label")
        root.addWidget(items_label)

        items_card = QWidget()
        items_card.setObjectName("dialog_card")
        items_layout = QVBoxLayout(items_card)
        items_layout.setContentsMargins(14, 10, 14, 10)
        items_layout.setSpacing(6)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setMinimumHeight(220)

        items_host = QWidget()
        items_host.setObjectName("section_content")
        host_layout = QVBoxLayout(items_host)
        host_layout.setContentsMargins(0, 0, 0, 0)
        host_layout.setSpacing(4)

        for item in IMPORT_ITEMS:
            checkbox = QCheckBox(self._t(item.label_key))
            checkbox.setChecked(True)
            checkbox.setToolTip(self._t(item.hint_key))
            self._checkboxes[item.id] = checkbox
            host_layout.addWidget(checkbox)

        host_layout.addStretch(1)
        scroll.setWidget(items_host)
        items_layout.addWidget(scroll)
        root.addWidget(items_card, 1)

        self.status_label = QLabel("")
        self.status_label.setObjectName("hint_label")
        self.status_label.setWordWrap(True)
        root.addWidget(self.status_label)

        button_row = QHBoxLayout()
        button_row.setContentsMargins(0, 0, 0, 0)
        button_row.setSpacing(8)
        button_row.addStretch(1)

        cancel_button = QPushButton(self._t("Cancel"))
        cancel_button.clicked.connect(self.reject)
        button_row.addWidget(cancel_button)

        self.import_button = QPushButton(self._t("import_settings_dialog_title"))
        self.import_button.setProperty("variant", "accent")
        self.import_button.setDefault(True)
        self.import_button.clicked.connect(self._on_import_clicked)
        button_row.addWidget(self.import_button)
        root.addLayout(button_row)

        self._path_validate_timer = QTimer(self)
        self._path_validate_timer.setSingleShot(True)
        self._path_validate_timer.setInterval(250)
        self._path_validate_timer.timeout.connect(self._validate_path)

    def _on_path_edited(self, _text: str) -> None:
        self._path_validate_timer.start()

    def _browse_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self,
            self._t("Select Folder"),
            self.path_edit.text().strip() or "",
        )
        if folder:
            self.path_edit.setText(folder)

    def _set_status(self, text: str, *, error: bool = False) -> None:
        self.status_label.setText(text)
        self.status_label.setProperty("statusState", "error" if error else "default")
        self.status_label.setObjectName("status_label" if text else "hint_label")
        style = self.status_label.style()
        style.unpolish(self.status_label)
        style.polish(self.status_label)

    def _selected_item_ids(self) -> list[str]:
        available = {entry.item.id for entry in self._availability if entry.available}
        return [
            item_id
            for item_id, checkbox in self._checkboxes.items()
            if checkbox.isChecked() and (not available or item_id in available)
        ]

    def _validate_path(self) -> None:
        raw = self.path_edit.text().strip().strip('"').strip("'")
        self._source = None
        self._availability = []

        if not raw:
            self._reset_item_checkboxes()
            self.import_button.setEnabled(False)
            self._set_status(self._t("import_settings_choose_folder"))
            return

        layout = inspect_translator_folder(raw)
        if layout is None:
            self._reset_item_checkboxes()
            self.import_button.setEnabled(False)
            self._set_status(self._t("import_settings_not_translator"), error=True)
            return

        if is_same_install(layout, self._dest):
            self._reset_item_checkboxes()
            self.import_button.setEnabled(False)
            self._set_status(self._t("import_settings_same_folder"), error=True)
            return

        self._source = layout
        self._availability = inspect_item_availability(layout)
        found = 0
        for entry in self._availability:
            checkbox = self._checkboxes[entry.item.id]
            checkbox.blockSignals(True)
            if entry.available:
                checkbox.setEnabled(True)
                checkbox.setChecked(True)
                checkbox.setText(self._t(entry.item.label_key))
                found += 1
            else:
                checkbox.setChecked(False)
                checkbox.setEnabled(False)
                checkbox.setText(
                    f"{self._t(entry.item.label_key)} {self._t('import_settings_item_missing')}"
                )
            checkbox.blockSignals(False)

        if found == 0:
            self.import_button.setEnabled(False)
            self._set_status(self._t("import_settings_no_items"), error=True)
            return

        self.import_button.setEnabled(True)
        self._set_status(self._t("import_settings_ready", count=found))

    def _reset_item_checkboxes(self) -> None:
        for item in IMPORT_ITEMS:
            checkbox = self._checkboxes[item.id]
            checkbox.blockSignals(True)
            checkbox.setEnabled(True)
            checkbox.setChecked(True)
            checkbox.setText(self._t(item.label_key))
            checkbox.blockSignals(False)

    def _on_import_clicked(self) -> None:
        if self._source is None:
            self._validate_path()
            if self._source is None:
                return

        item_ids = self._selected_item_ids()
        if not item_ids:
            themed_warning(
                self,
                self._t("Import Config"),
                self._t("import_settings_select_items"),
            )
            return

        confirm_text = self._t("import_settings_overwrite_confirm")
        if any(item_id == "models" for item_id in item_ids):
            confirm_text = f"{confirm_text}\n\n{self._t('import_settings_models_warning')}"

        answer = themed_question(
            self,
            self._t("Import Config"),
            confirm_text,
            QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if answer != QMessageBox.StandardButton.Ok:
            return

        self._start_copy(item_ids)

    def _start_copy(self, item_ids: list[str]) -> None:
        if self._source is None:
            return
        self.import_button.setEnabled(False)
        progress = create_progress_dialog(
            self,
            self._t("Import Config"),
            self._t("import_settings_copying"),
            self._t("Cancel"),
        )
        progress.setMinimum(0)
        progress.setMaximum(0)
        progress.setValue(0)
        self._progress = progress

        worker = _CopyWorker(self._source, self._dest, item_ids, self)
        self._worker = worker
        worker.progress.connect(self._on_copy_progress)
        worker.finished_ok.connect(self._on_copy_finished)
        worker.failed.connect(self._on_copy_failed)
        progress.canceled.connect(worker.requestInterruption)
        worker.start()
        progress.exec()

    def _on_copy_progress(self, current: int, total: int, name: str) -> None:
        if self._progress is None:
            return
        if total <= 0:
            self._progress.setMaximum(0)
        else:
            self._progress.setMaximum(total)
            self._progress.setValue(current)
        if name:
            self._progress.setLabelText(
                self._t("import_settings_copying_file", name=name)
            )

    def _close_progress(self) -> None:
        if self._progress is not None:
            self._progress.close()
            self._progress = None

    def _on_copy_finished(self, result: object) -> None:
        self._close_progress()
        self.import_button.setEnabled(True)
        if not isinstance(result, CopyResult):
            return
        self._copy_result = result
        if result.cancelled:
            themed_warning(
                self,
                self._t("Import Config"),
                self._t("import_settings_cancelled"),
            )
            return
        if result.copied <= 0 and result.errors:
            themed_warning(
                self,
                self._t("Import Failed"),
                self._t(
                    "import_settings_copy_failed",
                    error="\n".join(result.errors[:8]),
                ),
            )
            return
        if result.copied <= 0:
            themed_warning(
                self,
                self._t("Import Config"),
                self._t("import_settings_no_items"),
            )
            return
        self.accept()

    def _on_copy_failed(self, error: str) -> None:
        self._close_progress()
        self.import_button.setEnabled(True)
        themed_warning(
            self,
            self._t("Import Failed"),
            self._t("import_settings_copy_failed", error=error),
        )
