from __future__ import annotations

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QProgressDialog,
    QPushButton,
    QToolButton,
    QVBoxLayout,
)

from ui.theme import (
    apply_native_title_bar_theme,
    apply_widget_stylesheet,
    get_current_theme,
)
from ui.styles import generate_application_stylesheet, progress_dialog_stylesheet


def _global_progress_stylesheet() -> str:
    app = QApplication.instance()
    return app.styleSheet() if app is not None else generate_application_stylesheet(get_current_theme())


class ThemedProgressDialog(QProgressDialog):
    def __init__(self, label_text: str, cancel_button_text: str | None, parent=None):
        super().__init__(label_text, cancel_button_text, 0, 0, parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.FramelessWindowHint)
        self.setWindowModality(Qt.WindowModality.WindowModal)
        self.setMinimumDuration(0)

        # Extract children
        self.label = self.findChild(QLabel)
        self.progress_bar = self.findChild(QProgressBar)
        self.cancel_button = self.findChild(QPushButton)

        # Top-level layout for drop shadow padding
        top_layout = QVBoxLayout(self)
        top_layout.setContentsMargins(12, 12, 12, 12)
        top_layout.setSpacing(0)

        # Styled container
        self.container = QFrame(self)
        self.container.setObjectName("progressDialogContainer")
        top_layout.addWidget(self.container)

        # Drop shadow on the container
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(16)
        shadow.setColor(QColor(0, 0, 0, 90))
        shadow.setOffset(0, 4)
        self.container.setGraphicsEffect(shadow)

        # Container layout
        layout = QVBoxLayout(self.container)
        layout.setContentsMargins(18, 16, 18, 18)
        layout.setSpacing(12)

        # Header / Title Bar
        self.header = QFrame(self.container)
        self.header.setObjectName("dialogHeader")
        header_layout = QHBoxLayout(self.header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(8)

        self.title_label = QLabel(self.windowTitle(), self.header)
        self.title_label.setObjectName("dialogWindowTitle")
        self.title_label.setTextFormat(Qt.TextFormat.PlainText)
        header_layout.addWidget(self.title_label, 1)

        self.close_button = QToolButton(self.header)
        self.close_button.setObjectName("dialogCloseButton")
        self.close_button.setText("×")
        self.close_button.setAutoRaise(True)
        self.close_button.clicked.connect(self.cancel)
        header_layout.addWidget(self.close_button)

        layout.addWidget(self.header)

        # Add Label
        if self.label is not None:
            self.label.setParent(self.container)
            self.label.setObjectName("progressDialogLabel")
            self.label.setWordWrap(True)
            self.label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            layout.addWidget(self.label)

        # Add Progress Bar
        if self.progress_bar is not None:
            self.progress_bar.setParent(self.container)
            self.progress_bar.setObjectName("progressDialogBar")
            self.progress_bar.setTextVisible(False)
            self.progress_bar.setFixedHeight(8)
            layout.addWidget(self.progress_bar)

        # Add Cancel Button
        if self.cancel_button is not None:
            self.cancel_button.setParent(self.container)
            self.cancel_button.setObjectName("progressDialogCancelButton")

            btn_layout = QHBoxLayout()
            btn_layout.setContentsMargins(0, 4, 0, 0)
            btn_layout.addStretch()
            btn_layout.addWidget(self.cancel_button)
            layout.addLayout(btn_layout)

        # Apply stylesheet
        apply_widget_stylesheet(self, progress_dialog_stylesheet())

        # Size settings
        self.setMinimumWidth(400)
        self.setMinimumHeight(150)
        self.adjustSize()

    def setWindowTitle(self, title: str):
        super().setWindowTitle(title)
        if hasattr(self, "title_label") and self.title_label is not None:
            self.title_label.setText(title)

    def resizeEvent(self, event):
        QDialog.resizeEvent(self, event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_position = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.MouseButton.LeftButton and hasattr(self, "_drag_position"):
            self.move(event.globalPosition().toPoint() - self._drag_position)
            event.accept()
        else:
            super().mouseMoveEvent(event)


def apply_progress_dialog_style(dialog: QProgressDialog) -> QProgressDialog:
    if isinstance(dialog, ThemedProgressDialog):
        return dialog

    dialog.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
    dialog.setWindowModality(Qt.WindowModality.WindowModal)
    dialog.setMinimumWidth(360)
    dialog.setWindowFlag(Qt.WindowType.WindowContextHelpButtonHint, False)
    apply_widget_stylesheet(dialog, _global_progress_stylesheet())
    QTimer.singleShot(0, lambda: apply_native_title_bar_theme(dialog, get_current_theme()))

    progress_bar = dialog.findChild(QProgressBar)
    if progress_bar is not None:
        progress_bar.setTextVisible(False)

    return dialog


def create_progress_dialog(parent, title: str, label_text: str, cancel_button_text: str | None = None) -> QProgressDialog:
    dialog = ThemedProgressDialog(label_text, cancel_button_text, parent)
    dialog.setWindowTitle(title)
    if cancel_button_text is None:
        dialog.setCancelButton(None)
    return dialog
