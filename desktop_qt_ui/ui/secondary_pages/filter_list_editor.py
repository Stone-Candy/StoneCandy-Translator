import json
from typing import Any, Callable

from PyQt6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
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

from manga_translator.utils.text_filter import (
    ensure_filter_list_exists,
    save_filter_list_config,
)


def _split_rules(text: str) -> list[str]:
    rules = []
    for line in text.splitlines():
        normalized = line.strip()
        if normalized:
            rules.append(normalized)
    return rules


def _sanitize_rule_values(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    rules = []
    for value in values:
        text = str(value or "").strip()
        if text:
            rules.append(text)
    return rules


class FilterListEditorDialog(QDialog):
    def __init__(self, file_path: str | None = None, t_func: Callable[[str], str] | None = None, parent=None):
        super().__init__(parent)
        self._t = t_func or (lambda text, **kwargs: text.format(**kwargs) if kwargs else text)
        self._file_path = file_path or ensure_filter_list_exists()
        self._original_content = ""
        self._extra_data: dict[str, Any] = {}
        self._setup_ui()
        self._load_from_disk()

    def _setup_ui(self):
        self.setWindowTitle(self._t("Edit Filter List"))
        self.setMinimumSize(880, 620)
        self.resize(980, 720)
        apply_widget_stylesheet(self, _dialog_stylesheet())

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 14)
        root.setSpacing(10)

        title = QLabel(self._t("Edit Filter List"))
        title.setObjectName("dialog_title")
        subtitle = QLabel(self._t("Edit OCR text filter rules skipped during translation."))
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

        self._build_rules_tab()
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

    def _build_rules_tab(self):
        page = QWidget()
        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(8, 8, 8, 8)
        page_layout.setSpacing(10)

        page_layout.addWidget(self._build_rules_card(
            self._t("Contains Filter"),
            self._t("Skip when OCR text contains any of these rules."),
            "contains",
        ))
        page_layout.addWidget(self._build_rules_card(
            self._t("Exact Filter"),
            self._t("Skip only when OCR text exactly matches one of these rules."),
            "exact",
        ))
        page_layout.addStretch(1)

        self.tabs.addTab(page, self._t("Filter Rules"))

    def _build_rules_card(self, title_text: str, hint_text: str, mode: str) -> QWidget:
        card = QWidget()
        card.setObjectName("section_card")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(6)

        title = QLabel(title_text)
        title.setObjectName("section_label")
        hint = QLabel(hint_text)
        hint.setObjectName("hint_label")
        hint.setWordWrap(True)

        editor = QPlainTextEdit()
        editor.setFont(_monospace_font())
        editor.setTabStopDistance(28)
        editor.setPlaceholderText(self._t("One rule per line"))

        layout.addWidget(title)
        layout.addWidget(hint)
        layout.addWidget(editor, 1)

        if mode == "contains":
            self.contains_editor = editor
        else:
            self.exact_editor = editor
        return card

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

    def _set_status(self, message: str, kind: str = "default"):
        self.status_label.setStyleSheet(_status_stylesheet(kind))
        self.status_label.setText(message)

    def _load_from_disk(self):
        self._file_path = ensure_filter_list_exists()
        try:
            with open(self._file_path, 'r', encoding='utf-8') as handle:
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
            if not isinstance(parsed, dict):
                raise ValueError(self._t("JSON root must be an object"))
        except Exception as exc:
            self.contains_editor.setPlainText("")
            self.exact_editor.setPlainText("")
            self._extra_data = {}
            self._set_status(f"{self._t('JSON format error')}: {exc}", kind="error")
            return

        self._extra_data = {k: v for k, v in parsed.items() if k not in ("contains", "exact")}
        self.contains_editor.setPlainText("\n".join(_sanitize_rule_values(parsed.get("contains", []))))
        self.exact_editor.setPlainText("\n".join(_sanitize_rule_values(parsed.get("exact", []))))
        self._set_status(self._t("Loaded successfully"))

    def _collect_structured_data(self) -> dict[str, Any]:
        data = dict(self._extra_data)
        data["contains"] = _split_rules(self.contains_editor.toPlainText())
        data["exact"] = _split_rules(self.exact_editor.toPlainText())
        return data

    def _collect_raw_data(self) -> dict[str, Any]:
        content = self.raw_editor.toPlainText().strip() or "{}"
        parsed = json.loads(content)
        if not isinstance(parsed, dict):
            raise ValueError(self._t("JSON root must be an object"))
        return parsed

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

        try:
            save_filter_list_config(data)
        except Exception as exc:
            self._set_status(f"{self._t('Save failed')}: {exc}", kind="error")
            return

        formatted = json.dumps(data, indent=2, ensure_ascii=False)
        self._original_content = formatted
        self.raw_editor.setPlainText(formatted)
        self._extra_data = {k: v for k, v in data.items() if k not in ("contains", "exact")}
        self.contains_editor.setPlainText("\n".join(data.get("contains", [])))
        self.exact_editor.setPlainText("\n".join(data.get("exact", [])))
        self._set_status(self._t("Saved successfully"), kind="success")

    def get_was_modified(self) -> bool:
        current = self.raw_editor.toPlainText().strip()
        return current != self._original_content.strip()
