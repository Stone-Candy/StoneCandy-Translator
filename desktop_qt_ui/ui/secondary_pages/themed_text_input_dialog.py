from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QShowEvent
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)
from ui.styles import (
    secondary_editor_dialog_stylesheet as _dialog_stylesheet,
)
from ui.theme import apply_widget_stylesheet
from utils.resource_helper import apply_app_icon_to_window


class ThemedTextInputDialog(QDialog):
    def __init__(
        self,
        parent=None,
        *,
        title: str,
        label: str,
        text: str = "",
        ok_text: str = "OK",
        cancel_text: str = "Cancel",
        placeholder: str = "",
    ):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.setMinimumWidth(420)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setWindowFlag(Qt.WindowType.WindowContextHelpButtonHint, False)
        apply_widget_stylesheet(self, _dialog_stylesheet())

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 14)
        root.setSpacing(10)

        title_label = QLabel(title)
        title_label.setObjectName("dialog_title")
        root.addWidget(title_label)

        card = QWidget()
        card.setObjectName("dialog_card")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(14, 14, 14, 14)
        card_layout.setSpacing(8)

        prompt_label = QLabel(label)
        prompt_label.setObjectName("dialog_prompt")
        prompt_label.setWordWrap(True)
        card_layout.addWidget(prompt_label)

        self.line_edit = QLineEdit()
        self.line_edit.setText(text)
        self.line_edit.setPlaceholderText(placeholder)
        self.line_edit.returnPressed.connect(self.accept)
        card_layout.addWidget(self.line_edit)

        root.addWidget(card)

        button_row = QHBoxLayout()
        button_row.setContentsMargins(0, 0, 0, 0)
        button_row.setSpacing(8)
        button_row.addStretch(1)

        cancel_button = QPushButton(cancel_text)
        cancel_button.clicked.connect(self.reject)
        button_row.addWidget(cancel_button)

        ok_button = QPushButton(ok_text)
        ok_button.setProperty("variant", "accent")
        ok_button.setDefault(True)
        ok_button.setAutoDefault(True)
        ok_button.clicked.connect(self.accept)
        button_row.addWidget(ok_button)

        root.addLayout(button_row)

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        apply_app_icon_to_window(self)
        self.line_edit.setFocus()
        self.line_edit.selectAll()

    def text_value(self) -> str:
        return self.line_edit.text()


def themed_get_text(
    parent,
    title: str,
    label: str,
    text: str = "",
    ok_text: str = "OK",
    cancel_text: str = "Cancel",
    placeholder: str = "",
) -> tuple[str, bool]:
    dialog = ThemedTextInputDialog(
        parent,
        title=title,
        label=label,
        text=text,
        ok_text=ok_text,
        cancel_text=cancel_text,
        placeholder=placeholder,
    )
    accepted = dialog.exec() == QDialog.DialogCode.Accepted
    return dialog.text_value(), accepted
