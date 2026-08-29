"""
自定义 Toggle Switch 控件，替代 QCheckBox 实现更现代的滑块开关。
"""

from ui.theme import _to_qcolor, get_current_theme_colors
from PyQt6.QtCore import (
    QEasingCurve,
    QPointF,
    QPropertyAnimation,
    QRectF,
    Qt,
    pyqtProperty,
    pyqtSignal,
)
from PyQt6.QtGui import QBrush, QColor, QLinearGradient, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import QWidget


class ToggleSwitch(QWidget):
    """iOS / Material 风格的滑块开关"""

    stateChanged = pyqtSignal(int)  # 0 or 2, compatible with QCheckBox

    def __init__(self, parent=None, checked=False):
        super().__init__(parent)
        self._checked = checked
        self._hovered = False
        self._handle_position = 1.0 if checked else 0.0
        self._animation = QPropertyAnimation(self, b"handlePosition", self)
        self._animation.setEasingCurve(QEasingCurve.Type.InOutCubic)
        self._animation.setDuration(200)

        self.setFixedSize(44, 24)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def isChecked(self) -> bool:
        return self._checked

    def setChecked(self, checked: bool):
        if self._checked != checked:
            self._checked = checked
            self._animate(checked)

    def setCheckedNoSignal(self, checked: bool):
        """设置状态但不触发信号和动画"""
        self._checked = checked
        self._handle_position = 1.0 if checked else 0.0
        self.update()

    @pyqtProperty(float)
    def handlePosition(self):
        return self._handle_position

    @handlePosition.setter
    def handlePosition(self, pos):
        self._handle_position = pos
        self.update()

    def _animate(self, checked: bool):
        self._animation.stop()
        self._animation.setStartValue(self._handle_position)
        self._animation.setEndValue(1.0 if checked else 0.0)
        self._animation.start()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._checked = not self._checked
            self._animate(self._checked)
            self.stateChanged.emit(2 if self._checked else 0)
        super().mousePressEvent(event)

    def enterEvent(self, event):
        self._hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hovered = False
        self.update()
        super().leaveEvent(event)

    @staticmethod
    def _mix_color(foreground: QColor, background: QColor, ratio: float) -> QColor:
        inv = 1.0 - ratio
        return QColor(
            int(foreground.red() * ratio + background.red() * inv),
            int(foreground.green() * ratio + background.green() * inv),
            int(foreground.blue() * ratio + background.blue() * inv),
            255,
        )

    @staticmethod
    def _blend_with_background(color: QColor, bg: QColor) -> QColor:
        """将半透明的主题色与不透明卡片背景色进行预混合，渲染出高级且柔和的实心色彩"""
        alpha = color.alpha() / 255.0
        return QColor(
            int(color.red() * alpha + bg.red() * (1.0 - alpha)),
            int(color.green() * alpha + bg.green() * (1.0 - alpha)),
            int(color.blue() * alpha + bg.blue() * (1.0 - alpha)),
            255
        )

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height()
        radius = h / 2.0
        handle_radius = h / 2.0 - 3.0
        pos = self._handle_position

        # 背景轨道
        track_path = QPainterPath()
        track_path.addRoundedRect(QRectF(0, 0, w, h), radius, radius)

        c = get_current_theme_colors()
        # 读取当前主题的卡片背景色作为混合基色，若不合法则兜底为白色
        bg = _to_qcolor(c.get("bg_card", "#ffffff"))
        if not bg.isValid():
            bg = QColor(255, 255, 255)
        bg.setAlpha(255)

        # 混合出高级感软色（避开刺眼的纯黑/纯高饱和蓝色）
        track_off = self._blend_with_background(_to_qcolor(c["btn_soft_bg"]), bg)
        track_off_soft = self._blend_with_background(_to_qcolor(c["bg_surface_soft"]), bg)
        track_on_start = self._blend_with_background(_to_qcolor(c["btn_primary_bg"]), bg)
        track_on_end = self._blend_with_background(_to_qcolor(c["btn_primary_hover"]), bg)
        border_off = self._blend_with_background(_to_qcolor(c["btn_soft_border"]), bg)
        border_on = self._blend_with_background(_to_qcolor(c["btn_primary_border"]), bg)
        
        handle_off = _to_qcolor(c["bg_surface_raised"])
        handle_on = _to_qcolor(c["btn_primary_text"])
        shadow_color = _to_qcolor(c["shadow_color"])

        if self._hovered and pos < 1.0:
            hover_color = self._blend_with_background(_to_qcolor(c["btn_soft_hover"]), bg)
            track_off = self._mix_color(hover_color, track_off, 0.30)

        gradient = QLinearGradient(0, 0, w, 0)
        gradient.setColorAt(0.0, self._mix_color(track_on_start, track_off, pos))
        gradient.setColorAt(1.0, self._mix_color(track_on_end, track_off_soft, pos))
        p.fillPath(track_path, QBrush(gradient))

        # 轨道边框（柔和渐变）
        border_color = self._mix_color(border_on, border_off, pos)
        p.setPen(QPen(border_color, 1.0))
        p.drawPath(track_path)

        # 滑块手柄
        handle_x = 3.0 + pos * (w - 2 * 3.0 - 2 * handle_radius)
        handle_y = h / 2.0

        # 手柄阴影（调淡阴影使视觉更干净）
        shadow_color.setAlpha(30 if self._checked else 20)
        p.setBrush(QBrush(shadow_color))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QPointF(handle_x + handle_radius + 0.5, handle_y + 0.5), handle_radius, handle_radius)

        # 手柄本体
        handle_color = self._mix_color(handle_on, handle_off, pos)
        handle_border = self._mix_color(border_on, border_off, pos)
        p.setBrush(QBrush(handle_color))
        p.setPen(QPen(handle_border, 1.0))
        p.drawEllipse(QPointF(handle_x + handle_radius, handle_y), handle_radius, handle_radius)

        p.end()

    def sizeHint(self):
        from PyQt6.QtCore import QSize
        return QSize(44, 24)
