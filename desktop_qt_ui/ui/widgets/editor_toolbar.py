
import logging
import os

from PyQt6.QtCore import QByteArray, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QCursor, QIcon, QPainter, QPalette, QPixmap
from PyQt6.QtSvg import QSvgRenderer
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLayout,
    QPushButton,
    QSizePolicy,
    QToolButton,
    QWidget,
)
from services import get_i18n_manager
from utils.resource_helper import resource_path
from ui.widgets.hover_hint import set_hover_hint


class _OverflowClipHost(QWidget):
    """Keeps the child at its natural size and clips overflow instead of shrinking it."""

    def __init__(self, child: QWidget, parent=None):
        super().__init__(parent)
        self._child = child
        child.setParent(self)
        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        # Styled background makes Qt clip children to this widget's rect.
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet("background: transparent;")

    def sizeHint(self) -> QSize:
        return self._child.sizeHint()

    def minimumSizeHint(self) -> QSize:
        return QSize(0, max(self._child.sizeHint().height(), 1))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        hint = self._child.sizeHint()
        y = max(0, (event.size().height() - hint.height()) // 2)
        self._child.setGeometry(0, y, hint.width(), hint.height())


class EditorToolbar(QWidget):
    """
    编辑器顶部工具栏，包含返回、导出、撤销/重做、缩放、视图模式等全局操作。
    """
    # --- Define signals for all actions ---
    back_requested = pyqtSignal()
    export_requested = pyqtSignal()
    undo_requested = pyqtSignal()
    redo_requested = pyqtSignal()
    zoom_in_requested = pyqtSignal()
    zoom_out_requested = pyqtSignal()
    fit_window_requested = pyqtSignal()
    display_mode_changed = pyqtSignal(str)
    show_original_only_toggled = pyqtSignal(bool)
    align_requested = pyqtSignal(str)
    distribute_requested = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.i18n = get_i18n_manager()
        self._init_ui()
        self._connect_signals()
    
    def _t(self, key: str, **kwargs) -> str:
        """翻译辅助方法"""
        if self.i18n:
            return self.i18n.translate(key, **kwargs)
        return key

    def _init_ui(self):
        self.setMinimumWidth(0)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(11, 5, 5, 5)
        layout.setSpacing(10)

        # --- File Actions ---
        self.back_button = QToolButton()
        self.back_button.setText(self._t("Back"))
        set_hover_hint(self.back_button, self._t("Back to Main"))
        self.back_button.setObjectName("editor_back_button")
        layout.addWidget(self.back_button)

        self.export_button = QToolButton()
        self.export_button.setText(self._t("Export Image"))
        set_hover_hint(self.export_button, self._t("Export current rendered image") + " (Ctrl+S)")
        self.export_button.setObjectName("editor_export_button")
        layout.addWidget(self.export_button)

        layout.addWidget(self._create_separator())

        # --- Edit Actions ---
        self.undo_button = QToolButton()
        self.undo_button.setText(self._t("Undo"))
        self.undo_button.setEnabled(False)
        set_hover_hint(self.undo_button, self._t("Undo last operation") + " (Ctrl+Z)")
        self.undo_button.setObjectName("editor_undo_button")
        layout.addWidget(self.undo_button)

        self.redo_button = QToolButton()
        self.redo_button.setText(self._t("Redo"))
        self.redo_button.setEnabled(False)
        set_hover_hint(self.redo_button, self._t("Redo last undone operation") + " (Ctrl+Y)")
        self.redo_button.setObjectName("editor_redo_button")
        layout.addWidget(self.redo_button)

        layout.addWidget(self._create_separator())

        # --- View Actions ---
        self.zoom_out_button = QToolButton()
        self.zoom_out_button.setText(self._t("Zoom Out (-)"))
        self.zoom_out_button.setObjectName("editor_zoom_out_button")
        layout.addWidget(self.zoom_out_button)

        self.zoom_label = QLabel("100%")
        self.zoom_label.setMinimumWidth(40)
        self.zoom_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.zoom_label)

        self.zoom_in_button = QToolButton()
        self.zoom_in_button.setText(self._t("Zoom In (+)"))
        self.zoom_in_button.setObjectName("editor_zoom_in_button")
        layout.addWidget(self.zoom_in_button)

        self.fit_window_button = QToolButton()
        self.fit_window_button.setText(self._t("Fit to Window"))
        self.fit_window_button.setObjectName("editor_fit_window_button")
        layout.addWidget(self.fit_window_button)

        layout.addWidget(self._create_separator())

        # --- Display Mode ---
        # 创建一个容器来包装显示模式控件，确保它们作为一个整体
        display_mode_container = QWidget()
        display_mode_container.setObjectName("editor_display_mode_container")
        display_mode_layout = QHBoxLayout(display_mode_container)
        display_mode_layout.setContentsMargins(0, 0, 0, 0)
        display_mode_layout.setSpacing(5)
        
        self.display_mode_label = QLabel(self._t("Display Mode:"))
        display_mode_layout.addWidget(self.display_mode_label)
        
        self.display_mode_combo = QComboBox()
        self.display_mode_combo.setObjectName("editor_display_mode_combo")
        self._populate_display_mode_items()
        # 需要容纳新增的“原图对比”模式
        self.display_mode_combo.setFixedWidth(180)
        display_mode_layout.addWidget(self.display_mode_combo)
        
        # 添加分隔符到容器内
        display_mode_layout.addWidget(self._create_separator())
        
        # 设置容器的尺寸策略，防止被压缩
        from PyQt6.QtWidgets import QSizePolicy
        display_mode_container.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
        
        # 将整个容器添加到主布局
        layout.addWidget(display_mode_container, 0)

        self.show_original_only_checkbox = QCheckBox(self._t("Show Original (Z)"))
        self.show_original_only_checkbox.setObjectName("show_original_only_checkbox")
        layout.addWidget(self.show_original_only_checkbox)

        layout.addWidget(self._create_separator())

        # --- Align / Distribute ---
        self._build_align_distribute_ui(layout)

        layout.addStretch() # Pushes everything to the left

    # ------------------------------------------------------------------
    # 对齐/分布 UI — 单行 PS 风格布局
    # ------------------------------------------------------------------

    _ICONS_DIR = resource_path(os.path.join("desktop_qt_ui", "ui", "icons"))

    def _themed_icon(self, svg_name: str) -> QIcon:
        """读 SVG 模板,把占位符颜色替换为主题色后渲染为 QIcon。

        SVG 用 `#5599ff` 作参考线占位符,`#888888` 作矩形占位符。
        线色取主题强调色,矩形色取主题文字色,跟主题切换。
        """
        pal = self.palette()
        rect_color = pal.color(QPalette.ColorRole.Text).name()
        accent = pal.color(QPalette.ColorRole.Highlight)
        # accent 太暗/太亮时退回固定蓝
        if accent.lightness() < 60 or accent.lightness() > 230:
            line_color = "#5599ff"
        else:
            line_color = accent.name()
        path = os.path.join(self._ICONS_DIR, svg_name)
        try:
            with open(path, "r", encoding="utf-8") as f:
                svg_text = f.read()
        except OSError as exc:
            logging.getLogger(__name__).warning("加载工具栏图标失败 (%s): %s", path, exc)
            return QIcon()
        svg_text = svg_text.replace("#5599ff", line_color).replace("#888888", rect_color)
        renderer = QSvgRenderer(QByteArray(svg_text.encode("utf-8")))
        pixmap = QPixmap(28, 28)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        renderer.render(painter)
        painter.end()
        return QIcon(pixmap)

    def _build_align_distribute_ui(self, layout: QHBoxLayout):
        """构建对齐/分布按钮组：单行 PS 风格。"""
        BTN_W = 28

        def _make_icon_btn(icon, obj_name, tip):
            btn = QPushButton()
            btn.setIcon(icon)
            btn.setObjectName(obj_name)
            btn.setToolTip(tip)
            btn.setFixedSize(QSize(BTN_W + 2, BTN_W + 2))
            btn.setIconSize(QSize(BTN_W, BTN_W))
            btn.setFlat(True)
            btn.setStyleSheet("QPushButton { padding: 0px; border: none; background: transparent; }"
                             "QPushButton:hover { background: rgba(128,128,128,0.2); }"
                             "QPushButton:disabled { background: transparent; }")
            btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            btn.setEnabled(False)
            return btn

        # 参照模式切换（独立放在外面）
        self.align_ref_button = QToolButton()
        self.align_ref_button.setText(self._t("Selection"))
        self.align_ref_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        self.align_ref_button.setObjectName("editor_align_ref_button")
        self.align_ref_button.setToolTip(self._t("Align reference: selection (bounding box) / canvas (whole image)"))
        self._align_ref = "selection"
        self._last_selection_count = 0
        self.align_ref_button.clicked.connect(self._toggle_align_ref)
        layout.addWidget(self.align_ref_button)
        layout.addWidget(self._create_separator())

        # 图标按钮用一个独立容器，内部间距统一为 2px，竖线分隔符嵌在其中
        icon_container = QWidget()
        icon_container.setObjectName("editor_align_icon_container")
        icon_layout = QHBoxLayout(icon_container)
        icon_layout.setContentsMargins(0, 0, 0, 0)
        icon_layout.setSpacing(10)
        icon_layout.setSizeConstraint(QLayout.SizeConstraint.SetFixedSize)

        # ── 第 1 组: 左对齐 / 水平居中 / 右对齐 / 垂直间距分布 ──
        self.align_buttons: dict[str, QToolButton] = {}
        group1 = [
            ("left", self._t("Align Left")),
            ("horizontal_center", self._t("Align Horizontal Center")),
            ("right", self._t("Align Right")),
        ]
        for mode, tip in group1:
            icon = self._themed_icon(f"align_{mode}.svg")
            btn = _make_icon_btn(icon, f"editor_align_{mode}", tip)
            btn.clicked.connect(lambda checked, m=mode: self.align_requested.emit(m))
            self.align_buttons[mode] = btn
            icon_layout.addWidget(btn)

        icon = self._themed_icon("distribute_spacing_v.svg")
        btn = _make_icon_btn(icon, "editor_dist_vertical_spacing", self._t("Distribute Vertical Spacing"))
        btn.clicked.connect(lambda: self._on_dist_spacing("vertical"))
        self._dist_v_btn = btn
        icon_layout.addWidget(btn)

        # ── 第 2 组: 顶对齐 / 垂直居中 / 底对齐 / 水平间距分布 ──
        group2 = [
            ("top", self._t("Align Top")),
            ("vertical_center", self._t("Align Vertical Center")),
            ("bottom", self._t("Align Bottom")),
        ]
        for mode, tip in group2:
            icon = self._themed_icon(f"align_{mode}.svg")
            btn = _make_icon_btn(icon, f"editor_align_{mode}", tip)
            btn.clicked.connect(lambda checked, m=mode: self.align_requested.emit(m))
            self.align_buttons[mode] = btn
            icon_layout.addWidget(btn)

        icon = self._themed_icon("distribute_spacing_h.svg")
        btn = _make_icon_btn(icon, "editor_dist_horizontal_spacing", self._t("Distribute Horizontal Spacing"))
        btn.clicked.connect(lambda: self._on_dist_spacing("horizontal"))
        self._dist_h_btn = btn
        icon_layout.addWidget(btn)

        # 图标组保持固定宽度，空间不足时从右侧裁切
        clip_host = _OverflowClipHost(icon_container)
        clip_host.setObjectName("editor_align_icon_clip")
        clip_host.setFixedHeight(BTN_W + 2)
        layout.addWidget(clip_host)

    def _on_dist_spacing(self, orientation: str):
        """处理间距分布按钮点击（垂直/水平空白间隙均分）。"""
        if orientation == "vertical":
            self.distribute_requested.emit("spacing_v")
        else:
            self.distribute_requested.emit("spacing_h")

    def _toggle_align_ref(self):
        """切换对齐参照模式：选区 ↔ 画布。同时更新按钮启用状态。"""
        if self._align_ref == "selection":
            self._align_ref = "canvas"
            self.align_ref_button.setText(self._t("Canvas"))
        else:
            self._align_ref = "selection"
            self.align_ref_button.setText(self._t("Selection"))
        self.update_align_distribute_buttons(self._last_selection_count)

    def get_align_reference(self) -> str:
        return self._align_ref

    def update_align_distribute_buttons(self, selection_count: int):
        """根据选中数量和参照模式更新按钮启用状态。更多按钮始终可用。"""
        self._last_selection_count = selection_count
        align_enabled = (selection_count >= 1 and self._align_ref == "canvas") or (selection_count >= 2)
        dist_enabled = selection_count >= 3
        for btn in self.align_buttons.values():
            btn.setEnabled(align_enabled)
        self._dist_v_btn.setEnabled(dist_enabled)
        self._dist_h_btn.setEnabled(dist_enabled)

    def _create_separator(self):
        separator = QFrame()
        separator.setObjectName("editor_toolbar_separator")
        separator.setFrameShape(QFrame.Shape.VLine)
        separator.setFrameShadow(QFrame.Shadow.Sunken)
        separator.setLineWidth(1)
        separator.setMidLineWidth(0)
        separator.setFixedWidth(2)
        separator.setMinimumHeight(20)
        return separator

    def _connect_signals(self):
        self.back_button.clicked.connect(self.back_requested)
        self.export_button.clicked.connect(self.export_requested)
        self.undo_button.clicked.connect(self.undo_requested)
        self.redo_button.clicked.connect(self.redo_requested)
        self.zoom_in_button.clicked.connect(self.zoom_in_requested)
        self.zoom_out_button.clicked.connect(self.zoom_out_requested)
        self.fit_window_button.clicked.connect(self.fit_window_requested)
        self.display_mode_combo.currentIndexChanged.connect(self._emit_display_mode_changed)
        self.show_original_only_checkbox.toggled.connect(self.show_original_only_toggled)

    def _display_mode_definitions(self):
        return [
            ("full", "Show Text and Boxes"),
            ("text_only", "Show Text Only"),
            ("box_only", "Show Boxes Only"),
            ("none", "Show Nothing"),
            ("compare_original_split", "Compare with Original (Two Panels)"),
        ]

    def _populate_display_mode_items(self, selected_mode: str | None = None):
        self.display_mode_combo.clear()
        for mode, text_key in self._display_mode_definitions():
            self.display_mode_combo.addItem(self._t(text_key), mode)

        target_mode = selected_mode or "full"
        mode_index = self.display_mode_combo.findData(target_mode)
        if mode_index < 0:
            mode_index = 0
        self.display_mode_combo.setCurrentIndex(mode_index)

    def _emit_display_mode_changed(self, index: int):
        mode = self.display_mode_combo.itemData(index)
        if mode:
            self.display_mode_changed.emit(str(mode))

    # --- Public Slots ---
    def update_undo_redo_state(self, can_undo: bool, can_redo: bool):
        self.undo_button.setEnabled(can_undo)
        self.redo_button.setEnabled(can_redo)

    def set_show_original_only_checked(self, checked: bool):
        """토글 상태를 체크박스에 동기화 (신호 재발생 방지, Z 키/페이지 전환 등에서 호출)"""
        self.show_original_only_checkbox.blockSignals(True)
        self.show_original_only_checkbox.setChecked(checked)
        self.show_original_only_checkbox.blockSignals(False)

    def update_zoom_level(self, zoom_level: float):
        self.zoom_label.setText(f"{zoom_level:.0%}")
    
    def set_export_enabled(self, enabled: bool):
        """设置导出按钮的启用状态"""
        self.export_button.setEnabled(enabled)
    
    def refresh_ui_texts(self):
        """刷新所有UI文本（用于语言切换）"""
        # 刷新按钮文本
        self.back_button.setText(self._t("Back"))
        set_hover_hint(self.back_button, self._t("Back to Main"))
        self.export_button.setText(self._t("Export Image"))
        set_hover_hint(self.export_button, self._t("Export current rendered image") + " (Ctrl+S)")
        self.undo_button.setText(self._t("Undo"))
        set_hover_hint(self.undo_button, self._t("Undo last operation") + " (Ctrl+Z)")
        self.redo_button.setText(self._t("Redo"))
        set_hover_hint(self.redo_button, self._t("Redo last undone operation") + " (Ctrl+Y)")
        self.zoom_out_button.setText(self._t("Zoom Out (-)"))
        self.zoom_in_button.setText(self._t("Zoom In (+)"))
        self.fit_window_button.setText(self._t("Fit to Window"))
        
        # 刷新下拉菜单
        current_mode = self.display_mode_combo.currentData()
        self.display_mode_combo.blockSignals(True)
        self._populate_display_mode_items(current_mode)
        self.display_mode_combo.blockSignals(False)
        
        # 刷新标签
        if hasattr(self, 'display_mode_label'):
            self.display_mode_label.setText(self._t("Display Mode:"))
        if hasattr(self, 'opacity_label'):
            self.opacity_label.setText(self._t("Original Image Opacity:"))
        if hasattr(self, 'show_original_only_checkbox'):
            self.show_original_only_checkbox.setText(self._t("Show Original (Z)"))
