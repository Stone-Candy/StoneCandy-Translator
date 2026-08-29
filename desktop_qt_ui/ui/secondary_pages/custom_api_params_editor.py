import json
from typing import Any, Callable

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListView,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)
from ui.styles import (
    monospace_font as _monospace_font,
    secondary_editor_dialog_stylesheet as _dialog_stylesheet,
    status_stylesheet as _status_stylesheet,
)
from ui.theme import apply_widget_stylesheet
from ui.widgets.wheel_filter import NoWheelComboBox as QComboBox

from manga_translator.custom_api_params import (
    CUSTOM_API_PARAM_SECTIONS,
    build_custom_api_params_payload,
    normalize_custom_api_params_payload,
)


def _identity_translate(text: str, **kwargs) -> str:
    if not kwargs:
        return text
    try:
        return text.format(**kwargs)
    except Exception:
        return text


def _infer_type(value: Any) -> str:
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return "number"
    if value is None:
        return "null"
    if isinstance(value, str):
        return "string"
    return "json"


def _create_combo_popup_view(parent: QWidget | None = None) -> QListView:
    view = QListView(parent)
    view.setObjectName("combo_popup_view")
    view.setUniformItemSizes(True)
    view.setAlternatingRowColors(False)
    return view


class CustomApiParamRow(QWidget):
    remove_requested = pyqtSignal(QWidget)

    def __init__(self, t_func: Callable[..., str] | None = None, parent=None):
        super().__init__(parent)
        self._t = t_func or _identity_translate
        self.setObjectName("param_row")
        self._is_placeholder_row = True
        self._setup_ui()

    def _setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        key_col = QVBoxLayout()
        key_col.setSpacing(6)
        key_label = QLabel(self._t("Key"))
        key_label.setObjectName("section_label")
        self.key_input = QLineEdit()
        self.key_input.setPlaceholderText("temperature")
        self.key_input.setMinimumWidth(180)
        key_col.addWidget(key_label)
        key_col.addWidget(self.key_input)
        layout.addLayout(key_col, 3)

        type_col = QVBoxLayout()
        type_col.setSpacing(6)
        type_label = QLabel(self._t("Type"))
        type_label.setObjectName("section_label")
        self.type_combo = QComboBox()
        self.type_combo.setView(_create_combo_popup_view(self.type_combo))
        self.type_combo.setMinimumWidth(118)
        for label, value in [
            (self._t("String"), "string"),
            (self._t("Number"), "number"),
            (self._t("Boolean"), "boolean"),
            (self._t("Null"), "null"),
            ("JSON", "json"),
        ]:
            self.type_combo.addItem(label, value)
        type_col.addWidget(type_label)
        type_col.addWidget(self.type_combo)
        layout.addLayout(type_col, 2)

        value_col = QVBoxLayout()
        value_col.setSpacing(6)
        value_label = QLabel(self._t("Value"))
        value_label.setObjectName("section_label")
        self.value_stack = QStackedWidget()

        self.string_input = QLineEdit()
        self.string_input.setPlaceholderText("gpt-4o-mini")

        self.number_input = QLineEdit()
        self.number_input.setPlaceholderText("0.2")
        self.number_input.setFont(_monospace_font(10))

        self.boolean_input = QComboBox()
        self.boolean_input.setView(_create_combo_popup_view(self.boolean_input))
        self.boolean_input.addItem("true", True)
        self.boolean_input.addItem("false", False)

        self.null_label = QLabel("null")
        self.null_label.setObjectName("null_value_label")
        self.null_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.json_input = QLineEdit()
        self.json_input.setPlaceholderText('{"type": "json"}')
        self.json_input.setFont(_monospace_font(10))

        self.value_stack.addWidget(self.string_input)
        self.value_stack.addWidget(self.number_input)
        self.value_stack.addWidget(self.boolean_input)
        self.value_stack.addWidget(self.null_label)
        self.value_stack.addWidget(self.json_input)

        value_col.addWidget(value_label)
        value_col.addWidget(self.value_stack)
        layout.addLayout(value_col, 4)

        remove_col = QVBoxLayout()
        remove_col.setSpacing(6)
        remove_col.addWidget(QLabel(""))
        self.remove_button = QPushButton(self._t("Delete"))
        self.remove_button.setProperty("variant", "danger")
        self.remove_button.setFixedWidth(80)
        self.remove_button.clicked.connect(lambda: self.remove_requested.emit(self))
        remove_col.addWidget(self.remove_button)
        remove_col.addStretch(1)
        layout.addLayout(remove_col)

        self.type_combo.currentIndexChanged.connect(self._sync_type_editor)
        self.key_input.textEdited.connect(self._mark_user_edited)
        self.string_input.textEdited.connect(self._mark_user_edited)
        self.number_input.textEdited.connect(self._mark_user_edited)
        self.json_input.textChanged.connect(self._mark_user_edited)
        self.type_combo.currentIndexChanged.connect(self._mark_user_edited)
        self.boolean_input.currentIndexChanged.connect(self._mark_user_edited)
        self._sync_type_editor()

    def _sync_type_editor(self):
        current_type = self.type_combo.currentData()
        index_map = {
            "string": 0,
            "number": 1,
            "boolean": 2,
            "null": 3,
            "json": 4,
        }
        self.value_stack.setCurrentIndex(index_map.get(current_type, 0))

    def _mark_user_edited(self, *args):
        del args
        self._is_placeholder_row = False

    def set_entry(self, key: str, value: Any):
        self._is_placeholder_row = False
        self.key_input.setText(key)
        value_type = _infer_type(value)
        combo_index = self.type_combo.findData(value_type)
        if combo_index >= 0:
            self.type_combo.setCurrentIndex(combo_index)

        if value_type == "string":
            self.string_input.setText(value)
        elif value_type == "number":
            self.number_input.setText(str(value))
        elif value_type == "boolean":
            bool_index = self.boolean_input.findData(bool(value))
            self.boolean_input.setCurrentIndex(max(bool_index, 0))
        elif value_type == "json":
            self.json_input.setText(json.dumps(value, ensure_ascii=False))

        self._sync_type_editor()

    def is_empty_placeholder(self) -> bool:
        return self._is_placeholder_row and not self.key_input.text().strip()

    def _parse_number(self) -> int | float:
        raw = self.number_input.text().strip()
        if not raw:
            raise ValueError(self._t("Number value is empty"))
        parsed = json.loads(raw)
        if isinstance(parsed, bool) or not isinstance(parsed, (int, float)):
            raise ValueError(self._t("Number value is invalid"))
        return parsed

    def _parse_json_value(self) -> Any:
        raw = self.json_input.text().strip()
        if not raw:
            raise ValueError(self._t("JSON value is empty"))
        return json.loads(raw)

    def get_entry(self) -> tuple[str, Any]:
        key = self.key_input.text().strip()
        if not key:
            raise ValueError(self._t("Parameter name cannot be empty"))

        value_type = self.type_combo.currentData()
        if value_type == "string":
            value = self.string_input.text()
        elif value_type == "number":
            value = self._parse_number()
        elif value_type == "boolean":
            value = self.boolean_input.currentData()
        elif value_type == "null":
            value = None
        else:
            value = self._parse_json_value()
        return key, value


class CustomApiParamsEditorDialog(QDialog):
    def __init__(self, file_path: str, t_func: Callable[..., str] | None = None, parent=None):
        super().__init__(parent)
        self._t = t_func or _identity_translate
        self._file_path = file_path
        self._original_content = ""
        self.section_tabs: QTabWidget | None = None
        self.section_layouts: dict[str, QVBoxLayout] = {}
        self.section_contents: dict[str, QWidget] = {}
        self._setup_ui()
        self._load_from_disk()

    def _setup_ui(self):
        self.setWindowTitle(self._t("Edit Custom API Params"))
        self.setMinimumSize(880, 620)
        self.resize(980, 720)
        apply_widget_stylesheet(self, _dialog_stylesheet())

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 14)
        root.setSpacing(10)

        title = QLabel(self._t("Edit Custom API Params"))
        title.setObjectName("dialog_title")
        subtitle = QLabel(
            self._t("Edit custom API request parameters passed directly to the translator backend.")
        )
        subtitle.setObjectName("dialog_subtitle")
        subtitle.setWordWrap(True)
        root.addWidget(title)
        root.addWidget(subtitle)

        divider = QFrame()
        divider.setObjectName("divider")
        divider.setFrameShape(QFrame.Shape.HLine)
        root.addWidget(divider)

        self.tabs = QTabWidget()
        root.addWidget(self.tabs, 1)

        self._build_params_tab()
        self._build_raw_tab()

        self.status_label = QLabel("")
        self.status_label.setObjectName("hint_label")
        root.addWidget(self.status_label)

        button_row = QHBoxLayout()
        button_row.addStretch(1)

        self.refresh_button = QPushButton(self._t("Refresh"))
        self.refresh_button.clicked.connect(self._load_from_disk)

        self.cancel_button = QPushButton(self._t("Cancel"))
        self.cancel_button.clicked.connect(self.reject)

        self.save_button = QPushButton(self._t("Save"))
        self.save_button.setProperty("variant", "accent")
        self.save_button.clicked.connect(self._save)

        button_row.addWidget(self.refresh_button)
        button_row.addWidget(self.cancel_button)
        button_row.addWidget(self.save_button)
        root.addLayout(button_row)

    def _build_params_tab(self):
        page = QWidget()
        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(8, 8, 8, 8)
        page_layout.setSpacing(8)

        card = QWidget()
        card.setObjectName("path_card")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(14, 12, 14, 12)
        card_layout.setSpacing(4)

        title = QLabel(self._t("Grouped API Params"))
        title.setObjectName("section_label")
        hint = QLabel(
            self._t(
                "Parameters in each group are sent only to the matching AI backend. "
                "Raw top-level keys are treated as common params."
            )
        )
        hint.setObjectName("hint_label")
        hint.setWordWrap(True)

        card_layout.addWidget(title)
        card_layout.addWidget(hint)
        page_layout.addWidget(card)

        self.section_tabs = QTabWidget()
        for section in CUSTOM_API_PARAM_SECTIONS:
            section_page = QWidget()
            section_page_layout = QVBoxLayout(section_page)
            section_page_layout.setContentsMargins(0, 0, 0, 0)
            section_page_layout.setSpacing(8)

            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setFrameShape(QFrame.Shape.NoFrame)

            content = QWidget()
            content.setObjectName("section_content")

            layout = QVBoxLayout(content)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(10)
            layout.addStretch(1)

            scroll.setWidget(content)

            add_row = QHBoxLayout()
            add_row.addStretch(1)
            add_button = QPushButton("+ " + self._t("Add Row"))
            add_button.clicked.connect(lambda _=False, s=section: self._append_row(s))
            add_row.addWidget(add_button)

            section_page_layout.addWidget(scroll, 1)
            section_page_layout.addLayout(add_row)

            self.section_contents[section] = content
            self.section_layouts[section] = layout
            self.section_tabs.addTab(section_page, self._section_title(section))

        page_layout.addWidget(self.section_tabs, 1)
        self.tabs.addTab(page, self._t("Template Edit"))

    def _build_raw_tab(self):
        page = QWidget()
        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(8, 8, 8, 8)
        page_layout.setSpacing(8)

        hint = QLabel(self._t("Edit the raw file content directly"))
        hint.setObjectName("hint_label")
        page_layout.addWidget(hint)

        self.raw_editor = QPlainTextEdit()
        self.raw_editor.setFont(_monospace_font())
        self.raw_editor.setTabStopDistance(28)
        page_layout.addWidget(self.raw_editor, 1)

        self.tabs.addTab(page, self._t("Raw Edit"))

    def _section_title(self, section: str) -> str:
        if section == "common":
            return self._t("General")
        if section == "translator":
            return self._t("label_translator")
        if section == "ocr":
            return self._t("label_ocr")
        if section == "render":
            return self._t("label_renderer")
        if section == "colorizer":
            return self._t("label_colorizer")
        return section

    def _insert_row_widget(self, section: str, row: CustomApiParamRow):
        row.setProperty("section_name", section)
        row.remove_requested.connect(self._remove_row)
        layout = self.section_layouts[section]
        insert_index = max(layout.count() - 1, 0)
        layout.insertWidget(insert_index, row)

    def _append_row(self, section: str, key: str = "", value: Any = ""):
        row = CustomApiParamRow(t_func=self._t, parent=self.section_contents[section])
        if key:
            row.set_entry(key, value)
        self._insert_row_widget(section, row)
        return row

    def _clear_rows(self):
        for layout in self.section_layouts.values():
            while layout.count() > 1:
                item = layout.takeAt(0)
                widget = item.widget()
                if widget is not None:
                    widget.deleteLater()

    def _remove_row(self, row: QWidget):
        row.setParent(None)
        row.deleteLater()

    def _load_from_disk(self):
        try:
            with open(self._file_path, "r", encoding="utf-8") as handle:
                content = handle.read().strip()
        except FileNotFoundError:
            content = "{}"
        except Exception as exc:
            self._set_status(f"{self._t('Load failed')}: {exc}", kind="error")
            return

        if not content:
            content = "{}"

        self._original_content = content
        self.raw_editor.setPlainText(content)

        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as exc:
            self._populate_rows({})
            self._set_status(f"{self._t('JSON format error')}: {exc}", kind="error")
            return

        if not isinstance(parsed, dict):
            self._populate_rows({})
            self._set_status(self._t("JSON root must be an object"), kind="error")
            return

        self._populate_rows(parsed)
        self._set_status(self._t("Loaded successfully"))

    def _populate_rows(self, data: dict[str, Any]):
        self._clear_rows()
        section_data = normalize_custom_api_params_payload(data)
        for section in CUSTOM_API_PARAM_SECTIONS:
            values = section_data.get(section) or {}
            if not values:
                self._append_row(section)
                continue
            for key, value in values.items():
                self._append_row(section, key, value)

    def _collect_structured_data(self) -> dict[str, Any]:
        section_data: dict[str, dict[str, Any]] = {
            section: {} for section in CUSTOM_API_PARAM_SECTIONS
        }

        for section in CUSTOM_API_PARAM_SECTIONS:
            container = self.section_contents.get(section)
            if container is None:
                continue

            row_widgets = container.findChildren(
                CustomApiParamRow,
                options=Qt.FindChildOption.FindDirectChildrenOnly,
            )
            for row in row_widgets:
                if row.is_empty_placeholder():
                    continue
                key, value = row.get_entry()
                if key in section_data[section]:
                    raise ValueError(self._t("Duplicate parameter name: {name}", name=key))
                section_data[section][key] = value

        return build_custom_api_params_payload(section_data)

    def _collect_raw_data(self) -> dict[str, Any]:
        content = self.raw_editor.toPlainText().strip() or "{}"
        parsed = json.loads(content)
        if not isinstance(parsed, dict):
            raise ValueError(self._t("JSON root must be an object"))
        return parsed

    def _set_status(self, message: str, kind: str = "default"):
        self.status_label.setStyleSheet(_status_stylesheet(kind))
        self.status_label.setText(message)

    def _save(self):
        try:
            if self.tabs.currentIndex() == 0:
                data = self._collect_structured_data()
            else:
                data = self._collect_raw_data()
        except json.JSONDecodeError as exc:
            self._set_status(f"{self._t('JSON format error')}: {exc}", kind="error")
            return
        except ValueError as exc:
            self._set_status(str(exc), kind="error")
            return

        content = json.dumps(data, indent=2, ensure_ascii=False)
        try:
            with open(self._file_path, "w", encoding="utf-8") as handle:
                handle.write(content)
                handle.write("\n")
        except Exception as exc:
            self._set_status(f"{self._t('Save failed')}: {exc}", kind="error")
            return

        self._original_content = content
        self.raw_editor.setPlainText(content)
        self._populate_rows(data)
        self._set_status(self._t("Saved successfully"), kind="success")

    def get_was_modified(self) -> bool:
        current = self.raw_editor.toPlainText().strip()
        return current != self._original_content.strip()
