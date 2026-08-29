from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QDialog, QLabel, QPushButton, QVBoxLayout
from ui.styles import secondary_editor_dialog_stylesheet
from ui.theme import apply_widget_stylesheet, get_current_theme_colors


class ExistingOutputDialog(QDialog):
    CONTINUE = "continue"
    OVERWRITE_ALL = "overwrite_all"
    OVERWRITE_CURRENT = "overwrite_current"
    CANCEL = "cancel"

    def __init__(
        self,
        parent=None,
        *,
        title: str,
        body: str,
        prompt: str,
        continue_text: str,
        overwrite_all_text: str,
        overwrite_current_text: str,
        cancel_text: str,
        show_continue: bool = True,
        show_overwrite_current: bool = True,
        show_prompt: bool = True,
    ):
        super().__init__(parent)
        self.choice = self.CANCEL
        self.setWindowTitle(title or "")
        self.setModal(True)
        self.setMinimumWidth(480)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setWindowFlag(Qt.WindowType.WindowContextHelpButtonHint, False)
        apply_widget_stylesheet(self, secondary_editor_dialog_stylesheet(include_tables=False))

        colors = get_current_theme_colors()
        text_style = (
            f"color: {colors['text_primary']};"
            "background: transparent;"
            "font-size: 13px;"
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 14)
        root.setSpacing(12)

        body_label = QLabel(body)
        body_label.setWordWrap(True)
        body_label.setStyleSheet(text_style + "font-weight: 700;")
        root.addWidget(body_label)

        if show_prompt and prompt:
            prompt_label = QLabel(prompt)
            prompt_label.setWordWrap(True)
            prompt_label.setStyleSheet(text_style + "font-weight: 400;")
            prompt_label.setContentsMargins(0, 10, 0, 10)
            root.addWidget(prompt_label)

        buttons: list[QPushButton] = []
        default_button: QPushButton | None = None

        if show_continue:
            continue_button = QPushButton(continue_text)
            continue_button.setProperty("variant", "accent")
            continue_button.clicked.connect(lambda: self._choose(self.CONTINUE))
            buttons.append(continue_button)
            default_button = continue_button

        overwrite_all_button = QPushButton(overwrite_all_text)
        overwrite_all_button.setProperty("variant", "accent")
        overwrite_all_button.clicked.connect(lambda: self._choose(self.OVERWRITE_ALL))
        buttons.append(overwrite_all_button)
        if default_button is None:
            default_button = overwrite_all_button

        if show_overwrite_current:
            overwrite_current_button = QPushButton(overwrite_current_text)
            overwrite_current_button.clicked.connect(lambda: self._choose(self.OVERWRITE_CURRENT))
            buttons.append(overwrite_current_button)

        cancel_button = QPushButton(cancel_text)
        cancel_button.setProperty("variant", "danger")
        cancel_button.style().unpolish(cancel_button)
        cancel_button.style().polish(cancel_button)
        cancel_button.clicked.connect(self.reject)
        buttons.append(cancel_button)

        for button in buttons:
            button.setMinimumHeight(36)
            button.setAutoDefault(False)
            button.style().unpolish(button)
            button.style().polish(button)
            root.addWidget(button)
        if default_button is not None:
            default_button.setDefault(True)
            default_button.setAutoDefault(True)

    def _choose(self, choice: str) -> None:
        self.choice = choice
        self.accept()

    def reject(self) -> None:
        self.choice = self.CANCEL
        super().reject()
