"""Unified stylesheet definitions for the desktop UI."""

from __future__ import annotations

from PyQt6.QtGui import QFont

from ui.theme import get_current_theme_colors, get_theme_colors


def build_tooltip_stylesheet(colors: dict) -> str:
    return f"""
        QToolTip {{
            background-color: {colors["bg_dropdown"]};
            color: {colors["text_accent"]};
            border: 1px solid {colors["border_input"]};
            border-radius: 10px;
            padding: 8px 12px;
            font-size: 12px;
            font-weight: 400;
        }}
    """


def build_shared_button_stylesheet(colors: dict) -> str:
    return f"""
        QPushButton,
        QToolButton {{
            background: {colors["btn_soft_bg"]};
            border: 1px solid {colors["btn_soft_border"]};
            border-radius: 10px;
            color: {colors["btn_soft_text"]};
            padding: 7px 12px;
            font-weight: 500;
        }}
        QPushButton:hover,
        QToolButton:hover {{
            background: {colors["btn_soft_hover"]};
            border-color: {colors["border_input_hover"]};
        }}
        QPushButton:pressed,
        QToolButton:pressed {{
            background: {colors["btn_soft_pressed"]};
            border-color: {colors["btn_soft_checked_border"]};
        }}
        QPushButton:disabled,
        QToolButton:disabled {{
            background: {colors["btn_disabled_bg"]};
            border-color: {colors["btn_disabled_border"]};
            color: {colors["text_disabled"]};
        }}
        QPushButton:checked,
        QToolButton:checked {{
            background: {colors["btn_soft_checked_bg"]};
            border-color: {colors["btn_soft_checked_border"]};
            color: {colors["btn_soft_text"]};
        }}

        QPushButton[chipButton="true"],
        QToolButton[chipButton="true"] {{
            background: {colors["btn_soft_bg"]};
            border: 1px solid {colors["btn_soft_border"]};
            color: {colors["btn_soft_text"]};
            padding: 6px 10px;
            font-weight: 500;
        }}
        QPushButton[chipButton="true"][wideChip="true"],
        QToolButton[chipButton="true"][wideChip="true"] {{
            padding-left: 15px;
            padding-right: 15px;
        }}
        QPushButton[chipButton="true"]:hover,
        QToolButton[chipButton="true"]:hover {{
            background: {colors["btn_soft_hover"]};
            border-color: {colors["border_input_hover"]};
            color: {colors["btn_soft_text"]};
        }}
        QPushButton[chipButton="true"][heartChip="true"] {{
            font-size: 15px;
        }}

        QPushButton[variant="accent"],
        QToolButton[variant="accent"],
        QPushButton[primaryAction="true"],
        QToolButton[primaryAction="true"] {{
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                                        stop:0 {colors["cta_gradient_start"]}, stop:1 {colors["cta_gradient_end"]});
            border: 1px solid {colors["cta_border"]};
            color: {colors["cta_text"]};
            border-radius: 10px;
            font-weight: 600;
        }}
        QPushButton[variant="accent"]:hover,
        QToolButton[variant="accent"]:hover,
        QPushButton[primaryAction="true"]:hover,
        QToolButton[primaryAction="true"]:hover {{
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                                        stop:0 {colors["cta_hover_start"]}, stop:1 {colors["cta_hover_end"]});
        }}
        QPushButton[variant="accent"]:pressed,
        QToolButton[variant="accent"]:pressed,
        QPushButton[primaryAction="true"]:pressed,
        QToolButton[primaryAction="true"]:pressed {{
            background: {colors["btn_primary_pressed"]};
        }}

        QPushButton[variant="danger"],
        QToolButton[variant="danger"] {{
            background: {colors["danger_bg"]};
            background-color: {colors["danger_bg"]};
            border: 1px solid {colors["danger_border"]};
            color: {colors["danger_text"]};
            font-weight: 500;
        }}
        QPushButton[variant="danger"]:hover,
        QToolButton[variant="danger"]:hover {{
            background: {colors["danger_hover"]};
            background-color: {colors["danger_hover"]};
        }}
        QPushButton[chipButton="true"][variant="danger"],
        QToolButton[chipButton="true"][variant="danger"] {{
            background: {colors["danger_bg"]};
            background-color: {colors["danger_bg"]};
            border-color: {colors["danger_border"]};
            color: {colors["danger_text"]};
        }}
        QPushButton[chipButton="true"][variant="danger"]:hover,
        QToolButton[chipButton="true"][variant="danger"]:hover {{
            background: {colors["danger_hover"]};
            background-color: {colors["danger_hover"]};
            border-color: {colors["danger_border"]};
            color: {colors["danger_text"]};
        }}
    """


def _scoped_selector(scope: str, selector: str) -> str:
    return f"{scope} {selector}" if scope else selector


def _selector_list(scope: str, selectors: tuple[str, ...]) -> str:
    return ",\n        ".join(_scoped_selector(scope, selector) for selector in selectors)


def _join_selectors(selectors: tuple[str, ...]) -> str:
    return ",\n        ".join(selectors)


def build_input_controls_stylesheet(
    colors: dict,
    scope: str = "",
    *,
    controls: tuple[str, ...] = ("QLineEdit", "QComboBox"),
    radius: str = "8px",
    padding: str = "7px 10px",
    min_height: str = "22px",
    border_key: str = "border_input",
    text_color_key: str = "text_accent",
    include_combo_popup: bool = True,
    selection_bg_key: str | None = None,
    selection_text_key: str | None = None,
) -> str:
    # Separate multi-line controls (QTextEdit, QPlainTextEdit) from single-line controls.
    # Multi-line controls should NOT get min-height from stylesheet, as it overrides
    # programmatic setMinimumHeight() and causes them to display as single-line.
    multiline_controls = ("QTextEdit", "QPlainTextEdit")
    singleline_controls = tuple(c for c in controls if c not in multiline_controls)

    selector = _selector_list(scope, controls)
    hover_selector = _selector_list(scope, tuple(f"{control}:hover" for control in controls))
    focus_selector = _selector_list(scope, tuple(f"{control}:focus" for control in controls))
    combo_css = ""
    if include_combo_popup and "QComboBox" in controls:
        combo_css = f"""
        {_scoped_selector(scope, "QComboBox")} {{
            padding-right: 24px;
        }}
        {_scoped_selector(scope, "QComboBox::drop-down")} {{
            width: 24px;
            border: none;
        }}
        {_scoped_selector(scope, "QComboBoxPrivateContainer")} {{
            background: {colors["bg_dropdown"]};
            background-color: {colors["bg_dropdown"]};
            border: 1px solid {colors["border_input"]};
        }}
        {_scoped_selector(scope, "QComboBox QAbstractItemView")} {{
            background: {colors["bg_dropdown"]};
            background-color: {colors["bg_dropdown"]};
            alternate-background-color: {colors["bg_dropdown"]};
            color: {colors[text_color_key]};
            border: none;
            border-radius: 0px;
            selection-background-color: {colors["dropdown_selection"]};
            selection-color: {colors["list_item_selected_text"]};
            outline: none;
        }}
        {_scoped_selector(scope, "QComboBox QAbstractItemView::item:selected")} {{
            background: {colors["dropdown_selection"]};
            background-color: {colors["dropdown_selection"]};
            color: {colors["list_item_selected_text"]};
        }}
        """
    selection_css = ""
    if selection_bg_key:
        selection_css += f"\n            selection-background-color: {colors[selection_bg_key]};"
    if selection_text_key:
        selection_css += f"\n            selection-color: {colors[selection_text_key]};"

    # Common styles for ALL controls (no min-height here)
    base_css = f"""
        {selector} {{
            background: {colors["bg_input"]};
            border: 1px solid {colors[border_key]};
            border-radius: {radius};
            color: {colors[text_color_key]};
            padding: {padding};{selection_css}
        }}
        {hover_selector} {{
            border-color: {colors["border_input_hover"]};
        }}
        {focus_selector} {{
            border-color: {colors["border_input_focus"]};
            background: {colors["bg_input_focus"]};
        }}
        {combo_css}
    """

    # Apply min-height ONLY to single-line controls
    if singleline_controls:
        sl_selector = _selector_list(scope, singleline_controls)
        base_css += f"""
        {sl_selector} {{
            min-height: {min_height};
        }}
    """

    return base_css


def build_cta_button_stylesheet(
    colors: dict,
    selector: str,
    *,
    radius: str = "10px",
    padding: str = "7px 12px",
    font_size: str | None = None,
    min_height: str | None = None,
) -> str:
    optional = ""
    if font_size:
        optional += f"\n            font-size: {font_size};"
    if min_height:
        optional += f"\n            min-height: {min_height};"
    return f"""
        {selector} {{
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                                        stop:0 {colors["cta_gradient_start"]}, stop:1 {colors["cta_gradient_end"]});
            border: 1px solid {colors["cta_border"]};
            color: {colors["cta_text"]};
            border-radius: {radius};
            padding: {padding};
            font-weight: 600;{optional}
        }}
        {selector}:hover {{
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                                        stop:0 {colors["cta_hover_start"]}, stop:1 {colors["cta_hover_end"]});
        }}
        {selector}:pressed {{
            background: {colors["btn_primary_pressed"]};
        }}
    """


def build_scrollbar_stylesheet(colors: dict, scope: str = "") -> str:
    return f"""
        {_scoped_selector(scope, "QScrollBar:vertical")},
        {_scoped_selector(scope, "QScrollBar:horizontal")} {{
            background: transparent;
            border-radius: 3px;
            border: none;
        }}
        {_scoped_selector(scope, "QScrollBar::handle:vertical")},
        {_scoped_selector(scope, "QScrollBar::handle:horizontal")} {{
            background: {colors["scroll_handle"]};
            border-radius: 3px;
        }}
        {_scoped_selector(scope, "QScrollBar::handle:vertical:hover")},
        {_scoped_selector(scope, "QScrollBar::handle:horizontal:hover")} {{
            background: {colors["scroll_handle_hover"]};
        }}
        {_scoped_selector(scope, "QScrollBar::add-line")},
        {_scoped_selector(scope, "QScrollBar::sub-line")} {{
            width: 0px;
            height: 0px;
        }}
    """


def build_menu_stylesheet(
    colors: dict,
    scope: str = "",
    *,
    bg_key: str = "bg_surface_raised",
    border_key: str = "border_card",
    text_color_key: str = "text_accent",
    selected_bg_key: str = "tab_hover",
    selected_text_key: str = "text_bright",
    item_padding: str = "7px 14px",
    include_separator: bool = False,
    separator_key: str = "divider_sub_line",
) -> str:
    separator_css = ""
    if include_separator:
        separator_css = f"""
        {_scoped_selector(scope, "QMenu::separator")} {{
            height: 1px;
            margin: 5px 10px;
            background: {colors[separator_key]};
        }}
        """
    return f"""
        {_scoped_selector(scope, "QMenu")} {{
            background: {colors[bg_key]};
            background-color: {colors[bg_key]};
            color: {colors[text_color_key]};
            border: 1px solid {colors[border_key]};
            border-radius: 10px;
            padding: 6px 4px;
        }}
        {_scoped_selector(scope, "QMenu::item")} {{
            background: transparent;
            color: {colors[text_color_key]};
            padding: {item_padding};
            margin: 1px 4px;
            border-radius: 6px;
        }}
        {_scoped_selector(scope, "QMenu::item:selected")} {{
            background: {colors[selected_bg_key]};
            background-color: {colors[selected_bg_key]};
            color: {colors[selected_text_key]};
        }}
        {separator_css}
    """


def build_section_icon_button_stylesheet(colors: dict) -> str:
    return f"""
        QPushButton[sectionIconButton="true"],
        QToolButton[sectionIconButton="true"] {{
            min-width: 28px;
            max-width: 28px;
            min-height: 24px;
            max-height: 24px;
            padding: 0px;
            border: none;
            border-radius: 6px;
            background: transparent;
            color: {colors["text_muted"]};
            font-size: 14px;
            font-weight: 700;
        }}
        QPushButton[sectionIconButton="true"]:hover,
        QToolButton[sectionIconButton="true"]:hover {{
            background: {colors["btn_soft_hover"]};
            color: {colors["text_bright"]};
        }}
        QPushButton[sectionIconButton="true"]:pressed,
        QToolButton[sectionIconButton="true"]:pressed {{
            background: {colors["btn_soft_pressed"]};
            color: {colors["text_bright"]};
        }}
        QPushButton[sectionIconButton="true"]:disabled,
        QToolButton[sectionIconButton="true"]:disabled {{
            background: transparent;
            color: {colors["text_disabled"]};
        }}
        QPushButton[sectionIconButton="true"][variant="danger"],
        QToolButton[sectionIconButton="true"][variant="danger"] {{
            background: {colors["danger_bg"]};
            background-color: {colors["danger_bg"]};
            border: 1px solid {colors["danger_border"]};
            color: {colors["danger_text"]};
        }}
        QPushButton[sectionIconButton="true"][variant="danger"]:hover,
        QToolButton[sectionIconButton="true"][variant="danger"]:hover {{
            background: {colors["danger_hover"]};
            background-color: {colors["danger_hover"]};
            border-color: {colors["danger_border"]};
            color: {colors["danger_text"]};
        }}
        QPushButton[sectionIconButton="true"][variant="danger"]:pressed,
        QToolButton[sectionIconButton="true"][variant="danger"]:pressed {{
            background: {colors["danger_bg"]};
            background-color: {colors["danger_bg"]};
            border-color: {colors["danger_border"]};
            color: {colors["danger_text"]};
        }}
        QPushButton[sectionIconButton="true"][variant="danger"]:disabled,
        QToolButton[sectionIconButton="true"][variant="danger"]:disabled {{
            background: transparent;
            color: {colors["text_disabled"]};
        }}
    """


def generate_application_stylesheet(theme: str) -> str:
    c = get_theme_colors(theme)
    return f"""
        QMainWindow, QDialog {{
            background: {c["bg_window_shell"]};
        }}
        QWidget {{
            font-family: "Microsoft YaHei UI", "Segoe UI", sans-serif;
            font-size: 12px;
            color: {c["text_primary"]};
        }}
        QWidget:disabled {{
            color: {c["text_disabled"]};
        }}

        {build_tooltip_stylesheet(c)}

        {build_menu_stylesheet(c, bg_key="bg_dropdown", border_key="border_card", item_padding="7px 16px", include_separator=True)}

        QGroupBox {{
            background: {c["bg_card"]};
            border: 1px solid {c["border_subtle"]};
            border-radius: 16px;
            margin-top: 12px;
            padding: 12px;
            font-weight: 500;
            color: {c["text_card_title"]};
        }}
        QGroupBox::title {{
            subcontrol-origin: margin;
            subcontrol-position: top left;
            margin-left: 10px;
            padding: 0 8px;
            background: transparent;
            color: {c["text_card_title"]};
        }}

        QInputDialog {{
            background: {c["bg_panel"]};
            border: 1px solid {c["border_card"]};
            border-radius: 14px;
        }}
        QInputDialog QLabel {{
            background: transparent;
            color: {c["text_page_title"]};
            font-size: 13px;
            font-weight: 600;
            min-width: 280px;
        }}
        QInputDialog QLineEdit {{
            min-height: 24px;
            padding: 8px 10px;
        }}
        QInputDialog QPushButton {{
            min-width: 88px;
            min-height: 32px;
        }}
        QInputDialog QPushButton:default {{
            background: {c["btn_primary_bg"]};
            border-color: {c["btn_primary_border"]};
            color: {c["btn_primary_text"]};
        }}
        QInputDialog QPushButton:default:hover {{
            background: {c["btn_primary_hover"]};
        }}
        QInputDialog QPushButton:default:pressed {{
            background: {c["btn_primary_pressed"]};
        }}

        QMessageBox#themedMessageBox {{
            background: {c["bg_panel"]};
            border: 1px solid {c["border_input"]};
            border-radius: 14px;
        }}
        QMessageBox#themedMessageBox QLabel {{
            background: transparent;
            color: {c["text_primary"]};
            font-family: "Microsoft YaHei UI", "Segoe UI", sans-serif;
            font-size: 12px;
        }}
        QMessageBox#themedMessageBox QLabel#qt_msgbox_label {{
            color: {c["text_primary"]};
            font-size: 13px;
            font-weight: 600;
        }}
        QMessageBox#themedMessageBox QLabel#qt_msgbox_informativelabel {{
            color: {c["text_primary"]};
            font-size: 12px;
        }}
        QMessageBox#themedMessageBox QPushButton {{
            min-width: 88px;
            min-height: 34px;
            border-radius: 8px;
            padding: 6px 14px;
            font-size: 12px;
            font-weight: 500;
            background: {c["btn_soft_bg"]};
            border: 1px solid {c["btn_soft_border"]};
            color: {c["btn_soft_text"]};
        }}
        QMessageBox#themedMessageBox QPushButton:hover {{
            background: {c["btn_soft_hover"]};
            border-color: {c["border_input_focus"]};
        }}
        QMessageBox#themedMessageBox QPushButton:pressed {{
            background: {c["btn_soft_pressed"]};
        }}
        QMessageBox#themedMessageBox QPushButton[dialogDefault="true"] {{
            background: {c["btn_primary_bg"]};
            border: 1px solid {c["btn_primary_border"]};
            color: {c["btn_primary_text"]};
        }}
        QMessageBox#themedMessageBox QPushButton[dialogDefault="true"]:hover {{
            background: {c["btn_primary_hover"]};
        }}
        QMessageBox#themedMessageBox QPushButton[dialogDefault="true"]:pressed {{
            background: {c["btn_primary_pressed"]};
        }}

        {build_input_controls_stylesheet(
            c,
            controls=("QLineEdit", "QTextEdit", "QPlainTextEdit", "QComboBox", "QSpinBox", "QDoubleSpinBox"),
            selection_bg_key="dropdown_selection",
            selection_text_key="list_item_selected_text",
        )}
        #workflow_mode_combo QComboBoxPrivateContainer {{
            background: {c["bg_surface_raised"]};
            background-color: {c["bg_surface_raised"]};
            border: 1px solid {c["border_card"]};
            border-radius: 0px;
        }}
        #workflow_mode_combo QAbstractItemView {{
            background: {c["bg_surface_raised"]};
            background-color: {c["bg_surface_raised"]};
            border: 1px solid {c["border_card"]};
            border-radius: 0px;
        }}

        {build_shared_button_stylesheet(c)}

        QCheckBox {{
            spacing: 8px;
        }}
        QCheckBox::indicator {{
            width: 18px;
            height: 18px;
            border-radius: 4px;
            border: 1px solid {c["checkbox_border"]};
            background: {c["checkbox_bg"]};
        }}
        QCheckBox::indicator:checked {{
            background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                                        stop:0 {c["checkbox_checked_start"]}, stop:1 {c["checkbox_checked_end"]});
            border-color: {c["checkbox_checked_border"]};
        }}
        QCheckBox::indicator:hover {{
            border-color: {c["checkbox_hover_border"]};
        }}

        QSlider::groove:horizontal {{
            background: {c["slider_groove"]};
            height: 4px;
            border-radius: 2px;
        }}
        QSlider::handle:horizontal {{
            background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                                        stop:0 {c["slider_handle_start"]}, stop:1 {c["slider_handle_end"]});
            width: 14px;
            height: 14px;
            margin: -5px 0;
            border-radius: 7px;
            border: 1px solid {c["slider_handle_border"]};
        }}
        QSlider::handle:horizontal:hover {{
            background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                                        stop:0 {c["slider_handle_hover_start"]}, stop:1 {c["slider_handle_hover_end"]});
        }}

        QTabWidget::pane {{
            border: none;
            background: transparent;
        }}
        QTabWidget#replacements_tabs::pane {{
            border: none;
            background: transparent;
            padding: 0px;
            border-radius: 0px;
        }}
        QWidget#replacements_tab_page {{
            background: transparent;
            border: none;
            border-radius: 0px;
        }}
        QTabBar::tab {{
            background: transparent;
            border: none;
            border-radius: 8px;
            color: {c["text_secondary"]};
            padding: 6px 14px;
            margin: 2px 3px;
            font-weight: 500;
        }}
        QTabBar::tab:selected {{
            background: {c["nav_checked_bg"]};
            color: {c["text_bright"]};
            font-weight: 600;
        }}
        QTabBar::tab:hover:!selected {{
            background: {c["nav_hover_bg"]};
            color: {c["text_accent"]};
        }}

        QListWidget,
        QListView,
        QTreeWidget,
        QTreeView,
        QTableWidget,
        QTableView {{
            background: {c["bg_list"]};
            border: 1px solid {c["border_list"]};
            border-radius: 10px;
            color: {c["text_accent"]};
            outline: none;
        }}
        QTableWidget#replacements_table {{
            border-radius: 0px;
        }}
        QListWidget::item,
        QListView::item,
        QTreeWidget::item,
        QTreeView::item {{
            padding: 6px 8px;
            border-radius: 6px;
        }}
        QListWidget::item:hover,
        QListView::item:hover,
        QTreeWidget::item:hover,
        QTreeView::item:hover {{
            background: {c["list_item_hover"]};
        }}
        QListWidget::item:selected,
        QListView::item:selected,
        QTreeWidget::item:selected,
        QTreeView::item:selected,
        QTableView::item:selected,
        QTableWidget::item:selected {{
            background: {c["list_item_selected"]};
            color: {c["list_item_selected_text"]};
        }}
        QHeaderView::section {{
            background: {c["bg_surface_soft"]};
            color: {c["text_secondary"]};
            border: none;
            border-bottom: 1px solid {c["border_subtle"]};
            padding: 8px 10px;
            font-weight: 600;
        }}

        QScrollArea {{
            background: transparent;
            border: none;
        }}
        {build_scrollbar_stylesheet(c)}
        QScrollBar:vertical {{
            width: 6px;
        }}
        QScrollBar:horizontal {{
            height: 6px;
        }}
        QScrollBar::handle:vertical,
        QScrollBar::handle:horizontal {{
            min-height: 24px;
            min-width: 24px;
        }}

        QSplitter::handle {{
            background: {c["splitter_handle"]};
        }}
        QSplitter::handle:hover {{
            background: {c["splitter_handle_hover"]};
        }}

        QLabel[status="success"] {{
            color: {c["success_color"]};
        }}
        QLabel[status="error"] {{
            color: {c["danger_bg"]};
        }}
    """


def generate_main_view_style(theme: str = "dark") -> str:
    c = get_theme_colors(theme)
    return f"""
        #main_view_root {{
            background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                                        stop:0 {c["bg_gradient_start"]},
                                        stop:0.45 {c["bg_gradient_mid"]},
                                        stop:1 {c["bg_gradient_end"]});
        }}
        #main_view_root QWidget#content_page_translation,
        #main_view_root QWidget#content_page_settings,
        #main_view_root QWidget#content_page_env,
        #main_view_root QWidget#content_page_prompts,
        #main_view_root QWidget#content_page_fonts,
        #main_view_root QWidget#content_page_replacements,
        #main_view_root QWidget#content_page_batch_edit,
        #main_view_root QWidget#content_page_folder_sync {{
            background: transparent;
        }}
        #main_view_root QListWidget#folder_sync_list[dragOver="true"] {{
            border: 1px dashed {c["border_input_focus"]};
            background: {c["list_item_hover"]};
        }}
        #main_view_root QLabel#folder_sync_item_title {{
            color: {c["text_primary"]};
            font-weight: 600;
        }}
        #main_view_root QLabel#folder_sync_kicker {{
            color: {c["text_row_label"]};
            font-size: 13px;
            font-weight: 700;
        }}
        #main_view_root QPushButton#folder_sync_button {{
            font-size: 13px;
        }}
        #main_view_root QLabel {{
            color: {c["text_primary"]};
        }}

        #main_view_splitter::handle:horizontal {{
            background: {c["splitter_handle"]};
            width: 6px;
            margin: 6px 0;
            border-radius: 3px;
        }}
        #main_view_splitter::handle:horizontal:hover {{
            background: {c["splitter_handle_hover"]};
        }}

        #sidebar_panel {{
            background: {c["bg_sidebar"]};
            border-right: 1px solid {c["border_sidebar"]};
        }}
        #sidebar_nav_column {{
            background-color: transparent;
            border: none;
        }}
        #sidebar_logo_header,
        #sidebar_logo {{
            background-color: transparent;
            border: none;
            padding: 0px;
            margin: 0px;
        }}
        #sidebar_group_label {{
            color: {c["text_sidebar_group"]};
            font-size: 10px;
            font-weight: 600;
            padding: 8px 6px 2px 6px;
        }}
        #sidebar_api_status {{
            color: {c["text_secondary"]};
            font-size: 11px;
            font-weight: normal;
            padding: 4px 6px 8px 6px;
            line-height: 1.25;
        }}
        #sidebar_api_status_scroll {{
            background: transparent;
            border: none;
        }}
        #sidebar_panel QPushButton[navButton="true"],
        #sidebar_panel QPushButton[navActionButton="true"] {{
            background: transparent;
            border: none;
            border-radius: 8px;
            color: {c["text_secondary"]};
            text-align: left;
            padding: 8px 12px;
            margin: 1px 8px;
            font-size: 13px;
            font-weight: 600;
        }}
        #sidebar_panel QPushButton[navButton="true"]:hover,
        #sidebar_panel QPushButton[navActionButton="true"]:hover {{
            background: {c["nav_hover_bg"]};
            color: {c["text_accent"]};
        }}
        #sidebar_panel QPushButton[navButton="true"]:checked {{
            background: {c["nav_checked_bg"]};
            color: {c["text_bright"]};
        }}

        #content_panel {{
            background: transparent;
        }}
        #content_vertical_splitter::handle:vertical {{
            background: {c["splitter_handle"]};
            height: 6px;
            margin: 0 18px;
            border-radius: 3px;
        }}
        #content_vertical_splitter::handle:vertical:hover {{
            background: {c["splitter_handle_hover"]};
        }}

        QGroupBox#section_card,
        #settings_desc_panel,
        #log_container {{
            background: {c["bg_header_card"]};
            border: 1px solid {c["border_subtle"]};
            border-radius: 16px;
        }}
        #header_card {{
            background: transparent;
            border: none;
        }}
        QGroupBox#section_card {{
            margin-top: 12px;
            padding: 12px;
        }}
        QGroupBox#section_card[role="conditions"] {{
            margin-bottom: 9px;
        }}
        QGroupBox#section_card::title {{
            color: {c["text_desc_name"]};
            font-size: 13px;
            font-weight: 600;
        }}
        #page_title {{
            color: {c["text_page_title"]};
            font-family: "Malgun Gothic", "맑은 고딕";
            font-size: 19px;
            font-weight: 700;
        }}
        #page_subtitle {{
            color: {c["text_page_subtitle"]};
            font-size: 12px;
        }}
        #header_card QLabel#page_subtitle {{
            padding-bottom: 12px;
        }}
        #row_label {{
            color: {c["text_row_label"]};
            font-size: 12px;
            font-weight: 500;
        }}
        #workflow_mode_combo {{
            min-height: 75px;
            max-height: 75px;
            padding: 0px;
            border: none;
            border-width: 0px;
            border-radius: 0px;
            outline: none;
        }}
        #workflow_mode_combo:hover,
        #workflow_mode_combo:focus,
        #workflow_mode_combo:on,
        #workflow_mode_combo:pressed,
        #workflow_mode_combo:disabled {{
            border: none;
            border-width: 0px;
            outline: none;
        }}
        #workflow_mode_combo::drop-down {{
            border: none;
        }}
        #workflow_mode_combo QComboBoxPrivateContainer {{
            background: {c["bg_surface_raised"]};
            background-color: {c["bg_surface_raised"]};
            border: 1px solid {c["border_card"]};
            border-radius: 0px;
        }}
        #workflow_mode_combo QAbstractItemView {{
            background: {c["bg_surface_raised"]};
            background-color: {c["bg_surface_raised"]};
            border: 1px solid {c["border_card"]};
            border-radius: 0px;
        }}
        #workflow_mode_combo QAbstractItemView::item {{
            min-height: 72px;
            padding: 6px 8px;
        }}
        #output_path_conflict_warning {{
            color: {c["warning_color"]};
            font-size: 12px;
            font-weight: 500;
        }}
        #inline_toolbar {{
            background: transparent;
        }}

        {build_file_list_stylesheet(
            c,
            ("#translation_file_list", "#asset_list"),
            file_item_selectors=("#translation_file_list", "#asset_list"),
            mark_json_status=True,
        )}
        #main_view_root QPushButton#file_item_remove_button {{
            background: {c["btn_soft_bg"]};
            border: 1px solid {c["btn_soft_border"]};
            color: {c["btn_soft_text"]};
            border-radius: 10px;
            min-width: 20px;
            max-width: 20px;
            min-height: 20px;
            max-height: 20px;
            padding: 0px;
            font-size: 11px;
            font-weight: 500;
        }}
        #main_view_root QPushButton#file_item_remove_button:hover {{
            background: {c["danger_bg"]};
            border-color: {c["danger_border"]};
            color: {c["danger_text"]};
        }}

        {build_cta_button_stylesheet(c, "#main_view_root QPushButton#start_translation_button", radius="12px", padding="10px 18px", font_size="14px", min_height="44px")}
        #main_view_root QPushButton#start_translation_button[translationState="stop"] {{
            background: {c["danger_bg"]};
            border: 1px solid {c["danger_border"]};
            color: {c["danger_text"]};
        }}
        #main_view_root QPushButton#start_translation_button[translationState="stop"]:hover {{
            background: {c["danger_hover"]};
        }}
        #main_view_root QPushButton#start_translation_button[translationState="stopping"] {{
            background: {c["btn_disabled_bg"]};
            border-color: {c["btn_disabled_border"]};
            color: {c["text_disabled"]};
        }}

        #translation_progress_bar {{
            min-height: 24px;
            border-radius: 8px;
            text-align: center;
            padding: 0px 4px;
        }}
        #translation_progress_bar[progressState="idle"] {{
            background: {c["bg_input"]};
            border: 1px solid {c["border_list"]};
            color: {c["text_muted"]};
        }}
        #translation_progress_bar[progressState="idle"]::chunk {{
            background: {c["scroll_handle"]};
            border-radius: 8px;
        }}
        #translation_progress_bar[progressState="active"] {{
            background: {c["bg_input_focus"]};
            border: 1px solid {c["cta_border"]};
            color: {c["text_bright"]};
        }}
        #translation_progress_bar[progressState="active"]::chunk {{
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                                        stop:0 {c["cta_gradient_start"]}, stop:1 {c["cta_gradient_end"]});
            border-radius: 8px;
        }}
        #progress_info_label {{
            color: {c["text_page_subtitle"]};
            font-size: 12px;
            padding: 0 2px 2px 2px;
        }}

        #settings_tabs::pane,
        #settings_tab_widget::pane {{
            border: none;
            background: transparent;
            padding: 0px;
            top: 4px;
        }}
        #settings_tabs > QTabBar::tab,
        #settings_tab_widget > QTabBar::tab {{
            background: {c["tab_bg"]};
            border: 1px solid {c["border_tab"]};
            border-bottom: 1px solid transparent;
            border-top-left-radius: 8px;
            border-top-right-radius: 8px;
            color: {c["text_muted"]};
            padding: 7px 16px;
            margin-right: 3px;
            font-weight: 500;
        }}
        #settings_tabs > QTabBar::tab:selected,
        #settings_tab_widget > QTabBar::tab:selected {{
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                        stop:0 {c["tab_selected_start"]}, stop:1 {c["tab_selected_end"]});
            color: {c["text_bright"]};
            border-color: {c["border_tab_selected"]};
        }}
        #settings_tabs > QTabBar::tab:hover:!selected,
        #settings_tab_widget > QTabBar::tab:hover:!selected {{
            background: {c["tab_hover"]};
            color: {c["text_accent"]};
        }}

        #settings_scroll_area {{
            background: transparent;
            border: none;
        }}
        #settings_scroll_content {{
            background: transparent;
        }}
        #settings_scroll_content QLabel {{
            color: {c["text_settings_label"]};
            font-size: 12px;
            padding: 2px 0px;
        }}
        #settings_scroll_content QLabel#settings_form_label {{
            color: {c["text_row_label"]};
            font-weight: 500;
        }}
        #settings_scroll_content QFrame#api_slot_card {{
            background: {c["bg_header_card"]};
            border: 1px solid {c["border_subtle"]};
            border-radius: 10px;
            margin: 2px 0px 6px 0px;
        }}
        #settings_scroll_content QWidget#api_slot_header {{
            background: transparent;
            border: none;
        }}
        #settings_scroll_content QLabel#api_slot_badge {{
            background: {c["nav_checked_bg"]};
            border: 1px solid {c["nav_checked_border"]};
            border-radius: 7px;
            color: {c["text_bright"]};
            font-size: 11px;
            font-weight: 700;
            padding: 0px;
        }}
        #settings_scroll_content QLabel#api_slot_title {{
            color: {c["text_bright"]};
            font-size: 13px;
            font-weight: 600;
            padding: 0px;
        }}
        #settings_scroll_content QFrame#api_slot_divider {{
            background: {c["divider_sub_line"]};
            border: none;
            max-height: 1px;
        }}
        #settings_scroll_content QLabel#api_slot_field_label {{
            color: {c["text_row_label"]};
            font-size: 12px;
            font-weight: 500;
            padding: 2px 0px;
        }}
        #main_view_root QPushButton#api_slot_add_button {{
            margin-top: 2px;
            padding: 7px 12px;
        }}
        #settings_scroll_content QFrame#api_empty_state {{
            background: {c["bg_surface_soft"]};
            border: 1px solid {c["border_subtle"]};
            border-radius: 14px;
            margin-top: 14px;
        }}
        #settings_scroll_content QLabel#api_empty_state_text {{
            color: {c["text_muted"]};
            font-size: 20px;
            font-weight: 500;
            padding: 0px;
        }}
        #settings_desc_panel {{
            background: {c["settings_desc_panel_bg"]};
            border: 1px solid {c["border_subtle"]};
            border-radius: 16px;
        }}
        #settings_desc_header {{
            color: {c["text_desc_header"]};
            font-size: 14px;
            font-weight: 600;
        }}
        #settings_desc_divider {{
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                                        stop:0 {c["divider_desc"]}, stop:1 {c["divider_desc_end"]});
            max-height: 1px;
            border: none;
        }}
        #settings_desc_name {{
            color: {c["text_desc_name"]};
            font-size: 15px;
            font-weight: 600;
            padding-top: 4px;
        }}
        #main_view_root QLabel#settings_desc_key {{
            color: {c["text_muted"]};
            font-size: 11px;
            font-family: "Consolas", "Microsoft YaHei UI", monospace;
            padding: 8px 0px 2px 0px;
        }}
        #settings_desc_text {{
            color: {c["text_desc_text"]};
            font-size: 13px;
            padding: 6px 0px;
        }}
        #main_view_root QLabel#conditions_empty_label {{
            color: {c["text_desc_text"]};
            font-size: 13px;
        }}
        #settings_body_splitter::handle:horizontal {{
            background: {c["splitter_handle"]};
            width: 6px;
            margin: 18px 0;
            border-radius: 3px;
        }}
        #settings_body_splitter::handle:horizontal:hover {{
            background: {c["splitter_handle_hover"]};
        }}

        #font_preview_name {{
            color: {c["text_desc_name"]};
            font-size: 15px;
            font-weight: 600;
        }}
        #font_preview_text {{
            color: {c["text_primary"]};
            padding: 4px 2px;
        }}

        #main_view_root #settings_divider_line,
        #main_view_root #settings_divider_sub_line {{
            border: none;
            background-color: {c["border_input"]};
            height: 1px;
            max-height: 1px;
        }}
        #main_view_root #settings_divider_title {{
            color: {c["text_desc_key"]};
            font-size: 13px;
            font-weight: 700;
        }}
        #main_view_root #settings_divider_sub_title {{
            color: {c["text_secondary"]};
            font-size: 12px;
            font-weight: 600;
        }}
        #main_view_root #settings_divider_dot {{
            color: {c["text_divider_dot"]};
            font-size: 10px;
        }}
    """


def build_file_list_stylesheet(
    colors: dict,
    list_selectors: tuple[str, ...],
    *,
    file_item_selectors: tuple[str, ...] = (),
    mark_json_status: bool = False,
) -> str:
    lists = _join_selectors(list_selectors)
    items = _join_selectors(tuple(f"{selector}::item" for selector in list_selectors))
    hover_items = _join_selectors(tuple(f"{selector}::item:hover" for selector in list_selectors))
    selected_items = _join_selectors(tuple(f"{selector}::item:selected" for selector in list_selectors))
    file_roots = _join_selectors(tuple(f"{selector} QWidget#file_item_root" for selector in file_item_selectors))
    file_names = _join_selectors(tuple(f"{selector} QLabel#file_item_name_label" for selector in file_item_selectors))
    remove_buttons = _join_selectors(tuple(f"{selector} QPushButton#file_item_remove_button" for selector in file_item_selectors))
    remove_buttons_json = _join_selectors(
        tuple(f'{selector} QPushButton#file_item_remove_button[hasJson="true"]' for selector in file_item_selectors)
    )
    remove_buttons_hover = _join_selectors(
        tuple(f"{selector} QPushButton#file_item_remove_button:hover" for selector in file_item_selectors)
    )
    file_item_css = ""
    if file_item_selectors:
        file_item_css = f"""
        {file_roots} {{
            background: transparent;
            border-radius: 8px;
            margin-top: -3px;
        }}
        {file_names} {{
            color: {colors["text_accent"]};
            font-weight: 500;
        }}
        {remove_buttons} {{
            background: {colors["btn_soft_bg"]};
            border: 1px solid {colors["btn_soft_border"]};
            color: {colors["btn_soft_text"]};
            border-radius: 10px;
            min-width: 20px;
            max-width: 20px;
            min-height: 20px;
            max-height: 20px;
            padding: 0px;
            font-size: 11px;
            font-weight: 500;
        }}
        {f'''{remove_buttons_json} {{
            background: {colors["accent_60"]};
            border: 1px solid {colors["btn_primary_bg"]};
            color: #FFFFFF;
        }}''' if mark_json_status else ""}
        {remove_buttons_hover} {{
            background: {colors["danger_bg"]};
            border-color: {colors["danger_border"]};
            color: {colors["danger_text"]};
        }}
        """
    return f"""
        {lists} {{
            background: {colors["bg_list"]};
            border: 1px solid {colors["border_list"]};
            border-radius: 12px;
            padding: 6px;
            outline: none;
        }}
        {items} {{
            border-radius: 8px;
            padding: 0px;
            margin: 1px 0;
        }}
        {hover_items} {{
            background: {colors["list_item_hover"]};
        }}
        {selected_items} {{
            background: {colors["list_item_selected"]};
        }}
        {file_item_css}
    """


def generate_editor_style(theme: str = "dark") -> str:
    c = get_theme_colors(theme)
    return f"""
        #editor_view_root {{
            background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                                        stop:0 {c["bg_gradient_start"]},
                                        stop:0.45 {c["bg_gradient_mid"]},
                                        stop:1 {c["bg_gradient_end"]});
        }}
        #editor_toolbar {{
            background: {c["bg_toolbar"]};
            border-bottom: 1px solid {c["bg_toolbar_border"]};
        }}
        #editor_toolbar QToolButton {{
            background: {c["btn_soft_bg"]};
            border: 1px solid {c["btn_soft_border"]};
            border-radius: 10px;
            color: {c["btn_soft_text"]};
            padding: 4px 11px;
            font-size: 11px;
            font-weight: 500;
            min-height: 20px;
            max-height: 28px;
        }}
        #editor_toolbar QToolButton:hover {{
            background: {c["btn_soft_hover"]};
            border-color: {c["border_input_hover"]};
            color: {c["btn_soft_text"]};
        }}
        #editor_toolbar QToolButton:pressed {{
            background: {c["btn_soft_pressed"]};
            border-color: {c["btn_soft_checked_border"]};
            color: {c["btn_soft_text"]};
        }}
        #editor_toolbar QToolButton:checked {{
            background: {c["btn_soft_checked_bg"]};
            border-color: {c["btn_soft_checked_border"]};
            color: {c["btn_soft_text"]};
        }}
        #editor_toolbar QToolButton[variant="accent"],
        #editor_toolbar QToolButton[primaryAction="true"] {{
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                                        stop:0 {c["cta_gradient_start"]}, stop:1 {c["cta_gradient_end"]});
            border: 1px solid {c["cta_border"]};
            color: {c["cta_text"]};
            border-radius: 9px;
            padding: 5px 14px;
            min-height: 22px;
            font-size: 12px;
            font-weight: 600;
        }}
        #editor_toolbar QToolButton[variant="accent"]:hover,
        #editor_toolbar QToolButton[primaryAction="true"]:hover {{
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                                        stop:0 {c["cta_hover_start"]}, stop:1 {c["cta_hover_end"]});
        }}
        #editor_toolbar QToolButton[variant="accent"]:pressed,
        #editor_toolbar QToolButton[primaryAction="true"]:pressed {{
            background: {c["btn_primary_pressed"]};
        }}
        #editor_export_button {{
            min-width: 98px;
        }}
        #editor_toolbar QLabel {{
            color: {c["text_secondary"]};
            font-size: 11px;
            padding: 0 2px;
        }}
        #editor_toolbar QComboBox {{
            background: {c["bg_input"]};
            border: 1px solid {c["border_input"]};
            border-radius: 7px;
            color: {c["text_accent"]};
            padding: 3px 20px 3px 6px;
            min-height: 18px;
            max-height: 26px;
            font-size: 11px;
        }}
        #editor_toolbar QComboBox:hover {{
            border-color: {c["border_input_hover"]};
        }}
        #editor_toolbar QComboBox:focus {{
            border-color: {c["border_input_focus"]};
            background: {c["bg_input_focus"]};
        }}
        #editor_toolbar QComboBoxPrivateContainer {{
            background: {c["bg_dropdown"]};
            background-color: {c["bg_dropdown"]};
            border: 1px solid {c["border_input"]};
        }}
        #editor_toolbar QComboBox QAbstractItemView {{
            background: {c["bg_dropdown"]};
            background-color: {c["bg_dropdown"]};
            alternate-background-color: {c["bg_dropdown"]};
            color: {c["text_accent"]};
            border: 1px solid {c["border_input"]};
            selection-background-color: {c["dropdown_selection"]};
            selection-color: {c["list_item_selected_text"]};
        }}
        #editor_toolbar QComboBox QAbstractItemView::item:selected {{
            background: {c["dropdown_selection"]};
            background-color: {c["dropdown_selection"]};
            color: {c["list_item_selected_text"]};
        }}
        #editor_toolbar QSlider::groove:horizontal {{
            background: {c["slider_groove"]};
            height: 4px;
            border-radius: 2px;
        }}
        #editor_toolbar QSlider::handle:horizontal {{
            background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                                        stop:0 {c["slider_handle_start"]}, stop:1 {c["slider_handle_end"]});
            width: 14px;
            height: 14px;
            margin: -5px 0;
            border-radius: 7px;
            border: 1px solid {c["slider_handle_border"]};
        }}
        #editor_toolbar QSlider::handle:horizontal:hover {{
            background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                                        stop:0 {c["slider_handle_hover_start"]}, stop:1 {c["slider_handle_hover_end"]});
        }}
        #editor_toolbar QFrame#editor_toolbar_separator {{
            color: {c["separator_color"]};
        }}

        #editor_main_splitter::handle:horizontal {{
            background: {c["splitter_handle"]};
            width: 6px;
            margin: 12px 0;
            border-radius: 3px;
        }}
        #editor_main_splitter::handle:horizontal:hover {{
            background: {c["splitter_handle_hover"]};
        }}

        #editor_left_tabs::pane {{
            border: none;
            background: transparent;
            padding: 0px;
        }}
        #editor_left_tabs > QTabBar::tab {{
            background: transparent;
            border: none;
            border-radius: 8px;
            color: {c["text_muted"]};
            padding: 6px 12px;
            margin: 2px 3px;
            font-weight: 500;
        }}
        #editor_left_tabs > QTabBar::tab:first {{
            margin: 2px 3px 2px 15px;
        }}
        #editor_left_tabs > QTabBar::tab:selected {{
            background: {c["nav_checked_bg"]};
            color: {c["text_bright"]};
            font-weight: 600;
        }}
        #editor_left_tabs > QTabBar::tab:hover:!selected {{
            background: {c["nav_hover_bg"]};
            color: {c["text_accent"]};
        }}

        #editor_translation_page,
        #editor_property_panel {{
            background: transparent;
        }}
        #editor_search_bar {{
            background: {c["bg_surface_soft"]};
            border: 1px solid {c["border_subtle"]};
            border-radius: 10px;
        }}
        #editor_search_bar QPushButton {{
            min-height: 28px;
            padding: 5px 10px;
        }}

        #editor_view_root QGroupBox {{
            background: {c["bg_card"]};
            border: 1px solid {c["border_subtle"]};
            border-radius: 16px;
            margin-top: 10px;
            padding: 10px;
            font-weight: 600;
            color: {c["text_card_title"]};
        }}
        #editor_view_root QGroupBox::title {{
            padding: 0 8px;
            margin-left: 10px;
            color: {c["text_card_title"]};
        }}

        #editor_property_scroll {{
            background: transparent;
            border: none;
        }}
        #editor_property_content {{
            background: transparent;
        }}
        #editor_property_content QFrame#editor_section_divider {{
            background: {c["border_subtle"]};
            max-height: 1px;
            border: none;
        }}
        #editor_property_content QLabel {{
            color: {c["text_secondary"]};
            font-size: 12px;
        }}
        #editor_property_content QLabel#editor_shortcut_hint {{
            color: {c["text_muted"]};
            font-size: 12px;
            font-weight: 400;
        }}
        #editor_property_content QLabel#editor_text_stats_overlay {{
            color: {c["text_muted"]};
            font-size: 11px;
            font-weight: 500;
            background: transparent;
            padding: 0px;
        }}
        #editor_property_content QLabel#editor_brush_size_value_label {{
            color: {c["text_muted"]};
            font-size: 11px;
            font-weight: 500;
        }}
        QWidget#color_picker_root {{
            background: transparent;
            border: none;
        }}
        QWidget#color_picker_root QLabel#color_picker_rgb_label {{
            color: {c["text_muted"]};
        }}
        QWidget#color_picker_root QToolButton#color_picker_saved_button {{
            background: {c["btn_soft_bg"]};
            border: 1px solid {c["btn_soft_border"]};
            color: {c["btn_soft_text"]};
            border-radius: 8px;
        }}
        QWidget#color_picker_root QToolButton#color_picker_saved_button:hover {{
            background: {c["btn_soft_hover"]};
            border-color: {c["border_input_hover"]};
        }}

        #editor_view_root QPushButton[softAction="true"] {{
            min-height: 30px;
        }}
        #editor_view_root QPushButton[editorToolButton="true"] {{
            min-width: 0px;
            min-height: 28px;
            padding: 7px 10px;
        }}
        /* Font size 입력창: 기존 28px + 5px */
        #editor_view_root QLineEdit#editor_font_size_input {{
            min-height: 33px;
            max-height: 33px;
            padding: 0px 6px;
        }}
        #editor_view_root QPushButton[fontEmphasisButton="true"] {{
            padding: 0px;
            margin: 0px;
            border-radius: 8px;
            font-family: Tahoma;
            font-size: 15px;
            font-weight: 500;
            background: {c["btn_soft_bg"]};
            border: 1px solid {c["btn_soft_border"]};
            color: {c["btn_soft_text"]};
        }}
        #editor_view_root QPushButton#editor_italic_button {{
            font-style: italic;
        }}
        #editor_view_root QPushButton#editor_bold_button {{
            font-weight: 700;
        }}
        #editor_view_root QPushButton[fontEmphasisButton="true"]:hover {{
            background: {c["btn_soft_hover"]};
            border-color: {c["border_input_hover"]};
        }}
        #editor_view_root QPushButton[fontEmphasisButton="true"]:checked {{
            background: {c["btn_soft_checked_bg"]};
            border-color: {c["btn_soft_checked_border"]};
        }}
        #editor_copy_action_button,
        #editor_paste_action_button,
        #editor_delete_action_button,
        #editor_clear_masks_button {{
            min-height: 32px;
        }}
        #editor_view_root QPushButton#editor_recognize_button[softAction="true"],
        #editor_view_root QPushButton#editor_translate_button[softAction="true"] {{
            min-height: 22px;
            padding: 7px 12px;
        }}
        #editor_apply_button {{
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                                        stop:0 {c["cta_gradient_start"]}, stop:1 {c["cta_gradient_end"]});
            border: 1px solid {c["cta_border"]};
            color: {c["cta_text"]};
            border-radius: 12px;
            font-size: 12px;
            font-weight: 600;
        }}
        #editor_apply_button:hover {{
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                                        stop:0 {c["cta_hover_start"]}, stop:1 {c["cta_hover_end"]});
        }}
        #editor_apply_button:pressed {{
            background: {c["btn_primary_pressed"]};
        }}

        #editor_center_panel {{
            background: {c["bg_canvas_overlay"]};
            border: 1px solid {c["border_card"]};
            border-radius: 0px;
        }}
        QGraphicsView#editor_graphics_view {{
            background: {c["bg_canvas"]};
            border: 1px solid {c["border_subtle"]};
            border-radius: 0px;
        }}
        QGraphicsView#editor_graphics_view:focus {{
            border-color: {c["border_input_focus"]};
        }}

        #editor_right_panel {{
            background: {c["bg_sidebar"]};
            border-left: 1px solid {c["border_sidebar"]};
        }}
        #editor_file_actions {{
            background: transparent;
        }}
        {build_file_list_stylesheet(
            c,
            ("#editor_file_list", "#editor_region_list"),
            file_item_selectors=("#editor_file_list",),
            mark_json_status=True,
        )}

    """


def editor_tokens() -> dict[str, str]:
    colors = get_current_theme_colors()
    return {
        **colors,
        "fg": colors["text_primary"],
        "fg_dim": colors["text_page_subtitle"],
        "fg_bright": colors["text_page_title"],
        "accent": colors["divider_accent_start"],
        "card_bg": colors["bg_desc_panel"],
        "card_border": colors["desc_panel_border"],
        "editor_bg": colors["bg_text_edit"],
        "editor_border": colors["border_input_focus"],
        "table_bg": colors["bg_list"],
        "table_border": colors["border_list"],
        "table_alt_bg": colors["bg_surface_soft"],
        "table_grid": colors["divider_sub_line"],
        "table_header_bg": colors["bg_toolbar"],
        "selection_bg": colors["list_item_selected"],
        "selection_fg": colors["list_item_selected_text"],
        "menu_hover_bg": colors["tab_hover"],
        "status_success": colors.get("success_color", "#10B981"),
        "status_error": colors.get("danger_bg", "#EF4444"),
    }


def monospace_font(size: int = 11) -> QFont:
    font = QFont("Consolas", size)
    font.setStyleHint(QFont.StyleHint.Monospace)
    return font


def secondary_editor_dialog_stylesheet(*, include_tables: bool = True) -> str:
    t = editor_tokens()
    table_css = table_stylesheet(editable=True, scoped=False) if include_tables else ""
    return f"""
        QDialog {{
            background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                                        stop:0 {t["bg_gradient_start"]},
                                        stop:0.55 {t["bg_gradient_mid"]},
                                        stop:1 {t["bg_gradient_end"]});
        }}

        QLabel {{
            color: {t["fg"]};
            background: transparent;
        }}

        QLabel#dialog_title {{
            color: {t["fg_bright"]};
            font-size: 16px;
            font-weight: 600;
        }}

        QLabel#dialog_subtitle {{
            color: {t["fg_dim"]};
            font-size: 12px;
        }}

        QLabel#dialog_prompt {{
            color: {t["fg_dim"]};
            font-size: 12px;
        }}

        QLabel#section_label {{
            color: {t["fg_bright"]};
            font-size: 13px;
            font-weight: 600;
            padding: 4px 0 2px 0;
        }}

        QLabel#hint_label {{
            color: {t["fg_dim"]};
            font-size: 12px;
            padding: 2px 0;
        }}

        QLabel#null_value_label {{
            color: {t["fg_dim"]};
            background: {t["bg_surface_soft"]};
            border: 1px solid {t["border_input"]};
            border-radius: 8px;
            padding: 7px 10px;
        }}

        QLabel#status_label[statusState="default"] {{
            color: {t["fg_dim"]};
        }}

        QLabel#status_label[statusState="success"] {{
            color: {t["status_success"]};
        }}

        QLabel#status_label[statusState="error"] {{
            color: {t["status_error"]};
        }}

        QFrame#divider {{
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                                        stop:0 {t["divider_line_start"]},
                                        stop:1 {t["divider_line_end"]});
            max-height: 1px;
            border: none;
        }}

        QWidget#section_card,
        QWidget#dialog_card,
        QWidget#params_card,
        QWidget#path_card {{
            background: {t["card_bg"]};
            border: 1px solid {t["card_border"]};
            border-radius: 16px;
        }}

        QWidget#param_row {{
            background: {t["bg_surface_soft"]};
            border: 1px solid {t["border_subtle"]};
            border-radius: 12px;
        }}

        QWidget#section_content,
        QWidget#editor_scroll_content {{
            background: transparent;
        }}

        {build_input_controls_stylesheet(
            t,
            controls=("QLineEdit", "QTextEdit", "QPlainTextEdit", "QComboBox", "QSpinBox", "QDoubleSpinBox"),
            text_color_key="fg",
            selection_bg_key="dropdown_selection",
            selection_text_key="selection_fg",
        )}

        QPlainTextEdit {{
            background: {t["editor_bg"]};
            border: 1px solid {t["border_settings_input"]};
            border-radius: 12px;
            color: {t["fg"]};
            padding: 10px;
            selection-background-color: {t["dropdown_selection"]};
            selection-color: {t["selection_fg"]};
        }}

        QScrollArea,
        QScrollArea#editor_scroll {{
            border: none;
            background: transparent;
        }}

        QTabWidget::pane {{
            border: none;
            background: transparent;
            padding: 0px;
        }}

        QTabBar::tab {{
            background: transparent;
            border: none;
            border-radius: 8px;
            color: {t["fg_dim"]};
            padding: 6px 14px;
            margin: 2px 3px;
            font-size: 12px;
            font-weight: 500;
        }}

        QTabBar::tab:selected {{
            background: {t["nav_checked_bg"]};
            color: {t["fg_bright"]};
            font-weight: 600;
        }}

        QTabBar::tab:hover:!selected {{
            background: {t["nav_hover_bg"]};
            color: {t["fg"]};
        }}

        {build_menu_stylesheet(
            t,
            bg_key="bg_dropdown",
            border_key="border_input",
            text_color_key="fg",
            selected_bg_key="menu_hover_bg",
            selected_text_key="fg_bright",
            item_padding="7px 16px",
            include_separator=True,
        )}

        {build_tooltip_stylesheet(t)}
        {build_shared_button_stylesheet(t)}

        QPushButton {{
            min-height: 34px;
            border-radius: 10px;
            padding: 6px 14px;
            font-size: 12px;
            font-weight: 500;
        }}

        {build_section_icon_button_stylesheet(t)}

        QPushButton#add_section_button {{
            border-style: dashed;
            padding-left: 20px;
            padding-right: 20px;
        }}

        QLabel#shortcut_key {{
            color: {t["fg_bright"]};
            background: {t["bg_surface_soft"]};
            border: 1px solid {t["border_subtle"]};
            border-radius: 6px;
            padding: 3px 8px;
            font-size: 12px;
            font-weight: 600;
        }}

        QLabel#shortcut_desc {{
            color: {t["fg"]};
            font-size: 12px;
            padding: 2px 0;
        }}

        QLabel#shortcut_note {{
            color: {t["fg_dim"]};
            background: {t["bg_surface_soft"]};
            border: 1px solid {t["border_subtle"]};
            border-radius: 10px;
            padding: 10px 12px;
            font-size: 12px;
        }}

        QCheckBox {{
            color: {t["fg"]};
            spacing: 8px;
            font-size: 13px;
            background: transparent;
        }}
        QCheckBox:disabled {{
            color: {t["fg_dim"]};
        }}
        QCheckBox::indicator {{
            width: 18px;
            height: 18px;
            border-radius: 4px;
            border: 1px solid {t["checkbox_border"]};
            background: {t["checkbox_bg"]};
        }}
        QCheckBox::indicator:checked {{
            background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                                        stop:0 {t["checkbox_checked_start"]}, stop:1 {t["checkbox_checked_end"]});
            border-color: {t["checkbox_checked_border"]};
        }}
        QCheckBox::indicator:hover {{
            border-color: {t["checkbox_hover_border"]};
        }}
        QCheckBox::indicator:disabled {{
            background: {t["btn_disabled_bg"]};
            border-color: {t["btn_disabled_border"]};
        }}

        {table_css}
    """


def section_label_stylesheet() -> str:
    t = editor_tokens()
    return (
        f"color: {t['fg_bright']}; font-size: 13px; font-weight: 600; "
        "padding: 4px 0 2px 0; background: transparent;"
    )


def dim_label_stylesheet() -> str:
    t = editor_tokens()
    return f"color: {t['fg_dim']}; font-size: 12px; background: transparent;"


def body_label_stylesheet() -> str:
    t = editor_tokens()
    return f"color: {t['fg']}; font-size: 12px; background: transparent; padding: 2px 0;"


def divider_stylesheet() -> str:
    t = editor_tokens()
    return (
        "background: qlineargradient(x1:0,y1:0,x2:1,y2:0,"
        f"stop:0 {t['divider_line_start']}, stop:1 {t['divider_line_end']});"
        "max-height: 1px; border: none;"
    )


def prompt_card_stylesheet() -> str:
    t = editor_tokens()
    return f"""
        #prompt_preview_card {{
            background: {t["card_bg"]};
            border: 1px solid {t["card_border"]};
            border-radius: 16px;
        }}
    """


def title_stylesheet(size: int) -> str:
    t = editor_tokens()
    return f"color: {t['fg_bright']}; font-size: {size}px; font-weight: 600; background: transparent;"


def table_stylesheet(editable: bool = False, *, scoped: bool = True, border_radius: int = 12) -> str:
    t = editor_tokens()
    del scoped
    selector = "QTableWidget, QTableView"
    editor_css = ""
    if editable:
        editor_css = f"""
            {selector} QLineEdit {{
                background: {t["bg_input_focus"]};
                color: {t["fg"]};
                border: 1px solid {t["editor_border"]};
                border-radius: 6px;
                padding: 2px 6px;
                font-size: 12px;
            }}
        """
    square_css = ""
    if border_radius <= 0:
        square_css = f"""
            {selector} QHeaderView::section,
            QHeaderView::section {{
                border-radius: 0px;
            }}
            {selector} QTableCornerButton::section {{
                border: none;
                border-radius: 0px;
                background: {t["table_header_bg"]};
                border-bottom: 1px solid {t["table_border"]};
            }}
            {selector} QWidget#qt_scrollarea_viewport {{
                border: none;
                border-radius: 0px;
            }}
        """
    return f"""
        {selector} {{
            background: {t["table_bg"]};
            border: 1px solid {t["table_border"]};
            border-radius: {max(0, border_radius)}px;
            color: {t["fg"]};
            gridline-color: {t["table_grid"]};
            font-size: 12px;
        }}
        {selector}::item {{
            padding: 6px 10px;
        }}
        {selector}::item:alternate {{
            background: {t["table_alt_bg"]};
        }}
        {selector}::item:selected {{
            background: {t["selection_bg"]};
            color: {t["selection_fg"]};
        }}
        {selector} QHeaderView::section,
        QHeaderView::section {{
            background: {t["table_header_bg"]};
            color: {t["fg_bright"]};
            font-weight: 600;
            font-size: 11px;
            padding: 7px 10px;
            border: none;
            border-bottom: 1px solid {t["table_border"]};
        }}
        {editor_css}
        {square_css}
    """


def tabs_stylesheet() -> str:
    t = editor_tokens()
    return f"""
        QTabWidget::pane {{
            border: none;
            background: transparent;
        }}
        QTabBar::tab {{
            background: transparent;
            border: none;
            border-radius: 8px;
            color: {t["fg_dim"]};
            padding: 6px 14px;
            margin: 2px 3px;
            font-size: 12px;
            font-weight: 500;
        }}
        QTabBar::tab:selected {{
            background: {t["nav_checked_bg"]};
            color: {t["fg_bright"]};
            font-weight: 600;
        }}
        QTabBar::tab:hover:!selected {{
            background: {t["nav_hover_bg"]};
            color: {t["fg"]};
        }}
    """


def text_edit_stylesheet() -> str:
    t = editor_tokens()
    return f"""
        QPlainTextEdit {{
            background: {t["editor_bg"]};
            border: 1px solid {t["border_settings_input"]};
            border-radius: 12px;
            color: {t["fg"]};
            padding: 10px;
            selection-background-color: {t["selection_bg"]};
            selection-color: {t["selection_fg"]};
        }}
        QPlainTextEdit:hover {{
            border-color: {t["border_input_hover"]};
        }}
        QPlainTextEdit:focus {{
            border-color: {t["border_input_focus"]};
            background: {t["bg_input_focus"]};
        }}
    """


def line_edit_stylesheet() -> str:
    t = editor_tokens()
    return build_input_controls_stylesheet(
        t,
        controls=("QLineEdit",),
        border_key="border_settings_input",
        text_color_key="fg",
        min_height="20px",
        include_combo_popup=False,
    )


def add_section_button_stylesheet() -> str:
    t = editor_tokens()
    return f"""
        QPushButton {{
            background: {t["btn_chip_bg"]};
            border: 1px dashed {t["btn_chip_border"]};
            border-radius: 10px;
            color: {t["accent"]};
            padding: 10px 20px;
            font-weight: 600;
            font-size: 13px;
        }}
        QPushButton:hover {{
            background: {t["btn_chip_hover"]};
            border-color: {t["border_tab_selected"]};
            color: {t["fg_bright"]};
        }}
    """


def menu_stylesheet() -> str:
    t = editor_tokens()
    return build_menu_stylesheet(
        t,
        bg_key="bg_dropdown",
        border_key="border_input",
        text_color_key="fg",
        selected_bg_key="menu_hover_bg",
        selected_text_key="fg_bright",
        item_padding="8px 20px",
    ) + """
        QMenu::item {
            background-color: transparent;
            font-size: 13px;
        }
    """


def status_stylesheet(kind: str) -> str:
    t = editor_tokens()
    color = t["fg_dim"]
    if kind == "success":
        color = t["status_success"]
    elif kind == "error":
        color = t["status_error"]
    return f"color: {color}; font-size: 12px; background: transparent;"


def model_selector_dialog_stylesheet() -> str:
    return """
        QLabel#promptLabel {
            font-size: 13px;
            font-weight: 700;
        }
        QLineEdit#searchInput {
            min-height: 34px;
            padding: 7px 12px;
        }
        QListWidget#modelList {
            padding: 6px;
        }
        QListWidget#modelList::item {
            min-height: 30px;
            padding: 6px 10px;
        }
    """


def color_dialog_stylesheet() -> str:
    c = get_current_theme_colors()
    return f"""
        QColorDialog {{
            background: {c["bg_panel"]};
        }}
        QColorDialog QWidget {{
            color: {c["text_primary"]};
            font-size: 12px;
        }}
        QColorDialog QLabel {{
            color: {c["text_secondary"]};
        }}
        {build_input_controls_stylesheet(
            c,
            "QColorDialog",
            controls=("QLineEdit", "QSpinBox", "QDoubleSpinBox", "QComboBox"),
            radius="8px",
            padding="6px 8px",
            min_height="18px",
        )}
        QColorDialog QPushButton,
        QColorDialog QToolButton {{
            border-radius: 8px;
            padding: 6px 10px;
            font-weight: 700;
        }}
        QColorDialog QDialogButtonBox QPushButton {{
            min-width: 72px;
        }}
    """


def _message_dialog_tokens() -> dict[str, str]:
    colors = get_current_theme_colors()
    return {
        **colors,
        "bg_dialog": colors["bg_dropdown"],
        "border": colors["border_input"],
        "fg": colors["text_primary"],
        "fg_muted": colors["text_muted"],
        "soft_bg": colors["btn_soft_bg"],
        "soft_hover": colors["btn_soft_hover"],
        "soft_pressed": colors["btn_soft_pressed"],
        "soft_border": colors["btn_soft_border"],
        "soft_text": colors["btn_soft_text"],
        "primary_bg": colors["btn_primary_bg"],
        "primary_hover": colors["btn_primary_hover"],
        "primary_pressed": colors["btn_primary_pressed"],
        "primary_border": colors["btn_primary_border"],
        "primary_text": colors["btn_primary_text"],
    }


def _framed_dialog_chrome_stylesheet(tokens: dict[str, str], container_selector: str) -> str:
    return f"""
        {container_selector} {{
            background: {tokens["bg_dialog"]};
            border: 1px solid {tokens["border"]};
            border-radius: 14px;
        }}
        {container_selector} QWidget#dialogHeader {{
            background: transparent;
        }}
        {container_selector} QLabel#dialogWindowTitle {{
            color: {tokens["fg"]};
            font-family: "Microsoft YaHei UI", "Segoe UI", sans-serif;
            font-size: 12px;
            font-weight: 600;
        }}
        {container_selector} QToolButton#dialogCloseButton {{
            background: transparent;
            border: none;
            border-radius: 8px;
            color: {tokens["fg_muted"]};
            font-size: 16px;
            font-weight: 600;
            min-width: 28px;
            min-height: 28px;
            padding: 0;
        }}
        {container_selector} QToolButton#dialogCloseButton:hover {{
            background: {tokens["soft_bg"]};
            color: {tokens["fg"]};
        }}
        {container_selector} QToolButton#dialogCloseButton:pressed {{
            background: {tokens["soft_pressed"]};
        }}
    """


def _dialog_soft_button_stylesheet(
    tokens: dict[str, str],
    selector: str,
    *,
    min_width: str,
    min_height: str,
    padding: str,
    font_weight: str,
) -> str:
    return f"""
        {selector} {{
            min-width: {min_width};
            min-height: {min_height};
            border-radius: 8px;
            padding: {padding};
            font-family: "Microsoft YaHei UI", "Segoe UI", sans-serif;
            font-size: 12px;
            font-weight: {font_weight};
            background: {tokens["soft_bg"]};
            border: 1px solid {tokens["soft_border"]};
            color: {tokens["soft_text"]};
        }}
        {selector}:hover {{
            background: {tokens["soft_hover"]};
            border-color: {tokens["border"]};
        }}
        {selector}:pressed {{
            background: {tokens["soft_pressed"]};
        }}
    """


def error_dialog_stylesheet() -> str:
    t = _message_dialog_tokens()
    return f"""
        QFrame#errorDialogContainer QLabel {{
            background: transparent;
            color: {t["fg"]};
            font-family: "Microsoft YaHei UI", "Segoe UI", sans-serif;
            font-size: 12px;
        }}
        {_framed_dialog_chrome_stylesheet(t, "QFrame#errorDialogContainer")}
        QFrame#errorDialogContainer QLabel#errorDialogTitle {{
            color: {t["fg"]};
            font-size: 13px;
            font-weight: 700;
        }}
        QFrame#errorDialogContainer QLabel#dialogIcon {{
            background: transparent;
        }}
        QFrame#errorDialogContainer QScrollArea#errorDialogScroll {{
            background: transparent;
            border: none;
        }}
        QFrame#errorDialogContainer QWidget#qt_scrollarea_viewport,
        QFrame#errorDialogContainer QScrollArea#errorDialogScroll > QWidget > QWidget {{
            background: transparent;
        }}
        QFrame#errorDialogContainer QLabel#errorDialogDetails {{
            background: transparent;
            color: {t["fg"]};
            border: none;
            font-family: "Microsoft YaHei UI", "Segoe UI", sans-serif;
            font-size: 12px;
            padding: 0;
        }}
        QFrame#errorDialogContainer QLabel#errorDialogDetails a {{
            color: {t["primary_bg"]};
            text-decoration: underline;
        }}
        {_dialog_soft_button_stylesheet(
            t,
            "QFrame#errorDialogContainer QDialogButtonBox QPushButton",
            min_width="88px",
            min_height="34px",
            padding="6px 14px",
            font_weight="600",
        )}
        QFrame#errorDialogContainer QDialogButtonBox QPushButton[dialogDefault="true"] {{
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                                        stop:0 {t["cta_gradient_start"]}, stop:1 {t["cta_gradient_end"]});
            border: 1px solid {t["cta_border"]};
            color: {t["cta_text"]};
        }}
        QFrame#errorDialogContainer QDialogButtonBox QPushButton[dialogDefault="true"]:hover {{
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                                        stop:0 {t["cta_hover_start"]}, stop:1 {t["cta_hover_end"]});
            border-color: {t["cta_border"]};
        }}
        QFrame#errorDialogContainer QDialogButtonBox QPushButton[dialogDefault="true"]:pressed {{
            background: {t["primary_pressed"]};
        }}
    """


def progress_dialog_stylesheet() -> str:
    t = _message_dialog_tokens()
    return f"""
        {_framed_dialog_chrome_stylesheet(t, "QFrame#progressDialogContainer")}
        QFrame#progressDialogContainer QLabel#progressDialogLabel {{
            background: transparent;
            color: {t["fg"]};
            font-family: "Microsoft YaHei UI", "Segoe UI", sans-serif;
            font-size: 12px;
            line-height: 1.4;
        }}
        QFrame#progressDialogContainer QProgressBar#progressDialogBar {{
            border: none;
            background: {t["border"]};
            height: 6px;
            border-radius: 3px;
        }}
        QFrame#progressDialogContainer QProgressBar#progressDialogBar::chunk {{
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                                        stop:0 {t["cta_gradient_start"]}, stop:1 {t["cta_gradient_end"]});
            border-radius: 3px;
        }}
        {_dialog_soft_button_stylesheet(
            t,
            "QFrame#progressDialogContainer QPushButton#progressDialogCancelButton",
            min_width="80px",
            min_height="28px",
            padding="4px 12px",
            font_weight="500",
        )}
    """
