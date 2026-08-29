from __future__ import annotations

from collections.abc import Callable

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QShowEvent
from PyQt6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)
from ui.styles import secondary_editor_dialog_stylesheet as _dialog_stylesheet
from ui.theme import apply_widget_stylesheet
from utils.resource_helper import apply_app_icon_to_window


def _catalog() -> list[tuple[str, list[tuple[str, str]]]]:
    """Section key -> [(shortcut keys, description key), ...]."""
    return [
        (
            "shortcut_section_mouse",
            [
                ("Wheel", "shortcut_wheel_zoom"),
                ("Middle-click", "shortcut_middle_pan"),
                ("Ctrl+Wheel", "shortcut_ctrl_wheel_font"),
                ("Shift+Wheel", "shortcut_shift_wheel_brush"),
                ("Alt+Wheel", "shortcut_alt_wheel_brush"),
                ("Alt+Click", "shortcut_eyedropper"),
                ("Alt+Shift+Click", "shortcut_eyedropper_stroke"),
                ("Ctrl+Click", "shortcut_ctrl_click_region"),
            ],
        ),
        (
            "shortcut_section_tools",
            [
                ("Q", "shortcut_tool_select"),
                ("W", "shortcut_tool_inpaint_brush"),
                ("E", "shortcut_tool_inpaint_erase"),
                ("R", "shortcut_tool_overlay_brush"),
                ("T", "shortcut_tool_overlay_erase"),
            ],
        ),
        (
            "shortcut_section_navigate",
            [
                ("A / PageUp", "shortcut_prev_image"),
                ("D / PageDown", "shortcut_next_image"),
                ("Shift+A / Shift+PageUp", "shortcut_prev_image_x10"),
                ("Shift+D / Shift+PageDown", "shortcut_next_image_x10"),
                ("F", "Fit to Window"),
            ],
        ),
        (
            "shortcut_section_display",
            [
                ("F1", "Show Text and Boxes"),
                ("F2", "Show Text Only"),
                ("F3", "Show Boxes Only"),
                ("F4", "Show Nothing"),
                ("F5", "Compare with Original (Two Panels)"),
                ("Tab", "shortcut_toggle_inpaint"),
                ("Shift+Tab", "shortcut_toggle_overlay"),
                ("Z", "shortcut_toggle_original"),
            ],
        ),
        (
            "shortcut_section_edit",
            [
                ("Ctrl+Z", "Undo"),
                ("Ctrl+Y", "Redo"),
                ("Ctrl+C", "shortcut_copy"),
                ("Ctrl+V", "shortcut_paste"),
                ("Ctrl+A", "shortcut_select_all"),
                ("Delete", "shortcut_delete"),
                ("Ctrl+S", "Export Image"),
            ],
        ),
        (
            "shortcut_section_style",
            [
                ("1–0", "shortcut_apply_style_slot"),
                ("Ctrl+1–0", "shortcut_copy_style_slot"),
                ("X", "shortcut_toggle_direction"),
                ("I", "shortcut_toggle_italic"),
                ("B", "shortcut_toggle_bold"),
                ("Ctrl+Left / Ctrl+Right", "shortcut_letter_spacing"),
                ("Ctrl+Alt+Left / Ctrl+Alt+Right", "shortcut_char_width"),
                ("Ctrl+Up / Ctrl+Down", "shortcut_line_spacing"),
                ("Alt+Left / Down / Right", "shortcut_align"),
                ("Alt+Up", "shortcut_toggle_distort"),
                ("Alt+Shift+Up / Down", "shortcut_stroke_width"),
            ],
        ),
    ]


class ShortcutListDialog(QDialog):
    def __init__(self, parent: QWidget | None, t_func: Callable[..., str]):
        super().__init__(parent)
        self._t = t_func
        self.setWindowTitle(self._t("Shortcut List"))
        self.setModal(False)
        self.setWindowModality(Qt.WindowModality.NonModal)
        self.setMinimumSize(813, 560)
        self.resize(920, 660)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.WindowTitleHint
            | Qt.WindowType.WindowSystemMenuHint
            | Qt.WindowType.WindowMinMaxButtonsHint
            | Qt.WindowType.WindowCloseButtonHint
        )
        apply_widget_stylesheet(self, _dialog_stylesheet(include_tables=False))
        self._build_ui()

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        apply_app_icon_to_window(self)

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 14)
        root.setSpacing(10)

        title = QLabel(self._t("Shortcut List"))
        title.setObjectName("dialog_title")
        root.addWidget(title)

        subtitle = QLabel(self._t("shortcut_list_description"))
        subtitle.setObjectName("dialog_subtitle")
        subtitle.setWordWrap(True)
        root.addWidget(subtitle)

        divider = QFrame()
        divider.setObjectName("divider")
        divider.setFrameShape(QFrame.Shape.HLine)
        root.addWidget(divider)

        scroll = QScrollArea()
        scroll.setObjectName("editor_scroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        content = QWidget()
        content.setObjectName("editor_scroll_content")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(4, 2, 10, 2)
        content_layout.setSpacing(10)

        columns = QHBoxLayout()
        columns.setContentsMargins(0, 0, 0, 0)
        columns.setSpacing(10)

        left_col = QVBoxLayout()
        right_col = QVBoxLayout()
        left_col.setContentsMargins(0, 0, 0, 0)
        right_col.setContentsMargins(0, 0, 0, 0)
        left_col.setSpacing(10)
        right_col.setSpacing(10)

        catalog = _catalog()
        split = (len(catalog) + 1) // 2
        for index, section in enumerate(catalog):
            card = self._build_section_card(*section)
            if index < split:
                left_col.addWidget(card)
            else:
                right_col.addWidget(card)

        left_col.addStretch(1)
        right_col.addStretch(1)
        columns.addLayout(left_col, 1)
        columns.addLayout(right_col, 1)
        content_layout.addLayout(columns)
        content_layout.addStretch(1)

        scroll.setWidget(content)
        root.addWidget(scroll, 1)

        note = QLabel(self._t("shortcut_style_preset_note"))
        note.setObjectName("shortcut_note")
        note.setWordWrap(True)
        note.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        root.addWidget(note)

        button_row = QHBoxLayout()
        button_row.setContentsMargins(0, 0, 0, 0)
        button_row.setSpacing(8)
        button_row.addStretch(1)

        close_button = QPushButton(self._t("Close"))
        close_button.setProperty("variant", "accent")
        close_button.setDefault(True)
        close_button.setAutoDefault(True)
        close_button.setMinimumWidth(132)
        close_button.setMinimumHeight(36)
        close_button.clicked.connect(self.accept)
        button_row.addWidget(close_button)
        root.addLayout(button_row)

    def _build_section_card(self, section_key: str, rows: list[tuple[str, str]]) -> QWidget:
        card = QWidget()
        card.setObjectName("dialog_card")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(6)

        heading = QLabel(self._t(section_key))
        heading.setObjectName("section_label")
        layout.addWidget(heading)

        divider = QFrame()
        divider.setObjectName("divider")
        divider.setFrameShape(QFrame.Shape.HLine)
        divider.setFixedHeight(1)
        layout.addWidget(divider)

        for keys, desc_key in rows:
            layout.addLayout(self._build_row(keys, self._t(desc_key)))
        layout.addStretch(1)
        return card

    def _build_row(self, keys: str, description: str) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)

        key_label = QLabel(keys)
        key_label.setObjectName("shortcut_key")
        key_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        key_label.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        key_label.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Preferred)

        desc_label = QLabel(description)
        desc_label.setObjectName("shortcut_desc")
        desc_label.setWordWrap(True)
        desc_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        desc_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        row.addWidget(key_label, 0)
        row.addWidget(desc_label, 1)
        return row
