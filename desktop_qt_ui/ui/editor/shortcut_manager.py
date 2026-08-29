"""
快捷键管理模块
负责统一管理Qt UI的所有快捷键设置和处理
"""

import math
from typing import Callable, Optional

from PyQt6.QtCore import QEvent, QObject, Qt
from PyQt6.QtGui import QKeyEvent, QKeySequence, QShortcut
from PyQt6.QtWidgets import QApplication, QLineEdit, QTextEdit, QWidget


class ShortcutManager(QObject):
    """
    快捷键管理器
    统一管理应用程序的所有快捷键
    """
    
    def __init__(self, parent: QWidget):
        """
        初始化快捷键管理器
        
        Args:
            parent: 父窗口部件
        """
        super().__init__(parent)
        self.parent_widget = parent
        self.shortcuts = {}
    
    def register_shortcut(
        self,
        name: str,
        key_sequence: QKeySequence.StandardKey,
        callback: Callable,
        context_aware: bool = False
    ) -> QShortcut:
        """
        注册一个快捷键
        
        Args:
            name: 快捷键名称（用于标识）
            key_sequence: 按键序列
            callback: 回调函数
            context_aware: 是否需要上下文感知（检查焦点控件）
            
        Returns:
            创建的QShortcut对象
        """
        shortcut = QShortcut(key_sequence, self.parent_widget)
        
        if context_aware:
            # 包装回调函数，添加上下文检查
            def context_aware_callback():
                focused_widget = self.parent_widget.focusWidget()
                callback(focused_widget)
            shortcut.activated.connect(context_aware_callback)
        else:
            shortcut.activated.connect(callback)
        
        self.shortcuts[name] = shortcut
        return shortcut
    
    def get_shortcut(self, name: str) -> Optional[QShortcut]:
        """
        获取快捷键对象
        
        Args:
            name: 快捷键名称
            
        Returns:
            QShortcut对象，如果不存在则返回None
        """
        return self.shortcuts.get(name)
    
    @staticmethod
    def is_text_widget(widget) -> bool:
        """
        检查控件是否为文本编辑控件
        
        Args:
            widget: 要检查的控件
            
        Returns:
            是否为文本编辑控件
        """
        return isinstance(widget, (QTextEdit, QLineEdit))


class EditorShortcutManager(ShortcutManager):
    """
    编辑器快捷键管理器
    专门用于编辑器视图的快捷键管理
    """
    
    def __init__(self, editor_view):
        """
        初始化编辑器快捷键管理器
        
        Args:
            editor_view: 编辑器视图对象
        """
        super().__init__(editor_view)
        self.editor_view = editor_view
        self.controller = editor_view.controller
        self._setup_editor_shortcuts()
        self._setup_wheel_shortcuts()
        self._setup_text_box_escape()
    
    def _setup_editor_shortcuts(self):
        """设置编辑器的所有快捷键"""
        # 撤销快捷键
        self.register_shortcut(
            'undo',
            QKeySequence.StandardKey.Undo,
            self._handle_undo,
            context_aware=True
        )
        
        # 重做快捷键
        self.register_shortcut(
            'redo',
            QKeySequence.StandardKey.Redo,
            self._handle_redo,
            context_aware=True
        )
        
        # 复制快捷键
        self.register_shortcut(
            'copy',
            QKeySequence.StandardKey.Copy,
            self._handle_copy,
            context_aware=True
        )
        
        # 粘贴快捷键
        self.register_shortcut(
            'paste',
            QKeySequence.StandardKey.Paste,
            self._handle_paste,
            context_aware=True
        )

        # 全选快捷键
        self.register_shortcut(
            'select_all',
            QKeySequence.StandardKey.SelectAll,
            self._handle_select_all,
            context_aware=True
        )
        
        # 删除快捷键
        self.register_shortcut(
            'delete',
            QKeySequence.StandardKey.Delete,
            self._handle_delete,
            context_aware=True
        )
        
        # 导出快捷键 (Ctrl+S)
        self.register_shortcut(
            'export',
            QKeySequence("Ctrl+S"),
            self._handle_export,
            context_aware=True
        )
        
        # 工具快捷键 Q (选择)
        self.register_shortcut(
            'tool_select',
            QKeySequence("Q"),
            self._handle_tool_select,
            context_aware=True
        )
        
        # 工具快捷键 W (画笔)
        self.register_shortcut(
            'tool_brush',
            QKeySequence("W"),
            self._handle_tool_brush,
            context_aware=True
        )
        
        # 工具快捷键 E (橡皮擦)
        self.register_shortcut(
            'tool_eraser',
            QKeySequence("E"),
            self._handle_tool_eraser,
            context_aware=True
        )

        # 工具快捷键 R (페인트 브러시)
        self.register_shortcut(
            'tool_paint',
            QKeySequence("R"),
            self._handle_tool_paint,
            context_aware=True
        )

        # 工具快捷键 T (페인트 지우개)
        self.register_shortcut(
            'tool_paint_erase',
            QKeySequence("T"),
            self._handle_tool_paint_erase,
            context_aware=True
        )

        # 上一张图片 (A)
        self.register_shortcut(
            'prev_image',
            QKeySequence("A"),
            self._handle_prev_image,
            context_aware=True
        )
        
        # 下一张图片 (D)
        self.register_shortcut(
            'next_image',
            QKeySequence("D"),
            self._handle_next_image,
            context_aware=True
        )

        # 10페이지 앞으로/뒤로 이동 (Shift+A / Shift+D)
        self.register_shortcut(
            'prev_image_x10',
            QKeySequence("Shift+A"),
            self._handle_prev_image_x10,
            context_aware=True
        )
        self.register_shortcut(
            'next_image_x10',
            QKeySequence("Shift+D"),
            self._handle_next_image_x10,
            context_aware=True
        )

        # PageUp / PageDown = A / D 와 동일 (이전/다음 이미지)
        self.register_shortcut(
            'prev_image_pageup',
            QKeySequence("PgUp"),
            self._handle_prev_image_pageup,
            context_aware=True
        )
        self.register_shortcut(
            'next_image_pagedown',
            QKeySequence("PgDown"),
            self._handle_next_image_pagedown,
            context_aware=True
        )
        self.register_shortcut(
            'prev_image_x10_pageup',
            QKeySequence("Shift+PgUp"),
            self._handle_prev_image_x10_pageup,
            context_aware=True
        )
        self.register_shortcut(
            'next_image_x10_pagedown',
            QKeySequence("Shift+PgDown"),
            self._handle_next_image_x10_pagedown,
            context_aware=True
        )

        # 표시 모드 전환 (F1~F5)
        # F1 = 텍스트+상자, F2 = 텍스트만, F3 = 상자만, F4 = 아무것도 표시 안함, F5 = 원본과 비교
        display_mode_map = {
            1: ('display_mode_full', 'full'),
            2: ('display_mode_text_only', 'text_only'),
            3: ('display_mode_box_only', 'box_only'),
            4: ('display_mode_none', 'none'),
            5: ('display_mode_compare', 'compare_original_split'),
        }
        for digit, (name, mode) in display_mode_map.items():
            key_enum = getattr(Qt.Key, f"Key_F{digit}")
            self.register_shortcut(
                name,
                QKeySequence(f"F{digit}"),
                self._make_display_mode_handler(digit, key_enum, mode),
                context_aware=True
            )

        # 정제된 마스크 표시 토글 (Tab)
        tab_shortcut = self.register_shortcut(
            'toggle_refined_mask',
            QKeySequence(Qt.Key.Key_Tab),
            self._handle_toggle_refined_mask,
            context_aware=True
        )
        tab_shortcut.setAutoRepeat(False)

        # 덧칠 영역 표시 토글 (Shift+Tab). Qt는 Shift+Tab을 Backtab으로 보낸다.
        paint_shortcut = self.register_shortcut(
            'toggle_paint_overlay',
            QKeySequence(Qt.Key.Key_Backtab),
            self._handle_toggle_paint_overlay,
            context_aware=True
        )
        paint_shortcut.setAutoRepeat(False)

        # 창에 맞추기 (F)
        self.register_shortcut(
            'fit_to_window',
            QKeySequence("F"),
            self._handle_fit_to_window,
            context_aware=True
        )

        # 스타일 슬롯 복사/적용 (Ctrl+1~0 복사, 1~0 적용)
        for digit in list(range(1, 10)) + [0]:
            self.register_shortcut(
                f'copy_style_slot_{digit}',
                QKeySequence(f"Ctrl+{digit}"),
                self._make_copy_style_slot_handler(digit),
                context_aware=True
            )
            apply_shortcut = self.register_shortcut(
                f'apply_style_slot_{digit}',
                QKeySequence(str(digit)),
                self._make_apply_style_slot_handler(digit),
                context_aware=True
            )
            apply_shortcut.setAutoRepeat(False)

        # 원본 이미지 불투명도 토글 (Z: 0 <-> 100, 어중간한 값이면 0으로)
        self.register_shortcut(
            'toggle_original_image_alpha',
            QKeySequence("Z"),
            self._handle_toggle_original_image_alpha,
            context_aware=True
        )

        # 텍스트 레이어 가로/세로 방향 토글 (X)
        self.register_shortcut(
            'toggle_direction',
            QKeySequence("X"),
            self._handle_toggle_direction,
            context_aware=True
        )

        # 텍스트박스 선택 시 자간/줄간격 (Ctrl+방향키, 0.05)
        self.register_shortcut(
            'letter_spacing_dec',
            QKeySequence("Ctrl+Left"),
            self._make_selected_style_handler(
                'letter_spacing_dec',
                Qt.Key.Key_Left,
                Qt.KeyboardModifier.ControlModifier,
                lambda selected: self.controller.nudge_regions_letter_spacing(selected, -0.05),
            ),
            context_aware=True,
        )
        self.register_shortcut(
            'letter_spacing_inc',
            QKeySequence("Ctrl+Right"),
            self._make_selected_style_handler(
                'letter_spacing_inc',
                Qt.Key.Key_Right,
                Qt.KeyboardModifier.ControlModifier,
                lambda selected: self.controller.nudge_regions_letter_spacing(selected, 0.05),
            ),
            context_aware=True,
        )
        # 텍스트박스 선택 시 가로 비율 (Ctrl+Alt+방향키, 0.05)
        self.register_shortcut(
            'char_width_dec',
            QKeySequence("Ctrl+Alt+Left"),
            self._make_selected_style_handler(
                'char_width_dec',
                Qt.Key.Key_Left,
                Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier,
                lambda selected: self.controller.nudge_regions_char_width(selected, -0.05),
            ),
            context_aware=True,
        )
        self.register_shortcut(
            'char_width_inc',
            QKeySequence("Ctrl+Alt+Right"),
            self._make_selected_style_handler(
                'char_width_inc',
                Qt.Key.Key_Right,
                Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier,
                lambda selected: self.controller.nudge_regions_char_width(selected, 0.05),
            ),
            context_aware=True,
        )
        self.register_shortcut(
            'line_spacing_inc',
            QKeySequence("Ctrl+Up"),
            self._make_selected_style_handler(
                'line_spacing_inc',
                Qt.Key.Key_Up,
                Qt.KeyboardModifier.ControlModifier,
                lambda selected: self.controller.nudge_regions_line_spacing(selected, 0.05),
            ),
            context_aware=True,
        )
        self.register_shortcut(
            'line_spacing_dec',
            QKeySequence("Ctrl+Down"),
            self._make_selected_style_handler(
                'line_spacing_dec',
                Qt.Key.Key_Down,
                Qt.KeyboardModifier.ControlModifier,
                lambda selected: self.controller.nudge_regions_line_spacing(selected, -0.05),
            ),
            context_aware=True,
        )

        # 텍스트박스 선택 시 정렬 / 4점 변환 (Alt+방향키)
        for name, key_seq, key_enum, alignment in (
            ('align_left', "Alt+Left", Qt.Key.Key_Left, "left"),
            ('align_center', "Alt+Down", Qt.Key.Key_Down, "center"),
            ('align_right', "Alt+Right", Qt.Key.Key_Right, "right"),
        ):
            shortcut = self.register_shortcut(
                name,
                QKeySequence(key_seq),
                self._make_selected_style_handler(
                    name,
                    key_enum,
                    Qt.KeyboardModifier.AltModifier,
                    lambda selected, value=alignment: self.controller.set_regions_alignment(selected, value),
                ),
                context_aware=True,
            )
            shortcut.setAutoRepeat(False)

        distort_alt = self.register_shortcut(
            'toggle_distort_mode',
            QKeySequence("Alt+Up"),
            self._handle_toggle_distort_mode,
            context_aware=True,
        )
        distort_alt.setAutoRepeat(False)

        # 텍스트박스 선택 시 테두리 두께 (Alt+Shift+Up/Down, 0.02)
        self.register_shortcut(
            'stroke_width_inc',
            QKeySequence("Alt+Shift+Up"),
            self._make_selected_style_handler(
                'stroke_width_inc',
                Qt.Key.Key_Up,
                Qt.KeyboardModifier.AltModifier | Qt.KeyboardModifier.ShiftModifier,
                lambda selected: self.controller.nudge_regions_stroke_width(selected, 0.02),
            ),
            context_aware=True,
        )
        self.register_shortcut(
            'stroke_width_dec',
            QKeySequence("Alt+Shift+Down"),
            self._make_selected_style_handler(
                'stroke_width_dec',
                Qt.Key.Key_Down,
                Qt.KeyboardModifier.AltModifier | Qt.KeyboardModifier.ShiftModifier,
                lambda selected: self.controller.nudge_regions_stroke_width(selected, -0.02),
            ),
            context_aware=True,
        )

        # 텍스트박스 선택 시 이탤릭/볼드 토글 (I / B)
        italic_shortcut = self.register_shortcut(
            'toggle_italic',
            QKeySequence("I"),
            self._handle_toggle_italic,
            context_aware=True,
        )
        italic_shortcut.setAutoRepeat(False)
        bold_shortcut = self.register_shortcut(
            'toggle_bold',
            QKeySequence("B"),
            self._handle_toggle_bold,
            context_aware=True,
        )
        bold_shortcut.setAutoRepeat(False)
    
    def _handle_undo(self, focused_widget):
        """处理撤销快捷键"""
        if self.is_text_widget(focused_widget):
            # 如果焦点在文本控件上，让文本控件处理撤销
            focused_widget.undo()
        else:
            # 否则调用编辑器的撤销
            self.controller.undo()
    
    def _handle_redo(self, focused_widget):
        """处理重做快捷键"""
        if self.is_text_widget(focused_widget):
            # 如果焦点在文本控件上，让文本控件处理重做
            focused_widget.redo()
        else:
            # 否则调用编辑器的重做
            self.controller.redo()
    
    def _handle_copy(self, focused_widget):
        """处理复制快捷键"""
        if self.is_text_widget(focused_widget):
            # 如果焦点在文本控件上，让文本控件处理复制
            focused_widget.copy()
        else:
            # 否则复制选中的区域
            selected_regions = self.editor_view.model.get_selection()
            if selected_regions:
                # 复制最后选中的区域
                self.controller.copy_region(selected_regions[-1])
    
    def _handle_paste(self, focused_widget):
        """处理粘贴快捷键"""
        if self.is_text_widget(focused_widget):
            # 如果焦点在文本控件上，让文本控件处理粘贴
            focused_widget.paste()
        else:
            selected_regions = self.editor_view.model.get_selection()
            if selected_regions:
                self.controller.paste_region_style(selected_regions)
            else:
                self.controller.paste_region()
    
    def _handle_select_all(self, focused_widget):
        """处理全选快捷键"""
        if self.is_text_widget(focused_widget):
            focused_widget.selectAll()
        else:
            regions = self.editor_view.model.get_regions()
            self.editor_view.model.set_selection(list(range(len(regions))))

    def _handle_delete(self, focused_widget):
        """处理删除快捷键"""
        if not self.is_text_widget(focused_widget):
            # 只有在非文本控件上才处理删除区域
            selected_regions = self.editor_view.model.get_selection()
            if selected_regions:
                self.controller.delete_regions(selected_regions)
    
    def _handle_export(self, focused_widget):
        """处理导出快捷键 (Ctrl+S)"""
        # 导出是全局操作
        self.controller.export_image()

    def _forward_key_to_widget(
        self,
        widget,
        key_code,
        text,
        shortcut_name,
        modifiers=Qt.KeyboardModifier.NoModifier,
    ):
        """
        将按键事件转发给控件，同时临时禁用对应的快捷键以防止递归
        """
        shortcut = self.get_shortcut(shortcut_name)
        if shortcut:
            shortcut.setEnabled(False)
            
            # 发送KeyPress
            event_press = QKeyEvent(QEvent.Type.KeyPress, key_code, modifiers, text)
            QApplication.sendEvent(widget, event_press)
            
            # 发送KeyRelease (部分输入法或控件可能依赖它)
            event_release = QKeyEvent(QEvent.Type.KeyRelease, key_code, modifiers, text)
            QApplication.sendEvent(widget, event_release)
            
            shortcut.setEnabled(True)

    def _handle_tool_select(self, focused_widget):
        """处理选择工具快捷键 (Q)"""
        if self.is_text_widget(focused_widget):
            self._forward_key_to_widget(focused_widget, Qt.Key.Key_Q, "q", 'tool_select')
        else:
            self.controller.set_active_tool('select')

    def _handle_tool_brush(self, focused_widget):
        """处理画笔工具快捷键 (W)"""
        if self.is_text_widget(focused_widget):
            self._forward_key_to_widget(focused_widget, Qt.Key.Key_W, "w", 'tool_brush')
        else:
            self.controller.set_active_tool('brush')

    def _handle_tool_eraser(self, focused_widget):
        """处理橡皮擦工具快捷键 (E)"""
        if self.is_text_widget(focused_widget):
            self._forward_key_to_widget(focused_widget, Qt.Key.Key_E, "e", 'tool_eraser')
        else:
            self.controller.set_active_tool('eraser')

    def _handle_tool_paint(self, focused_widget):
        """处理페인트 브러시 快捷键 (R)"""
        if self.is_text_widget(focused_widget):
            self._forward_key_to_widget(focused_widget, Qt.Key.Key_R, "r", 'tool_paint')
        else:
            self.controller.set_active_tool('paint')

    def _handle_tool_paint_erase(self, focused_widget):
        """处理페인트 지우개 快捷键 (T)"""
        if self.is_text_widget(focused_widget):
            self._forward_key_to_widget(focused_widget, Qt.Key.Key_T, "t", 'tool_paint_erase')
        else:
            self.controller.set_active_tool('paint_erase')

    def _handle_prev_image(self, focused_widget):
        """처리 이전 이미지 (A)"""
        self._navigate_image(focused_widget, 'prev_image', Qt.Key.Key_A, "a", -1)

    def _handle_next_image(self, focused_widget):
        """처리 다음 이미지 (D)"""
        self._navigate_image(focused_widget, 'next_image', Qt.Key.Key_D, "d", 1)

    def _handle_prev_image_x10(self, focused_widget):
        """처리 10페이지 이전 (Shift+A)"""
        self._navigate_image(focused_widget, 'prev_image_x10', Qt.Key.Key_A, "a", -10)

    def _handle_next_image_x10(self, focused_widget):
        """처리 10페이지 다음 (Shift+D)"""
        self._navigate_image(focused_widget, 'next_image_x10', Qt.Key.Key_D, "d", 10)

    def _handle_prev_image_pageup(self, focused_widget):
        """처리 이전 이미지 (PageUp, A와 동일)"""
        self._navigate_image(focused_widget, 'prev_image_pageup', Qt.Key.Key_PageUp, "", -1)

    def _handle_next_image_pagedown(self, focused_widget):
        """처리 다음 이미지 (PageDown, D와 동일)"""
        self._navigate_image(focused_widget, 'next_image_pagedown', Qt.Key.Key_PageDown, "", 1)

    def _handle_prev_image_x10_pageup(self, focused_widget):
        """처리 10페이지 이전 (Shift+PageUp, Shift+A와 동일)"""
        self._navigate_image(focused_widget, 'prev_image_x10_pageup', Qt.Key.Key_PageUp, "", -10)

    def _handle_next_image_x10_pagedown(self, focused_widget):
        """처리 10페이지 다음 (Shift+PageDown, Shift+D와 동일)"""
        self._navigate_image(focused_widget, 'next_image_x10_pagedown', Qt.Key.Key_PageDown, "", 10)

    def _navigate_image(self, focused_widget, shortcut_name, key_code, text, step: int):
        if self.is_text_widget(focused_widget):
            self._forward_key_to_widget(focused_widget, key_code, text, shortcut_name)
            return
        file_list = getattr(self.editor_view, 'file_list', None)
        if file_list is None:
            return
        if step == -1:
            file_list.select_prev_image()
        elif step == 1:
            file_list.select_next_image()
        else:
            file_list.select_image_by_step(step)

    def _make_display_mode_handler(self, digit: int, key_enum, mode: str):
        """F1~F5 표시 모드 전환 핸들러 (F1=full, F2=text_only, F3=box_only, F4=none, F5=compare)"""
        def handler(focused_widget):
            if self.is_text_widget(focused_widget):
                self._forward_key_to_widget(focused_widget, key_enum, "", f'display_mode_{mode}')
            else:
                self.controller.set_display_mode(mode)
                self._sync_display_mode_combo(mode)
        return handler

    def _sync_display_mode_combo(self, mode: str):
        """단축키로 표시 모드를 바꿨을 때 툴바 드롭다운도 같이 갱신 (모델 쪽에 별도 동기화 시그널이 없어 직접 처리)"""
        toolbar = getattr(self.editor_view, 'toolbar', None)
        combo = getattr(toolbar, 'display_mode_combo', None) if toolbar is not None else None
        if combo is None:
            return
        index = combo.findData(mode)
        if index < 0:
            return
        if combo.currentIndex() == index:
            return
        combo.blockSignals(True)
        combo.setCurrentIndex(index)
        combo.blockSignals(False)

    def _make_copy_style_slot_handler(self, digit: int):
        """Ctrl+digit: 선택된 영역 1개의 스타일을 번호 슬롯에 복사"""
        slot = str(digit)

        def handler(focused_widget):
            selected_regions = self.editor_view.model.get_selection()
            if len(selected_regions) != 1:
                return
            self.controller.copy_style_to_slot(selected_regions[0], slot)
        return handler

    def _make_apply_style_slot_handler(self, digit: int):
        """숫자 1~0: 번호 슬롯에 저장된 스타일을 선택된 영역(들)에 적용"""
        slot = str(digit)
        key_enum = getattr(Qt.Key, f"Key_{digit}")

        def handler(focused_widget):
            if self.is_text_widget(focused_widget):
                self._forward_key_to_widget(
                    focused_widget, key_enum, slot, f'apply_style_slot_{digit}'
                )
                return
            selected_regions = self.editor_view.model.get_selection()
            if not selected_regions:
                return
            self.controller.apply_style_from_slot(selected_regions, slot)
        return handler

    def _handle_toggle_refined_mask(self, focused_widget):
        """처리 정제된 마스크 표시 토글 (Tab). 텍스트 입력 중에는 Tab 기본 동작을 유지."""
        if self.is_text_widget(focused_widget):
            if isinstance(focused_widget, QTextEdit) and not focused_widget.tabChangesFocus():
                self._forward_key_to_widget(
                    focused_widget, Qt.Key.Key_Tab, "\t", 'toggle_refined_mask'
                )
            else:
                focused_widget.focusNextPrevChild(True)
            return
        is_visible = self.editor_view.model.get_display_mask_type() == 'refined'
        self.controller.set_display_mask_type('refined', not is_visible)

    def _handle_toggle_paint_overlay(self, focused_widget):
        """덧칠 영역 표시 토글 (Shift+Tab). 텍스트 입력 중에는 이전 포커스 이동."""
        if self.is_text_widget(focused_widget):
            focused_widget.focusNextPrevChild(False)
            return
        is_visible = self.editor_view.model.get_display_mask_type() == 'paint'
        self.controller.set_display_mask_type('paint', not is_visible)

    def _handle_fit_to_window(self, focused_widget):
        """处理창에 맞추기 (F)"""
        if self.is_text_widget(focused_widget):
            self._forward_key_to_widget(focused_widget, Qt.Key.Key_F, "f", 'fit_to_window')
        else:
            if hasattr(self.editor_view, 'graphics_view'):
                self.editor_view.graphics_view.fit_to_window()

    def _handle_toggle_original_image_alpha(self, focused_widget):
        """처리 원본 보기 토글 (Z): 텍스트/박스/인페인트/페인트 전부 숨기고 원본만, 다시 누르면 이전 상태로 복원"""
        if self.is_text_widget(focused_widget):
            self._forward_key_to_widget(focused_widget, Qt.Key.Key_Z, "z", 'toggle_original_image_alpha')
        else:
            self.controller.toggle_show_original_only()

    def _handle_toggle_direction(self, focused_widget):
        """처리 텍스트 레이어 가로/세로 방향 토글 (X)"""
        if self.is_text_widget(focused_widget):
            self._forward_key_to_widget(focused_widget, Qt.Key.Key_X, "x", 'toggle_direction')
            return
        selected_regions = self.editor_view.model.get_selection()
        if selected_regions:
            self.controller.toggle_regions_direction(selected_regions)

    def _handle_toggle_distort_mode(self, focused_widget):
        """처리 4점 변환 모드 토글 (Alt+Up)"""
        if self.is_text_widget(focused_widget):
            self._forward_key_to_widget(
                focused_widget,
                Qt.Key.Key_Up,
                "",
                'toggle_distort_mode',
                Qt.KeyboardModifier.AltModifier,
            )
            return
        selected_regions = self.editor_view.model.get_selection()
        if selected_regions:
            self.controller.toggle_regions_distort_mode(selected_regions)

    def _make_selected_style_handler(self, shortcut_name, key_code, modifiers, apply_fn):
        """텍스트 입력 중이면 키를 위젯에 넘기고, 텍스트박스 선택 시에만 스타일을 적용."""

        def handler(focused_widget):
            if self.is_text_widget(focused_widget):
                self._forward_key_to_widget(
                    focused_widget, key_code, "", shortcut_name, modifiers
                )
                return
            selected_regions = self.editor_view.model.get_selection()
            if selected_regions:
                apply_fn(selected_regions)

        return handler

    def _handle_toggle_italic(self, focused_widget):
        """처리 이탤릭 토글 (I)"""
        if self.is_text_widget(focused_widget):
            self._forward_key_to_widget(focused_widget, Qt.Key.Key_I, "i", 'toggle_italic')
            return
        selected_regions = self.editor_view.model.get_selection()
        if selected_regions:
            self.controller.toggle_regions_italic(selected_regions)

    def _handle_toggle_bold(self, focused_widget):
        """처리 볼드 토글 (B)"""
        if self.is_text_widget(focused_widget):
            self._forward_key_to_widget(focused_widget, Qt.Key.Key_B, "b", 'toggle_bold')
            return
        selected_regions = self.editor_view.model.get_selection()
        if selected_regions:
            self.controller.toggle_regions_bold(selected_regions)

    def _setup_wheel_shortcuts(self):
        """设置鼠标滚轮快捷键（通过事件过滤器实现）"""
        # 为 graphics_view 的 viewport 安装事件过滤器
        if hasattr(self.editor_view, 'graphics_view'):
            # 滚轮事件会先到达 viewport
            self.editor_view.graphics_view.viewport().installEventFilter(self)

    def _setup_text_box_escape(self):
        """텍스트박스 Esc만 처리. 콤보/메뉴 전역 단축키로 가로채지 않는다."""
        app = QApplication.instance()
        if app is None:
            return
        app.installEventFilter(self)
        self.destroyed.connect(self._remove_text_box_escape)

    def _remove_text_box_escape(self, *_args):
        app = QApplication.instance()
        if app is not None:
            app.removeEventFilter(self)

    def _is_plain_escape(self, event) -> bool:
        if event.type() != QEvent.Type.KeyPress or event.key() != Qt.Key.Key_Escape:
            return False
        if event.isAutoRepeat():
            return False
        blocked = (
            Qt.KeyboardModifier.ControlModifier
            | Qt.KeyboardModifier.AltModifier
            | Qt.KeyboardModifier.ShiftModifier
            | Qt.KeyboardModifier.MetaModifier
        )
        return not bool(event.modifiers() & blocked)

    def _is_editor_text_widget(self, widget) -> bool:
        if not self.is_text_widget(widget):
            return False
        editor = self.editor_view
        current = widget
        while current is not None:
            if current is editor:
                return True
            current = current.parentWidget()
        return False

    def _blur_editor_text_widget(self, widget) -> None:
        input_method = QApplication.inputMethod()
        if input_method is not None:
            input_method.reset()
        if hasattr(self.editor_view, "force_save_property_panel_edits"):
            self.editor_view.force_save_property_panel_edits()
        widget.clearFocus()
        graphics_view = getattr(self.editor_view, "graphics_view", None)
        if graphics_view is not None:
            graphics_view.setFocus(Qt.FocusReason.ShortcutFocusReason)

    def eventFilter(self, obj, event):
        """
        事件过滤器，用于处理鼠标滚轮快捷键
        
        支持的快捷键：
        - Ctrl + 滚轮：等比例缩放选中文本框（包括框的大小和字体）
        - Shift + 滚轮：调整画笔大小 (≤25는 5단위, 26+는 20단위)
        - Alt + 滚轮：调整画笔大小 (2단위)
        """
        if self._is_plain_escape(event) and self._is_editor_text_widget(obj):
            self._blur_editor_text_widget(obj)
            return True

        if event.type() == QEvent.Type.Wheel:
            # 检查是否是 graphics_view 的 viewport
            if obj == self.editor_view.graphics_view.viewport():
                modifiers = event.modifiers()
                
                # Shift + 滚轮：调整画笔大小 (≤25는 5단위, 26+는 20단위, 无论当前是什么工具)
                if modifiers == Qt.KeyboardModifier.ShiftModifier:
                    current_size = self.editor_view.model.get_brush_size()
                    # 尝试获取滚轮方向
                    angle_delta = event.angleDelta().y()
                    if angle_delta == 0:
                        angle_delta = event.pixelDelta().y()

                    step = 5 if current_size <= 25 else 20
                    delta = step if angle_delta > 0 else -step
                    new_size = max(5, min(250, current_size + delta))
                    self.controller.set_brush_size(new_size)
                    # 크기 원 커서 프리뷰 (select 등 비브러시 도구에서도 확인 가능)
                    graphics_view = self.editor_view.graphics_view
                    if hasattr(graphics_view, "show_brush_size_cursor_preview"):
                        graphics_view.show_brush_size_cursor_preview()
                    return True  # 阻止事件继续传递

                # Alt + 滚轮：调整画笔大小 (2단위, 无论当前是什么工具)
                elif modifiers == Qt.KeyboardModifier.AltModifier:
                    current_size = self.editor_view.model.get_brush_size()
                    # Alt+휠은 Windows에서 세로 스크롤이 가로 스크롤로 변환되는 경우가 많음
                    angle_delta = event.angleDelta().y()
                    if angle_delta == 0:
                        angle_delta = event.pixelDelta().y()
                    if angle_delta == 0:
                        angle_delta = event.angleDelta().x()
                    if angle_delta == 0:
                        angle_delta = event.pixelDelta().x()

                    delta = 2 if angle_delta > 0 else -2
                    new_size = max(5, min(250, current_size + delta))
                    self.controller.set_brush_size(new_size)
                    # Alt 홀드 시 스포이드 십자 대신 원 커서로 크기 확인
                    graphics_view = self.editor_view.graphics_view
                    if hasattr(graphics_view, "show_brush_size_cursor_preview"):
                        graphics_view.show_brush_size_cursor_preview()
                    return True  # 阻止事件继续传递
                
                # Ctrl + 滚轮：调整选中文本框的字体大小
                elif modifiers == Qt.KeyboardModifier.ControlModifier:
                    selected_regions = self.editor_view.model.get_selection()
                    if selected_regions:
                        angle_delta = event.angleDelta().y()
                        if angle_delta == 0:
                            angle_delta = event.pixelDelta().y()
                        for region_index in selected_regions:
                            region_data = self.controller._get_region_by_index(region_index)
                            if region_data:
                                old_size = float(region_data.get('font_size', 20) or 20)
                                is_integer = abs(old_size - round(old_size)) < 1e-9
                                if not is_integer:
                                    new_size = math.ceil(old_size - 1e-9) if angle_delta > 0 else math.floor(old_size + 1e-9)
                                else:
                                    delta = max(1, int(old_size * 0.05))
                                    new_size = old_size + (delta if angle_delta > 0 else -delta)
                                new_size = float(max(1, int(new_size)))
                                self.controller.update_font_size(region_index, new_size)
                        return True  # 阻止事件继续传递
        
        # 其他事件继续传递
        return super().eventFilter(obj, event)
