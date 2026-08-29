from __future__ import annotations

from PyQt6.QtCore import QEvent, QObject, QPoint, QTimer, Qt
from PyQt6.QtGui import QColor, QCursor, QFont, QPalette
from PyQt6.QtWidgets import (
    QApplication,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QWidget,
)

from ui.theme import get_current_theme_colors


# v3.0 다이얼로그와 동일: 바깥은 투명, 안쪽 네모에 배경+드롭쉐도우
_SHADOW_MARGIN = 12


class _HoverHintPopup(QWidget):
    def __init__(
        self,
        *,
        blur_radius: float = 16,
        offset: tuple[int, int] = (0, 4),
        color_alpha: int = 90,
    ):
        super().__init__(None)
        self.setObjectName("hoverHintPopup")
        self.setWindowFlags(
            Qt.WindowType.ToolTip
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(
            _SHADOW_MARGIN, _SHADOW_MARGIN, _SHADOW_MARGIN, _SHADOW_MARGIN
        )
        layout.setSpacing(0)

        self._bubble = QLabel(self)
        self._bubble.setObjectName("hoverHintBubble")
        self._bubble.setWordWrap(False)
        self._bubble.setMargin(0)
        self._bubble.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._bubble.setAutoFillBackground(True)
        layout.addWidget(self._bubble)

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(blur_radius)
        shadow.setOffset(*offset)
        shadow.setColor(QColor(0, 0, 0, color_alpha))
        self._bubble.setGraphicsEffect(shadow)

        self._apply_style()

    def _apply_style(self):
        colors = get_current_theme_colors()
        palette = self._bubble.palette()
        palette.setColor(QPalette.ColorRole.Window, QColor(colors["bg_dropdown"]))
        palette.setColor(QPalette.ColorRole.WindowText, QColor(colors["text_accent"]))
        self._bubble.setPalette(palette)
        font = QFont(self._bubble.font())
        font.setBold(False)
        font.setWeight(QFont.Weight.Normal)
        self._bubble.setFont(font)
        # 부모 선택자를 QWidget 전체에 걸면 안쪽 라벨 배경까지 투명해진다.
        self.setStyleSheet(
            f"""
            QWidget#hoverHintPopup {{
                background: transparent;
            }}
            QLabel#hoverHintBubble {{
                background-color: {colors["bg_dropdown"]};
                color: {colors["text_accent"]};
                border: 1px solid {colors["border_input"]};
                border-radius: 8px;
                padding: 6px 10px;
                font-size: 12px;
                font-weight: 400;
            }}
            """
        )

    def show_for(self, anchor: QWidget, text: str):
        self._prepare(text)
        visible_w = max(0, self.width() - (2 * _SHADOW_MARGIN))
        global_pos = anchor.mapToGlobal(
            QPoint(
                (anchor.width() - visible_w) // 2 - _SHADOW_MARGIN,
                anchor.height() + 8 - _SHADOW_MARGIN,
            )
        )
        self._place_at(global_pos)

    def show_at_cursor(self, text: str, offset: QPoint | None = None):
        self._prepare(text)
        self.move_to_cursor(offset)

    def move_to_cursor(self, offset: QPoint | None = None):
        if offset is None:
            offset = QPoint(15, -9)
        self._place_at(QCursor.pos() + offset)

    def _prepare(self, text: str):
        self._apply_style()
        self._bubble.setText(text)
        self._bubble.adjustSize()
        self.adjustSize()

    def _place_at(self, global_pos: QPoint):
        screen = QApplication.screenAt(QCursor.pos()) or QApplication.screenAt(global_pos) or QApplication.primaryScreen()
        if screen is not None:
            rect = screen.availableGeometry()
            x = max(rect.left() + 8, min(global_pos.x(), rect.right() - self.width() - 8))
            y = max(rect.top() + 8, min(global_pos.y(), rect.bottom() - self.height() - 8))
            global_pos = QPoint(x, y)
        self.move(global_pos)
        self.show()


class _HoverHintController(QObject):
    def __init__(
        self,
        widget: QWidget,
        text: str,
        delay_ms: int = 450,
        follow_cursor: bool = False,
    ):
        super().__init__(widget)
        self._widget = widget
        self._text = str(text or "")
        self._follow_cursor = follow_cursor
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(max(0, delay_ms))
        self._timer.timeout.connect(self._show_hint)
        if follow_cursor:
            self._popup = _HoverHintPopup(
                blur_radius=1, offset=(3, 3), color_alpha=30
            )
        else:
            self._popup = _HoverHintPopup()
        widget.setToolTip("")
        widget.installEventFilter(self)
        widget.destroyed.connect(self._cleanup)
        self._apply_tracking()

    def _apply_tracking(self):
        if self._widget is None or not self._follow_cursor:
            return
        self._widget.setMouseTracking(True)
        self._widget.setAttribute(Qt.WidgetAttribute.WA_Hover, True)

    def _show_hint(self):
        if self._widget is None:
            return
        if not self._text:
            return
        if not self._widget.isVisible() or not self._widget.underMouse():
            return
        if self._follow_cursor:
            self._popup.show_at_cursor(self._text)
        else:
            self._popup.show_for(self._widget, self._text)

    def _hide_hint(self):
        self._timer.stop()
        self._popup.hide()

    def _cleanup(self, *_args):
        self._hide_hint()
        self._widget = None
        self._popup.deleteLater()

    def set_text(
        self,
        text: str,
        delay_ms: int | None = None,
        follow_cursor: bool | None = None,
    ):
        self._text = str(text or "")
        if delay_ms is not None:
            self._timer.setInterval(max(0, delay_ms))
        if follow_cursor is not None:
            self._follow_cursor = follow_cursor
            self._apply_tracking()
        was_visible = self._popup.isVisible()
        if was_visible and self._follow_cursor and self._text:
            self._popup.show_at_cursor(self._text)
        else:
            self._hide_hint()
        if self._widget is not None:
            self._widget.setToolTip("")

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        event_type = event.type()
        if event_type in (QEvent.Type.Enter, QEvent.Type.HoverEnter):
            if self._follow_cursor or self._timer.interval() <= 0:
                self._show_hint()
            else:
                self._timer.start()
            return False
        if event_type == QEvent.Type.ToolTip:
            return True
        if self._follow_cursor and event_type in (
            QEvent.Type.MouseMove,
            QEvent.Type.HoverMove,
        ):
            if self._popup.isVisible():
                self._popup.move_to_cursor()
            elif self._widget is not None and self._widget.underMouse():
                self._show_hint()
            return False
        if event_type in (
            QEvent.Type.Leave,
            QEvent.Type.HoverLeave,
            QEvent.Type.Hide,
            QEvent.Type.MouseButtonPress,
            QEvent.Type.FocusOut,
        ):
            self._hide_hint()
        return super().eventFilter(watched, event)


class CursorFollowHint:
    """키/상태 기반으로 즉시 띄우는 커서 따라다니는 힌트.

    위젯 Enter 대기나 QApplication.keyboardModifiers()에 의존하지 않는다.
    메인화면 드롭다운 follow_cursor 툴팁과 같은 팝업을 쓴다.
    """

    def __init__(self, owner: QWidget | None = None):
        self._popup = _HoverHintPopup(
            blur_radius=1, offset=(3, 3), color_alpha=30
        )
        self._text = ""
        if owner is not None:
            owner.destroyed.connect(self._cleanup)

    def show(self, text: str) -> None:
        text = str(text or "")
        if not text:
            self.hide()
            return
        if self._popup.isVisible() and self._text == text:
            self._popup.move_to_cursor()
            return
        self._text = text
        self._popup.show_at_cursor(text)

    def move(self) -> None:
        if self._popup.isVisible():
            self._popup.move_to_cursor()

    def hide(self) -> None:
        self._text = ""
        self._popup.hide()

    def is_visible(self) -> bool:
        return self._popup.isVisible()

    def _cleanup(self, *_args):
        self.hide()
        self._popup.deleteLater()


def set_hover_hint(
    widget: QWidget,
    text: str,
    delay_ms: int = 450,
    follow_cursor: bool = False,
):
    controller = getattr(widget, "_hover_hint_controller", None)
    if isinstance(controller, _HoverHintController):
        controller.set_text(text, delay_ms=delay_ms, follow_cursor=follow_cursor)
        return controller

    controller = _HoverHintController(
        widget, text, delay_ms=delay_ms, follow_cursor=follow_cursor
    )
    setattr(widget, "_hover_hint_controller", controller)
    return controller


def install_hover_hint(
    widget: QWidget,
    text: str,
    delay_ms: int = 450,
    follow_cursor: bool = False,
):
    return set_hover_hint(widget, text, delay_ms=delay_ms, follow_cursor=follow_cursor)
