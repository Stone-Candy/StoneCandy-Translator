from __future__ import annotations

import textwrap

from ui.styles import error_dialog_stylesheet
from ui.theme import apply_widget_stylesheet
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QScrollArea,
    QSizePolicy,
    QStyle,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

_INSTALLED = False


def _refresh_button_state(box: QMessageBox) -> None:
    buttons = box.buttons()
    default_button = box.defaultButton()
    if default_button is None and len(buttons) == 1:
        default_button = buttons[0]

    for button in buttons:
        button.setProperty("dialogDefault", button is default_button)
        style = button.style()
        style.unpolish(button)
        style.polish(button)
        button.update()


def _wrap_dialog_text(text: str, width: int = 88) -> str:
    wrapped_lines: list[str] = []
    for line in str(text or "").splitlines():
        if not line:
            wrapped_lines.append("")
            continue
        wrapped_lines.extend(
            textwrap.wrap(
                line,
                width=width,
                break_long_words=True,
                break_on_hyphens=False,
            )
            or [""]
        )
    return "\n".join(wrapped_lines)


def apply_message_box_style(box: QMessageBox) -> QMessageBox:
    box.setObjectName("themedMessageBox")
    box.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
    box.setTextFormat(Qt.TextFormat.PlainText)
    # WindowModal with no parent does not block any window, so the rest of
    # the UI stays clickable and can spawn duplicate prompts.
    box.setWindowModality(
        Qt.WindowModality.WindowModal
        if box.parentWidget() is not None
        else Qt.WindowModality.ApplicationModal
    )
    _refresh_button_state(box)
    style = box.style()
    style.unpolish(box)
    style.polish(box)
    box.update()
    for label in box.findChildren(QLabel):
        label.setWordWrap(True)
        label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    return box


def apply_error_dialog_style(dialog: QDialog) -> QDialog:
    dialog.setObjectName("errorDialog")
    dialog.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
    apply_widget_stylesheet(dialog, error_dialog_stylesheet())
    style = dialog.style()
    style.unpolish(dialog)
    style.polish(dialog)
    dialog.update()
    for label in dialog.findChildren(QLabel):
        label.setWordWrap(True)
        label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        if label.objectName() == "errorDialogDetails":
            label.setTextFormat(Qt.TextFormat.PlainText)
    for text_edit in dialog.findChildren(QTextEdit):
        if not text_edit.objectName():
            text_edit.setObjectName("errorDialogDetails")
    for scroll_area in dialog.findChildren(QScrollArea):
        if not scroll_area.objectName():
            scroll_area.setObjectName("errorDialogScroll")
    for widget in dialog.findChildren(QWidget):
        if widget.objectName() == "qt_scrollarea_viewport":
            widget.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
    for button_box in dialog.findChildren(QDialogButtonBox):
        for button in button_box.buttons():
            style = button.style()
            style.unpolish(button)
            style.polish(button)
            button.update()
    return dialog


def _icon_pixmap(parent, icon: QMessageBox.Icon):
    if icon == QMessageBox.Icon.Warning:
        standard_icon = QStyle.StandardPixmap.SP_MessageBoxWarning
    elif icon == QMessageBox.Icon.Critical:
        standard_icon = QStyle.StandardPixmap.SP_MessageBoxCritical
    elif icon == QMessageBox.Icon.Information:
        standard_icon = QStyle.StandardPixmap.SP_MessageBoxInformation
    elif icon == QMessageBox.Icon.Question:
        standard_icon = QStyle.StandardPixmap.SP_MessageBoxQuestion
    else:
        return None
    return parent.style().standardIcon(standard_icon).pixmap(36, 36)


def _label_height_for_width(label: QLabel | None, width: int) -> int:
    if label is None:
        return 0
    text = str(label.text() or "")
    if not text.strip():
        return 0
    width = max(int(width), 80)
    height = label.heightForWidth(width)
    if height <= 0:
        height = label.sizeHint().height()
    min_height = label.fontMetrics().lineSpacing() * max(len(text.splitlines()), 1)
    return max(height, min_height)


def _fit_error_dialog_size(
    dialog: QDialog,
    scroll_area: QScrollArea,
    details_label: QLabel,
    heading_label: QLabel | None,
    has_icon: bool,
    dialog_width: int | None = None,
    dialog_height: int | None = None,
) -> None:
    details_text = str(details_label.text() or "")
    heading_text = str(heading_label.text() if heading_label is not None else "").strip()
    line_count = len(details_text.splitlines()) or 1
    is_compact = not heading_text and line_count <= 8 and len(details_text) <= 360
    has_custom_size = dialog_width is not None or dialog_height is not None

    outer_width = dialog_width if dialog_width is not None else (443 if is_compact else 720)
    text_width = outer_width - 24 - 36 - (50 if has_icon else 0) - 14
    text_width = max(text_width, 160 if has_custom_size else 240)

    details_label.setMaximumWidth(text_width)
    if heading_label is not None:
        heading_label.setMaximumWidth(text_width)

    dialog.ensurePolished()
    details_label.ensurePolished()
    text_height = max(_label_height_for_width(details_label, text_width), 18)

    max_scroll = 420
    scroll_area.setMinimumSize(0, 0)
    scroll_area.setMaximumHeight(16777215)
    scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    if has_custom_size:
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll_area.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
    elif text_height <= max_scroll:
        scroll_area.setFixedHeight(text_height + 4)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll_area.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    else:
        scroll_area.setMinimumHeight(160)
        scroll_area.setMaximumHeight(max_scroll)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll_area.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

    dialog.setMinimumSize(200 if has_custom_size else (443 if is_compact else 520), 120 if has_custom_size else 125)
    dialog.setSizeGripEnabled(has_custom_size or not is_compact)
    if dialog.layout() is not None:
        dialog.layout().activate()
    dialog.adjustSize()

    hint = dialog.sizeHint()
    if dialog_width is not None:
        width = dialog_width
    else:
        width = min(max(hint.width(), 443 if is_compact else 640), 920)
    height = hint.height()
    if dialog_height is not None:
        height = dialog_height
    elif is_compact:
        chrome_height = 12 * 2 + 18 * 2 + 32 + 12 + 12 + 40
        fitted_height = chrome_height + max(36 if has_icon else 0, text_height + 4) + 5
        height = min(height, fitted_height + 8) if height > fitted_height else max(height, fitted_height)
    dialog.resize(width, height)


_STANDARD_BUTTON_MAP = (
    (QMessageBox.StandardButton.Ok, QDialogButtonBox.StandardButton.Ok),
    (QMessageBox.StandardButton.Yes, QDialogButtonBox.StandardButton.Yes),
    (QMessageBox.StandardButton.No, QDialogButtonBox.StandardButton.No),
    (QMessageBox.StandardButton.Cancel, QDialogButtonBox.StandardButton.Cancel),
    (QMessageBox.StandardButton.Close, QDialogButtonBox.StandardButton.Close),
)


def _to_dialog_standard_button(button: QMessageBox.StandardButton):
    for message_button, dialog_button in _STANDARD_BUTTON_MAP:
        if button == message_button:
            return dialog_button
    return None


def _to_message_standard_button(button) -> QMessageBox.StandardButton:
    for message_button, dialog_button in _STANDARD_BUTTON_MAP:
        if button == dialog_button:
            return message_button
    return QMessageBox.StandardButton.NoButton


def show_error_dialog(
    parent,
    window_title: str,
    heading: str,
    details: str,
    icon: QMessageBox.Icon = QMessageBox.Icon.NoIcon,
    buttons: QMessageBox.StandardButton = QMessageBox.StandardButton.Ok,
    default_button: QMessageBox.StandardButton = QMessageBox.StandardButton.NoButton,
    rich_text: bool = False,
    dialog_width: int | None = None,
    dialog_height: int | None = None,
) -> QMessageBox.StandardButton:
    dialog_parent = parent or QApplication.activeWindow()
    dialog = QDialog(dialog_parent)
    dialog.setWindowTitle(window_title)
    dialog.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
    dialog.setWindowFlags(dialog.windowFlags() | Qt.WindowType.FramelessWindowHint)
    dialog.setModal(True)
    dialog.setWindowModality(
        Qt.WindowModality.WindowModal if dialog_parent is not None else Qt.WindowModality.ApplicationModal
    )

    # Top-level layout for drop shadow padding
    top_layout = QVBoxLayout(dialog)
    top_layout.setContentsMargins(12, 12, 12, 12)
    top_layout.setSpacing(0)

    # Styled container
    container = QFrame(dialog)
    container.setObjectName("errorDialogContainer")
    top_layout.addWidget(container)

    # Add drop shadow to the container
    shadow = QGraphicsDropShadowEffect(dialog)
    shadow.setBlurRadius(16)
    shadow.setColor(QColor(0, 0, 0, 90))
    shadow.setOffset(0, 4)
    container.setGraphicsEffect(shadow)

    # Layout for contents inside the container
    layout = QVBoxLayout(container)
    layout.setContentsMargins(18, 18, 18, 18)
    layout.setSpacing(12)

    header = QWidget(container)
    header.setObjectName("dialogHeader")
    header_layout = QHBoxLayout(header)
    header_layout.setContentsMargins(0, 0, 0, 0)
    header_layout.setSpacing(8)

    title_label = QLabel(window_title, header)
    title_label.setObjectName("dialogWindowTitle")
    title_label.setTextFormat(Qt.TextFormat.PlainText)
    header_layout.addWidget(title_label, 1)

    close_button = QToolButton(header)
    close_button.setObjectName("dialogCloseButton")
    close_button.setText("×")
    close_button.setAutoRaise(True)
    close_button.clicked.connect(dialog.reject)
    header_layout.addWidget(close_button)
    layout.addWidget(header)

    body_layout = QHBoxLayout()
    body_layout.setContentsMargins(0, 0, 0, 0)
    body_layout.setSpacing(14)

    icon_pixmap = _icon_pixmap(container, icon)
    if icon_pixmap is not None:
        icon_label = QLabel(container)
        icon_label.setObjectName("dialogIcon")
        icon_label.setPixmap(icon_pixmap)
        icon_label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)
        body_layout.addWidget(icon_label, 0, Qt.AlignmentFlag.AlignTop)

    content_layout = QVBoxLayout()
    content_layout.setContentsMargins(0, 0, 0, 0)
    content_layout.setSpacing(10)

    summary_label = None
    normalized_heading = str(heading or "").strip()
    if normalized_heading:
        summary_label = QLabel(normalized_heading, container)
        summary_label.setObjectName("errorDialogTitle")
        summary_label.setTextFormat(Qt.TextFormat.PlainText)
        summary_label.setWordWrap(True)
        summary_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        content_layout.addWidget(summary_label)

    scroll_area = QScrollArea(container)
    scroll_area.setObjectName("errorDialogScroll")
    scroll_area.setWidgetResizable(True)
    scroll_area.setFrameShape(QFrame.Shape.NoFrame)
    scroll_area.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)

    details_container = QWidget(scroll_area)
    details_layout = QVBoxLayout(details_container)
    details_layout.setContentsMargins(0, 0, 0, 0)

    details_label = QLabel(details_container)
    details_label.setObjectName("errorDialogDetails")
    details_label.setTextFormat(
        Qt.TextFormat.RichText if rich_text else Qt.TextFormat.PlainText
    )
    details_label.setWordWrap(True)
    details_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
    if rich_text:
        details_label.setOpenExternalLinks(True)
        details_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextBrowserInteraction
            | Qt.TextInteractionFlag.TextSelectableByMouse
            | Qt.TextInteractionFlag.TextSelectableByKeyboard
        )
    else:
        details_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
            | Qt.TextInteractionFlag.TextSelectableByKeyboard
        )
    details_label.setText(str(details or ""))
    details_layout.addWidget(details_label)

    scroll_area.setWidget(details_container)
    content_layout.addWidget(scroll_area)
    body_layout.addLayout(content_layout, 1)
    layout.addLayout(body_layout)

    if buttons == QMessageBox.StandardButton.NoButton:
        buttons = QMessageBox.StandardButton.Ok

    button_box = QDialogButtonBox(parent=container)
    added_buttons = 0
    for message_button, dialog_button in _STANDARD_BUTTON_MAP:
        if buttons & message_button:
            button_box.addButton(dialog_button)
            added_buttons += 1
    if added_buttons == 0:
        button_box.addButton(QDialogButtonBox.StandardButton.Ok)

    def _handle_button_clicked(button):
        standard_button = _to_message_standard_button(button_box.standardButton(button))
        dialog.done(int(standard_button))

    button_box.clicked.connect(_handle_button_clicked)

    effective_default = default_button
    if effective_default == QMessageBox.StandardButton.NoButton:
        box_buttons = button_box.buttons()
        if len(box_buttons) == 1:
            effective_default = _to_message_standard_button(button_box.standardButton(box_buttons[0]))
    if effective_default != QMessageBox.StandardButton.NoButton:
        dialog_default = _to_dialog_standard_button(effective_default)
        if dialog_default is not None:
            default_qbutton = button_box.button(dialog_default)
            if default_qbutton is not None:
                default_qbutton.setProperty("dialogDefault", True)
                default_qbutton.setDefault(True)
    layout.addWidget(button_box)

    apply_error_dialog_style(dialog)
    if rich_text:
        details_label.setTextFormat(Qt.TextFormat.RichText)
        details_label.setOpenExternalLinks(True)
        details_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextBrowserInteraction
            | Qt.TextInteractionFlag.TextSelectableByMouse
            | Qt.TextInteractionFlag.TextSelectableByKeyboard
        )
        details_label.setText(str(details or ""))
    _fit_error_dialog_size(
        dialog,
        scroll_area=scroll_area,
        details_label=details_label,
        heading_label=summary_label,
        has_icon=icon_pixmap is not None,
        dialog_width=dialog_width,
        dialog_height=dialog_height,
    )
    result = dialog.exec()
    if result in (QDialog.DialogCode.Accepted, QDialog.DialogCode.Rejected):
        return QMessageBox.StandardButton.NoButton
    return QMessageBox.StandardButton(result)


def _show_message_box(
    parent,
    icon: QMessageBox.Icon,
    title: str,
    text: str,
    buttons: QMessageBox.StandardButton = QMessageBox.StandardButton.Ok,
    default_button: QMessageBox.StandardButton = QMessageBox.StandardButton.NoButton,
) -> QMessageBox.StandardButton:
    return show_error_dialog(
        parent,
        title,
        "",
        _wrap_dialog_text(text, width=72),
        icon=icon,
        buttons=buttons,
        default_button=default_button,
    )


def themed_information(
    parent,
    title: str,
    text: str,
    buttons: QMessageBox.StandardButton = QMessageBox.StandardButton.Ok,
    default_button: QMessageBox.StandardButton = QMessageBox.StandardButton.NoButton,
):
    return _show_message_box(parent, QMessageBox.Icon.Information, title, text, buttons, default_button)


def themed_warning(
    parent,
    title: str,
    text: str,
    buttons: QMessageBox.StandardButton = QMessageBox.StandardButton.Ok,
    default_button: QMessageBox.StandardButton = QMessageBox.StandardButton.NoButton,
):
    return _show_message_box(parent, QMessageBox.Icon.Warning, title, text, buttons, default_button)


def themed_critical(
    parent,
    title: str,
    text: str,
    buttons: QMessageBox.StandardButton = QMessageBox.StandardButton.Ok,
    default_button: QMessageBox.StandardButton = QMessageBox.StandardButton.NoButton,
):
    return _show_message_box(parent, QMessageBox.Icon.Critical, title, text, buttons, default_button)


def themed_question(
    parent,
    title: str,
    text: str,
    buttons: QMessageBox.StandardButton = QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
    default_button: QMessageBox.StandardButton = QMessageBox.StandardButton.NoButton,
):
    return _show_message_box(parent, QMessageBox.Icon.Question, title, text, buttons, default_button)


def install_themed_message_boxes() -> None:
    global _INSTALLED
    if _INSTALLED:
        return

    QMessageBox.information = staticmethod(themed_information)
    QMessageBox.warning = staticmethod(themed_warning)
    QMessageBox.critical = staticmethod(themed_critical)
    QMessageBox.question = staticmethod(themed_question)
    _INSTALLED = True
