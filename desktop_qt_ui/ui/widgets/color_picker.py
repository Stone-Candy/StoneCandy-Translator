
import logging

from ui.styles import build_menu_stylesheet, color_dialog_stylesheet
from ui.theme import _to_qcolor, get_current_theme_colors
from PyQt6.QtCore import QEvent, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QAction, QColor, QCursor, QFont, QIcon, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import (
    QApplication,
    QColorDialog,
    QFrame,
    QHBoxLayout,
    QMenu,
    QPushButton,
    QSizePolicy,
    QToolButton,
    QWidget,
)
from ui.widgets.hover_hint import set_hover_hint

logger = logging.getLogger('manga_translator')


# ═══════════════════════════════════════════════════════════════
#  ScreenColorPicker — 全屏自定义屏幕取色器
# ═══════════════════════════════════════════════════════════════

class ScreenColorPicker(QWidget):
    """全屏屏幕取色器：稳定十字光标 + 像素放大镜 + 实时颜色/RGB 预览。

    - 左键点击拾取颜色
    - 右键 / ESC 取消
    """

    color_picked = pyqtSignal(QColor)
    canceled = pyqtSignal()

    MAG_N = 11        # 放大区域边长(像素，奇数)
    MAG_S = 10        # 每像素放大倍数
    OFFSET = 25       # 预览框离光标偏移

    def __init__(self):
        super().__init__(None)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.BlankCursor)

        self._color = QColor(0, 0, 0)
        self._mpos = QCursor.pos()
        self._shot: QPixmap | None = None
        self._img = None
        self._dpr = 1.0

    # ── 公开接口 ──────────────────────────────────────────────

    def start(self):
        screen = QApplication.primaryScreen()
        if not screen:
            return
        geo = screen.virtualGeometry()
        self._shot = screen.grabWindow(0, geo.x(), geo.y(), geo.width(), geo.height())
        self._img = self._shot.toImage()
        self._dpr = self._shot.devicePixelRatio()
        self.setGeometry(geo)
        self.show()
        self.activateWindow()
        self.raise_()

    # ── 内部 ──────────────────────────────────────────────────

    def _px_color(self, lx, ly):
        if self._img is None:
            return QColor(0, 0, 0)
        px, py = int(lx * self._dpr), int(ly * self._dpr)
        if 0 <= px < self._img.width() and 0 <= py < self._img.height():
            return self._img.pixelColor(px, py)
        return QColor(0, 0, 0)

    # ── 绘制 ──────────────────────────────────────────────────

    def paintEvent(self, _event):
        if self._shot is None:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.drawPixmap(self.rect(), self._shot)
        p.fillRect(self.rect(), QColor(0, 0, 0, 15))

        loc = self.mapFromGlobal(self._mpos)
        cx, cy = loc.x(), loc.y()
        self._draw_cross(p, cx, cy)
        self._draw_panel(p, cx, cy)
        p.end()

    def _draw_cross(self, p, x, y):
        gap, ln = 6, 22
        for c, w in [(QColor(0, 0, 0, 160), 3), (QColor(255, 255, 255, 220), 1)]:
            p.setPen(QPen(c, w))
            p.drawLine(x - ln, y, x - gap, y)
            p.drawLine(x + gap, y, x + ln, y)
            p.drawLine(x, y - ln, x, y - gap)
            p.drawLine(x, y + gap, x, y + ln)

    def _draw_panel(self, p, cx, cy):
        n, s = self.MAG_N, self.MAG_S
        mag = n * s
        pad = 12
        pw = mag + pad * 2
        ph = pad + mag + 8 + 50 + pad

        # 位置（避免出屏）
        off = self.OFFSET
        bx = cx + off if cx + off + pw <= self.width() else cx - off - pw
        by = cy + off if cy + off + ph <= self.height() else cy - off - ph
        bx, by = max(bx, 0), max(by, 0)

        # 背景
        p.setBrush(QColor(24, 24, 28, 235))
        p.setPen(QPen(QColor(70, 70, 70), 1))
        p.drawRoundedRect(bx, by, pw, ph, 8, 8)

        # 放大镜
        mx, my = bx + pad, by + pad
        half = n // 2
        for dy in range(n):
            for dx in range(n):
                p.fillRect(mx + dx * s, my + dy * s, s, s,
                           self._px_color(cx - half + dx, cy - half + dy))

        # 网格
        p.setPen(QPen(QColor(50, 50, 50, 80), 1))
        for i in range(1, n):
            p.drawLine(mx + i * s, my, mx + i * s, my + mag)
            p.drawLine(mx, my + i * s, mx + mag, my + i * s)
        p.setPen(QPen(QColor(100, 100, 100), 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(mx, my, mag, mag)
        # 中心高亮
        p.setPen(QPen(QColor(255, 255, 255), 2))
        p.drawRect(mx + half * s, my + half * s, s, s)

        # 颜色信息
        iy = my + mag + 10
        sw = 26
        p.setBrush(self._color)
        p.setPen(QPen(QColor(180, 180, 180), 1))
        p.drawRoundedRect(mx, iy, sw, sw, 3, 3)

        tx = mx + sw + 8
        f = QFont("Consolas", 10)
        f.setBold(True)
        p.setFont(f)
        p.setPen(QColor(240, 240, 240))
        p.drawText(tx, iy + 12, self._color.name().upper())
        f.setBold(False)
        f.setPointSize(9)
        p.setFont(f)
        p.setPen(QColor(180, 180, 180))
        r, g, b = self._color.red(), self._color.green(), self._color.blue()
        p.drawText(tx, iy + 26, f"R:{r} G:{g} B:{b}")

    # ── 事件 ──────────────────────────────────────────────────

    def mouseMoveEvent(self, ev):
        self._mpos = ev.globalPosition().toPoint()
        loc = self.mapFromGlobal(self._mpos)
        self._color = self._px_color(loc.x(), loc.y())
        self.update()

    def mousePressEvent(self, ev):
        if ev.button() == Qt.MouseButton.LeftButton:
            self.color_picked.emit(self._color)
            self.close()
        elif ev.button() == Qt.MouseButton.RightButton:
            self.canceled.emit()
            self.close()

    def keyPressEvent(self, ev):
        if ev.key() == Qt.Key.Key_Escape:
            self.canceled.emit()
            self.close()


class _DialogColorGridOverlay(QWidget):
    """Overlay grid lines on top of QColorDialog well arrays for better swatch contrast."""

    def __init__(self, host: QWidget, rows: int, cols: int = 8):
        super().__init__(host)
        self._rows = max(1, rows)
        self._cols = max(1, cols)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        host.installEventFilter(self)
        self._sync_geometry()
        self.show()
        self.raise_()

    def _sync_geometry(self):
        host = self.parentWidget()
        if host is None:
            return
        self.setGeometry(host.rect())
        self.raise_()

    def eventFilter(self, obj, event):
        if obj is self.parentWidget() and event.type() in (
            QEvent.Type.Resize,
            QEvent.Type.Show,
            QEvent.Type.Move,
        ):
            self._sync_geometry()
        return super().eventFilter(obj, event)

    def paintEvent(self, _event):
        c = get_current_theme_colors()
        outer_pen = QPen(_to_qcolor(c["border_input_hover"]))
        outer_pen.setCosmetic(True)
        outer_pen.setWidth(1)

        inner_pen = QPen(_to_qcolor(c["border_input"]))
        inner_pen.setCosmetic(True)
        inner_pen.setWidth(1)

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        rect = self.rect().adjusted(0, 0, -1, -1)

        painter.setPen(outer_pen)
        painter.drawRect(rect)

        cell_width = rect.width() / float(self._cols)
        cell_height = rect.height() / float(self._rows)

        painter.setPen(inner_pen)
        for col in range(1, self._cols):
            x = round(rect.left() + col * cell_width)
            painter.drawLine(x, rect.top() + 1, x, rect.bottom() - 1)
        for row in range(1, self._rows):
            y = round(rect.top() + row * cell_height)
            painter.drawLine(rect.left() + 1, y, rect.right() - 1, y)

        painter.end()


# ═══════════════════════════════════════════════════════════════
#  ColorPickerWidget
# ═══════════════════════════════════════════════════════════════

class ColorPickerWidget(QWidget):
    """可复用的颜色选择器组件，包含颜色按钮和常用颜色菜单。"""

    color_changed = pyqtSignal(str)  # 颜色变化时发出 hex 颜色值

    # 类级别的颜色剪贴板，所有实例共享
    _color_clipboard = None

    def __init__(self, dialog_title="Select color", default_color="#000000",
                 config_key="saved_colors", config_service=None, i18n_func=None,
                 parent=None):
        super().__init__(parent)
        self.setObjectName("color_picker_root")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self._dialog_title = dialog_title
        self._default_color = default_color
        self._current_color = default_color
        self._config_key = config_key
        self._config_service = config_service
        self._t = i18n_func or (lambda s, **kw: s)

        self._saved_colors = []
        self._load_saved_colors()
        self._init_ui()
        self._connect_signals()

    # ── UI ────────────────────────────────────────────────────────

    def _init_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # 主颜色按钮
        self.color_button = QPushButton()
        self.color_button.setObjectName("color_picker_swatch")
        self.color_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.color_button.setFixedWidth(61)
        set_hover_hint(self.color_button, self._t("Click to select color"))
        layout.addWidget(self.color_button, 0)

        self.saved_colors_button = QToolButton()
        self.saved_colors_button.setObjectName("color_picker_saved_button")
        self.saved_colors_button.setText("▾")
        set_hover_hint(self.saved_colors_button, self._t("Saved colors menu"))
        self.saved_colors_button.setFixedWidth(28)
        self.saved_colors_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        layout.addWidget(self.saved_colors_button, 0)

        self._apply_component_theme()
        self._update_color_tooltips(self._current_color)
        self._rebuild_saved_colors_menu()

    def _connect_signals(self):
        self.color_button.clicked.connect(self._on_color_clicked)

    # ── Public API ────────────────────────────────────────────────

    def set_color(self, hex_color: str):
        """设置当前颜色（更新按钮样式和 RGB 标签），不发射信号。"""
        self._current_color = hex_color
        self._apply_component_theme()
        self._update_color_tooltips(hex_color)

    def get_color(self) -> str:
        """获取当前颜色 hex 值。"""
        return self._current_color

    def reset(self, default_color: str | None = None):
        """重置为默认颜色，不发射信号。"""
        color = default_color or self._default_color
        self.set_color(color)

    def refresh_ui_texts(self):
        """语言切换时刷新按钮文本。"""
        self.refresh_theme()

    def refresh_theme(self):
        """主题切换时刷新组件自身和常用颜色菜单样式。"""
        self._apply_component_theme()
        self._update_color_tooltips(self._current_color)
        self._rebuild_saved_colors_menu()

    def _apply_component_theme(self):
        c = get_current_theme_colors()
        self.setStyleSheet(
            f"""
            QWidget#color_picker_root {{
                background: transparent;
                border: none;
            }}
            QPushButton#color_picker_swatch {{
                background: {self._current_color};
                border: 1px solid {c["checkbox_border"]};
                border-radius: 8px;
                padding: 0px;
                min-height: 30px;
            }}
            QPushButton#color_picker_swatch:hover {{
                border-color: {c["checkbox_hover_border"]};
            }}
            QPushButton#color_picker_swatch:pressed {{
                border-color: {c["checkbox_hover_border"]};
            }}
            QToolButton#color_picker_saved_button {{
                background: {c["btn_soft_bg"]};
                border: 1px solid {c["btn_soft_border"]};
                border-radius: 8px;
                color: {c["btn_soft_text"]};
                padding: 0px;
                min-height: 28px;
                font-size: 17px;
                font-weight: 700;
            }}
            QToolButton#color_picker_saved_button:hover {{
                background: {c["btn_soft_hover"]};
                border-color: {c["border_input_hover"]};
            }}
            QToolButton#color_picker_saved_button:pressed {{
                background: {c["btn_soft_pressed"]};
                border-color: {c["btn_soft_checked_border"]};
            }}
            QToolButton#color_picker_saved_button::menu-indicator {{
                image: none;
                width: 0px;
            }}
            """
        )

    # ── 颜色对话框 ───────────────────────────────────────────────

    def _on_color_clicked(self):
        current = QColor(self._current_color) if self._current_color else QColor("black")

        dialog = QColorDialog(current, self)
        dialog.setWindowTitle(self._t(self._dialog_title))
        dialog.setOption(QColorDialog.ColorDialogOption.DontUseNativeDialog, True)
        dialog.setOption(QColorDialog.ColorDialogOption.ShowAlphaChannel, False)
        dialog.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        dialog.setStyleSheet(color_dialog_stylesheet())
        QTimer.singleShot(0, lambda d=dialog: self._style_dialog_private_widgets(d))

        # 将保存的常用颜色加载到对话框的自定义颜色槽
        for i, color_hex in enumerate(self._saved_colors[:16]):
            dialog.setCustomColor(i, QColor(color_hex))

        # 替换内置的屏幕取色按钮
        self._hook_screen_picker(dialog)

        if dialog.exec() == QColorDialog.DialogCode.Accepted:
            hex_color = dialog.currentColor().name()
            self._apply_color(hex_color)

            # 自动保存到常用颜色
            if hex_color not in self._saved_colors:
                self._saved_colors.insert(0, hex_color)
                if len(self._saved_colors) > 20:
                    self._saved_colors = self._saved_colors[:20]
                self._persist_saved_colors()
                self._rebuild_saved_colors_menu()

    def _hook_screen_picker(self, dialog):
        """查找并替换 QColorDialog 内置的 '拾取屏幕颜色' 按钮行为。"""
        for btn in dialog.findChildren(QPushButton):
            text = btn.text()
            if '拾取' in text or 'pick' in text.lower() or 'screen' in text.lower():
                try:
                    btn.clicked.disconnect()
                except (TypeError, RuntimeError):
                    pass
                btn.clicked.connect(
                    lambda _checked=False, d=dialog: self._launch_screen_pick(d)
                )
                break

    def _launch_screen_pick(self, dialog):
        """隐藏对话框 → 截屏 → 启动自定义取色器。"""
        dialog.hide()
        QTimer.singleShot(150, lambda: self._do_screen_pick(dialog))

    def _do_screen_pick(self, dialog):
        picker = ScreenColorPicker()

        def on_picked(color):
            # QColorDialog 非原生实现的 setCurrentColor 无法可靠同步内部子控件，
            # 导致点击 OK 后 currentColor() 仍返回旧值。
            # 解决方案：直接关闭对话框并手动应用拾取到的颜色。
            hex_color = color.name()
            dialog.close()
            self._apply_color(hex_color)
            # 同步保存到常用颜色
            if hex_color not in self._saved_colors:
                self._saved_colors.insert(0, hex_color)
                if len(self._saved_colors) > 20:
                    self._saved_colors = self._saved_colors[:20]
                self._persist_saved_colors()
                self._rebuild_saved_colors_menu()

        def on_cancel():
            dialog.show()
            dialog.activateWindow()
            dialog.raise_()

        picker.color_picked.connect(on_picked)
        picker.canceled.connect(on_cancel)
        # 保持引用防止被 GC
        self._screen_picker = picker
        picker.start()

    def _apply_color(self, hex_color: str):
        """应用颜色并发射信号。"""
        self.set_color(hex_color)
        self.color_changed.emit(hex_color)

    # ── 复制 / 粘贴 ──────────────────────────────────────────────

    def _on_copy(self):
        if self._current_color:
            ColorPickerWidget._color_clipboard = self._current_color
            for widget in self._all_instances():
                widget._rebuild_saved_colors_menu()

    def _on_paste(self):
        if ColorPickerWidget._color_clipboard:
            self._apply_color(ColorPickerWidget._color_clipboard)

    def _all_instances(self):
        """获取同一父层级中所有 ColorPickerWidget 实例。"""
        top = self.window()
        if top:
            return top.findChildren(ColorPickerWidget)
        return [self]

    # ── RGB 标签 ──────────────────────────────────────────────────

    def _update_color_tooltips(self, hex_color: str):
        try:
            c = QColor(hex_color)
            rgb_text = f"{c.red()},{c.green()},{c.blue()}"
            tooltip = f"{c.name().upper()} | RGB: {rgb_text}"
            set_hover_hint(self.color_button, tooltip)
            set_hover_hint(self.saved_colors_button, tooltip)
        except Exception:
            set_hover_hint(self.color_button, self._t("Click to select color"))
            set_hover_hint(self.saved_colors_button, self._t("Saved colors menu"))

    # ── 常用颜色菜单 ─────────────────────────────────────────────

    def _rebuild_saved_colors_menu(self):
        menu = QMenu(self)
        menu.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        menu.setStyleSheet(self._menu_stylesheet())

        current_color = QColor(self._current_color) if self._current_color else QColor()
        if current_color.isValid():
            current_action = QAction(self)
            current_action.setEnabled(False)
            current_action.setIcon(self._create_color_icon(current_color.name()))
            current_action.setText(
                f"{current_color.name().upper()}  (R:{current_color.red()} G:{current_color.green()} B:{current_color.blue()})"
            )
            menu.addAction(current_action)
            menu.addSeparator()

        copy_action = QAction(self._t("Copy current color"), self)
        copy_action.triggered.connect(self._on_copy)
        menu.addAction(copy_action)

        paste_action = QAction(self._t("Paste copied color"), self)
        paste_action.setEnabled(ColorPickerWidget._color_clipboard is not None)
        paste_action.triggered.connect(self._on_paste)
        menu.addAction(paste_action)
        menu.addSeparator()

        if self._saved_colors:
            for color_hex in self._saved_colors:
                action = QAction(self)
                action.setIcon(self._create_color_icon(color_hex))
                c = QColor(color_hex)
                action.setText(f"{color_hex}  (R:{c.red()} G:{c.green()} B:{c.blue()})")
                action.triggered.connect(lambda checked, ch=color_hex: self._apply_color(ch))
                menu.addAction(action)
            menu.addSeparator()

        save_action = QAction(self._t("Save current color"), self)
        save_action.triggered.connect(self._save_current_color)
        menu.addAction(save_action)

        if self._saved_colors:
            clear_action = QAction(self._t("Clear saved colors"), self)
            clear_action.triggered.connect(self._clear_saved_colors)
            menu.addAction(clear_action)

        self.saved_colors_button.setMenu(menu)

    def _menu_stylesheet(self) -> str:
        c = get_current_theme_colors()
        return build_menu_stylesheet(c, include_separator=True)

    def _style_dialog_private_widgets(self, dialog: QColorDialog):
        c = get_current_theme_colors()
        overlays = []

        well_arrays = sorted(
            [
                widget
                for widget in dialog.findChildren(QWidget)
                if widget.metaObject().className() == "QtPrivate::QWellArray"
            ],
            key=lambda widget: widget.mapTo(dialog, widget.rect().topLeft()).y(),
        )
        for well in well_arrays:
            well.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
            well.setStyleSheet(
                f"border: 1px solid {c['border_input']};"
                f"background: {c['bg_surface_raised']};"
            )
            rows = 2 if well.height() <= 56 else max(2, round(well.height() / 24))
            overlays.append(_DialogColorGridOverlay(well, rows=rows))

        for widget in dialog.findChildren(QWidget):
            cls = widget.metaObject().className()
            if cls == "QtPrivate::QColorShowLabel":
                widget.setFrameShape(QFrame.Shape.Box)
                widget.setFrameShadow(QFrame.Shadow.Plain)
                widget.setLineWidth(1)
                widget.setStyleSheet(
                    f"border: 1px solid {c['border_input_hover']};"
                    f"background: transparent;"
                )
            elif cls in ("QtPrivate::QColorPicker", "QtPrivate::QColorLuminancePicker"):
                widget.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
                widget.setStyleSheet(
                    f"border: 1px solid {c['border_input']};"
                    f"background: transparent;"
                )

        dialog._color_dialog_theme_overlays = overlays

    def _save_current_color(self):
        if self._current_color and self._current_color not in self._saved_colors:
            self._saved_colors.insert(0, self._current_color)
            if len(self._saved_colors) > 20:
                self._saved_colors = self._saved_colors[:20]
            self._persist_saved_colors()
            self._rebuild_saved_colors_menu()

    def _clear_saved_colors(self):
        self._saved_colors = []
        self._persist_saved_colors()
        self._rebuild_saved_colors_menu()

    # ── 持久化 ────────────────────────────────────────────────────

    def _load_saved_colors(self):
        if not self._config_service:
            return
        try:
            config = self._config_service.get_config()
            colors = getattr(config.app, self._config_key, None)
            if colors:
                self._saved_colors = list(colors)
            else:
                self._saved_colors = []
        except Exception as e:
            logger.warning(f"저장된 색 로드 실패 ({self._config_key}): {e}")
            self._saved_colors = []

    def _persist_saved_colors(self):
        if not self._config_service:
            return
        try:
            self._config_service.update_config({
                'app': {
                    self._config_key: self._saved_colors
                }
            })
            self._config_service.save_config_file()
        except Exception as e:
            logger.error(f"색 저장 실패 ({self._config_key}): {e}")

    # ── 工具方法 ──────────────────────────────────────────────────

    @staticmethod
    def _create_color_icon(hex_color: str) -> QIcon:
        c = get_current_theme_colors()
        pixmap = QPixmap(16, 16)
        pixmap.fill(QColor(hex_color))
        painter = QPainter(pixmap)
        painter.setPen(QColor(c["border_input"]))
        painter.drawRect(0, 0, 15, 15)
        painter.end()
        return QIcon(pixmap)
