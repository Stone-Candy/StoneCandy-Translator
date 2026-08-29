
import logging

from PyQt6.QtCore import QEvent, QLocale, QSize, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QCursor, QDoubleValidator, QMouseEvent, QTextCursor, QWheelEvent
from PyQt6.QtWidgets import (
    QApplication,
    QAbstractSpinBox,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QSlider,
    QStyle,
    QStyleOptionSlider,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)
from services import get_config_service, get_i18n_manager
from utils.font_list import FontComboBox, set_system_fonts_enabled

from .color_picker import ColorPickerWidget
from .hover_hint import set_hover_hint

# from .collapsible_frame import CollapsibleFrame  # 不再使用折叠框
from ui.secondary_pages.themed_text_input_dialog import themed_get_text

logger = logging.getLogger('manga_translator')


def _quantize_font_size(value, minimum: float = 1.0) -> float:
    try:
        font_size = float(value)
    except (TypeError, ValueError):
        return float(minimum)
    return max(float(minimum), round(font_size * 10.0) / 10.0)


def _format_font_size(value) -> str:
    return f"{_quantize_font_size(value):.1f}"


def convert_arrows_to_tags(raw_text: str) -> str:
    """
    将文本中的 ⇄ 符号转换为 <H> 标签

    Args:
        raw_text: 包含 ⇄ 符号的原始文本

    Returns:
        转换后的文本，⇄ 符号被替换为成对的 <H></H> 标签

    Note:
        - 如果 ⇄ 是偶数个，会正确配对为 <H></H>
        - 如果 ⇄ 是奇数个，最后一个会被转换为 <H>，但会记录警告
    """
    if '⇄' not in raw_text:
        return raw_text

    parts = raw_text.split('⇄')
    text_with_tags = ''

    for i, part in enumerate(parts):
        text_with_tags += part
        if i < len(parts) - 1:  # 不是最后一个部分
            if i % 2 == 0:  # 偶数索引,添加开始标签
                text_with_tags += '<H>'
            else:  # 奇数索引,添加结束标签
                text_with_tags += '</H>'

    # 检查是否有未闭合的标签（奇数个⇄）
    arrow_count = len(parts) - 1
    if arrow_count % 2 != 0:
        logger.warning(f"홀수 개의 ⇄ 기호를 감지했습니다({arrow_count}개)，마지막 <H> 태그가 닫히지 않았습니다")

    return text_with_tags


def _qtext_to_raw(text_edit) -> str:
    """QTextEdit → 원문. toPlainText()는 NBSP를 일반 스페이스로 바꿔서 쓰지 않는다."""
    document = text_edit.document()
    if document is not None and hasattr(document, "toRawText"):
        return document.toRawText()
    return text_edit.toPlainText()


def _plain_text_to_br(raw_text: str) -> str:
    """QTextEdit plain text → stored translation. Keep empty lines and spaces."""
    text_with_tags = convert_arrows_to_tags(raw_text or "")
    text_with_tags = (
        text_with_tags.replace("\r\n", "\n").replace("\r", "\n").replace("\u2029", "\n")
    )
    return text_with_tags.replace("\n", "[BR]")


_EDGE_WS = " \t\u00a0\u3000"


def _clean_translation_plain(text: str) -> str:
    """Old [BR] \\s* + edge empty-line cleanup, on QTextEdit plain text."""
    import re

    text = (text or "").replace("\r\n", "\n").replace("\r", "\n").replace("\u2029", "\n")
    text = re.sub(rf"[{re.escape(_EDGE_WS)}]*\n[{re.escape(_EDGE_WS)}]*", "\n", text)
    text = re.sub(rf"[{re.escape(_EDGE_WS)}]{{2,}}", " ", text)
    lines = [line.strip(_EDGE_WS) for line in text.split("\n")]
    while lines and not lines[0]:
        lines.pop(0)
    while lines and not lines[-1]:
        lines.pop()
    return "\n".join(lines)


class CustomSlider(QSlider):
    """点击滑槽任意位置时指针直接跳转到该位置。滚轮不改值,避免滚动面板时误调。"""

    def wheelEvent(self, event: QWheelEvent):
        event.ignore()

    def mousePressEvent(self, event: QMouseEvent):
        """左键点击滑槽任意位置时，先将滑块跳转到点击位置，再交给父类处理，
        这样既能实现点击跳转，又能保留正常的拖动行为"""
        if event.button() == Qt.MouseButton.LeftButton:
            opt = QStyleOptionSlider()
            self.initStyleOption(opt)
            groove_rect = self.style().subControlRect(
                QStyle.ComplexControl.CC_Slider, opt, QStyle.SubControl.SC_SliderGroove, self
            )
            handle_rect = self.style().subControlRect(
                QStyle.ComplexControl.CC_Slider, opt, QStyle.SubControl.SC_SliderHandle, self
            )

            click_pos = event.position().toPoint()

            # 如果点击的不是滑块手柄本身，先跳转到点击位置，
            # 这样手柄会移动到鼠标下方，后续交给父类处理时就能被当作
            # "按住手柄拖动"来正确处理，从而不破坏拖动功能
            if not handle_rect.contains(click_pos):
                if self.orientation() == Qt.Orientation.Horizontal:
                    handle_length = handle_rect.width()
                    slider_min = groove_rect.x()
                    slider_max = groove_rect.right() - handle_length + 1
                    pos = click_pos.x() - handle_length / 2
                else:
                    handle_length = handle_rect.height()
                    slider_min = groove_rect.y()
                    slider_max = groove_rect.bottom() - handle_length + 1
                    pos = click_pos.y() - handle_length / 2

                value = QStyle.sliderValueFromPosition(
                    self.minimum(), self.maximum(), int(pos - slider_min), max(slider_max - slider_min, 1)
                )
                self.setValue(value)

        # 交给父类处理，正常初始化拖动所需的内部状态（点击偏移量等），
        # 这样点击后紧接着拖动依然可以正常工作
        super().mousePressEvent(event)


class PropertyPanel(QWidget):
    """
    左侧属性面板，功能完整版。
    """
    # --- Define all required signals ---
    translated_text_modified = pyqtSignal(int, str)
    translation_raw_modified = pyqtSignal(int, str)
    white_frame_release_requested = pyqtSignal(int)
    original_text_modified = pyqtSignal(int, str)
    ocr_requested = pyqtSignal()
    translation_requested = pyqtSignal()
    font_size_changed = pyqtSignal(int, float)
    italic_changed = pyqtSignal(int, bool)
    bold_changed = pyqtSignal(int, bool)
    font_color_changed = pyqtSignal(int, str)
    stroke_color_changed = pyqtSignal(int, str)
    stroke_width_changed = pyqtSignal(int, float)
    line_spacing_changed = pyqtSignal(int, float)
    letter_spacing_changed = pyqtSignal(int, float)
    char_width_changed = pyqtSignal(int, float)
    angle_changed = pyqtSignal(int, float)
    distort_mode_changed = pyqtSignal(int, bool)
    font_family_changed = pyqtSignal(int, str)  # New signal for font family
    alignment_changed = pyqtSignal(int, str)
    direction_changed = pyqtSignal(int, str)
    copy_region_requested = pyqtSignal()
    paste_region_requested = pyqtSignal()
    delete_region_requested = pyqtSignal()
    
    # Mask signals
    mask_tool_changed = pyqtSignal(str)
    brush_size_changed = pyqtSignal(int)
    toggle_mask_visibility = pyqtSignal(bool)
    toggle_overlay_visibility = pyqtSignal(bool)
    clear_all_masks_requested = pyqtSignal()
    # Paint overlay signals
    brush_color_changed = pyqtSignal(str)
    clear_paint_overlay_requested = pyqtSignal()

    def __init__(self, model, app_logic, parent=None):
        super().__init__(parent)
        self.model = model
        self.app_logic = app_logic
        self.config_service = get_config_service()
        self.i18n = get_i18n_manager()

        self._init_ui()
        self._connect_signals()
        self._connect_model_signals() # Connect to model signals
        self.block_updates = False
        self._translation_box_active = False
        self.current_region_index = -1
        self.clear_and_disable_selection_dependent()
        
        from ui.widgets.wheel_filter import install_wheel_filter
        install_wheel_filter(self)
    
    def _t(self, key: str, **kwargs) -> str:
        """翻译辅助方法"""
        if self.i18n:
            return self.i18n.translate(key, **kwargs)
        return key

    def _t_field(self, key: str, **kwargs) -> str:
        return self._t(key, **kwargs).rstrip(" :：")

    def _sync_ocr_translate_row_metrics(self):
        combo = getattr(self, "ocr_model_combo", None)
        buttons = [getattr(self, "ocr_button", None), getattr(self, "translate_button", None)]
        if combo is None or any(btn is None for btn in buttons):
            return
        for btn in buttons:
            btn.setMinimumSize(0, 0)
            btn.setMaximumSize(16777215, 16777215)
        combo.ensurePolished()
        for btn in buttons:
            btn.ensurePolished()
        combo_height = combo.height() if combo.height() > 1 else combo.sizeHint().height()
        width = max(btn.sizeHint().width() for btn in buttons) + 8
        for btn in buttons:
            btn.setFixedSize(width, combo_height)

    def _sane_control_height(self, widget, cap: int = 60) -> int:
        if widget is None:
            return 0
        widget.ensurePolished()
        hint = widget.sizeHint().height()
        if 1 < hint <= cap:
            return hint
        geom = widget.height()
        if 1 < geom <= cap:
            return geom
        return 0

    def _align_form_label(self, label, field):
        if label is None or field is None:
            return
        label.setMinimumHeight(0)
        label.setMaximumHeight(16777215)
        field_h = self._sane_control_height(field)
        if field_h > 1:
            label.setFixedHeight(field_h)
        label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

    def _sync_font_row_metrics(self):
        combo = getattr(self, "font_family_combo", None)
        if combo is not None:
            self._align_form_label(getattr(self, "font_label", None), combo)

        font_size_input = getattr(self, "font_size_input", None)
        if font_size_input is None:
            return
        font_size_h = 33
        font_size_input.setFixedHeight(font_size_h)
        font_size_label = getattr(self, "font_size_label", None)
        if font_size_label is not None:
            font_size_label.setMinimumHeight(0)
            font_size_label.setMaximumHeight(16777215)
            font_size_label.setFixedHeight(font_size_h)
            font_size_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        btn_width = max(1, round(font_size_h * 1.10))
        for btn in (getattr(self, "bold_button", None), getattr(self, "italic_button", None)):
            if btn is not None:
                btn.setFixedSize(btn_width, font_size_h)
        self._sync_insert_chip_metrics()
        for label, field in (
            (getattr(self, "font_color_label", None), getattr(self, "font_color_picker", None)),
            (getattr(self, "stroke_color_label", None), getattr(self, "stroke_color_picker", None)),
            (getattr(self, "stroke_width_label", None), getattr(self, "stroke_width_spinbox", None)),
            (getattr(self, "line_spacing_label", None), getattr(self, "line_spacing_spinbox", None)),
            (getattr(self, "letter_spacing_label", None), getattr(self, "letter_spacing_spinbox", None)),
            (getattr(self, "char_width_label", None), getattr(self, "char_width_spinbox", None)),
            (getattr(self, "angle_style_label", None), getattr(self, "angle_spinbox", None)),
            (getattr(self, "alignment_label", None), getattr(self, "alignment_combo", None)),
            (getattr(self, "direction_label", None), getattr(self, "direction_combo", None)),
        ):
            self._align_form_label(label, field)

    def _sync_insert_chip_metrics(self):
        clean = getattr(self, "insert_placeholder_button", None)
        if clean is None:
            return
        clean.setMinimumHeight(0)
        clean.setMaximumHeight(16777215)
        clean.ensurePolished()
        height = clean.sizeHint().height() + 2
        clean.setFixedHeight(height)
        for btn in (
            getattr(self, "insert_note_button", None),
            getattr(self, "insert_heart_outline_button", None),
            getattr(self, "insert_heart_filled_button", None),
        ):
            if btn is not None:
                btn.setFixedHeight(height)

    def showEvent(self, event):
        super().showEvent(event)
        self._sync_ocr_translate_row_metrics()
        QTimer.singleShot(0, self._sync_font_row_metrics)

    def _init_ui(self):
        # 创建主布局
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(main_layout)
        
        # 创建滚动区域
        from PyQt6.QtWidgets import QScrollArea
        scroll_area = QScrollArea()
        scroll_area.setObjectName("editor_property_scroll")
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QScrollArea.Shape.NoFrame)
        
        # 创建内容容器
        content_widget = QWidget()
        content_widget.setObjectName("editor_property_content")
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(8, 2, 8, 2)
        content_layout.setSpacing(10)
        content_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        
        self._create_mask_edit_section(content_layout)
        self._create_text_section(content_layout)
        self._create_style_section(content_layout)
        self._create_action_section(content_layout)
        self._create_region_info_section(content_layout)

        # 添加一个弹性空间，将所有内容向上推，使布局更紧凑
        content_layout.addStretch()
        
        # 将内容容器放入滚动区域
        scroll_area.setWidget(content_widget)
        main_layout.addWidget(scroll_area)

        # 不再使用语法高亮器,改用符号替换
        # self.highlighter = HorizontalTagHighlighter(self.translated_text_box.document())

    def _set_selection_controls_blocked(self, blocked: bool):
        """统一阻止/恢复与区域样式相关控件信号，避免切换选区时误写回。"""
        for child in self.findChildren(QWidget):
            if isinstance(child, (QLineEdit, QTextEdit, QComboBox, QSlider, QAbstractSpinBox)):
                child.blockSignals(blocked)
        # B/I 토글은 입력 위젯이 아니라 별도 차단
        italic_btn = getattr(self, "italic_button", None)
        if italic_btn is not None:
            italic_btn.blockSignals(blocked)
        bold_btn = getattr(self, "bold_button", None)
        if bold_btn is not None:
            bold_btn.blockSignals(blocked)
        distort_cb = getattr(self, "distort_mode_checkbox", None)
        if distort_cb is not None:
            distort_cb.blockSignals(blocked)

    def _create_region_info_section(self, layout):
        self.info_group = QGroupBox(self._t("Region Info"))
        self.info_group.setObjectName("editor_info_group")
        info_layout = QFormLayout(self.info_group)
        info_layout.setContentsMargins(8, 8, 8, 6)
        info_layout.setHorizontalSpacing(17)
        info_layout.setVerticalSpacing(6)
        self.index_label = QLabel("-")
        self.bbox_label = QLabel("-")
        self.size_label = QLabel("-")
        self.angle_label = QLabel("-")
        self.index_row_label = QLabel(self._t_field("Index:"))
        self.bbox_row_label = QLabel(self._t_field("Position:"))
        self.size_row_label = QLabel(self._t_field("Size:"))
        self.angle_row_label = QLabel(self._t_field("Angle:"))
        info_layout.addRow(self.index_row_label, self.index_label)
        info_layout.addRow(self.bbox_row_label, self.bbox_label)
        info_layout.addRow(self.size_row_label, self.size_label)
        info_layout.addRow(self.angle_row_label, self.angle_label)
        layout.addWidget(self.info_group)

    def _create_mask_edit_section(self, layout):
        self.mask_edit_frame = QWidget()
        self.mask_edit_frame.setObjectName("editor_mask_group")
        frame_layout = QVBoxLayout(self.mask_edit_frame)
        frame_layout.setContentsMargins(6, 6, 6, 6)
        frame_layout.setSpacing(0)

        self.mask_tool_group = QButtonGroup(self)
        self.mask_tool_group.setExclusive(True)

        def make_tool_button(text, object_name, hint):
            button = QPushButton(text)
            button.setObjectName(object_name)
            button.setProperty("editorToolButton", True)
            button.setProperty("softAction", True)
            button.setCheckable(True)
            button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            set_hover_hint(button, hint)
            return button

        self.select_button = make_tool_button(
            self._t("Selection Tool"),
            "editor_mask_select_button",
            self._t("Selection Tool") + " (Q)",
        )
        self.brush_button = make_tool_button(
            self._t("Inpaint Brush"),
            "editor_mask_brush_button",
            self._t("Inpaint Brush") + " (W)",
        )
        self.eraser_button = make_tool_button(
            self._t("Inpaint Erase"),
            "editor_mask_eraser_button",
            self._t("Inpaint Erase") + " (E)",
        )
        self.paint_brush_button = make_tool_button(
            self._t("Overlay Brush"),
            "editor_paint_brush_button",
            self._t("Overlay Brush") + " (R)",
        )
        self.paint_eraser_button = make_tool_button(
            self._t("Overlay Eraser"),
            "editor_paint_eraser_button",
            self._t("Overlay Eraser") + " (T)",
        )

        self.mask_tool_group.addButton(self.select_button, 0)
        self.mask_tool_group.addButton(self.brush_button, 1)
        self.mask_tool_group.addButton(self.eraser_button, 2)
        self.mask_tool_group.addButton(self.paint_brush_button, 3)
        self.mask_tool_group.addButton(self.paint_eraser_button, 4)
        self.select_button.setChecked(True)

        frame_layout.addWidget(self.select_button)
        frame_layout.addSpacing(9)

        brush_row = QHBoxLayout()
        brush_row.setContentsMargins(0, 0, 0, 0)
        brush_row.setSpacing(7)
        brush_row.addWidget(self.brush_button)
        brush_row.addWidget(self.paint_brush_button)
        frame_layout.addLayout(brush_row)
        frame_layout.addSpacing(9)

        erase_row = QHBoxLayout()
        erase_row.setContentsMargins(0, 0, 0, 0)
        erase_row.setSpacing(7)
        erase_row.addWidget(self.eraser_button)
        erase_row.addWidget(self.paint_eraser_button)
        frame_layout.addLayout(erase_row)
        frame_layout.addSpacing(10)

        color_row = QHBoxLayout()
        color_row.setContentsMargins(0, 0, 0, 0)
        color_row.setSpacing(6)
        self.paint_color_label = QLabel(self._t_field("Overlay Brush Color:") + " ")
        color_row.addWidget(self.paint_color_label)
        self.paint_color_picker = ColorPickerWidget(
            dialog_title="Select brush color",
            default_color="#ffffff",
            config_key="saved_colors",
            config_service=self.config_service,
            i18n_func=self._t,
        )
        self.paint_color_picker.setFixedWidth(96)
        color_row.addWidget(self.paint_color_picker)
        color_row.addStretch()
        frame_layout.addLayout(color_row)
        frame_layout.addSpacing(9)

        brush_size_layout = QHBoxLayout()
        brush_size_layout.setContentsMargins(0, 1, 0, 3)
        brush_size_layout.setSpacing(6)
        self.brush_size_title_label = QLabel(self._t_field("Brush Size:") + " ")
        brush_size_layout.addWidget(self.brush_size_title_label)
        self.brush_size_slider = CustomSlider(Qt.Orientation.Horizontal)
        self.brush_size_slider.setObjectName("editor_brush_size_slider")
        self.brush_size_slider.setRange(5, 250)
        self.brush_size_value_label = QLabel("30")
        self.brush_size_value_label.setObjectName("editor_brush_size_value_label")
        self.brush_size_value_label.setFixedWidth(32)
        self.brush_size_value_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.brush_size_slider.setValue(30)
        brush_size_layout.addWidget(self.brush_size_slider)
        brush_size_layout.addWidget(self.brush_size_value_label)
        frame_layout.addLayout(brush_size_layout)
        frame_layout.addSpacing(10)

        self.show_refined_mask_checkbox = QCheckBox(self._t("Show Inpaint Area"))
        self.show_refined_mask_checkbox.setChecked(False)
        self._add_checkbox_shortcut_row(frame_layout, self.show_refined_mask_checkbox, "(Tab)")
        frame_layout.addSpacing(8)
        self.show_paint_overlay_checkbox = QCheckBox(self._t("Show Overlay Area"))
        self.show_paint_overlay_checkbox.setChecked(False)
        self._add_checkbox_shortcut_row(frame_layout, self.show_paint_overlay_checkbox, "(Shift + Tab)")

        # 인페인트 영역 모두 삭제 / 덧칠 모두 삭제는 당분간 숨김
        # self.clear_all_masks_button = QPushButton(self._t("Clear All Masks"))
        # self.clear_all_masks_button.setObjectName("editor_clear_masks_button")
        # self.clear_all_masks_button.setProperty("softAction", True)
        # frame_layout.addWidget(self.clear_all_masks_button)
        # self.clear_paint_overlay_button = QPushButton(self._t("Clear Paint Layer"))
        # self.clear_paint_overlay_button.setObjectName("editor_clear_paint_button")
        # self.clear_paint_overlay_button.setProperty("softAction", True)
        # frame_layout.addWidget(self.clear_paint_overlay_button)

        layout.addWidget(self.mask_edit_frame)

    def _add_checkbox_shortcut_row(self, parent_layout, checkbox: QCheckBox, shortcut_text: str) -> QLabel:
        row = QWidget()
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(4)
        hint = QLabel(shortcut_text)
        hint.setObjectName("editor_shortcut_hint")
        row_layout.addWidget(checkbox)
        row_layout.addWidget(hint)
        row_layout.addStretch(1)
        parent_layout.addWidget(row)
        return hint

    def _make_section_divider(self, bottom: int = 3) -> QWidget:
        line = QFrame()
        line.setObjectName("editor_section_divider")
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Plain)
        line.setFixedHeight(1)
        wrap = QWidget()
        wrap_layout = QVBoxLayout(wrap)
        wrap_layout.setContentsMargins(0, 0, 0, bottom)
        wrap_layout.setSpacing(0)
        wrap_layout.addWidget(line)
        return wrap

    def _create_text_section(self, layout):
        self.text_edit_frame = QWidget()
        self.text_edit_frame.setObjectName("editor_text_group")
        text_layout = QVBoxLayout(self.text_edit_frame)
        text_layout.setContentsMargins(8, 3, 8, 4)
        text_layout.setSpacing(8)
        
        # 原文文本框
        self.original_text_box = QTextEdit()
        self.original_text_box.setUndoRedoEnabled(True)
        self.original_text_box.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.original_text_box.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.original_text_box.setMinimumHeight(72)
        self.original_text_box.setMaximumHeight(132)
        
        self.translated_text_box = QTextEdit()
        self.translated_text_box.setObjectName("translationEdit")
        self.translated_text_box.setUndoRedoEnabled(True)
        self.translated_text_box.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.translated_text_box.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.translated_text_box.setMinimumHeight(196)
        self.translated_text_box.setMaximumHeight(343)
        self.translated_text_box.installEventFilter(self)
        self.translated_text_box.viewport().installEventFilter(self)
        self._create_text_stats_overlay()

        self.original_text_label = QLabel(self._t_field("Original Text:"))
        text_layout.addWidget(self._make_section_divider())
        text_layout.addWidget(self.original_text_label)
        text_layout.addWidget(self.original_text_box)
        self.translated_text_label = QLabel(self._t_field("Translated Text:"))
        text_layout.addWidget(self.translated_text_label)
        text_layout.addWidget(self.translated_text_box)
        insert_buttons_layout = QHBoxLayout()
        insert_buttons_layout.setContentsMargins(0, 0, 0, 0)
        insert_buttons_layout.setSpacing(6)
        self.insert_placeholder_button = QPushButton(self._t("Clean Whitespace"))
        self.insert_placeholder_button.setProperty("chipButton", True)
        self.insert_placeholder_button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        set_hover_hint(self.insert_placeholder_button, self._t("Clean Whitespace"))

        self.insert_note_button = QPushButton("♪")
        self.insert_note_button.setProperty("chipButton", True)
        self.insert_note_button.setFixedWidth(32)
        set_hover_hint(self.insert_note_button, self._t("Insert ♪"))

        self.insert_heart_outline_button = QPushButton("♡")
        self.insert_heart_outline_button.setProperty("chipButton", True)
        self.insert_heart_outline_button.setFixedWidth(32)
        set_hover_hint(self.insert_heart_outline_button, self._t("Insert ♡"))

        self.insert_heart_filled_button = QPushButton("♥")
        self.insert_heart_filled_button.setProperty("chipButton", True)
        self.insert_heart_filled_button.setFixedWidth(32)
        set_hover_hint(self.insert_heart_filled_button, self._t("Insert ♥"))

        for button in (
            self.insert_note_button,
            self.insert_heart_outline_button,
            self.insert_heart_filled_button,
        ):
            button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            button.setAutoDefault(False)
            button.setDefault(False)
            button.setProperty("heartChip", True)
            button.installEventFilter(self)

        insert_buttons_layout.addWidget(self.insert_placeholder_button)
        insert_buttons_layout.addWidget(self.insert_note_button)
        insert_buttons_layout.addWidget(self.insert_heart_outline_button)
        insert_buttons_layout.addWidget(self.insert_heart_filled_button)
        text_layout.addLayout(insert_buttons_layout)
        QTimer.singleShot(0, self._sync_insert_chip_metrics)
        # 자동치환 미적용 편집은 항상 켠 채로 둔다.
        # self.translation_raw_checkbox = QCheckBox(self._t("Show Translation (Raw)"))
        # self.translation_raw_checkbox.setChecked(True)
        # self.translation_raw_checkbox.toggled.connect(self._on_translation_raw_mode_toggled)
        # text_layout.addWidget(self.translation_raw_checkbox)
        layout.addWidget(self.text_edit_frame)

    def _create_style_section(self, layout):
        self.style_edit_frame = QWidget()
        self.style_edit_frame.setObjectName("editor_style_group")
        style_layout = QFormLayout(self.style_edit_frame)
        style_layout.setContentsMargins(8, 0, 8, 6)
        style_layout.setHorizontalSpacing(8)
        style_layout.setVerticalSpacing(8)
        style_layout.addRow(self._make_section_divider(bottom=4))

        preset_widget = QWidget()
        preset_layout = QHBoxLayout(preset_widget)
        preset_layout.setContentsMargins(0, 0, 0, 0)
        preset_layout.setSpacing(4)
        self.style_preset_combo = QComboBox()
        self.style_preset_combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.style_preset_combo.setMinimumContentsLength(12)
        self.style_preset_combo.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        preset_layout.addWidget(self.style_preset_combo, 1)
        self.save_style_preset_button = QPushButton()
        self.save_style_preset_button.setObjectName("editor_style_preset_save_button")
        self.save_style_preset_button.setProperty("chipButton", True)
        self.save_style_preset_button.setFixedSize(30, 30)
        self.save_style_preset_button.setIconSize(QSize(16, 16))
        preset_layout.addWidget(self.save_style_preset_button)
        self.delete_style_preset_button = QPushButton()
        self.delete_style_preset_button.setObjectName("editor_style_preset_delete_button")
        self.delete_style_preset_button.setProperty("chipButton", True)
        self.delete_style_preset_button.setFixedSize(30, 30)
        self.delete_style_preset_button.setIconSize(QSize(16, 16))
        preset_layout.addWidget(self.delete_style_preset_button)
        self._refresh_style_preset_action_buttons()
        self.style_preset_label = QLabel(self._t_field("Style Preset:"))
        style_preset_row = QWidget()
        style_preset_row_layout = QHBoxLayout(style_preset_row)
        style_preset_row_layout.setContentsMargins(0, 0, 0, 0)
        style_preset_row_layout.setSpacing(8)
        style_preset_row_layout.addWidget(self.style_preset_label)
        style_preset_row_layout.addWidget(preset_widget, 1)
        style_preset_wrap = QWidget()
        style_preset_wrap_layout = QVBoxLayout(style_preset_wrap)
        style_preset_wrap_layout.setContentsMargins(0, 0, 0, 1)
        style_preset_wrap_layout.addWidget(style_preset_row)
        style_layout.addRow(style_preset_wrap)
        self._refresh_style_preset_combo()
        # 시작 시 숫자로 시작하는 프리셋 → Ctrl+숫자 슬롯 자동 할당
        self._sync_style_slots_from_presets()
        
        try:
            set_system_fonts_enabled(not bool(self.config_service.get_config().render.disable_system_fonts))
        except Exception:
            pass
        locale_getter = self.i18n.get_current_locale if getattr(self, "i18n", None) else None
        self.font_family_combo = FontComboBox(self, locale_getter=locale_getter)
        self.font_family_combo.setMinimumWidth(120)
        self.font_label = QLabel(self._t_field("Font:"))
        self.font_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        style_layout.addRow(self.font_label, self.font_family_combo)
        
        # Font size + B/I 토글 (입력창 33px, B/I는 가로 110%)
        font_size_layout = QHBoxLayout()
        font_size_layout.setContentsMargins(0, 0, 0, 0)
        font_size_layout.setSpacing(4)
        font_size_layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        font_size_h = 33
        self.font_size_input = QLineEdit()
        self.font_size_input.setObjectName("editor_font_size_input")
        font_size_validator = QDoubleValidator(8.0, 1000.0, 1, self)
        font_size_validator.setNotation(QDoubleValidator.Notation.StandardNotation)
        font_size_validator.setLocale(QLocale.c())
        self.font_size_input.setValidator(font_size_validator)
        self.font_size_input.setFixedWidth(64)
        self.font_size_input.setFixedHeight(font_size_h)
        self.font_size_input.setAlignment(Qt.AlignmentFlag.AlignCenter)
        font_size_layout.addWidget(
            self.font_size_input, 0, Qt.AlignmentFlag.AlignVCenter
        )
        font_size_layout.addSpacing(1)

        self.bold_button = QPushButton("B")
        self.bold_button.setObjectName("editor_bold_button")
        self.bold_button.setProperty("fontEmphasisButton", True)
        self.bold_button.setCheckable(True)
        set_hover_hint(self.bold_button, "굵게 (B)")
        font_size_layout.addWidget(
            self.bold_button, 0, Qt.AlignmentFlag.AlignVCenter
        )

        self.italic_button = QPushButton("I")
        self.italic_button.setObjectName("editor_italic_button")
        self.italic_button.setProperty("fontEmphasisButton", True)
        self.italic_button.setCheckable(True)
        set_hover_hint(self.italic_button, "기울임 (I)")
        font_size_layout.addWidget(
            self.italic_button, 0, Qt.AlignmentFlag.AlignVCenter
        )
        font_size_layout.addStretch(1)

        self.font_size_label = QLabel(self._t_field("Font Size:"))
        self.font_size_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.font_size_label.setFixedHeight(font_size_h)
        style_layout.addRow(self.font_size_label, font_size_layout)
        QTimer.singleShot(0, self._sync_font_row_metrics)
        
        # Font color
        self.font_color_picker = ColorPickerWidget(
            dialog_title="Select font color",
            default_color="#000000",
            config_key="saved_colors",
            config_service=self.config_service,
            i18n_func=self._t,
        )
        self.font_color_picker.setFixedWidth(96)
        self.font_color_label = QLabel(self._t_field("Font Color:"))
        self.font_color_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        style_layout.addRow(self.font_color_label, self.font_color_picker)

        # Stroke color (描边颜色)
        self.stroke_color_picker = ColorPickerWidget(
            dialog_title="Select stroke color",
            default_color="#ffffff",
            config_key="saved_stroke_colors",
            config_service=self.config_service,
            i18n_func=self._t,
        )
        self.stroke_color_picker.setFixedWidth(96)
        self.stroke_color_label = QLabel(self._t_field("Stroke Color:"))
        self.stroke_color_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        style_layout.addRow(self.stroke_color_label, self.stroke_color_picker)

        # Stroke width (描边宽度)
        stroke_width_layout = QHBoxLayout()
        stroke_width_layout.setContentsMargins(0, 0, 0, 0)
        self.stroke_width_spinbox = QDoubleSpinBox()
        self.stroke_width_spinbox.setRange(0.0, 1.0)
        self.stroke_width_spinbox.setSingleStep(0.01)
        self.stroke_width_spinbox.setDecimals(2)
        self.stroke_width_spinbox.setKeyboardTracking(False)
        self.stroke_width_spinbox.setValue(0.07)
        self.stroke_width_spinbox.setMaximumWidth(96)
        stroke_width_layout.addWidget(self.stroke_width_spinbox)
        self.stroke_width_label = QLabel(self._t_field("Stroke Width:"))
        self.stroke_width_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        style_layout.addRow(self.stroke_width_label, stroke_width_layout)
        
        # Line spacing (行间距倍率)
        line_spacing_layout = QHBoxLayout()
        line_spacing_layout.setContentsMargins(0, 0, 0, 0)
        self.line_spacing_spinbox = QDoubleSpinBox()
        self.line_spacing_spinbox.setRange(0.1, 5.0)
        self.line_spacing_spinbox.setSingleStep(0.1)
        self.line_spacing_spinbox.setDecimals(2)
        self.line_spacing_spinbox.setKeyboardTracking(False)
        self.line_spacing_spinbox.setValue(1.0)
        self.line_spacing_spinbox.setMaximumWidth(96)
        line_spacing_layout.addWidget(self.line_spacing_spinbox)
        self.line_spacing_label = QLabel(self._t_field("Line Spacing:"))
        self.line_spacing_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        style_layout.addRow(self.line_spacing_label, line_spacing_layout)

        letter_spacing_layout = QHBoxLayout()
        letter_spacing_layout.setContentsMargins(0, 0, 0, 0)
        self.letter_spacing_spinbox = QDoubleSpinBox()
        self.letter_spacing_spinbox.setRange(0.1, 5.0)
        self.letter_spacing_spinbox.setSingleStep(0.1)
        self.letter_spacing_spinbox.setDecimals(2)
        self.letter_spacing_spinbox.setKeyboardTracking(False)
        self.letter_spacing_spinbox.setValue(1.0)
        self.letter_spacing_spinbox.setMaximumWidth(96)
        letter_spacing_layout.addWidget(self.letter_spacing_spinbox)
        self.letter_spacing_label = QLabel(self._t_field("Letter Spacing:"))
        self.letter_spacing_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        style_layout.addRow(self.letter_spacing_label, letter_spacing_layout)

        char_width_layout = QHBoxLayout()
        char_width_layout.setContentsMargins(0, 0, 0, 0)
        self.char_width_spinbox = QDoubleSpinBox()
        self.char_width_spinbox.setRange(0.1, 5.0)
        self.char_width_spinbox.setSingleStep(0.1)
        self.char_width_spinbox.setDecimals(2)
        self.char_width_spinbox.setKeyboardTracking(False)
        self.char_width_spinbox.setValue(1.0)
        self.char_width_spinbox.setMaximumWidth(96)
        char_width_layout.addWidget(self.char_width_spinbox)
        self.char_width_label = QLabel(self._t_field("Char Width:"))
        self.char_width_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        style_layout.addRow(self.char_width_label, char_width_layout)

        angle_layout = QHBoxLayout()
        angle_layout.setContentsMargins(0, 0, 0, 0)
        self.angle_spinbox = QDoubleSpinBox()
        self.angle_spinbox.setRange(-9999.0, 9999.0)
        self.angle_spinbox.setSingleStep(1.0)
        self.angle_spinbox.setDecimals(1)
        self.angle_spinbox.setKeyboardTracking(False)
        self.angle_spinbox.setSuffix("°")
        self.angle_spinbox.setValue(0.0)
        self.angle_spinbox.setMaximumWidth(110)
        angle_layout.addWidget(self.angle_spinbox)
        self.angle_style_label = QLabel(self._t_field("Angle:"))
        self.angle_style_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        style_layout.addRow(self.angle_style_label, angle_layout)

        self.distort_mode_checkbox = QCheckBox(self._t("4-Point Distort"))
        self.distort_mode_checkbox.setObjectName("editor_distort_mode_checkbox")
        set_hover_hint(self.distort_mode_checkbox, self._t("4-Point Distort Hint") + " (Alt+↑)")
        distort_wrap = QWidget()
        distort_wrap_layout = QVBoxLayout(distort_wrap)
        distort_wrap_layout.setContentsMargins(0, 0, 0, 1)
        distort_wrap_layout.addWidget(self.distort_mode_checkbox)
        style_layout.addRow("", distort_wrap)
        
        # Alignment and direction
        self.alignment_combo = QComboBox()
        self.direction_combo = QComboBox()
        self.alignment_combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.alignment_combo.setMinimumContentsLength(6)
        self.direction_combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.direction_combo.setMinimumContentsLength(6)
        self.alignment_label = QLabel(self._t_field("Alignment:"))
        self.alignment_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.direction_label = QLabel(self._t_field("Direction:"))
        self.direction_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        style_layout.addRow(self.alignment_label, self.alignment_combo)
        style_layout.addRow(self.direction_label, self.direction_combo)
        
        layout.addWidget(self.style_edit_frame)
    
    def _create_action_section(self, layout):
        self.action_frame = QWidget()
        self.action_frame.setObjectName("editor_action_group")
        action_layout = QVBoxLayout(self.action_frame)
        action_layout.setContentsMargins(6, 8, 6, 6)
        action_layout.setSpacing(0)
        self.copy_button = QPushButton(self._t("Copy Style"))
        self.copy_button.setObjectName("editor_copy_action_button")
        self.copy_button.setProperty("softAction", True)
        self.copy_button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        set_hover_hint(self.copy_button, self._t("Copy Style") + " (Ctrl+C)")
        self.paste_button = QPushButton(self._t("Paste Style"))
        self.paste_button.setObjectName("editor_paste_action_button")
        self.paste_button.setProperty("softAction", True)
        self.paste_button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        set_hover_hint(self.paste_button, self._t("Paste Style") + " (Ctrl+V)")
        self.delete_button = QPushButton(self._t("Delete Layer"))
        self.delete_button.setObjectName("editor_delete_action_button")
        self.delete_button.setProperty("variant", "danger")
        self.delete_button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        set_hover_hint(self.delete_button, self._t("Delete Layer") + " (Del)")
        copy_paste_row = QHBoxLayout()
        copy_paste_row.setContentsMargins(0, 0, 0, 0)
        copy_paste_row.setSpacing(7)
        copy_paste_row.addWidget(self.copy_button)
        copy_paste_row.addWidget(self.paste_button)
        action_layout.addLayout(copy_paste_row)
        action_layout.addSpacing(9)
        action_layout.addWidget(self.delete_button)
        action_layout.addSpacing(12)
        action_layout.addWidget(self._make_section_divider())
        action_layout.addSpacing(8)
        action_layout.addWidget(self._create_ocr_translate_block())
        layout.addWidget(self.action_frame)

    def _create_ocr_translate_block(self) -> QWidget:
        block = QWidget()
        ocr_trans_config_layout = QVBoxLayout(block)
        ocr_trans_config_layout.setContentsMargins(0, 0, 0, 0)
        ocr_trans_config_layout.setSpacing(9)
        self.ocr_model_combo = QComboBox()
        self.ocr_model_combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.ocr_model_combo.setMinimumContentsLength(8)
        self.translator_combo = QComboBox()
        self.translator_combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.translator_combo.setMinimumContentsLength(8)
        self.target_language_combo = QComboBox()
        self.target_language_combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.target_language_combo.setMinimumContentsLength(8)
        self.ocr_button = QPushButton(self._t("OCR Re-recognize"))
        self.ocr_button.setObjectName("editor_recognize_button")
        self.ocr_button.setProperty("softAction", True)
        self.translate_button = QPushButton(self._t("API Re-translate"))
        self.translate_button.setObjectName("editor_translate_button")
        self.translate_button.setProperty("softAction", True)
        model_label_text = self._t_field("Model:")
        self.ocr_model_row_label = QLabel(model_label_text)
        self.translator_row_label = QLabel(model_label_text)
        self.ocr_model_row_label.setBuddy(self.ocr_model_combo)
        self.translator_row_label.setBuddy(self.translator_combo)
        for combo in (self.ocr_model_combo, self.translator_combo):
            combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            combo.setMinimumWidth(0)
        for label in (self.ocr_model_row_label, self.translator_row_label):
            label.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
            label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        for button in (self.ocr_button, self.translate_button):
            button.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
        ocr_trans_grid = QGridLayout()
        ocr_trans_grid.setContentsMargins(0, 0, 0, 0)
        ocr_trans_grid.setHorizontalSpacing(7)
        ocr_trans_grid.setVerticalSpacing(9)
        ocr_trans_grid.setColumnStretch(0, 0)
        ocr_trans_grid.setColumnStretch(1, 1)
        ocr_trans_grid.setColumnStretch(2, 0)
        ocr_trans_grid.addWidget(self.ocr_model_row_label, 0, 0)
        ocr_trans_grid.addWidget(self.ocr_model_combo, 0, 1)
        ocr_trans_grid.addWidget(self.ocr_button, 0, 2)
        ocr_trans_grid.addWidget(self.translator_row_label, 1, 0)
        ocr_trans_grid.addWidget(self.translator_combo, 1, 1)
        ocr_trans_grid.addWidget(self.translate_button, 1, 2)
        ocr_trans_config_layout.addLayout(ocr_trans_grid)
        QTimer.singleShot(0, self._sync_ocr_translate_row_metrics)
        self.target_lang_row_label = QLabel(self._t_field("Target Language:"))
        self.target_lang_row_label.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
        self.target_language_combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.target_lang_row_label.setBuddy(self.target_language_combo)
        target_lang_row = QWidget()
        target_lang_row_layout = QHBoxLayout(target_lang_row)
        target_lang_row_layout.setContentsMargins(0, 0, 0, 0)
        target_lang_row_layout.setSpacing(8)
        target_lang_row_layout.addWidget(self.target_lang_row_label)
        target_lang_row_layout.addWidget(self.target_language_combo, 1)
        ocr_trans_config_layout.addWidget(target_lang_row)
        return block
    
    def _connect_signals(self):
        # Mask
        self.mask_tool_group.buttonClicked.connect(self._on_mask_tool_changed)
        self.brush_size_slider.valueChanged.connect(self._on_brush_size_changed)
        self.show_refined_mask_checkbox.stateChanged.connect(self._on_inpaint_area_toggled)
        self.show_paint_overlay_checkbox.stateChanged.connect(self._on_overlay_area_toggled)
        # self.clear_all_masks_button.clicked.connect(self.clear_all_masks_requested.emit)

        # Paint overlay
        self.paint_color_picker.color_changed.connect(self._on_paint_color_changed)
        # self.clear_paint_overlay_button.clicked.connect(self.clear_paint_overlay_requested.emit)

        # Style
        self.font_family_combo.currentIndexChanged.connect(self._on_font_family_changed)
        self.font_size_input.editingFinished.connect(self._on_font_size_editing_finished)
        self.italic_button.toggled.connect(self._on_italic_toggled)
        self.bold_button.toggled.connect(self._on_bold_toggled)
        self.font_color_picker.color_changed.connect(self._on_font_color_changed)
        self.stroke_color_picker.color_changed.connect(self._on_stroke_color_changed)
        self.stroke_width_spinbox.valueChanged.connect(self._on_stroke_width_changed)
        self.line_spacing_spinbox.valueChanged.connect(self._on_line_spacing_changed)
        self.letter_spacing_spinbox.valueChanged.connect(self._on_letter_spacing_changed)
        self.char_width_spinbox.valueChanged.connect(self._on_char_width_changed)
        self.angle_spinbox.valueChanged.connect(self._on_angle_changed)
        self.distort_mode_checkbox.toggled.connect(self._on_distort_mode_toggled)
        self.style_preset_combo.activated.connect(self._on_style_preset_activated)
        self.save_style_preset_button.clicked.connect(self._on_save_style_preset_clicked)
        self.delete_style_preset_button.clicked.connect(self._on_delete_style_preset_clicked)
        # 实时更新（textChanged）
        self.translated_text_box.textChanged.connect(self._on_translated_text_changed)
        # self.translated_text_box.focusOutEvent = self._make_focus_out_handler(self.translated_text_box, self._on_translated_text_focus_out)
        self.alignment_combo.currentTextChanged.connect(self._on_alignment_changed)
        self.direction_combo.currentTextChanged.connect(self._on_direction_changed)

        # Text
        # 实时更新（textChanged）
        self.original_text_box.textChanged.connect(self._on_original_text_changed)
        # self.original_text_box.focusOutEvent = self._make_focus_out_handler(self.original_text_box, self._on_original_text_focus_out)
        self.ocr_model_combo.currentTextChanged.connect(self._on_ocr_model_change)
        self.translator_combo.currentTextChanged.connect(self._on_translator_change)
        self.target_language_combo.currentTextChanged.connect(self._on_target_language_change)
        self.ocr_button.clicked.connect(self.ocr_requested.emit)
        self.translate_button.clicked.connect(self.translation_requested.emit)
        self.insert_placeholder_button.clicked.connect(self._clean_whitespace_clicked)
        
        # Action buttons
        self.copy_button.clicked.connect(self.copy_region_requested.emit)
        self.paste_button.clicked.connect(self.paste_region_requested.emit)
        self.delete_button.clicked.connect(self.delete_region_requested.emit)
    def _connect_model_signals(self):
        self.model.display_mask_type_changed.connect(self._on_display_mask_type_changed)
        self.model.refined_mask_changed.connect(self._on_refined_mask_changed)
        self.model.regions_changed.connect(self.on_regions_updated)
        self.model.region_style_updated.connect(self.on_single_region_updated)

    def _on_inpaint_area_toggled(self, state):
        self.toggle_mask_visibility.emit(bool(state))

    def _on_overlay_area_toggled(self, state):
        self.toggle_overlay_visibility.emit(bool(state))

    def _sync_area_display_checkboxes(self, mask_type: str):
        inpaint_checked = mask_type == "refined"
        overlay_checked = mask_type == "paint"
        if hasattr(self, "show_refined_mask_checkbox"):
            self.show_refined_mask_checkbox.blockSignals(True)
            self.show_refined_mask_checkbox.setChecked(inpaint_checked)
            self.show_refined_mask_checkbox.blockSignals(False)
        if hasattr(self, "show_paint_overlay_checkbox"):
            self.show_paint_overlay_checkbox.blockSignals(True)
            self.show_paint_overlay_checkbox.setChecked(overlay_checked)
            self.show_paint_overlay_checkbox.blockSignals(False)

    def _on_display_mask_type_changed(self, mask_type: str):
        """响应显示蒙版类型变化"""
        self._sync_area_display_checkboxes(mask_type)

    def _on_refined_mask_changed(self, mask):
        """响应refined mask数据变化"""
        # 不自动勾选checkbox，让用户自己决定是否显示
        pass

    def repopulate_options(self):
        """Public method to populate combo boxes from config. Should be called after config is loaded."""
        if not self.app_logic:
            return

        config = self.app_logic.config_service.get_config()
        ocr_config = config.ocr
        translator_config = config.translator

        # OCR - 阻止信号避免触发不必要的配置更新
        self.ocr_model_combo.blockSignals(True)
        ocr_options = self.app_logic.get_options_for_key('ocr')
        if ocr_options:
            self.ocr_model_combo.clear()
            self.ocr_model_combo.addItems(ocr_options)
            current_ocr = ocr_config.ocr
            if current_ocr in ocr_options:
                self.ocr_model_combo.setCurrentText(current_ocr)
        self.ocr_model_combo.blockSignals(False)

        # Translator - 阻止信号避免触发不必要的配置更新
        self.translator_combo.blockSignals(True)
        translator_map = self.app_logic.get_display_mapping('translator')
        if translator_map:
            self.translator_display_to_key = {v: k for k, v in translator_map.items()}
            self.translator_combo.clear()
            self.translator_combo.addItems(list(translator_map.values()))
            current_translator_key = translator_config.translator
            current_translator_display = translator_map.get(current_translator_key)
            if current_translator_display:
                self.translator_combo.setCurrentText(current_translator_display)
        self.translator_combo.blockSignals(False)

        # Target Language - 阻止信号避免触发不必要的配置更新
        self.target_language_combo.blockSignals(True)
        lang_map = self.app_logic.get_display_mapping('target_lang')
        if lang_map:
            self.lang_name_to_code = {v: k for k, v in lang_map.items()}
            self.target_language_combo.clear()
            self.target_language_combo.addItems(list(lang_map.values()))
            current_lang_key = translator_config.target_lang
            current_lang_display = lang_map.get(current_lang_key)
            if current_lang_display:
                self.target_language_combo.setCurrentText(current_lang_display)
        self.target_language_combo.blockSignals(False)

        # Alignment
        alignment_map = self.app_logic.get_display_mapping('alignment')
        if alignment_map:
            self.alignment_combo.clear()
            self.alignment_combo.addItems(list(alignment_map.values()))

        # Direction
        direction_map = self.app_logic.get_display_mapping('direction')
        if direction_map:
            self.direction_combo.clear()
            direction_items = [v for k, v in direction_map.items() if k != 'auto']
            self.direction_combo.addItems(direction_items)
    
    def refresh_ui_texts(self):
        """刷新所有UI文本（用于语言切换）"""
        # 刷新分组框标题
        if hasattr(self, 'info_group'):
            self.info_group.setTitle(self._t("Region Info"))
        
        # 刷新标签
        if hasattr(self, 'index_row_label'):
            self.index_row_label.setText(self._t_field("Index:"))
        if hasattr(self, 'bbox_row_label'):
            self.bbox_row_label.setText(self._t_field("Position:"))
        if hasattr(self, 'size_row_label'):
            self.size_row_label.setText(self._t_field("Size:"))
        if hasattr(self, 'angle_row_label'):
            self.angle_row_label.setText(self._t_field("Angle:"))
        if hasattr(self, 'brush_size_title_label'):
            self.brush_size_title_label.setText(self._t_field("Brush Size:") + " ")
        if hasattr(self, 'target_lang_row_label'):
            self.target_lang_row_label.setText(self._t_field("Target Language:"))
        model_label_text = self._t_field("Model:")
        if hasattr(self, 'ocr_model_row_label'):
            self.ocr_model_row_label.setText(model_label_text)
        if hasattr(self, 'translator_row_label'):
            self.translator_row_label.setText(model_label_text)
        if hasattr(self, 'font_label'):
            self.font_label.setText(self._t_field("Font:"))
        if hasattr(self, 'font_family_combo'):
            self.font_family_combo.refresh_ui_texts()
        if hasattr(self, 'style_preset_label'):
            self.style_preset_label.setText(self._t_field("Style Preset:"))
        if hasattr(self, 'font_size_label'):
            self.font_size_label.setText(self._t_field("Font Size:"))
        if hasattr(self, 'bold_button'):
            self.bold_button.setText("B")
            set_hover_hint(self.bold_button, "굵게 (B)")
        if hasattr(self, 'italic_button'):
            self.italic_button.setText("I")
            set_hover_hint(self.italic_button, "기울임 (I)")
        if hasattr(self, 'font_color_label'):
            self.font_color_label.setText(self._t_field("Font Color:"))
        if hasattr(self, 'stroke_color_label'):
            self.stroke_color_label.setText(self._t_field("Stroke Color:"))

        # 刷新颜色选择器内部文本
        if hasattr(self, 'font_color_picker'):
            self.font_color_picker.refresh_ui_texts()
        if hasattr(self, 'stroke_color_picker'):
            self.stroke_color_picker.refresh_ui_texts()

        if hasattr(self, 'stroke_width_label'):
            self.stroke_width_label.setText(self._t_field("Stroke Width:"))
        if hasattr(self, 'line_spacing_label'):
            self.line_spacing_label.setText(self._t_field("Line Spacing:"))
        if hasattr(self, 'letter_spacing_label'):
            self.letter_spacing_label.setText(self._t_field("Letter Spacing:"))
        if hasattr(self, 'char_width_label'):
            self.char_width_label.setText(self._t_field("Char Width:"))
        if hasattr(self, 'angle_style_label'):
            self.angle_style_label.setText(self._t_field("Angle:"))
        if hasattr(self, 'distort_mode_checkbox'):
            self.distort_mode_checkbox.setText(self._t("4-Point Distort"))
            set_hover_hint(self.distort_mode_checkbox, self._t("4-Point Distort Hint") + " (Alt+↑)")
        if hasattr(self, 'alignment_label'):
            self.alignment_label.setText(self._t_field("Alignment:"))
        if hasattr(self, 'direction_label'):
            self.direction_label.setText(self._t_field("Direction:"))
        if hasattr(self, 'original_text_label'):
            self.original_text_label.setText(self._t_field("Original Text:"))
        if hasattr(self, 'translation_raw_checkbox'):
            self.translation_raw_checkbox.setText(self._t("Show Translation (Raw)"))
        if hasattr(self, 'insert_placeholder_button'):
            self.insert_placeholder_button.setText(self._t("Clean Whitespace"))
            set_hover_hint(self.insert_placeholder_button, self._t("Clean Whitespace"))
        if hasattr(self, 'translated_text_label'):
            self.translated_text_label.setText(self._t_field("Translated Text:"))
        if hasattr(self, 'text_esc_hint_label'):
            self.text_esc_hint_label.setText(self._t("Esc: Finish editing"))
        if hasattr(self, 'text_stats_label'):
            self._refresh_text_stats()
        
        # 刷新按钮
        if hasattr(self, 'ocr_button'):
            self.ocr_button.setText(self._t("OCR Re-recognize"))
        if hasattr(self, 'translate_button'):
            self.translate_button.setText(self._t("API Re-translate"))
        self._sync_ocr_translate_row_metrics()
        QTimer.singleShot(0, self._sync_font_row_metrics)
        if hasattr(self, 'brush_button'):
            self.brush_button.setText(self._t("Inpaint Brush"))
            set_hover_hint(self.brush_button, self._t("Inpaint Brush") + " (W)")
        if hasattr(self, 'eraser_button'):
            self.eraser_button.setText(self._t("Inpaint Erase"))
            set_hover_hint(self.eraser_button, self._t("Inpaint Erase") + " (E)")
        if hasattr(self, 'select_button'):
            self.select_button.setText(self._t("Selection Tool"))
            set_hover_hint(self.select_button, self._t("Selection Tool") + " (Q)")
        if hasattr(self, 'paint_brush_button'):
            self.paint_brush_button.setText(self._t("Overlay Brush"))
            set_hover_hint(self.paint_brush_button, self._t("Overlay Brush") + " (R)")
        if hasattr(self, 'paint_eraser_button'):
            self.paint_eraser_button.setText(self._t("Overlay Eraser"))
            set_hover_hint(self.paint_eraser_button, self._t("Overlay Eraser") + " (T)")
        if hasattr(self, 'paint_color_label'):
            self.paint_color_label.setText(self._t_field("Overlay Brush Color:") + " ")
        if hasattr(self, 'paint_color_picker'):
            self.paint_color_picker.refresh_ui_texts()
        if hasattr(self, 'clear_paint_overlay_button'):
            self.clear_paint_overlay_button.setText(self._t("Clear Paint Layer"))
        if hasattr(self, 'insert_note_button'):
            set_hover_hint(self.insert_note_button, self._t("Insert ♪"))
        if hasattr(self, 'insert_heart_outline_button'):
            set_hover_hint(self.insert_heart_outline_button, self._t("Insert ♡"))
        if hasattr(self, 'insert_heart_filled_button'):
            set_hover_hint(self.insert_heart_filled_button, self._t("Insert ♥"))
        if hasattr(self, 'copy_button'):
            self.copy_button.setText(self._t("Copy Style"))
            set_hover_hint(self.copy_button, self._t("Copy Style") + " (Ctrl+C)")
        if hasattr(self, 'paste_button'):
            self.paste_button.setText(self._t("Paste Style"))
            set_hover_hint(self.paste_button, self._t("Paste Style") + " (Ctrl+V)")
        if hasattr(self, 'delete_button'):
            self.delete_button.setText(self._t("Delete Layer"))
            set_hover_hint(self.delete_button, self._t("Delete Layer") + " (Del)")
        if hasattr(self, 'save_style_preset_button') or hasattr(self, 'delete_style_preset_button'):
            self._refresh_style_preset_action_buttons()
        
        # 刷新复选框
        if hasattr(self, 'show_refined_mask_checkbox'):
            self.show_refined_mask_checkbox.setText(self._t("Show Inpaint Area"))
        if hasattr(self, 'show_paint_overlay_checkbox'):
            self.show_paint_overlay_checkbox.setText(self._t("Show Overlay Area"))
        if hasattr(self, 'clear_all_masks_button'):
            self.clear_all_masks_button.setText(self._t("Clear All Masks"))
        
        # 刷新下拉菜单（重新填充以使用新的翻译）
        self._refresh_combo_boxes()
        self._refresh_style_preset_combo()
    
    def _refresh_combo_boxes(self):
        """刷新所有下拉菜单的选项"""
        # 保存当前选中的索引（而不是文本，因为文本会随语言变化）
        current_translator_index = self.translator_combo.currentIndex()
        current_target_lang_index = self.target_language_combo.currentIndex()
        current_alignment_index = self.alignment_combo.currentIndex()
        current_direction_index = self.direction_combo.currentIndex()
        
        # 重新填充翻译器下拉菜单
        translator_map = self.app_logic.get_display_mapping('translator')
        if translator_map:
            self.translator_combo.blockSignals(True)
            self.translator_combo.clear()
            self.translator_combo.addItems(list(translator_map.values()))
            # 恢复选中的索引
            if 0 <= current_translator_index < self.translator_combo.count():
                self.translator_combo.setCurrentIndex(current_translator_index)
            self.translator_combo.blockSignals(False)
        
        # 重新填充目标语言下拉菜单
        lang_map = self.app_logic.get_display_mapping('target_lang')
        if lang_map:
            self.target_language_combo.blockSignals(True)
            self.target_language_combo.clear()
            self.target_language_combo.addItems(list(lang_map.values()))
            # 恢复选中的索引
            if 0 <= current_target_lang_index < self.target_language_combo.count():
                self.target_language_combo.setCurrentIndex(current_target_lang_index)
            self.target_language_combo.blockSignals(False)
        
        # 重新填充对齐下拉菜单
        alignment_map = self.app_logic.get_display_mapping('alignment')
        if alignment_map:
            self.alignment_combo.blockSignals(True)
            self.alignment_combo.clear()
            self.alignment_combo.addItems(list(alignment_map.values()))
            # 恢复选中的索引
            if 0 <= current_alignment_index < self.alignment_combo.count():
                self.alignment_combo.setCurrentIndex(current_alignment_index)
            self.alignment_combo.blockSignals(False)
        
        # 重新填充方向下拉菜单
        direction_map = self.app_logic.get_display_mapping('direction')
        if direction_map:
            self.direction_combo.blockSignals(True)
            self.direction_combo.clear()
            direction_items = [v for k, v in direction_map.items() if k != 'auto']
            self.direction_combo.addItems(direction_items)
            # 恢复选中的索引
            if 0 <= current_direction_index < self.direction_combo.count():
                self.direction_combo.setCurrentIndex(current_direction_index)
            self.direction_combo.blockSignals(False)

    def _get_saved_style_presets(self):
        config_ref = self.config_service.get_config_reference()
        presets = getattr(getattr(config_ref, "app", None), "saved_style_presets", None)
        return presets if isinstance(presets, dict) else {}

    def _get_editor_controller(self):
        """EditorView 등 상위 위젯에서 EditorController를 찾는다."""
        parent = self.parent()
        while parent is not None:
            controller = getattr(parent, "controller", None)
            if controller is not None and hasattr(controller, "set_style_slot_data"):
                return controller
            parent = parent.parent()
        return None

    @staticmethod
    def _parse_style_slot_from_preset_name(name: str) -> str | None:
        """프리셋 이름 맨 앞 숫자(0-9)를 슬롯 키로 반환. 예: '3 감정표현' -> '3'."""
        text = str(name or "").strip()
        if not text:
            return None
        first = text[0]
        if first.isdigit():
            return first
        return None

    def _sync_style_slots_from_presets(self):
        """이름이 숫자로 시작하는 스타일 프리셋을 Ctrl+숫자 슬롯에 할당.

        '3 감정표현' 프리셋 → 슬롯 '3'에 넣는 것은 Ctrl+3으로 복사한 것과 동일.
        콤보 매 갱신마다 호출하지 않고, 로드/저장/삭제 시에만 호출해
        사용자가 수동으로 넣은 슬롯을 불필요하게 덮어쓰지 않는다.
        """
        controller = self._get_editor_controller()
        if controller is None:
            return

        presets = self._get_saved_style_presets()
        for name, raw_style in presets.items():
            slot = self._parse_style_slot_from_preset_name(str(name))
            if slot is None:
                continue
            style_data = self._normalize_saved_style_preset(raw_style)
            if style_data:
                controller.set_style_slot_data(slot, style_data)

    def _refresh_style_preset_combo(self, selected_name: str | None = None):
        if not hasattr(self, "style_preset_combo"):
            return

        current_name = selected_name if selected_name is not None else self.style_preset_combo.currentData()
        presets = self._get_saved_style_presets()

        self.style_preset_combo.blockSignals(True)
        try:
            self.style_preset_combo.clear()
            self.style_preset_combo.addItem(self._t("Select saved style"), None)
            for name in presets.keys():
                self.style_preset_combo.addItem(name, name)

            if current_name in presets:
                target_index = self.style_preset_combo.findData(current_name)
                self.style_preset_combo.setCurrentIndex(target_index if target_index >= 0 else 0)
            else:
                self.style_preset_combo.setCurrentIndex(0)
        finally:
            self.style_preset_combo.blockSignals(False)

        self.style_preset_combo.setToolTip(self._t("Choose a saved style to apply"))

    def _normalize_region_style_state(self, region_data):
        if not isinstance(region_data, dict):
            return {}

        default_font_color = self.config_service.get_config().render.font_color or "#000000"
        normalized = {}
        font_value = region_data.get("font_family", "")
        normalized["font_family"] = "" if font_value is None else str(font_value)

        font_color = region_data.get("font_color")
        fg_colors = region_data.get("fg_colors")
        if not font_color and isinstance(fg_colors, (list, tuple)) and len(fg_colors) == 3:
            font_color = f"#{int(fg_colors[0]):02x}{int(fg_colors[1]):02x}{int(fg_colors[2]):02x}"
        font_color = str(font_color or default_font_color).strip()
        normalized["font_color"] = QColor(font_color).name() if QColor(font_color).isValid() else "#000000"

        stroke_color = region_data.get("stroke_color")
        if not stroke_color:
            bg_color = region_data.get("bg_color")
            bg_colors = region_data.get("bg_colors")
            if isinstance(bg_color, (list, tuple)) and len(bg_color) == 3:
                stroke_color = f"#{int(bg_color[0]):02x}{int(bg_color[1]):02x}{int(bg_color[2]):02x}"
            elif isinstance(bg_colors, (list, tuple)) and len(bg_colors) == 3:
                stroke_color = f"#{int(bg_colors[0]):02x}{int(bg_colors[1]):02x}{int(bg_colors[2]):02x}"
        stroke_color = str(stroke_color or "#ffffff").strip()
        normalized["stroke_color"] = QColor(stroke_color).name() if QColor(stroke_color).isValid() else "#ffffff"

        try:
            normalized["stroke_width"] = float(region_data.get("stroke_width", region_data.get("default_stroke_width", 0.07)))
        except (TypeError, ValueError):
            normalized["stroke_width"] = 0.07

        try:
            normalized["line_spacing"] = float(region_data.get("line_spacing", 1.0))
        except (TypeError, ValueError):
            normalized["line_spacing"] = 1.0

        try:
            normalized["letter_spacing"] = float(region_data.get("letter_spacing", 1.0))
        except (TypeError, ValueError):
            normalized["letter_spacing"] = 1.0

        try:
            normalized["char_width"] = float(region_data.get("char_width", 1.0))
        except (TypeError, ValueError):
            normalized["char_width"] = 1.0

        normalized["italic"] = bool(region_data.get("italic", False))
        normalized["bold"] = bool(region_data.get("bold", False))
        normalized["alignment"] = self._alignment_value_from_text(region_data.get("alignment", "auto"))
        normalized["direction"] = self._direction_value_from_text(region_data.get("direction", "horizontal"))
        return normalized

    def _find_matching_style_preset_name(self, region_data) -> str | None:
        normalized_region_style = self._normalize_region_style_state(region_data)
        if not normalized_region_style:
            return None

        for name, preset_data in self._get_saved_style_presets().items():
            if self._normalize_saved_style_preset(preset_data) == normalized_region_style:
                return str(name)
        return None

    def _refresh_style_preset_action_buttons(self):
        if hasattr(self, "save_style_preset_button"):
            self.save_style_preset_button.setText("")
            self.save_style_preset_button.setIcon(
                self.style().standardIcon(QStyle.StandardPixmap.SP_DialogSaveButton)
            )
            set_hover_hint(self.save_style_preset_button, self._t("Save current style combination"))
            self.save_style_preset_button.setAccessibleName(self._t("Save Style"))

        if hasattr(self, "delete_style_preset_button"):
            self.delete_style_preset_button.setText("")
            self.delete_style_preset_button.setIcon(
                self.style().standardIcon(QStyle.StandardPixmap.SP_DialogCancelButton)
            )
            set_hover_hint(self.delete_style_preset_button, self._t("Delete selected saved style"))
            self.delete_style_preset_button.setAccessibleName(self._t("Delete Style"))

    def _alignment_value_from_text(self, text: str) -> str:
        raw_text = str(text or "").strip()
        if raw_text in {"auto", "left", "center", "right"}:
            return raw_text

        alignment_map = self.app_logic.get_display_mapping('alignment') or {}
        reverse_map = {display: value for value, display in alignment_map.items()}
        if raw_text in reverse_map:
            return reverse_map[raw_text]

        fallback_map = {"自动": "auto", "左对齐": "left", "居中": "center", "右对齐": "right"}
        return fallback_map.get(raw_text, "auto")

    def _alignment_text_for_value(self, value: str) -> str:
        alignment_map = self.app_logic.get_display_mapping('alignment') or {}
        normalized_value = self._alignment_value_from_text(value)
        fallback_map = {"auto": "自动", "left": "左对齐", "center": "居中", "right": "右对齐"}
        return alignment_map.get(normalized_value, fallback_map.get(normalized_value, normalized_value))

    def _direction_value_from_text(self, text: str) -> str:
        raw_text = str(text or "").strip()
        lower_text = raw_text.lower()
        if lower_text in {"h", "horizontal"}:
            return "horizontal"
        if lower_text in {"v", "vertical"}:
            return "vertical"

        direction_map = self.app_logic.get_display_mapping('direction') or {}
        horizontal_text = direction_map.get('h', self._t("direction_horizontal"))
        vertical_text = direction_map.get('v', self._t("direction_vertical"))
        if raw_text == vertical_text or raw_text == "竖排":
            return "vertical"
        if raw_text == horizontal_text or raw_text == "横排":
            return "horizontal"
        return "horizontal"

    def _direction_text_for_value(self, value: str) -> str:
        direction_map = self.app_logic.get_display_mapping('direction') or {}
        horizontal_text = direction_map.get('h', self._t("direction_horizontal"))
        vertical_text = direction_map.get('v', self._t("direction_vertical"))
        normalized_value = self._direction_value_from_text(value)
        return vertical_text if normalized_value == "vertical" else horizontal_text

    def _set_font_family_combo_value(self, font_value: str):
        self.font_family_combo.setCurrentFamily(font_value)

    def _normalize_saved_style_preset(self, style_data):
        if not isinstance(style_data, dict):
            return {}

        normalized = {}
        font_value = style_data.get("font_family", "")
        normalized["font_family"] = "" if font_value is None else str(font_value)

        font_color = str(style_data.get("font_color") or "#000000").strip()
        normalized["font_color"] = QColor(font_color).name() if QColor(font_color).isValid() else "#000000"

        stroke_color = style_data.get("stroke_color")
        if not stroke_color:
            bg_colors = style_data.get("bg_colors", style_data.get("bg_color"))
            if isinstance(bg_colors, (list, tuple)) and len(bg_colors) == 3:
                stroke_color = f"#{int(bg_colors[0]):02x}{int(bg_colors[1]):02x}{int(bg_colors[2]):02x}"
        stroke_color = str(stroke_color or "#ffffff").strip()
        normalized["stroke_color"] = QColor(stroke_color).name() if QColor(stroke_color).isValid() else "#ffffff"

        try:
            normalized["stroke_width"] = float(style_data.get("stroke_width", 0.07))
        except (TypeError, ValueError):
            normalized["stroke_width"] = 0.07

        try:
            normalized["line_spacing"] = float(style_data.get("line_spacing", 1.0))
        except (TypeError, ValueError):
            normalized["line_spacing"] = 1.0

        try:
            normalized["letter_spacing"] = float(style_data.get("letter_spacing", 1.0))
        except (TypeError, ValueError):
            normalized["letter_spacing"] = 1.0

        try:
            normalized["char_width"] = float(style_data.get("char_width", 1.0))
        except (TypeError, ValueError):
            normalized["char_width"] = 1.0

        normalized["italic"] = bool(style_data.get("italic", False))
        normalized["bold"] = bool(style_data.get("bold", False))
        normalized["alignment"] = self._alignment_value_from_text(style_data.get("alignment", "auto"))
        normalized["direction"] = self._direction_value_from_text(style_data.get("direction", "horizontal"))
        return normalized

    def _collect_current_style_preset(self):
        current_font = self.font_family_combo.currentFamily()

        return {
            "font_family": str(current_font or ""),
            "font_color": self.font_color_picker.get_color(),
            "stroke_color": self.stroke_color_picker.get_color(),
            "stroke_width": float(self.stroke_width_spinbox.value()),
            "line_spacing": float(self.line_spacing_spinbox.value()),
            "letter_spacing": float(self.letter_spacing_spinbox.value()),
            "char_width": float(self.char_width_spinbox.value()),
            "italic": bool(self.italic_button.isChecked()),
            "bold": bool(self.bold_button.isChecked()),
            "alignment": self._alignment_value_from_text(self.alignment_combo.currentText()),
            "direction": self._direction_value_from_text(self.direction_combo.currentText()),
        }

    def _set_style_controls_from_preset(self, style_data):
        normalized = self._normalize_saved_style_preset(style_data)
        if not normalized:
            return

        self._set_font_family_combo_value(normalized.get("font_family", ""))
        self.font_color_picker.set_color(normalized.get("font_color", "#000000"))
        self.stroke_color_picker.set_color(normalized.get("stroke_color", "#ffffff"))
        self.stroke_width_spinbox.setValue(normalized.get("stroke_width", 0.07))
        self.line_spacing_spinbox.setValue(normalized.get("line_spacing", 1.0))
        self.letter_spacing_spinbox.setValue(normalized.get("letter_spacing", 1.0))
        self.char_width_spinbox.setValue(normalized.get("char_width", 1.0))
        self.italic_button.setChecked(bool(normalized.get("italic", False)))
        self.bold_button.setChecked(bool(normalized.get("bold", False)))
        self.alignment_combo.setCurrentText(self._alignment_text_for_value(normalized.get("alignment", "auto")))
        self.direction_combo.setCurrentText(self._direction_text_for_value(normalized.get("direction", "horizontal")))

    def _apply_saved_style_to_selection(self, preset_name: str):
        from PyQt6.QtWidgets import QMessageBox

        selected_indices = self.model.get_selection()
        if not selected_indices:
            QMessageBox.warning(self, self._t("Warning"), self._t("Please select at least one region"))
            self._refresh_style_preset_combo()
            return

        style_data = self._normalize_saved_style_preset(self._get_saved_style_presets().get(preset_name))
        if not style_data:
            QMessageBox.warning(self, self._t("Warning"), self._t("Selected style preset is invalid"))
            self._refresh_style_preset_combo()
            return

        self.block_updates = True
        try:
            self._set_style_controls_from_preset(style_data)
        finally:
            self.block_updates = False

        for region_index in selected_indices:
            self.font_family_changed.emit(region_index, style_data.get("font_family", ""))
            self.font_color_changed.emit(region_index, style_data.get("font_color", "#000000"))
            self.stroke_color_changed.emit(region_index, style_data.get("stroke_color", "#ffffff"))
            self.stroke_width_changed.emit(region_index, style_data.get("stroke_width", 0.07))
            self.line_spacing_changed.emit(region_index, style_data.get("line_spacing", 1.0))
            self.letter_spacing_changed.emit(region_index, style_data.get("letter_spacing", 1.0))
            self.char_width_changed.emit(region_index, style_data.get("char_width", 1.0))
            self.italic_changed.emit(region_index, bool(style_data.get("italic", False)))
            self.bold_changed.emit(region_index, bool(style_data.get("bold", False)))
            self.alignment_changed.emit(region_index, style_data.get("alignment", "auto"))
            self.direction_changed.emit(region_index, style_data.get("direction", "horizontal"))

        self._refresh_style_preset_combo(selected_name=preset_name)

    def _on_style_preset_activated(self, index: int):
        preset_name = self.style_preset_combo.itemData(index)
        if preset_name:
            self._apply_saved_style_to_selection(str(preset_name))

    def _on_save_style_preset_clicked(self):
        import copy

        from PyQt6.QtWidgets import QMessageBox

        default_name = self.style_preset_combo.currentData() or ""
        preset_name, ok = themed_get_text(
            self,
            title=self._t("Save Style"),
            label=self._t("Enter style preset name:"),
            text=str(default_name),
            ok_text=self._t("Save"),
            cancel_text=self._t("Cancel"),
        )
        if not ok:
            return

        preset_name = preset_name.strip()
        if not preset_name:
            QMessageBox.warning(self, self._t("Warning"), self._t("Style preset name cannot be empty"))
            return

        current_presets = copy.deepcopy(self._get_saved_style_presets())
        if preset_name in current_presets:
            reply = QMessageBox.question(
                self,
                self._t("Confirm"),
                self._t("Style preset '{name}' already exists. Overwrite?", name=preset_name),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

        new_presets = copy.deepcopy(current_presets)
        new_presets[preset_name] = self._collect_current_style_preset()

        config_ref = self.config_service.get_config_reference()
        config_ref.app.saved_style_presets = new_presets
        if not self.config_service.save_config_file():
            config_ref.app.saved_style_presets = current_presets or None
            QMessageBox.critical(self, self._t("Error"), self._t("Failed to save style preset"))
            return

        self._refresh_style_preset_combo(selected_name=preset_name)
        self._sync_style_slots_from_presets()

    def _on_delete_style_preset_clicked(self):
        import copy

        from PyQt6.QtWidgets import QMessageBox

        preset_name = self.style_preset_combo.currentData()
        if not preset_name:
            QMessageBox.warning(self, self._t("Warning"), self._t("Please select a saved style"))
            return

        reply = QMessageBox.question(
            self,
            self._t("Confirm"),
            self._t("Delete style preset '{name}'?", name=preset_name),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        current_presets = copy.deepcopy(self._get_saved_style_presets())
        if preset_name not in current_presets:
            self._refresh_style_preset_combo()
            return

        new_presets = copy.deepcopy(current_presets)
        del new_presets[preset_name]

        config_ref = self.config_service.get_config_reference()
        config_ref.app.saved_style_presets = new_presets or None
        if not self.config_service.save_config_file():
            config_ref.app.saved_style_presets = current_presets or None
            QMessageBox.critical(self, self._t("Error"), self._t("Failed to delete style preset"))
            return

        self._refresh_style_preset_combo()
        self._sync_style_slots_from_presets()

    def on_single_region_updated(self, index: int):
        """Slot to refresh the panel when a single region is updated in a targeted way."""
        selected_indices = self.model.get_selection()
        if not selected_indices or len(selected_indices) > 1 or selected_indices[0] != index:
            return # Not the currently selected item, do nothing

        region_data = self.model.get_region_by_index(index)
        if region_data:
            self._update_display(region_data, index)
    
    def force_refresh_from_model(self):
        """强制刷新属性栏，忽略焦点状态（用于OCR/翻译完成后）"""
        selected_indices = self.model.get_selection()
        if selected_indices and len(selected_indices) == 1:
            region_index = selected_indices[0]
            region_data = self.model.get_region_by_index(region_index)
            if region_data:
                self._update_display(region_data, region_index, force=True)

    def on_regions_updated(self, regions):
        """Slot to refresh the panel if the currently selected region's data has changed."""
        selected_indices = self.model.get_selection()
        if not selected_indices or len(selected_indices) > 1:
            return
        
        region_index = selected_indices[0]
        if 0 <= region_index < len(regions):
            # 直接使用信号传递过来的最新regions数据来更新显示
            self._update_display(regions[region_index], region_index)

    def on_selection_changed(self, selected_indices):
        """Slot to update the panel when the selection in the model changes."""
        if not selected_indices:
            # 没有选择，禁用所有控件
            self.clear_and_disable_selection_dependent()
        elif len(selected_indices) == 1:
            # 单选，显示该区域的详细信息
            self.info_group.setEnabled(True)
            self.text_edit_frame.setEnabled(True)
            self.style_edit_frame.setEnabled(True)
            self.action_frame.setEnabled(True)
            region_index = selected_indices[0]
            self.current_region_index = region_index
            regions = self.model.get_regions()
            if 0 <= region_index < len(regions):
                self._update_display(regions[region_index], region_index)
        else:
            # 多选，启用样式编辑，但禁用文本编辑和信息显示
            self.info_group.setEnabled(False)
            self.text_edit_frame.setEnabled(False)
            self.style_edit_frame.setEnabled(True)  # 启用样式编辑
            self.action_frame.setEnabled(True)
            self.current_region_index = -1
            
            # 清空显示但不禁用样式控件
            self.block_updates = True
            self.index_label.setText(f"多选 ({len(selected_indices)})")
            self.original_text_box.clear()
            self.translated_text_box.clear()
            self._refresh_style_preset_combo(selected_name="")
            self._refresh_text_stats()
            self.block_updates = False

    def clear_and_disable_selection_dependent(self):
        """Clears selection-dependent fields and disables their sections."""
        # Disable sections that depend on a selection
        self.info_group.setEnabled(False)
        self.text_edit_frame.setEnabled(False)
        self.style_edit_frame.setEnabled(False)
        self.action_frame.setEnabled(False)

        self.current_region_index = -1

        self.block_updates = True
        self._set_selection_controls_blocked(True)
        try:
            self.original_text_box.clear()
            self.translated_text_box.clear()
            self.font_size_input.clear()
            self.italic_button.setChecked(False)
            self.bold_button.setChecked(False)
            self.stroke_width_spinbox.setValue(0.07)  # 重置为默认值
            self.line_spacing_spinbox.setValue(1.0)  # 重置为默认值
            self.letter_spacing_spinbox.setValue(1.0)  # 重置为默认值
            self.char_width_spinbox.setValue(1.0)  # 重置为默认值
            self.angle_spinbox.setValue(0.0)
            self.distort_mode_checkbox.setChecked(False)
            self.angle_spinbox.setEnabled(True)
            default_color = self.config_service.get_config().render.font_color or "#000000"
            self.font_color_picker.reset(default_color)
            self.stroke_color_picker.reset("#ffffff")
            self.index_label.setText("-")
            self.bbox_label.setText("-")
            self.size_label.setText("-")
            self.angle_label.setText("-")
            self._refresh_style_preset_combo(selected_name="")
            self._refresh_text_stats()
        finally:
            self._set_selection_controls_blocked(False)
            self.block_updates = False

    def _format_index_label(self, region_index, region_data) -> str:
        region_id = ""
        if isinstance(region_data, dict):
            region_id = str(region_data.get("region_id") or "").strip()
        if region_id:
            return f"{region_index}  [{region_id}]"
        return str(region_index)

    def _update_display(self, region_data, region_index, force=False):
        """Populate all widgets with data from the selected region.
        
        Args:
            region_data: 区域数据字典
            region_index: 区域索引
            force: 是否强制更新文本框（忽略焦点状态），用于OCR/翻译完成后
        """
        self.block_updates = True
        self._set_selection_controls_blocked(True)
        try:
            # --- Update Region Info ---
            self.index_label.setText(self._format_index_label(region_index, region_data))
            wf_info = self._calculate_white_frame_info(region_data)
            if wf_info:
                cx, cy, w, h = wf_info
                self.bbox_label.setText(f"({cx:.0f}, {cy:.0f})")
                self.size_label.setText(f"{w:.0f} × {h:.0f}")
            else:
                self.bbox_label.setText("-")
                self.size_label.setText("-")
            angle = region_data.get('angle', 0)
            self.angle_label.setText(f"{angle:.1f}°")

            # --- Update Text & Styles ---
            # 如果force=True（OCR/翻译完成），或文本框没有焦点时才更新
            if force or not self.original_text_box.hasFocus():
                # 统一使用 text 字段（用户编辑和OCR识别都使用这个字段）
                original_text = region_data.get("text", "")
                self.original_text_box.setText(original_text)

            # 如果force=True（OCR/翻译完成），或文本框没有焦点时才更新
            if force or not self.translated_text_box.hasFocus():
                import re

                # 자동치환 미적용 편집 고정: 항상 translation_raw
                field_key = "translation_raw"
                translation_text = region_data.get(field_key, "") or region_data.get("translation", "")

                # 1. 将所有 AI 换行符 ([BR], <br>, 【BR】) 转换为 \n
                translation_text = re.sub(r'(\[BR\]|<br>|【BR】)', '\n', translation_text, flags=re.IGNORECASE)

                # 2. 将 <H> 标签替换为符号 ⇄ 显示在文本框中
                display_text = translation_text.replace('<H>', '⇄').replace('</H>', '⇄')

                # QTextEdit는 실제 줄바꿈(\n)을 그대로 표시할 수 있어서 ↵ 치환은 하지 않음
                self.translated_text_box.setText(display_text)
                self._refresh_text_stats()
            
            font_size = region_data.get("font_size", "")
            if font_size == "" or font_size is None:
                self.font_size_input.clear()
            else:
                font_size = _quantize_font_size(font_size, minimum=8.0)
                self.font_size_input.setText(_format_font_size(font_size))
            self.italic_button.setChecked(bool(region_data.get("italic", False)))
            self.bold_button.setChecked(bool(region_data.get("bold", False)))
            
            default_color = self.config_service.get_config().render.font_color or "#000000"
            color_hex = default_color
            fg_colors = region_data.get('fg_colors')
            font_color = region_data.get("font_color")

            # 优先使用用户设置的font_color，然后才是原始的fg_colors
            if font_color:
                 color_hex = font_color
            elif isinstance(fg_colors, (list, tuple)) and len(fg_colors) == 3:
                 color_hex = f"#{int(fg_colors[0]):02x}{int(fg_colors[1]):02x}{int(fg_colors[2]):02x}"

            self.font_color_picker.set_color(color_hex)

            # Update stroke color display
            # font_color와 동일한 패턴: 사용자가 설정한 stroke_color를 최우선으로, 없으면 bg_color/bg_colors로 폴백
            bg_colors = region_data.get('bg_colors')
            bg_color = region_data.get('bg_color')
            stroke_color = region_data.get('stroke_color')
            stroke_hex = "#ffffff"
            if stroke_color:
                stroke_hex = stroke_color
            elif isinstance(bg_color, (list, tuple)) and len(bg_color) == 3:
                stroke_hex = f"#{int(bg_color[0]):02x}{int(bg_color[1]):02x}{int(bg_color[2]):02x}"
            elif isinstance(bg_colors, (list, tuple)) and len(bg_colors) == 3:
                stroke_hex = f"#{int(bg_colors[0]):02x}{int(bg_colors[1]):02x}{int(bg_colors[2]):02x}"
            self.stroke_color_picker.set_color(stroke_hex)

            # Update stroke width
            stroke_width = region_data.get("stroke_width", region_data.get("default_stroke_width", 0.07))
            self.stroke_width_spinbox.setValue(stroke_width if stroke_width is not None else 0.07)
            
            # Update line spacing
            line_spacing = region_data.get("line_spacing", 1.0)
            self.line_spacing_spinbox.setValue(line_spacing if line_spacing is not None else 1.0)

            letter_spacing = region_data.get("letter_spacing", 1.0)
            self.letter_spacing_spinbox.setValue(letter_spacing if letter_spacing is not None else 1.0)
            char_width = region_data.get("char_width", 1.0)
            self.char_width_spinbox.setValue(char_width if char_width is not None else 1.0)
            self.angle_spinbox.setValue(float(region_data.get("angle", 0.0) or 0.0))
            distort_on = bool(region_data.get("distortMode", False))
            self.distort_mode_checkbox.setChecked(distort_on)
            self.angle_spinbox.setEnabled(not distort_on)
            
            self._set_font_family_combo_value(region_data.get("font_family", ""))
            self.alignment_combo.setCurrentText(self._alignment_text_for_value(region_data.get("alignment", "auto")))
            
            display_direction_map = self.app_logic.get_display_mapping('direction') or {}
            horizontal_text = display_direction_map.get('h', self._t("direction_horizontal"))
            vertical_text = display_direction_map.get('v', self._t("direction_vertical"))

            direction_value = str(region_data.get("direction", "")).strip().lower()
            if direction_value in ("v", "vertical"):
                direction_display = vertical_text
            elif direction_value in ("h", "horizontal"):
                direction_display = horizontal_text
            else:
                # 旧数据的 auto 或空值：在编辑器内按框形状回显横/竖
                if wf_info:
                    _, _, w, h = wf_info
                    direction_display = vertical_text if h > w else horizontal_text
                else:
                    direction_display = horizontal_text
            self.direction_combo.setCurrentText(direction_display)

            # --- Update Mask Checkboxes ---
            self._sync_area_display_checkboxes(self.model.get_display_mask_type())
            self._refresh_style_preset_combo(selected_name=self._find_matching_style_preset_name(region_data) or "")
        finally:
            self._set_selection_controls_blocked(False)
            self.block_updates = False

    def _make_focus_out_handler(self, text_edit, callback):
        """创建一个焦点丢失事件处理器，保存原始的focusOutEvent"""
        original_focus_out = text_edit.focusOutEvent
        
        def focus_out_wrapper(event):
            # 先调用原始的focusOutEvent
            original_focus_out(event)
            # 然后调用我们的回调
            callback()
        
        return focus_out_wrapper
    
    def force_save_text_edits(self):
        """强制保存当前文本框的编辑内容（在失去焦点前）"""
        if self.current_region_index == -1:
            return
        
        # 保存原文编辑
        current_original = self.original_text_box.toPlainText()
        region_data = self.model.get_region_by_index(self.current_region_index)
        if region_data:
            # 比较当前编辑的文本与original_text（如果没有则与text比较）
            stored_original = region_data.get("original_text") or region_data.get("text", "")
            if stored_original != current_original:
                self.original_text_modified.emit(self.current_region_index, current_original)
        
        # 保存译文编辑
        self._save_translated_text()
    
    def _save_translated_text(self):
        """保存译文编辑（执行与_on_translated_text_focus_out相同的逻辑）"""
        if self.current_region_index == -1:
            return

        text_with_br = _plain_text_to_br(_qtext_to_raw(self.translated_text_box))
        region_data = self.model.get_region_by_index(self.current_region_index)
        if region_data:
            if region_data.get("translation_raw", "") != text_with_br:
                self.translation_raw_modified.emit(self.current_region_index, text_with_br)
    
    def _on_original_text_focus_out(self):
        """当原文文本框失去焦点时更新model"""
        if self.current_region_index != -1:
            self.original_text_modified.emit(self.current_region_index, self.original_text_box.toPlainText())
    
    def _on_translated_text_focus_out(self):
        """当译文文本框失去焦点时更新model"""
        if self.current_region_index != -1:
            self.translation_raw_modified.emit(
                self.current_region_index,
                _plain_text_to_br(_qtext_to_raw(self.translated_text_box)),
            )
    
    def _on_original_text_changed(self):
        """保留这个方法以防需要，但现在不使用"""
        if self.current_region_index != -1 and not self.block_updates:
            self.original_text_modified.emit(self.current_region_index, self.original_text_box.toPlainText())
    def _create_text_stats_overlay(self):
        box = self.translated_text_box
        self.text_stats_label = QLabel(self._t("Character count:"), box)
        self.text_stats_label.setObjectName("editor_text_stats_overlay")
        self.text_stats_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.text_stats_label.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.text_stats_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.text_stats_label.setWordWrap(False)
        self.text_stats_label.show()
        self.text_esc_hint_label = QLabel(self._t("Esc: Finish editing"), box)
        self.text_esc_hint_label.setObjectName("editor_text_stats_overlay")
        self.text_esc_hint_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.text_esc_hint_label.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.text_esc_hint_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.text_esc_hint_label.setWordWrap(False)
        self.text_esc_hint_label.show()
        self._place_text_stats_overlay()

    def _place_text_stats_overlay(self):
        box = getattr(self, "translated_text_box", None)
        label = getattr(self, "text_stats_label", None)
        esc_label = getattr(self, "text_esc_hint_label", None)
        if box is None or label is None:
            return
        if getattr(self, "_placing_text_stats", False):
            return
        self._placing_text_stats = True
        try:
            label.adjustSize()
            if esc_label is not None:
                esc_label.adjustSize()
            pad_x, pad_y = 8, 4
            overlay_h = label.height()
            if esc_label is not None:
                overlay_h = max(overlay_h, esc_label.height())
            bottom = overlay_h + pad_y * 2
            if box.viewportMargins().bottom() != bottom:
                box.setViewportMargins(0, 0, 0, bottom)
            rect = box.contentsRect()
            viewport_right = box.viewport().geometry().right()
            y = rect.bottom() - overlay_h - pad_y
            y = max(rect.top() + pad_y, y)
            x = viewport_right - label.width() - pad_x
            label.move(max(rect.left() + pad_x, x), y)
            label.raise_()
            if esc_label is not None:
                esc_label.move(rect.left() + pad_x, y)
                esc_label.raise_()
        finally:
            self._placing_text_stats = False

    def _refresh_text_stats(self):
        if not hasattr(self, "text_stats_label"):
            return
        if getattr(self, "current_region_index", -1) == -1:
            self.text_stats_label.setText(self._t("Character count:"))
            self._place_text_stats_overlay()
            return
        text = ""
        if hasattr(self, "translated_text_box"):
            text = _qtext_to_raw(self.translated_text_box)
        count = len(text.replace("\r", "").replace("\n", ""))
        self.text_stats_label.setText(self._t("Character count: {count}", count=count))
        self._place_text_stats_overlay()

    def _on_translated_text_changed(self):
        self._refresh_text_stats()
        if self.current_region_index != -1 and not self.block_updates:
            self.translation_raw_modified.emit(
                self.current_region_index,
                _plain_text_to_br(_qtext_to_raw(self.translated_text_box)),
            )

    def _clean_whitespace_clicked(self):
        if self.current_region_index == -1:
            return
        self.white_frame_release_requested.emit(self.current_region_index)
        box = self.translated_text_box
        cleaned = _clean_translation_plain(_qtext_to_raw(box))
        if cleaned == _qtext_to_raw(box):
            return
        self.block_updates = True
        try:
            box.setPlainText(cleaned)
        finally:
            self.block_updates = False
        self._refresh_text_stats()
        self.translation_raw_modified.emit(
            self.current_region_index,
            _plain_text_to_br(cleaned),
        )

    def _on_translation_raw_mode_toggled(self, checked: bool):
        """复选框切换:重新刷新当前 region 的文本框内容(读取对应字段)。"""
        if self.current_region_index == -1:
            return
        region_data = self.model.get_region_by_index(self.current_region_index)
        if region_data:
            self._update_display(region_data, self.current_region_index, force=True)
    
    def get_selected_ocr_model(self) -> str:
        """获取当前选择的OCR模型"""
        return self.ocr_model_combo.currentText()
    
    def get_selected_translator(self) -> str:
        """获取当前选择的翻译器（返回key而不是display name）"""
        display_name = self.translator_combo.currentText()
        return self.translator_display_to_key.get(display_name, display_name)
    
    def get_selected_target_language(self) -> str:
        """获取当前选择的目标语言（返回key而不是display name）"""
        display_name = self.target_language_combo.currentText()
        # 使用 lang_name_to_code 映射（在 populate_options_from_config 中创建）
        if hasattr(self, 'lang_name_to_code'):
            return self.lang_name_to_code.get(display_name, display_name)
        return display_name
    def _on_font_size_editing_finished(self):
        if self.block_updates:
            return
        text = (self.font_size_input.text() or "").strip().replace(",", ".")
        try:
            value = _quantize_font_size(text, minimum=8.0)
        except Exception:
            return
        value = max(8.0, min(1000.0, value))
        self.font_size_input.setText(_format_font_size(value))

        selected_indices = self.model.get_selection()
        for region_index in selected_indices:
            self.font_size_changed.emit(region_index, value)

    def _on_italic_toggled(self, checked: bool):
        if self.block_updates:
            return
        selected_indices = self.model.get_selection()
        for region_index in selected_indices:
            self.italic_changed.emit(region_index, bool(checked))

    def _on_bold_toggled(self, checked: bool):
        if self.block_updates:
            return
        selected_indices = self.model.get_selection()
        for region_index in selected_indices:
            self.bold_changed.emit(region_index, bool(checked))

    def _on_font_family_changed(self, index):
        if self.block_updates:
            return
        if index < 0:
            return
        
        # 支持多选批量设置
        selected_indices = self.model.get_selection()
        if not selected_indices:
            return
        
        font_family = self.font_family_combo.currentFamily()
        for region_index in selected_indices:
            self.font_family_changed.emit(region_index, font_family)
    
    def _on_font_color_changed(self, hex_color):
        """字体颜色变化时的处理"""
        if self.block_updates:
            return
        for idx in self.model.get_selection():
            self.font_color_changed.emit(idx, hex_color)

    def _on_stroke_color_changed(self, hex_color):
        """描边颜色变化时的处理"""
        if self.block_updates:
            return
        for idx in self.model.get_selection():
            self.stroke_color_changed.emit(idx, hex_color)

    def _on_stroke_width_changed(self, value):
        """处理描边宽度变化"""
        if self.block_updates:
            return
        for region_index in self.model.get_selection():
            self.stroke_width_changed.emit(region_index, value)

    def _on_line_spacing_changed(self, value):
        """处理行间距倍率变化"""
        if self.block_updates:
            return
        # 支持多选批量设置
        selected_indices = self.model.get_selection()
        for region_index in selected_indices:
            self.line_spacing_changed.emit(region_index, value)

    def _on_letter_spacing_changed(self, value):
        """处理字间距倍率变化"""
        if self.block_updates:
            return
        selected_indices = self.model.get_selection()
        for region_index in selected_indices:
            self.letter_spacing_changed.emit(region_index, value)

    def _on_char_width_changed(self, value):
        """글자 가로폭 배율 변경"""
        if self.block_updates:
            return
        selected_indices = self.model.get_selection()
        for region_index in selected_indices:
            self.char_width_changed.emit(region_index, value)

    def _on_angle_changed(self, value):
        if self.block_updates:
            return
        selected_indices = self.model.get_selection()
        for region_index in selected_indices:
            self.angle_changed.emit(region_index, float(value))

    def _on_distort_mode_toggled(self, checked):
        if self.block_updates:
            return
        self.angle_spinbox.setEnabled(not bool(checked))
        selected_indices = self.model.get_selection()
        for region_index in selected_indices:
            self.distort_mode_changed.emit(region_index, bool(checked))

    def _on_mask_tool_changed(self, button):
        if button is self.select_button:
            self.mask_tool_changed.emit('select')
        elif button is self.brush_button:
            self.mask_tool_changed.emit('brush')
        elif button is self.eraser_button:
            self.mask_tool_changed.emit('eraser')
        elif button is self.paint_brush_button:
            self.mask_tool_changed.emit('paint')
        elif button is self.paint_eraser_button:
            self.mask_tool_changed.emit('paint_erase')

    def _on_brush_size_changed(self, value):
        self.brush_size_value_label.setText(str(value))
        self.brush_size_changed.emit(value)

    def _on_paint_color_changed(self, hex_color: str):
        self.brush_color_changed.emit(hex_color)

    def sync_brush_size_from_model(self, size: int):
        """从模型同步画笔大小到UI（不触发信号）"""
        self.brush_size_slider.blockSignals(True)
        self.brush_size_slider.setValue(size)
        self.brush_size_slider.blockSignals(False)
        self.brush_size_value_label.setText(str(size))

    def sync_brush_color_from_model(self, hex_color: str):
        """从模型同步画笔颜色到 UI（不触发信号）"""
        if hasattr(self, 'paint_color_picker') and self.paint_color_picker is not None:
            self.paint_color_picker.set_color(hex_color or "#ffffff")

    def sync_active_tool_from_model(self, tool: str):
        """model 的 active_tool 变化时，UI 同步高亮对应按钮。"""
        mapping = {
            'select': self.select_button,
            'brush': self.brush_button,
            'eraser': self.eraser_button,
            'paint': getattr(self, 'paint_brush_button', None),
            'paint_erase': getattr(self, 'paint_eraser_button', None),
        }
        button = mapping.get(tool)
        if button is None:
            return
        self.mask_tool_group.blockSignals(True)
        button.setChecked(True)
        self.mask_tool_group.blockSignals(False)

    def _on_alignment_changed(self, text: str):
        if self.block_updates:
            return
        # 支持多选批量设置
        selected_indices = self.model.get_selection()
        for region_index in selected_indices:
            self.alignment_changed.emit(region_index, text)

    def _on_direction_changed(self, text: str):
        if self.block_updates:
            return
        # 支持多选批量设置
        selected_indices = self.model.get_selection()
        for region_index in selected_indices:
            self.direction_changed.emit(region_index, text)

    def _calculate_white_frame_info(self, region_data):
        """计算白框中心世界坐标和宽高，返回 (cx, cy, w, h) 或 None。"""
        import math
        has_custom = bool(region_data.get('has_custom_white_frame', False))
        wf_local = None
        wf_local = region_data.get('render_box_rect_local')
        if not wf_local and has_custom:
            wf_local = region_data.get('white_frame_rect_local')
        if not wf_local:
            wf_local = region_data.get('white_frame_rect_local')
        center = region_data.get('center')
        angle = float(region_data.get('angle', 0))

        if wf_local and len(wf_local) == 4:
            left, top, right, bottom = wf_local
            w = max(0.0, right - left)
            h = max(0.0, bottom - top)
            lx = (left + right) / 2.0
            ly = (top + bottom) / 2.0
            if center and len(center) >= 2:
                rad = math.radians(angle)
                cos_a, sin_a = math.cos(rad), math.sin(rad)
                cx_base, cy_base = float(center[0]), float(center[1])
                cx = cx_base + lx * cos_a - ly * sin_a
                cy = cy_base + lx * sin_a + ly * cos_a
            else:
                cx, cy = lx, ly
            return (cx, cy, w, h)

        # 兜底：从 lines[0] bbox 计算
        lines = region_data.get('lines', [])
        if not lines or not lines[0]:
            return None
        all_points = lines[0]
        if not all_points:
            return None
        x_coords = [p[0] for p in all_points]
        y_coords = [p[1] for p in all_points]
        x0, x1 = min(x_coords), max(x_coords)
        y0, y1 = min(y_coords), max(y_coords)
        return ((x0 + x1) / 2.0, (y0 + y1) / 2.0, x1 - x0, y1 - y0)

    def _insert_chip_buttons(self):
        return (
            getattr(self, "insert_note_button", None),
            getattr(self, "insert_heart_outline_button", None),
            getattr(self, "insert_heart_filled_button", None),
        )

    def _is_insert_chip_under_cursor(self) -> bool:
        widget = QApplication.widgetAt(QCursor.pos())
        if widget is None:
            return False
        for button in self._insert_chip_buttons():
            if button is not None and (widget is button or button.isAncestorOf(widget)):
                return True
        return False

    def eventFilter(self, watched, event):
        box = getattr(self, "translated_text_box", None)
        if box is not None and watched in (box, box.viewport()):
            if event.type() in (QEvent.Type.Resize, QEvent.Type.Show):
                self._place_text_stats_overlay()
        if watched is box:
            if event.type() == QEvent.Type.FocusIn:
                self._translation_box_active = True
            elif event.type() == QEvent.Type.FocusOut and not self._is_insert_chip_under_cursor():
                self._translation_box_active = False
        elif (
            watched in self._insert_chip_buttons()
            and event.type() == QEvent.Type.MouseButtonPress
            and event.button() == Qt.MouseButton.LeftButton
        ):
            if watched is self.insert_note_button:
                symbol = "♪"
            elif watched is self.insert_heart_outline_button:
                symbol = "♡"
            else:
                symbol = "♥"
            self._insert_text_symbol(symbol)
            return True
        return super().eventFilter(watched, event)

    def _insert_text_symbol(self, symbol: str):
        """번역문에 기호 삽입. 칸 편집중이면 커서, 아니면 맨 뒤."""
        box = self.translated_text_box
        if self.current_region_index == -1 or not box.isEnabled():
            return
        at_cursor = self._translation_box_active
        if at_cursor:
            box.setFocus()
        cursor = box.textCursor()
        if not at_cursor:
            cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertText(symbol)
        box.setTextCursor(cursor)
        if not self.block_updates:
            self.translation_raw_modified.emit(
                self.current_region_index,
                _plain_text_to_br(_qtext_to_raw(box)),
            )

    def _mark_horizontal(self):
        """标记横排：有选中则两侧包裹，无选中则在光标处插入一个 ⇄。"""
        # 确保文本框有焦点,避免光标位置丢失
        self.translated_text_box.setFocus()
        cursor = self.translated_text_box.textCursor()
        if cursor.hasSelection():
            selected_text = cursor.selectedText()
            # Qt 的 selectedText() 会将段落分隔符转换为 \u2029,需要替换回实际换行符 \n
            selected_text = selected_text.replace('\u2029', '\n')
            cursor.insertText(f"⇄{selected_text}⇄")
        else:
            cursor.insertText("⇄")
        self.translated_text_box.setTextCursor(cursor)

    def _on_ocr_model_change(self, text):
        """OCR模型变化时保存配置"""
        self.app_logic.update_single_config('ocr.ocr', text)

    def _on_translator_change(self, display_name):
        """翻译器变化时保存配置"""
        translator_key = self.translator_display_to_key.get(display_name, display_name)
        self.app_logic.update_single_config('translator.translator', translator_key)

    def _on_target_language_change(self, display_name):
        """目标语言变化时保存配置"""
        lang_code = self.lang_name_to_code.get(display_name, "CHS")
        self.app_logic.update_single_config('translator.target_lang', lang_code)
        # 同时更新翻译服务的目标语言
        self.app_logic.translation_service.set_target_language(lang_code)

