"""
Toast通知组件
用于显示操作状态的非阻塞通知
"""
import os
import platform
import subprocess

from services import get_i18n_manager
from ui.theme import get_current_theme, get_current_theme_colors
from PyQt6.QtCore import QEasingCurve, QPoint, QPropertyAnimation, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QCursor, QFont
from PyQt6.QtWidgets import QGraphicsDropShadowEffect, QLabel


# Canvas(graphics_view) 좌상단 기준 토스트 앵커 (top-left, not center)
TOAST_ANCHOR_X = 80
TOAST_ANCHOR_Y = 50


def _t(key: str) -> str:
    """i18n 번역 헬퍼 (editor 쪽 다른 서비스들과 동일한 패턴)"""
    i18n = get_i18n_manager()
    if i18n:
        return i18n.translate(key)
    return key


class ToastNotification(QLabel):
    """Toast通知组件"""
    
    clicked = pyqtSignal(str)  # 点击事件，传递附加数据（如文件路径）
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.ToolTip | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        # 不使用WA_TranslucentBackground，保持背景可见
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setObjectName("toast_notification")
        
        self._apply_style(success=True, clickable=False)
        self.setAutoFillBackground(True)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setWordWrap(True)
        self.setMaximumWidth(800)
        self.setMargin(0)
        
        # 设置字体
        font = QFont()
        font.setPointSize(10)
        font.setWeight(QFont.Weight.DemiBold)
        self.setFont(font)
        
        # 阴影和透明度效果链
        self.shadow_effect = QGraphicsDropShadowEffect(self)
        self.shadow_effect.setBlurRadius(28)
        self.shadow_effect.setOffset(0, 8)
        self.shadow_effect.setColor(QColor(0, 0, 0, 85))
        self.setGraphicsEffect(self.shadow_effect)
        
        # 动画
        self.fade_animation = QPropertyAnimation(self, b"windowOpacity")
        self.fade_animation.setDuration(300)
        self.fade_animation.setEasingCurve(QEasingCurve.Type.InOutQuad)
        
        # 自动关闭定时器
        self.auto_close_timer = QTimer()
        self.auto_close_timer.timeout.connect(self.fade_out)
        
        # 附加数据（如文件路径）
        self._extra_data = None
        self._clickable = False

    def _apply_style(self, success: bool, clickable: bool):
        c = get_current_theme_colors()
        is_light = get_current_theme() == "light"
        if success:
            background = c["bg_surface_raised"]
            border = c["border_card"]
            text = c["text_accent"]
            accent = c["cta_gradient_start"] if clickable else c["success_color"]
        else:
            background = "#FFF5F4" if is_light else c["bg_surface_raised"]
            border = c["danger_border"]
            text = "#8A2621" if is_light else c["danger_text"]
            accent = c["danger_bg"]

        self.setStyleSheet(f"""
            QLabel#toast_notification {{
                background-color: {background};
                color: {text};
                border: 1px solid {border};
                border-left: 4px solid {accent};
                border-radius: 12px;
                padding: 10px 20px 10px 16px;
                font-size: 13px;
                font-weight: 600;
            }}
            QLabel#toast_notification[clickable="true"] {{
                border-color: {accent};
                color: {text};
            }}
            QLabel#toast_notification[clickable="true"]:hover {{
                background-color: {c["bg_panel"]};
            }}
            QLabel#toast_notification[clickable="false"] {{
                color: {text};
            }}
        """)

    def _resolve_anchor_widget(self):
        """그림이 그려지는 캔버스(graphics_view)를 우선 앵커로 사용."""
        parent_widget = self.parent()
        if parent_widget is None:
            return None
        graphics_view = getattr(parent_widget, "graphics_view", None)
        if graphics_view is not None:
            return graphics_view
        return parent_widget

    def place_on_canvas(self):
        """캔버스 좌상단 기준 (TOAST_ANCHOR_X, TOAST_ANCHOR_Y)에 토스트 top-left를 배치.
        연속 표시 시 같은 위치에 덮어 올림 (스택 오프셋 없음)."""
        anchor = self._resolve_anchor_widget()
        if anchor is not None:
            origin = anchor.mapToGlobal(QPoint(TOAST_ANCHOR_X, TOAST_ANCHOR_Y))
            self.move(origin.x(), origin.y())
            return

        from PyQt6.QtWidgets import QApplication
        screen = QApplication.primaryScreen().geometry()
        self.move(screen.x() + TOAST_ANCHOR_X, screen.y() + TOAST_ANCHOR_Y)
    
    def show_toast(self, message, duration=3000, success=True, clickable_path=None):
        """
        显示Toast通知
        
        Args:
            message: 显示的消息
            duration: 显示持续时间（毫秒）
            success: 是否为成功消息（影响颜色）
            clickable_path: 可点击的路径（如果提供，Toast可点击打开文件夹）
        """
        # 设置可点击
        self._clickable = clickable_path is not None
        self._extra_data = clickable_path
        self.setProperty("clickable", self._clickable)
        self._apply_style(success, self._clickable)
        self.setAutoFillBackground(True)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setWordWrap(True)
        self.setMaximumWidth(800)

        display_message = message
        if self._clickable:
            self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            # 可点击时添加完整提示
            display_message = message + "\n" + _t("Click to open containing folder")
        else:
            self.setCursor(QCursor(Qt.CursorShape.ArrowCursor))
        self.setText(display_message)
        
        # 调整大小后重新计算尺寸
        self.adjustSize()
        
        # 캔버스 좌상단 앵커 — top-left 기준, 항상 동일 좌표
        self.place_on_canvas()
        
        # 淡入动画
        self.fade_in()
        
        # 设置自动关闭 - 确保在主线程
        if duration > 0:
            self.auto_close_timer.stop()  # 先停止旧的timer
            self.auto_close_timer.start(duration)
    
    def fade_in(self):
        """淡入动画"""
        self.setWindowOpacity(0.0)
        self.show()
        self.fade_animation.setStartValue(0)
        self.fade_animation.setEndValue(1)
        self.fade_animation.start()
    
    def fade_out(self):
        """淡出动画"""
        self.auto_close_timer.stop()
        self.fade_animation.stop()  # 停止可能正在进行的动画
        self.fade_animation.setStartValue(self.windowOpacity())
        self.fade_animation.setEndValue(0)
        # 断开之前的连接，避免重复连接
        try:
            self.fade_animation.finished.disconnect()
        except Exception:
            pass
        self.fade_animation.finished.connect(self.close)  # 用close替代hide，确保销毁
        self.fade_animation.start()
    
    def mousePressEvent(self, event):
        """处理鼠标点击事件"""
        if self._clickable and self._extra_data:
            self.open_file_location(self._extra_data)
            self.clicked.emit(self._extra_data)
        self.fade_out()
    
    @staticmethod
    def open_file_location(file_path):
        """打开文件所在文件夹并选中文件"""
        if not os.path.exists(file_path):
            return
        
        system = platform.system()
        
        try:
            if system == "Windows":
                # Windows: 使用 explorer /select,<路径>
                subprocess.run(['explorer', '/select,', os.path.normpath(file_path)])
            elif system == "Darwin":  # macOS
                # macOS: 使用 open -R <路径>
                subprocess.run(['open', '-R', file_path])
            else:  # Linux
                # Linux: 打开文件所在目录
                folder_path = os.path.dirname(file_path)
                subprocess.run(['xdg-open', folder_path])
        except Exception as e:
            print(f"파일 위치를 열 수 없습니다: {e}")


class ToastManager:
    """Toast管理器，管理多个Toast的显示"""
    
    def __init__(self, parent):
        self.parent = parent
        self.active_toasts = []
    
    def show_toast(self, message, duration=3000, success=True, clickable_path=None):
        """显示一个Toast通知"""
        # 清理已关闭的Toast
        self.active_toasts = [toast for toast in self.active_toasts if toast.isVisible()]
        
        # 새 토스트는 같은 좌표에 덮어 올림 (이전 토스트는 각자 duration 후 사라짐)
        toast = ToastNotification(self.parent)
        toast.show_toast(message, duration, success, clickable_path)
        self.active_toasts.append(toast)
        
        return toast
    
    def show_success(self, message, duration=3000, clickable_path=None):
        """显示成功Toast"""
        return self.show_toast(message, duration, True, clickable_path)
    
    def show_error(self, message, duration=3000):
        """显示错误Toast"""
        return self.show_toast(message, duration, False, None)
    
    def show_info(self, message, duration=3000):
        """显示信息Toast"""
        return self.show_toast(message, duration, True, None)
    
    def close_all(self):
        """关闭所有活跃的Toast"""
        for toast in self.active_toasts:
            if toast.isVisible():
                toast.fade_out()
        self.active_toasts.clear()
