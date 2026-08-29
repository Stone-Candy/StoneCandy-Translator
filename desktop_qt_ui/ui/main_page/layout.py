import copy
import json
import logging
import os
import shutil
import sys
import time

from PyQt6.QtCore import QEvent, QObject, Qt
from PyQt6.QtGui import QBrush, QColor, QImage, QPixmap
from PyQt6.QtWidgets import (
    QButtonGroup,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QSplitter,
    QStackedWidget,
    QStyle,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)
from PIL import Image, ImageDraw, ImageFont
from utils.resource_helper import resource_path
from ui.widgets.wheel_filter import NoWheelComboBox as QComboBox
from ui.widgets.two_line_combo import TwoLineComboBox
from ui.widgets.file_list_view import FileListView
from ui.widgets.hover_hint import set_hover_hint

from ui.theme import THEME_OPTIONS, get_current_theme_colors, malgun_gothic_bold_font
from manga_translator.api_key_rotation import (
    get_api_status_snapshot,
    get_indexed_env_key,
    get_rotation_slot_count,
)
from manga_translator.utils.openai_compat import is_openai_api_key_optional


SIDEBAR_API_SPECS = {
    "translator_openai": ("label_translator", "translator", "openai", "OPENAI_API_KEY", "OPENAI_MODEL", "OPENAI_API_BASE", "", "", ""),
    "translator_gemini": ("label_translator", "translator", "gemini", "GEMINI_API_KEY", "GEMINI_MODEL", "GEMINI_API_BASE", "", "", ""),
    "ocr_openai": ("label_ocr", "ocr", "openai", "OCR_OPENAI_API_KEY", "OCR_OPENAI_MODEL", "OCR_OPENAI_API_BASE", "OPENAI_API_KEY", "", "OPENAI_API_BASE"),
    "ocr_gemini": ("label_ocr", "ocr", "gemini", "OCR_GEMINI_API_KEY", "OCR_GEMINI_MODEL", "OCR_GEMINI_API_BASE", "GEMINI_API_KEY", "", "GEMINI_API_BASE"),
    "color_openai": ("label_colorizer", "colorizer", "openai", "COLOR_OPENAI_API_KEY", "COLOR_OPENAI_MODEL", "COLOR_OPENAI_API_BASE", "OPENAI_API_KEY", "", "OPENAI_API_BASE"),
    "color_gemini": ("label_colorizer", "colorizer", "gemini", "COLOR_GEMINI_API_KEY", "COLOR_GEMINI_MODEL", "COLOR_GEMINI_API_BASE", "GEMINI_API_KEY", "", "GEMINI_API_BASE"),
    "render_openai": ("label_renderer", "renderer", "openai", "RENDER_OPENAI_API_KEY", "RENDER_OPENAI_MODEL", "RENDER_OPENAI_API_BASE", "OPENAI_API_KEY", "", "OPENAI_API_BASE"),
    "render_gemini": ("label_renderer", "renderer", "gemini", "RENDER_GEMINI_API_KEY", "RENDER_GEMINI_MODEL", "RENDER_GEMINI_API_BASE", "GEMINI_API_KEY", "", "GEMINI_API_BASE"),
}


def _cfg_value(value) -> str:
    return str(getattr(value, "value", value) or "").strip()


def _active_sidebar_api_specs(config) -> list[tuple]:
    keys: list[str] = []
    translator = _cfg_value(getattr(config.translator, "translator", ""))
    if translator in {"openai", "openai_hq"}:
        keys.append("translator_openai")
    elif translator in {"gemini", "gemini_hq"}:
        keys.append("translator_gemini")

    ocr_values = [_cfg_value(getattr(config.ocr, "ocr", ""))]
    if bool(getattr(config.ocr, "use_hybrid_ocr", False)):
        ocr_values.append(_cfg_value(getattr(config.ocr, "secondary_ocr", "")))
    for override_name in ("novelai_ocr", "novelai_secondary_ocr"):
        override_value = _cfg_value(getattr(config.ocr, override_name, "none"))
        if override_value and override_value.lower() != "none":
            ocr_values.append(override_value)
    if "openai_ocr" in ocr_values:
        keys.append("ocr_openai")
    if "gemini_ocr" in ocr_values:
        keys.append("ocr_gemini")

    colorizer = _cfg_value(getattr(config.colorizer, "colorizer", ""))
    if colorizer == "openai_colorizer":
        keys.append("color_openai")
    elif colorizer == "gemini_colorizer":
        keys.append("color_gemini")

    renderer = _cfg_value(getattr(config.render, "renderer", ""))
    if renderer == "openai_renderer":
        keys.append("render_openai")
    elif renderer == "gemini_renderer":
        keys.append("render_gemini")

    return [SIDEBAR_API_SPECS[key] for key in keys]


def _sidebar_provider_label(provider: str) -> str:
    return {
        "openai": "OpenAI",
        "gemini": "Gemini",
    }.get(str(provider or "").lower(), str(provider or ""))

def _resolve_settings_tab_layout_file() -> str:
    """打包/开发环境通用地定位 settings_tab_layout.json。

    Why: 打包后 __file__ 落在 PYZ 归档里，dirname() 算不出真实路径；
    GitHub Action 把 desktop_qt_ui/ui 复制到 _internal/desktop_qt_ui/ui/。
    """
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return os.path.join(sys._MEIPASS, "desktop_qt_ui", "ui", "main_page", "settings_tab_layout.json")
    return os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "settings_tab_layout.json",
    )


_SETTINGS_TAB_LAYOUT_FILE = _resolve_settings_tab_layout_file()

_PROMPT_EXTENSIONS = (".yaml", ".yml", ".json")
_FONT_EXTENSIONS = (".ttf", ".otf", ".ttc")
_CURRENT_ASSET_PREFIX = "✓ "
_FONT_PREVIEW_PIXMAP_CACHE = {}


def _fallback_settings_tab_layout():
    """JSON 缺失时使用的当前菜单布局默认值。"""
    try:
        from ui.main_page.settings_tab_layout_default import DEFAULT_SETTINGS_TAB_LAYOUT
        return copy.deepcopy(DEFAULT_SETTINGS_TAB_LAYOUT)
    except Exception as exc:
        logging.getLogger(__name__).warning("기본 설정 탭 레이아웃 로드 실패: %s", exc)
        return []


def _load_reclassify_settings_layout():
    """从 ui/main_page/settings_tab_layout.json 加载设置页分类排序布局。"""
    try:
        with open(_SETTINGS_TAB_LAYOUT_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        tabs = data.get("tabs", [])
        if tabs:
            return tabs
    except Exception as exc:
        logging.getLogger(__name__).warning(
            "加载 settings_tab_layout.json 失败 (%s): %s", _SETTINGS_TAB_LAYOUT_FILE, exc
        )
    return _fallback_settings_tab_layout()


def _font_preview_style(size: int) -> str:
    """字体预览文本回退样式。正常预览会直接渲染为 pixmap。"""
    text_color = get_current_theme_colors()["text_primary"]
    return f"font-size: {size}pt; color: {text_color};"


def _render_font_preview_pixmap(font_path: str | None, text: str, size: int) -> QPixmap | None:
    """Render preview text directly from the font file without Qt family matching."""
    if not font_path or not os.path.isfile(font_path):
        return None

    norm_path = os.path.normpath(font_path)
    text_color = get_current_theme_colors()["text_primary"]
    try:
        mtime = os.path.getmtime(norm_path)
    except OSError:
        mtime = 0.0
    cache_key = (norm_path, mtime, text, int(size), text_color)
    cached = _FONT_PREVIEW_PIXMAP_CACHE.get(cache_key)
    if cached is not None:
        return QPixmap(cached)

    try:
        font = ImageFont.truetype(norm_path, int(max(size, 1)))
    except Exception:
        return None

    lines = str(text or " ").splitlines() or [" "]
    probe = Image.new("RGBA", (1, 1), (0, 0, 0, 0))
    draw = ImageDraw.Draw(probe)
    try:
        ascent, descent = font.getmetrics()
    except Exception:
        ascent, descent = int(size), int(size * 0.25)
    line_gap = max(2, int(round(size * 0.18)))
    line_height = max(1, ascent + descent + line_gap)
    bboxes = []
    max_width = 1
    for line in lines:
        content = line or " "
        try:
            bbox = draw.textbbox((0, 0), content, font=font)
        except Exception:
            bbox = (0, 0, int(size * max(len(content), 1)), line_height)
        left, top, right, bottom = bbox
        max_width = max(max_width, right - left)
        bboxes.append((content, left, top, right, bottom))

    margin = max(4, int(round(size * 0.2)))
    width = max(1, max_width + margin * 2)
    height = max(1, line_height * len(lines) + margin * 2)
    width = max(1, min(width, 4096))
    height = max(1, min(height, 2048))

    qcolor = QColor(text_color)
    fill = (
        qcolor.red() if qcolor.isValid() else 31,
        qcolor.green() if qcolor.isValid() else 41,
        qcolor.blue() if qcolor.isValid() else 51,
        qcolor.alpha() if qcolor.isValid() else 255,
    )
    image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    y = margin
    for content, left, top, _right, _bottom in bboxes:
        draw.text((margin - left, y - top), content, font=font, fill=fill)
        y += line_height

    raw_data = image.tobytes("raw", "RGBA")
    qimage = QImage(raw_data, width, height, QImage.Format.Format_RGBA8888).copy()
    pixmap = QPixmap.fromImage(qimage)
    if len(_FONT_PREVIEW_PIXMAP_CACHE) >= 128:
        _FONT_PREVIEW_PIXMAP_CACHE.clear()
    _FONT_PREVIEW_PIXMAP_CACHE[cache_key] = QPixmap(pixmap)
    return pixmap


def refresh_font_preview_styles(self):
    """主题变化后刷新字体预览区域颜色。"""
    current_item = self.font_list_widget.currentItem() if hasattr(self, "font_list_widget") else None
    _on_font_selection_changed(self, current_item, None)


def _set_prompt_status(self, translation_key: str, **kwargs):
    if hasattr(self, "prompt_status_label"):
        self.prompt_status_label.setText(self._t(translation_key, **kwargs))


def _set_font_status(self, translation_key: str, **kwargs):
    if hasattr(self, "font_status_label"):
        self.font_status_label.setText(self._t(translation_key, **kwargs))


def _normalize_asset_filename(path_or_name: str | None) -> str:
    if not path_or_name:
        return ""
    return os.path.basename(str(path_or_name).replace("\\", "/").rstrip("/"))


def _get_asset_item_filename(item: QListWidgetItem | None) -> str:
    if not item:
        return ""
    raw_value = item.data(Qt.ItemDataRole.UserRole)
    if isinstance(raw_value, str) and raw_value.strip():
        return raw_value.strip()
    text = item.text().strip()
    if text.startswith(_CURRENT_ASSET_PREFIX):
        return text[len(_CURRENT_ASSET_PREFIX):].strip()
    return text


def _find_asset_item(list_widget: QListWidget, filename: str) -> QListWidgetItem | None:
    if not filename:
        return None
    for index in range(list_widget.count()):
        item = list_widget.item(index)
        if _get_asset_item_filename(item) == filename:
            return item
    return None


def _create_asset_list_item(self, filename: str, *, is_current: bool, tooltip_text: str | None = None) -> QListWidgetItem:
    item = QListWidgetItem(filename)
    item.setData(Qt.ItemDataRole.UserRole, filename)
    if is_current:
        item.setText(f"{_CURRENT_ASSET_PREFIX}{filename}")
        font = item.font()
        font.setBold(True)
        item.setFont(font)
        success_color = get_current_theme_colors().get("success_color")
        if success_color:
            item.setForeground(QBrush(QColor(success_color)))
        if tooltip_text:
            item.setToolTip(tooltip_text)
    return item


def _sanitize_file_stem(name: str) -> str:
    return "".join(c for c in name if c.isalnum() or c in ("_", "-", ".", " ")).strip()


def _normalize_prompt_filename(name: str, default_extension: str = ".yaml") -> str:
    safe_name = _sanitize_file_stem(name)
    if not safe_name:
        return ""

    stem, ext = os.path.splitext(safe_name)
    if ext and ext.lower() not in _PROMPT_EXTENSIONS:
        safe_name = stem
        stem, ext = os.path.splitext(safe_name)

    if ext.lower() not in _PROMPT_EXTENSIONS:
        safe_name = f"{safe_name}{default_extension}"

    final_stem = os.path.splitext(safe_name)[0].strip()
    if not final_stem:
        return ""
    return safe_name


SIDEBAR_LOGO_HEIGHT = 169
SIDEBAR_LOGO_PADDING = 1
SIDEBAR_LOGO_BOTTOM_MARGIN = 18
SIDEBAR_LOGO_RELATIVE_PATH = os.path.join("desktop_qt_ui", "ui", "icons", "sidebar_logo.png")
NAV_SELECTED_PREFIX = "> "


class _SidebarLogoClickFilter(QObject):
    def __init__(self, callback, parent=None):
        super().__init__(parent)
        self._callback = callback

    def eventFilter(self, obj, event):
        if (
            event.type() == QEvent.Type.MouseButtonRelease
            and event.button() == Qt.MouseButton.LeftButton
        ):
            self._callback()
            return True
        return False


def update_nav_button_labels(self):
    buttons = getattr(self, "page_nav_buttons", None)
    if not buttons:
        return
    for button in buttons.values():
        key = button.property("navTextKey")
        if not key:
            continue
        label = self._t(key)
        if button.isChecked():
            button.setText(f"{NAV_SELECTED_PREFIX}{label}")
        else:
            button.setText(label)


def create_left_sidebar(self) -> QWidget:
    sidebar = QWidget()
    sidebar.setObjectName("sidebar_panel")
    sidebar.setMinimumWidth(210)
    sidebar.setMaximumWidth(260)
    sidebar_layout = QVBoxLayout(sidebar)
    sidebar_layout.setContentsMargins(0, 0, 0, 0)
    sidebar_layout.setSpacing(0)

    logo_header = QWidget()
    logo_header.setObjectName("sidebar_logo_header")
    logo_header.setFixedHeight(SIDEBAR_LOGO_HEIGHT)
    logo_header_layout = QVBoxLayout(logo_header)
    logo_header_layout.setContentsMargins(
        SIDEBAR_LOGO_PADDING,
        SIDEBAR_LOGO_PADDING,
        SIDEBAR_LOGO_PADDING,
        SIDEBAR_LOGO_PADDING,
    )
    logo_header_layout.setSpacing(0)

    self.sidebar_logo_label = QLabel()
    self.sidebar_logo_label.setObjectName("sidebar_logo")
    self.sidebar_logo_label.setAlignment(
        Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom
    )
    self.sidebar_logo_label.setScaledContents(False)
    self.sidebar_logo_label.setSizePolicy(
        QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
    )
    logo_pixmap = QPixmap(resource_path(SIDEBAR_LOGO_RELATIVE_PATH))
    if not logo_pixmap.isNull():
        self.sidebar_logo_label.setPixmap(logo_pixmap)
    logo_header.setCursor(Qt.CursorShape.PointingHandCursor)
    self.sidebar_logo_label.setCursor(Qt.CursorShape.PointingHandCursor)
    self.sidebar_logo_label.setAttribute(
        Qt.WidgetAttribute.WA_TransparentForMouseEvents, True
    )
    self._sidebar_logo_click_filter = _SidebarLogoClickFilter(
        self._on_sidebar_logo_clicked, logo_header
    )
    logo_header.installEventFilter(self._sidebar_logo_click_filter)
    logo_header_layout.addWidget(self.sidebar_logo_label)
    sidebar_layout.addWidget(logo_header)

    nav_column = QWidget()
    nav_column.setObjectName("sidebar_nav_column")
    nav_layout = QVBoxLayout(nav_column)
    nav_layout.setContentsMargins(12, SIDEBAR_LOGO_BOTTOM_MARGIN, 12, 14)
    nav_layout.setSpacing(6)

    self.nav_translation_button = QPushButton(self._t("Select Translation Task"))
    self.nav_translation_button.setProperty("navButton", True)
    self.nav_translation_button.setProperty("navTextKey", "Select Translation Task")
    self.nav_translation_button.setCheckable(True)
    nav_layout.addWidget(self.nav_translation_button)

    self.nav_settings_button = QPushButton(self._t("Settings"))
    self.nav_settings_button.setProperty("navButton", True)
    self.nav_settings_button.setProperty("navTextKey", "Settings")
    self.nav_settings_button.setCheckable(True)
    nav_layout.addWidget(self.nav_settings_button)

    self.nav_env_button = QPushButton(self._t("API Management"))
    self.nav_env_button.setProperty("navButton", True)
    self.nav_env_button.setProperty("navTextKey", "API Management")
    self.nav_env_button.setCheckable(True)
    nav_layout.addWidget(self.nav_env_button)

    self.nav_prompt_button = QPushButton(self._t("Prompt Management"))
    self.nav_prompt_button.setProperty("navButton", True)
    self.nav_prompt_button.setProperty("navTextKey", "Prompt Management")
    self.nav_prompt_button.setCheckable(True)
    nav_layout.addWidget(self.nav_prompt_button)

    self.nav_font_button = QPushButton(self._t("Font Management"))
    self.nav_font_button.setProperty("navButton", True)
    self.nav_font_button.setProperty("navTextKey", "Font Management")
    self.nav_font_button.setCheckable(True)
    nav_layout.addWidget(self.nav_font_button)

    self.nav_replacements_button = QPushButton(self._t("Replacement Rules"))
    self.nav_replacements_button.setProperty("navButton", True)
    self.nav_replacements_button.setProperty("navTextKey", "Replacement Rules")
    self.nav_replacements_button.setCheckable(True)
    nav_layout.addWidget(self.nav_replacements_button)

    self.nav_batch_edit_button = QPushButton(self._t("Batch Management"))
    self.nav_batch_edit_button.setProperty("navButton", True)
    self.nav_batch_edit_button.setProperty("navTextKey", "Batch Management")
    self.nav_batch_edit_button.setCheckable(True)
    nav_layout.addWidget(self.nav_batch_edit_button)

    self.nav_folder_sync_button = QPushButton(self._t("Reset Folder Paths"))
    self.nav_folder_sync_button.setProperty("navButton", True)
    self.nav_folder_sync_button.setProperty("navTextKey", "Reset Folder Paths")
    self.nav_folder_sync_button.setCheckable(True)
    nav_layout.addWidget(self.nav_folder_sync_button)

    nav_layout.addStretch()

    self.sidebar_api_status_title = QLabel(self._t("API Status"))
    self.sidebar_api_status_title.setObjectName("sidebar_group_label")
    nav_layout.addWidget(self.sidebar_api_status_title)

    self.sidebar_api_status_scroll = QScrollArea()
    self.sidebar_api_status_scroll.setObjectName("sidebar_api_status_scroll")
    self.sidebar_api_status_scroll.setWidgetResizable(True)
    self.sidebar_api_status_scroll.setFrameShape(QFrame.Shape.NoFrame)
    self.sidebar_api_status_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    self.sidebar_api_status_scroll.setMinimumHeight(42)
    self.sidebar_api_status_scroll.setMaximumHeight(140)

    self.sidebar_api_status_label = QLabel("")
    self.sidebar_api_status_label.setObjectName("sidebar_api_status")
    self.sidebar_api_status_label.setWordWrap(True)
    self.sidebar_api_status_label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
    self.sidebar_api_status_scroll.setWidget(self.sidebar_api_status_label)
    nav_layout.addWidget(self.sidebar_api_status_scroll)

    self.nav_editor_button = QPushButton(self._t("Layout Editor"))
    self.nav_editor_button.setProperty("navActionButton", True)
    nav_layout.addWidget(self.nav_editor_button)
    sidebar_layout.addWidget(nav_column, 1)

    for button in [
        self.nav_translation_button,
        self.nav_settings_button,
        self.nav_env_button,
        self.nav_prompt_button,
        self.nav_font_button,
        self.nav_replacements_button,
        self.nav_batch_edit_button,
        self.nav_folder_sync_button,
        self.nav_editor_button,
    ]:
        button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        button.setAutoDefault(False)

    self.nav_button_group = QButtonGroup(self)
    self.nav_button_group.setExclusive(True)
    for button in [
        self.nav_translation_button,
        self.nav_settings_button,
        self.nav_env_button,
        self.nav_prompt_button,
        self.nav_font_button,
        self.nav_replacements_button,
        self.nav_batch_edit_button,
        self.nav_folder_sync_button,
    ]:
        self.nav_button_group.addButton(button)

    self.page_nav_buttons = {
        "translation": self.nav_translation_button,
        "settings": self.nav_settings_button,
        "env": self.nav_env_button,
        "prompts": self.nav_prompt_button,
        "fonts": self.nav_font_button,
        "replacements": self.nav_replacements_button,
        "batch_edit": self.nav_batch_edit_button,
        "folder_sync": self.nav_folder_sync_button,
    }

    self.nav_translation_button.clicked.connect(lambda: self._switch_content_page("translation"))
    self.nav_editor_button.clicked.connect(self._on_nav_editor_clicked)
    self.nav_settings_button.clicked.connect(lambda: self._switch_content_page("settings"))
    self.nav_env_button.clicked.connect(lambda: self._switch_content_page("env"))
    self.nav_prompt_button.clicked.connect(self._on_nav_prompt_clicked)
    self.nav_font_button.clicked.connect(self._on_nav_font_clicked)
    self.nav_replacements_button.clicked.connect(self._on_nav_replacements_clicked)
    self.nav_batch_edit_button.clicked.connect(self._on_nav_batch_edit_clicked)
    self.nav_folder_sync_button.clicked.connect(self._on_nav_folder_sync_clicked)

    self.nav_button_group.buttonToggled.connect(lambda *_: self._update_nav_button_labels())
    self.nav_translation_button.setChecked(True)
    self._update_nav_button_labels()
    return sidebar


def refresh_api_status_sidebar(self):
    if not hasattr(self, "sidebar_api_status_label"):
        return
    try:
        config = self.controller.config_service.get_config()
        env_vars = self.controller.config_service.load_env_vars()
        status_items = get_api_status_snapshot()
        active_specs = _active_sidebar_api_specs(config)
    except Exception:
        self.sidebar_api_status_label.setText(self._t("API status unavailable"))
        return

    if not active_specs:
        self.sidebar_api_status_label.setText(self._t("No API selected"))
        return

    def _latest_status_by_slot(feature: str, provider: str) -> dict[int, dict]:
        latest: dict[int, dict] = {}
        for item in status_items:
            if item.get("feature") != feature or item.get("provider") != provider:
                continue
            try:
                slot = int(item.get("slot") or 0)
            except (TypeError, ValueError):
                continue
            if slot <= 0:
                continue
            previous = latest.get(slot)
            if not previous or float(item.get("updated_at") or 0) >= float(previous.get("updated_at") or 0):
                latest[slot] = item
        return latest

    def _format_slot_list(slots: list[int]) -> str:
        return ", ".join(str(slot) for slot in slots)

    lines: list[str] = []
    for (
        label_key,
        feature,
        provider,
        api_key_env,
        model_env,
        api_base_env,
        fallback_api_key_env,
        fallback_model_env,
        fallback_api_base_env,
    ) in active_specs:
        label = f"{self._t(label_key)} ({_sidebar_provider_label(provider)})"
        slot_count = get_rotation_slot_count(
            env_vars,
            (
                api_key_env,
                model_env,
                api_base_env,
                fallback_api_key_env,
                fallback_model_env,
                fallback_api_base_env,
            ),
        )
        configured_slots: list[int] = []
        for index in range(1, slot_count + 1):
            key = get_indexed_env_key(api_key_env, index)
            fallback_key = get_indexed_env_key(fallback_api_key_env, index)
            base_key = get_indexed_env_key(api_base_env, index)
            fallback_base_key = get_indexed_env_key(fallback_api_base_env, index)
            has_api_key = bool(
                str(env_vars.get(key, "") or "").strip()
                or str(env_vars.get(fallback_key, "") or "").strip()
            )
            base_value = str(env_vars.get(base_key, "") or env_vars.get(fallback_base_key, "") or "").strip()
            if has_api_key or (provider == "openai" and is_openai_api_key_optional("", base_value)):
                configured_slots.append(index)

        latest_by_slot = _latest_status_by_slot(feature, provider)
        failed_slots: list[int] = []
        unavailable_slots: list[int] = []
        cooldown_slots: list[int] = []
        for slot in configured_slots:
            item = latest_by_slot.get(slot)
            if not item:
                continue
            state = item.get("state")
            if state == "unavailable":
                unavailable_slots.append(slot)
            elif state == "cooldown" and float(item.get("cooldown_until") or 0) > time.time():
                cooldown_slots.append(slot)
            elif state == "failed":
                failed_slots.append(slot)

        details: list[str] = []
        if failed_slots:
            details.append(self._t("API status detail failed", slots=_format_slot_list(failed_slots)))
        if unavailable_slots:
            details.append(self._t("API status detail unavailable", slots=_format_slot_list(unavailable_slots)))
        if cooldown_slots:
            details.append(self._t("API status detail cooldown", slots=_format_slot_list(cooldown_slots)))

        if details:
            lines.append(
                self._t(
                    "API status line with details",
                    label=label,
                    configured=len(configured_slots),
                    details=" / ".join(details),
                )
            )
    if not lines:
        self.sidebar_api_status_label.setText(self._t("No unavailable API"))
        return

    self.sidebar_api_status_label.setText("\n".join(lines))


def create_translation_page(self) -> QWidget:
    page = QWidget()
    page.setObjectName("content_page_translation")
    page_layout = QVBoxLayout(page)
    page_layout.setContentsMargins(18, 16, 25, 14)
    page_layout.setSpacing(12)

    self.workflow_mode_combo = TwoLineComboBox()
    self.workflow_mode_combo.setObjectName("workflow_mode_combo")
    self.workflow_mode_combo.setClosedTrailingText(self._t("Select Task"))
    self.workflow_mode_combo.blockSignals(True)
    self.populate_workflow_mode_combo()
    self.workflow_mode_combo.blockSignals(False)
    self.workflow_mode_combo.currentIndexChanged.connect(self._on_workflow_mode_changed)
    set_hover_hint(
        self.workflow_mode_combo,
        self._t("Click to select a work mode."),
        delay_ms=0,
        follow_cursor=True,
    )
    self.translation_input_card = QWidget()
    input_layout = QVBoxLayout(self.translation_input_card)
    input_layout.setContentsMargins(0, 0, 0, 0)
    input_layout.setSpacing(0)

    input_layout.addWidget(self.workflow_mode_combo)
    input_layout.addSpacing(1)

    file_button_widget = QWidget()
    file_button_widget.setObjectName("inline_toolbar")
    file_buttons_layout = QHBoxLayout(file_button_widget)
    file_buttons_layout.setContentsMargins(9, 0, 0, 6)
    file_buttons_layout.setSpacing(8)
    self.add_files_button = QPushButton(self._t("Add Files"))
    self.add_folder_button = QPushButton(self._t("Add Folder"))
    self.clear_list_button = QPushButton(self._t("Clear List"))
    self.add_files_button.setProperty("chipButton", True)
    self.add_folder_button.setProperty("chipButton", True)
    self.clear_list_button.setProperty("chipButton", True)
    file_buttons_layout.addWidget(self.add_files_button)
    file_buttons_layout.addWidget(self.add_folder_button)
    file_buttons_layout.addWidget(self.clear_list_button)
    file_buttons_layout.addStretch()
    input_layout.addWidget(file_button_widget)
    input_layout.addSpacing(10)

    self.file_list = FileListView(None, self)
    self.file_list.setObjectName("translation_file_list")
    input_layout.addWidget(self.file_list, 1)
    page_layout.addWidget(self.translation_input_card, 1)

    self.translation_task_card = QWidget()
    task_layout = QVBoxLayout(self.translation_task_card)
    task_layout.setContentsMargins(0, 6, 0, 15)
    task_layout.setSpacing(9)

    output_folder_widget = QWidget()
    output_folder_widget.setObjectName("inline_toolbar")
    output_folder_layout = QHBoxLayout(output_folder_widget)
    output_folder_layout.setContentsMargins(0, 0, 0, 0)
    output_folder_layout.setSpacing(8)
    self.output_folder_label = QLabel(self._t("Output Directory"))
    self.output_folder_label.setObjectName("row_label")
    self.output_folder_label.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
    self.output_folder_label.setContentsMargins(10, 0, 3, 0)
    self.output_folder_input = QLineEdit()
    self.output_folder_input.setPlaceholderText(self._t("Select or drag output folder..."))
    self.output_folder_label.setBuddy(self.output_folder_input)
    self.browse_button = QPushButton(self._t("Browse..."))
    self.open_button = QPushButton(self._t("Open Directory"))
    self.browse_button.setProperty("chipButton", True)
    self.open_button.setProperty("chipButton", True)
    self.browse_button.setProperty("wideChip", True)
    self.open_button.setProperty("wideChip", True)
    button_size_policy = QSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding)
    self.browse_button.setSizePolicy(button_size_policy)
    self.open_button.setSizePolicy(button_size_policy)
    output_folder_layout.addWidget(self.output_folder_label)
    output_folder_layout.addWidget(self.output_folder_input, 1)
    output_folder_layout.addWidget(self.browse_button)
    output_folder_layout.addWidget(self.open_button)
    task_layout.addWidget(output_folder_widget)

    self.output_path_conflict_label = QLabel("")
    self.output_path_conflict_label.setObjectName("output_path_conflict_warning")
    self.output_path_conflict_label.setWordWrap(True)
    self.output_path_conflict_label.setVisible(False)
    task_layout.addWidget(self.output_path_conflict_label)

    self.start_button = QPushButton(self._t("Start Translation"))
    self.start_button.setObjectName("start_translation_button")
    self.start_button.setProperty("primaryAction", True)
    self.start_button.setProperty("translationState", "ready")
    self.start_button.setFixedHeight(44)
    task_layout.addWidget(self.start_button)
    page_layout.addWidget(self.translation_task_card)

    self.add_files_button.clicked.connect(self._trigger_add_files)
    self.add_folder_button.clicked.connect(self.controller.add_folder)
    self.clear_list_button.clicked.connect(self.controller.clear_file_list)
    self.file_list.file_remove_requested.connect(self.controller.remove_file)
    self.output_folder_input.editingFinished.connect(self.controller.apply_output_folder_from_input)
    self.output_folder_input.returnPressed.connect(self.controller.apply_output_folder_from_input)
    self.browse_button.clicked.connect(self.controller.select_output_folder)
    self.open_button.clicked.connect(self.controller.open_output_folder)
    self.start_button.clicked.connect(self.controller.start_backend_task)

    return page


def create_settings_page(self) -> QWidget:
    page = QWidget()
    page.setObjectName("content_page_settings")
    page_layout = QVBoxLayout(page)
    page_layout.setContentsMargins(18, 16, 19, 14)
    page_layout.setSpacing(2)

    # Header card with title + config IO buttons
    header_card = QWidget()
    header_card.setObjectName("header_card")
    header_layout = QHBoxLayout(header_card)
    header_layout.setContentsMargins(12, 4, 12, 4)
    header_layout.setSpacing(8)

    title_col = QVBoxLayout()
    title_col.setContentsMargins(0, 0, 0, 0)
    title_col.setSpacing(8)
    self.settings_page_title = QLabel(self._t("Settings Page Title"))
    self.settings_page_title.setObjectName("page_title")
    self.settings_page_title.setFont(malgun_gothic_bold_font())
    self.settings_page_title.setIndent(2)
    self.settings_page_subtitle = QLabel(
        self._t("Settings Page Subtitle")
    )
    self.settings_page_subtitle.setObjectName("page_subtitle")
    self.settings_page_subtitle.setWordWrap(True)
    title_col.addWidget(self.settings_page_title)
    title_col.addWidget(self.settings_page_subtitle)
    header_layout.addLayout(title_col, 1)

    # self.export_config_button = QPushButton(self._t("Export Config"))
    self.import_config_button = QPushButton(self._t("Import Config"))
    # self.export_config_button.setProperty("chipButton", True)
    self.import_config_button.setProperty("chipButton", True)
    # header_layout.addWidget(self.export_config_button)
    header_layout.addWidget(self.import_config_button)
    page_layout.addWidget(header_card)

    # self.export_config_button.clicked.connect(self.controller.export_config)
    self.import_config_button.clicked.connect(self.controller.import_config)

    # --- 主体区域：左侧 tabs + 右侧描述面板 ---
    settings_body_splitter = QSplitter(Qt.Orientation.Horizontal)
    settings_body_splitter.setObjectName("settings_body_splitter")
    page_layout.addWidget(settings_body_splitter, 1)

    self.settings_tabs = QTabWidget()
    self.settings_tabs.setObjectName("settings_tabs")
    self.settings_tabs.setDocumentMode(True)
    self.settings_tabs.tabBar().setDrawBase(False)
    self.settings_tabs.tabBar().setExpanding(False)
    settings_body_splitter.addWidget(self.settings_tabs)

    # 右侧描述面板
    desc_panel = QWidget()
    desc_panel.setObjectName("settings_desc_panel")
    desc_panel_layout = QVBoxLayout(desc_panel)
    desc_panel_layout.setContentsMargins(16, 16, 16, 16)
    desc_panel_layout.setSpacing(12)

    self.settings_desc_header_label = QLabel(self._t("Settings Desc Header"))
    self.settings_desc_header_label.setObjectName("settings_desc_header")
    desc_panel_layout.addWidget(self.settings_desc_header_label)

    desc_divider = QFrame()
    desc_divider.setFrameShape(QFrame.Shape.HLine)
    desc_divider.setObjectName("settings_desc_divider")
    desc_panel_layout.addWidget(desc_divider)

    self.settings_desc_name = QLabel("")
    self.settings_desc_name.setObjectName("settings_desc_name")
    self.settings_desc_name.setWordWrap(True)
    desc_panel_layout.addWidget(self.settings_desc_name)

    self.settings_desc_text = QLabel(self._t("Settings Desc Placeholder"))
    self.settings_desc_text.setObjectName("settings_desc_text")
    self.settings_desc_text.setWordWrap(True)
    self.settings_desc_text.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
    desc_panel_layout.addWidget(self.settings_desc_text)

    self.settings_desc_key = QLabel("")
    self.settings_desc_key.setObjectName("settings_desc_key")
    self.settings_desc_key.setWordWrap(True)
    self.settings_desc_key.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    desc_panel_layout.addWidget(self.settings_desc_key)
    desc_panel_layout.addStretch(1)

    settings_body_splitter.addWidget(desc_panel)

    settings_body_splitter.setStretchFactor(0, 3)
    settings_body_splitter.setStretchFactor(1, 1)
    settings_body_splitter.setSizes([700, 280])
    settings_body_splitter.setCollapsible(0, False)
    settings_body_splitter.setCollapsible(1, True)

    self.tab_frames = {}
    self.settings_tab_layout = _load_reclassify_settings_layout()
    self._settings_tabs_use_reclassify = bool(self.settings_tab_layout)
    self.settings_tab_title_keys = []

    if self._settings_tabs_use_reclassify:
        for tab in self.settings_tab_layout:
            tab_id = tab["id"]
            tab_title_key = str(tab.get("title", "")).strip() or "Group"
            tab_display_name = self._t(tab_title_key)

            tab_content_widget = QWidget()
            tab_layout = QVBoxLayout(tab_content_widget)
            tab_layout.setContentsMargins(0, 0, 0, 0)

            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setObjectName("settings_scroll_area")
            scroll_content = QWidget()
            scroll_content.setObjectName("settings_scroll_content")
            scroll.setWidget(scroll_content)

            form = QFormLayout(scroll_content)
            form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
            form.setFormAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
            form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            form.setHorizontalSpacing(16)
            form.setVerticalSpacing(0)
            form.setContentsMargins(0, 4, 50, 0)

            tab_layout.addWidget(scroll)
            self.settings_tabs.addTab(tab_content_widget, tab_display_name)
            self.settings_tab_title_keys.append(tab_title_key)
            self.tab_frames[tab_id] = scroll_content
    else:
        tabs_config = [
            ("Application Settings", self._t("Application Settings")),
            ("Basic Settings", self._t("Basic Settings")),
            ("Advanced Settings", self._t("Advanced Settings")),
            ("Options", self._t("Options")),
        ]
        for tab_key, tab_display_name in tabs_config:
            tab_content_widget = QWidget()
            tab_layout = QVBoxLayout(tab_content_widget)
            tab_layout.setContentsMargins(0, 0, 0, 0)

            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll_content = QWidget()
            scroll.setWidget(scroll_content)

            form = QFormLayout(scroll_content)
            form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
            form.setFormAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
            form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            form.setHorizontalSpacing(10)
            form.setVerticalSpacing(8)

            tab_layout.addWidget(scroll)
            self.settings_tabs.addTab(tab_content_widget, tab_display_name)
            self.settings_tab_title_keys.append(tab_key)
            self.tab_frames[tab_key] = scroll_content

    self._populate_theme_combo()
    self._populate_language_combo()
    return page


def create_env_page(self) -> QWidget:
    page = QWidget()
    page.setObjectName("content_page_env")
    page_layout = QVBoxLayout(page)
    page_layout.setContentsMargins(18, 16, 19, 14)
    page_layout.setSpacing(12)

    # --- Header Card ---
    header_card = QWidget()
    header_card.setObjectName("header_card")
    header_layout = QVBoxLayout(header_card)
    header_layout.setContentsMargins(12, 4, 12, 4)
    header_layout.setSpacing(8)

    title_col = QVBoxLayout()
    title_col.setContentsMargins(0, 0, 0, 0)
    title_col.setSpacing(8)
    self.env_page_title_label = QLabel(self._t("API Management"))
    self.env_page_title_label.setObjectName("page_title")
    self.env_page_title_label.setFont(malgun_gothic_bold_font())
    self.env_page_title_label.setIndent(2)
    self.env_page_subtitle_label = QLabel(
        self._t("Manage API keys and environment variables for each translator")
    )
    self.env_page_subtitle_label.setObjectName("page_subtitle")
    self.env_page_subtitle_label.setWordWrap(True)
    title_col.addWidget(self.env_page_title_label)
    title_col.addWidget(self.env_page_subtitle_label)
    header_layout.addLayout(title_col)

    self.env_preset_layout = QHBoxLayout()
    self.env_preset_layout.setSpacing(8)
    header_layout.addLayout(self.env_preset_layout)

    page_layout.addWidget(header_card)

    # --- Native QTabWidget Setup ---
    self.env_tab_widget = QTabWidget()
    self.env_tab_widget.setObjectName("settings_tab_widget")
    self.env_tab_widget.setDocumentMode(True)
    self.env_tab_widget.tabBar().setDrawBase(False)
    self.env_tab_widget.tabBar().setExpanding(False)
    
    # 1. Translation Tab Content
    self.env_translation_page = QWidget()
    self.env_translation_layout = QVBoxLayout(self.env_translation_page)
    self.env_translation_layout.setContentsMargins(0, 0, 0, 0)
    
    env_scroll = QScrollArea()
    env_scroll.setWidgetResizable(True)
    env_scroll.setObjectName("settings_scroll_area")
    
    self.env_group_container = QWidget()
    self.env_group_container.setObjectName("settings_scroll_content")
    self.env_group_container_layout = QVBoxLayout(self.env_group_container)
    self.env_group_container_layout.setContentsMargins(0, 4, 50, 0)
    self.env_group_container_layout.setSpacing(12)
    env_scroll.setWidget(self.env_group_container)
    self.env_translation_layout.addWidget(env_scroll)
    
    # 2. OCR Tab Content
    self.env_ocr_page = QWidget()
    self.env_ocr_layout = QVBoxLayout(self.env_ocr_page)
    self.env_ocr_layout.setContentsMargins(0, 0, 0, 0)
    
    ocr_scroll = QScrollArea()
    ocr_scroll.setWidgetResizable(True)
    ocr_scroll.setObjectName("settings_scroll_area")
    self.ocr_container = QWidget()
    self.ocr_container.setObjectName("settings_scroll_content")
    self.ocr_container_layout = QVBoxLayout(self.ocr_container)
    self.ocr_container_layout.setContentsMargins(0, 4, 50, 0)
    self.ocr_container_layout.setSpacing(12)
    ocr_scroll.setWidget(self.ocr_container)
    self.env_ocr_layout.addWidget(ocr_scroll)
    
    # 3. Colorization Tab Content
    self.env_color_page = QWidget()
    self.env_color_layout = QVBoxLayout(self.env_color_page)
    self.env_color_layout.setContentsMargins(0, 0, 0, 0)
    
    color_scroll = QScrollArea()
    color_scroll.setWidgetResizable(True)
    color_scroll.setObjectName("settings_scroll_area")
    self.color_container = QWidget()
    self.color_container.setObjectName("settings_scroll_content")
    self.color_container_layout = QVBoxLayout(self.color_container)
    self.color_container_layout.setContentsMargins(0, 4, 50, 0)
    self.color_container_layout.setSpacing(12)
    color_scroll.setWidget(self.color_container)
    self.env_color_layout.addWidget(color_scroll)
    
    # 4. Render Tab Content
    self.env_render_page = QWidget()
    self.env_render_layout = QVBoxLayout(self.env_render_page)
    self.env_render_layout.setContentsMargins(0, 0, 0, 0)
    
    render_scroll = QScrollArea()
    render_scroll.setWidgetResizable(True)
    render_scroll.setObjectName("settings_scroll_area")
    self.render_container = QWidget()
    self.render_container.setObjectName("settings_scroll_content")
    self.render_container_layout = QVBoxLayout(self.render_container)
    self.render_container_layout.setContentsMargins(0, 4, 50, 0)
    self.render_container_layout.setSpacing(12)
    render_scroll.setWidget(self.render_container)
    self.env_render_layout.addWidget(render_scroll)
    
    self.env_tab_widget.addTab(self.env_translation_page, self._t("Translation"))
    self.env_tab_widget.addTab(self.env_ocr_page, self._t("OCR"))
    self.env_tab_widget.addTab(self.env_color_page, self._t("Colorization"))
    self.env_tab_widget.addTab(self.env_render_page, self._t("Render"))
    
    page_layout.addWidget(self.env_tab_widget, 1)
    return page


def create_prompt_page(self) -> QWidget:
    from ui.secondary_pages.prompt_preview import PromptPreviewPanel

    page = QWidget()
    page.setObjectName("content_page_prompts")
    page_layout = QVBoxLayout(page)
    page_layout.setContentsMargins(18, 16, 19, 14)
    page_layout.setSpacing(12)

    # --- Header Card ---
    header_card = QWidget()
    header_card.setObjectName("header_card")
    header_layout = QVBoxLayout(header_card)
    header_layout.setContentsMargins(12, 4, 12, 4)
    header_layout.setSpacing(8)

    title_col = QVBoxLayout()
    title_col.setContentsMargins(0, 0, 0, 0)
    title_col.setSpacing(8)
    self.prompt_page_title_label = QLabel(self._t("Prompt Management"))
    self.prompt_page_title_label.setObjectName("page_title")
    self.prompt_page_title_label.setFont(malgun_gothic_bold_font())
    self.prompt_page_title_label.setIndent(2)
    self.prompt_page_subtitle_label = QLabel(
        self._t("Manage and apply prompt files for translation")
    )
    self.prompt_page_subtitle_label.setObjectName("page_subtitle")
    self.prompt_page_subtitle_label.setWordWrap(True)
    title_col.addWidget(self.prompt_page_title_label)
    title_col.addWidget(self.prompt_page_subtitle_label)
    header_layout.addLayout(title_col)
    page_layout.addWidget(header_card)

    # --- 左右 Splitter ---
    prompt_splitter = QSplitter(Qt.Orientation.Horizontal)
    prompt_splitter.setObjectName("settings_body_splitter")

    # ===== 左侧: Prompt 列表 =====
    left_widget = QWidget()
    left_layout = QVBoxLayout(left_widget)
    left_layout.setContentsMargins(0, 0, 0, 0)
    left_layout.setSpacing(0)

    self.prompt_card = QGroupBox(self._t("Prompt List"))
    self.prompt_card.setObjectName("section_card")
    prompt_card_layout = QVBoxLayout(self.prompt_card)
    prompt_card_layout.setContentsMargins(12, 14, 12, 12)
    prompt_card_layout.setSpacing(10)

    button_row = QWidget()
    button_row.setObjectName("inline_toolbar")
    button_row_layout = QHBoxLayout(button_row)
    button_row_layout.setContentsMargins(0, 0, 0, 0)
    button_row_layout.setSpacing(8)
    self.prompt_new_button = QPushButton(self._t("New"))
    self.prompt_copy_button = QPushButton(self._t("Copy"))
    self.prompt_rename_button = QPushButton(self._t("Rename"))
    self.prompt_delete_button = QPushButton(self._t("Delete"))
    self.prompt_refresh_button = QPushButton(self._t("Refresh"))
    self.prompt_open_dir_button = QPushButton(self._t("Open Directory"))
    self.prompt_apply_button = QPushButton(self._t("Apply Selected Prompt"))
    self.prompt_new_button.setProperty("chipButton", True)
    self.prompt_copy_button.setProperty("chipButton", True)
    self.prompt_rename_button.setProperty("chipButton", True)
    self.prompt_delete_button.setProperty("chipButton", True)
    self.prompt_delete_button.setProperty("variant", "danger")
    self.prompt_refresh_button.setProperty("chipButton", True)
    self.prompt_open_dir_button.setProperty("chipButton", True)
    self.prompt_apply_button.setProperty("chipButton", True)
    button_row_layout.addWidget(self.prompt_new_button)
    button_row_layout.addWidget(self.prompt_copy_button)
    button_row_layout.addWidget(self.prompt_rename_button)
    button_row_layout.addWidget(self.prompt_delete_button)
    button_row_layout.addWidget(self.prompt_refresh_button)
    button_row_layout.addWidget(self.prompt_open_dir_button)
    button_row_layout.addWidget(self.prompt_apply_button)
    button_row_layout.addStretch()
    prompt_card_layout.addWidget(button_row)

    self.prompt_list_widget = QListWidget()
    self.prompt_list_widget.setObjectName("asset_list")
    prompt_card_layout.addWidget(self.prompt_list_widget)

    self.prompt_status_label = QLabel("")
    self.prompt_status_label.setObjectName("page_subtitle")
    self.prompt_status_label.setWordWrap(True)
    prompt_card_layout.addWidget(self.prompt_status_label)
    left_layout.addWidget(self.prompt_card, 1)

    prompt_splitter.addWidget(left_widget)

    # ===== 右侧: 预览面板 =====
    self.prompt_preview_panel = PromptPreviewPanel(t_func=self._t, parent=self)
    prompt_splitter.addWidget(self.prompt_preview_panel)

    prompt_splitter.setStretchFactor(0, 2)
    prompt_splitter.setStretchFactor(1, 3)
    prompt_splitter.setSizes([320, 580])
    prompt_splitter.setCollapsible(0, False)
    prompt_splitter.setCollapsible(1, False)

    page_layout.addWidget(prompt_splitter, 1)

    # --- 信号连接 ---
    self.prompt_new_button.clicked.connect(self._create_new_prompt)
    self.prompt_copy_button.clicked.connect(self._copy_selected_prompt)
    self.prompt_rename_button.clicked.connect(self._rename_selected_prompt)
    self.prompt_delete_button.clicked.connect(self._delete_selected_prompt)
    self.prompt_refresh_button.clicked.connect(self._refresh_prompt_manager)
    self.prompt_open_dir_button.clicked.connect(self.controller.open_dict_directory)
    self.prompt_apply_button.clicked.connect(self._apply_selected_prompt)
    self.prompt_list_widget.itemDoubleClicked.connect(lambda _: self._apply_selected_prompt())
    self.prompt_list_widget.currentItemChanged.connect(self._on_prompt_selection_changed)
    self.prompt_preview_panel.edit_requested.connect(self._open_prompt_editor)
    return page


def create_font_page(self) -> QWidget:
    page = QWidget()
    page.setObjectName("content_page_fonts")
    page_layout = QVBoxLayout(page)
    page_layout.setContentsMargins(18, 16, 19, 14)
    page_layout.setSpacing(12)

    # --- Header Card (与翻译/设置页面一致) ---
    header_card = QWidget()
    header_card.setObjectName("header_card")
    header_layout = QVBoxLayout(header_card)
    header_layout.setContentsMargins(12, 4, 12, 4)
    header_layout.setSpacing(8)

    title_col = QVBoxLayout()
    title_col.setContentsMargins(0, 0, 0, 0)
    title_col.setSpacing(8)
    self.font_page_title_label = QLabel(self._t("Font Management"))
    self.font_page_title_label.setObjectName("page_title")
    self.font_page_title_label.setFont(malgun_gothic_bold_font())
    self.font_page_title_label.setIndent(2)
    self.font_page_subtitle_label = QLabel(
        self._t("Manage and preview fonts for text rendering")
    )
    self.font_page_subtitle_label.setObjectName("page_subtitle")
    self.font_page_subtitle_label.setWordWrap(True)
    title_col.addWidget(self.font_page_title_label)
    title_col.addWidget(self.font_page_subtitle_label)
    header_layout.addLayout(title_col)
    page_layout.addWidget(header_card)

    # --- Font List Card ---
    self.font_card = QGroupBox(self._t("Font List"))
    self.font_card.setObjectName("section_card")
    font_card_layout = QVBoxLayout(self.font_card)
    font_card_layout.setContentsMargins(12, 14, 12, 12)
    font_card_layout.setSpacing(10)

    button_row = QWidget()
    button_row.setObjectName("inline_toolbar")
    button_row_layout = QHBoxLayout(button_row)
    button_row_layout.setContentsMargins(0, 0, 0, 0)
    button_row_layout.setSpacing(8)
    self.font_import_button = QPushButton(self._t("Import"))
    self.font_delete_button = QPushButton(self._t("Delete"))
    self.font_refresh_button = QPushButton(self._t("Refresh"))
    self.font_open_dir_button = QPushButton(self._t("Open Directory"))
    self.font_apply_button = QPushButton(self._t("Apply Selected Font"))
    self.font_import_button.setProperty("chipButton", True)
    self.font_delete_button.setProperty("chipButton", True)
    self.font_delete_button.setProperty("variant", "danger")
    self.font_refresh_button.setProperty("chipButton", True)
    self.font_open_dir_button.setProperty("chipButton", True)
    self.font_apply_button.setProperty("chipButton", True)
    button_row_layout.addWidget(self.font_import_button)
    button_row_layout.addWidget(self.font_delete_button)
    button_row_layout.addWidget(self.font_refresh_button)
    button_row_layout.addWidget(self.font_open_dir_button)
    button_row_layout.addWidget(self.font_apply_button)
    button_row_layout.addStretch()
    font_card_layout.addWidget(button_row)

    self.font_list_widget = QListWidget()
    self.font_list_widget.setObjectName("asset_list")
    font_card_layout.addWidget(self.font_list_widget)

    self.font_status_label = QLabel("")
    self.font_status_label.setObjectName("page_subtitle")
    self.font_status_label.setWordWrap(True)
    font_card_layout.addWidget(self.font_status_label)

    page_layout.addWidget(self.font_card, 1)

    # --- Font Preview Card ---
    self.font_preview_card = QGroupBox(self._t("Font Preview"))
    self.font_preview_card.setObjectName("section_card")
    self.font_preview_card.setFixedHeight(320)
    preview_card_layout = QVBoxLayout(self.font_preview_card)
    preview_card_layout.setContentsMargins(16, 14, 16, 14)
    preview_card_layout.setSpacing(8)

    # 1. Header Row (Font Filename + Font Size Indicator)
    header_row = QHBoxLayout()
    header_row.setSpacing(10)
    self.font_preview_name_label = QLabel(self._t("Select a font to preview"))
    self.font_preview_name_label.setObjectName("font_preview_name")
    header_row.addWidget(self.font_preview_name_label, 1)

    self.font_preview_size_indicator = QLabel("18pt")
    self.font_preview_size_indicator.setStyleSheet(
        f"color: {get_current_theme_colors()['text_muted']}; font-size: 11px; font-weight: 600; font-family: monospace;"
    )
    header_row.addWidget(self.font_preview_size_indicator)
    preview_card_layout.addLayout(header_row)

    # 2. Control Toolbar (Custom Text Input + Size Slider)
    toolbar_row = QHBoxLayout()
    toolbar_row.setSpacing(12)

    self.font_preview_input = QLineEdit()
    self.font_preview_input.setPlaceholderText(self._t("Type custom text to preview..."))
    self.font_preview_input.setClearButtonEnabled(True)
    toolbar_row.addWidget(self.font_preview_input, 3)

    self.font_preview_slider = QSlider(Qt.Orientation.Horizontal)
    self.font_preview_slider.setRange(12, 64)
    self.font_preview_slider.setValue(18)
    self.font_preview_slider.setToolTip(self._t("Adjust preview size"))
    toolbar_row.addWidget(self.font_preview_slider, 2)

    preview_card_layout.addLayout(toolbar_row)

    preview_divider = QFrame()
    preview_divider.setFrameShape(QFrame.Shape.HLine)
    preview_divider.setObjectName("settings_desc_divider")
    preview_card_layout.addWidget(preview_divider)

    # 3. Scrollable Specimen Area
    self.font_preview_scroll = QScrollArea()
    self.font_preview_scroll.setWidgetResizable(True)
    self.font_preview_scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
    
    scroll_content = QWidget()
    scroll_content.setStyleSheet("background: transparent;")
    self.scroll_content_layout = QVBoxLayout(scroll_content)
    self.scroll_content_layout.setContentsMargins(0, 4, 0, 4)
    self.scroll_content_layout.setSpacing(10)

    self.font_preview_labels = []
    # Create 3 specimen labels representing different sizes/contents
    for i in range(3):
        lbl = QLabel()
        lbl.setObjectName("font_preview_text")
        lbl.setWordWrap(False)
        lbl.setScaledContents(False)
        self.scroll_content_layout.addWidget(lbl)
        self.font_preview_labels.append(lbl)

    self.scroll_content_layout.addStretch()
    self.font_preview_scroll.setWidget(scroll_content)
    preview_card_layout.addWidget(self.font_preview_scroll, 1)

    self._current_preview_font_path = None
    page_layout.addWidget(self.font_preview_card)

    # --- Signals ---
    self.font_import_button.clicked.connect(self._import_fonts)
    self.font_delete_button.clicked.connect(self._delete_selected_font)
    self.font_refresh_button.clicked.connect(self._refresh_font_manager)
    self.font_open_dir_button.clicked.connect(self.controller.open_font_directory)
    self.font_apply_button.clicked.connect(self._apply_selected_font)
    self.font_list_widget.itemDoubleClicked.connect(lambda _: self._apply_selected_font())
    self.font_list_widget.currentItemChanged.connect(self._on_font_selection_changed)
    self.font_preview_input.textChanged.connect(self._update_font_preview)
    self.font_preview_slider.valueChanged.connect(self._update_font_preview)
    return page


def create_replacements_page(self) -> QWidget:
    from ui.secondary_pages.replacements_editor import ReplacementsEditorPanel

    page = QWidget()
    page.setObjectName("content_page_replacements")
    page_layout = QVBoxLayout(page)
    page_layout.setContentsMargins(18, 16, 19, 14)
    page_layout.setSpacing(12)

    # --- Header Card ---
    header_card = QWidget()
    header_card.setObjectName("header_card")
    header_layout = QVBoxLayout(header_card)
    header_layout.setContentsMargins(12, 4, 12, 4)
    header_layout.setSpacing(8)

    title_col = QVBoxLayout()
    title_col.setContentsMargins(0, 0, 0, 0)
    title_col.setSpacing(8)
    self.replacements_page_title_label = QLabel(self._t("Replacement Rules"))
    self.replacements_page_title_label.setObjectName("page_title")
    self.replacements_page_title_label.setFont(malgun_gothic_bold_font())
    self.replacements_page_title_label.setIndent(2)
    self.replacements_page_subtitle_label = QLabel(
        self._t("Manage text replacement rules applied to translations before rendering")
    )
    self.replacements_page_subtitle_label.setObjectName("page_subtitle")
    self.replacements_page_subtitle_label.setWordWrap(True)
    title_col.addWidget(self.replacements_page_title_label)
    title_col.addWidget(self.replacements_page_subtitle_label)
    header_layout.addLayout(title_col)
    page_layout.addWidget(header_card)

    # --- Editor Panel ---
    self.replacements_editor_panel = ReplacementsEditorPanel(t_func=self._t, parent=self)
    page_layout.addWidget(self.replacements_editor_panel, 1)

    return page


def create_batch_edit_page(self) -> QWidget:
    from ui.secondary_pages.batch_edit_panel import BatchEditPanel

    page = QWidget()
    page.setObjectName("content_page_batch_edit")
    page_layout = QVBoxLayout(page)
    page_layout.setContentsMargins(18, 16, 19, 14)
    page_layout.setSpacing(12)

    header_card = QWidget()
    header_card.setObjectName("header_card")
    header_layout = QVBoxLayout(header_card)
    header_layout.setContentsMargins(12, 4, 12, 4)
    header_layout.setSpacing(8)

    title_col = QVBoxLayout()
    title_col.setContentsMargins(0, 0, 0, 0)
    title_col.setSpacing(8)
    self.batch_edit_page_title_label = QLabel(self._t("Batch Management"))
    self.batch_edit_page_title_label.setObjectName("page_title")
    self.batch_edit_page_title_label.setFont(malgun_gothic_bold_font())
    self.batch_edit_page_title_label.setIndent(2)
    self.batch_edit_page_subtitle_label = QLabel(
        self._t(
            "You can search and batch-edit all JSON data linked to the main file list. "
            "It is not applied to the output image unless you render."
        )
    )
    self.batch_edit_page_subtitle_label.setObjectName("page_subtitle")
    self.batch_edit_page_subtitle_label.setWordWrap(True)
    title_col.addWidget(self.batch_edit_page_title_label)
    title_col.addWidget(self.batch_edit_page_subtitle_label)
    header_layout.addLayout(title_col)
    page_layout.addWidget(header_card)

    self.batch_edit_panel = BatchEditPanel(t_func=self._t, parent=self)
    page_layout.addWidget(self.batch_edit_panel, 1)
    return page


def create_folder_sync_page(self) -> QWidget:
    from ui.secondary_pages.folder_json_sync_panel import FolderJsonSyncPanel

    page = QWidget()
    page.setObjectName("content_page_folder_sync")
    page_layout = QVBoxLayout(page)
    page_layout.setContentsMargins(18, 16, 19, 14)
    page_layout.setSpacing(12)

    header_card = QWidget()
    header_card.setObjectName("header_card")
    header_layout = QVBoxLayout(header_card)
    header_layout.setContentsMargins(12, 4, 12, 4)
    header_layout.setSpacing(8)

    title_col = QVBoxLayout()
    title_col.setContentsMargins(0, 0, 0, 0)
    title_col.setSpacing(8)
    self.folder_sync_page_title_label = QLabel(self._t("Match JSON paths to the new folder location"))
    self.folder_sync_page_title_label.setObjectName("page_title")
    self.folder_sync_page_title_label.setFont(malgun_gothic_bold_font())
    self.folder_sync_page_title_label.setIndent(2)
    self.folder_sync_page_subtitle_label = QLabel(
        self._t(
            "Drop original folders on the left and translated folders on the right. JSON absolute paths are rewritten to the current locations even if folder names or drives changed."
        )
    )
    self.folder_sync_page_subtitle_label.setObjectName("page_subtitle")
    self.folder_sync_page_subtitle_label.setWordWrap(True)
    title_col.addWidget(self.folder_sync_page_title_label)
    title_col.addWidget(self.folder_sync_page_subtitle_label)
    header_layout.addLayout(title_col)
    page_layout.addWidget(header_card)

    self.folder_sync_panel = FolderJsonSyncPanel(t_func=self._t, parent=self)
    page_layout.addWidget(self.folder_sync_panel, 1)
    return page


def create_right_panel(self) -> QWidget:
    right_panel = QWidget()
    right_panel.setObjectName("content_panel")
    right_layout = QVBoxLayout(right_panel)
    right_layout.setContentsMargins(0, 0, 0, 0)

    right_splitter = QSplitter(Qt.Orientation.Vertical)
    right_splitter.setObjectName("content_vertical_splitter")
    right_layout.addWidget(right_splitter)

    self.content_stack = QStackedWidget()
    self.page_indexes = {}
    self.page_indexes["translation"] = self.content_stack.addWidget(self._create_translation_page())
    self.page_indexes["settings"] = self.content_stack.addWidget(self._create_settings_page())
    self.page_indexes["env"] = self.content_stack.addWidget(self._create_env_page())
    self.page_indexes["prompts"] = self.content_stack.addWidget(self._create_prompt_page())
    self.page_indexes["fonts"] = self.content_stack.addWidget(self._create_font_page())
    self.page_indexes["replacements"] = self.content_stack.addWidget(self._create_replacements_page())
    self.page_indexes["batch_edit"] = self.content_stack.addWidget(self._create_batch_edit_page())
    self.page_indexes["folder_sync"] = self.content_stack.addWidget(self._create_folder_sync_page())
    right_splitter.addWidget(self.content_stack)

    progress_container = QWidget()
    progress_container.setObjectName("log_container")
    progress_layout = QVBoxLayout(progress_container)
    progress_layout.setContentsMargins(12, 10, 12, 10)
    progress_layout.setSpacing(6)

    from PyQt6.QtWidgets import QProgressBar
    self.progress_bar = QProgressBar()
    self.progress_bar.setMinimum(0)
    self.progress_bar.setMaximum(100)
    self.progress_bar.setValue(0)
    self.progress_bar.setTextVisible(True)
    self.progress_bar.setFormat("0/0 (0%)")
    self.progress_bar.setFixedHeight(25)
    self.progress_bar.setObjectName("translation_progress_bar")
    self.progress_bar.setProperty("progressState", "idle")
    progress_layout.addWidget(self.progress_bar)
    self.progress_info_label = QLabel("")
    self.progress_info_label.setObjectName("progress_info_label")
    self.progress_info_label.setWordWrap(True)
    progress_layout.addWidget(self.progress_info_label)
    right_splitter.addWidget(progress_container)




    right_splitter.setStretchFactor(0, 3)
    right_splitter.setStretchFactor(1, 0)
    right_splitter.setSizes([760, 60])

    self._switch_content_page("translation")
    return right_panel


def switch_content_page(self, page_key: str):
    if not hasattr(self, "content_stack") or not hasattr(self, "page_indexes"):
        return
    target_index = self.page_indexes.get(page_key)
    if target_index is None:
        return
    self.content_stack.setCurrentIndex(target_index)

    if hasattr(self, "page_nav_buttons"):
        nav_button = self.page_nav_buttons.get(page_key)
        if nav_button and not nav_button.isChecked():
            nav_button.setChecked(True)

        if page_key == "settings" and not getattr(self, "_settings_ui_ready", False):
            self.set_parameters(self.controller.config_service.get_config().model_dump())
        if page_key == "env":
            self._refresh_env_api_groups()


def on_nav_prompt_clicked(self):
    self._switch_content_page("prompts")
    self._refresh_prompt_manager()


def on_sidebar_logo_clicked(self):
    try:
        from ui.startup_notice import show_startup_notice_if_enabled

        show_startup_notice_if_enabled(self.window(), force=True)
    except Exception:
        logging.exception("Failed to show startup notice")


def on_nav_editor_clicked(self):
    if hasattr(self, "editor_view_requested"):
        self.editor_view_requested.emit()


def on_nav_font_clicked(self):
    self._switch_content_page("fonts")


def on_nav_replacements_clicked(self):
    self._switch_content_page("replacements")
    if hasattr(self, "replacements_editor_panel"):
        self.replacements_editor_panel.refresh()
    self._refresh_font_manager()


def build_batch_edit_catalog_snapshot(self):
    from manga_translator.utils.path_manager import find_json_path

    json_by_file = {}
    try:
        files = self.controller.get_folder_tree_structure().get("files") or []
    except Exception:
        files = []
    for path in files:
        json_path = find_json_path(path)
        if json_path:
            json_by_file[path] = json_path
            json_by_file[os.path.abspath(path)] = json_path
    return type("FileCatalogSnapshot", (), {"json_by_file": json_by_file})()


def refresh_batch_edit_catalog(self):
    if not hasattr(self, "batch_edit_panel"):
        return
    self.batch_edit_panel.set_catalog_snapshot(self._build_batch_edit_catalog_snapshot())


def on_nav_batch_edit_clicked(self):
    self._switch_content_page("batch_edit")
    self._refresh_batch_edit_catalog()
    if hasattr(self, "batch_edit_panel"):
        self.batch_edit_panel.refresh()


def on_nav_folder_sync_clicked(self):
    self._switch_content_page("folder_sync")


def populate_theme_combo(self):
    if not hasattr(self, "theme_combo"):
        return
    config = self.config_service.get_config()
    theme_options = [(theme_key, self._t(theme_label)) for theme_key, theme_label in THEME_OPTIONS]
    self.theme_combo.blockSignals(True)
    self.theme_combo.clear()
    selected_index = 0
    for idx, (theme_key, theme_label) in enumerate(theme_options):
        self.theme_combo.addItem(theme_label, theme_key)
        if config.app.theme == theme_key:
            selected_index = idx
    self.theme_combo.setCurrentIndex(selected_index)
    self.theme_combo.blockSignals(False)


def populate_language_combo(self):
    if not hasattr(self, "language_combo"):
        return
    current_language = self.config_service.get_config().app.ui_language
    self.language_combo.blockSignals(True)
    self.language_combo.clear()
    if self.i18n:
        available_locales = self.i18n.get_available_locales()
        selected_index = 0
        for idx, (locale_code, locale_info) in enumerate(available_locales.items()):
            self.language_combo.addItem(locale_info.name, locale_code)
            if current_language == locale_code:
                selected_index = idx
        if self.language_combo.count() > 0:
            self.language_combo.setCurrentIndex(selected_index)
    self.language_combo.blockSignals(False)


def on_theme_combo_changed(self, index: int):
    if index < 0 or not hasattr(self, "theme_combo"):
        return
    theme_key = self.theme_combo.itemData(index)
    if theme_key:
        self.theme_change_requested.emit(theme_key)


def on_language_combo_changed(self, index: int):
    if index < 0 or not hasattr(self, "language_combo"):
        return
    locale_code = self.language_combo.itemData(index)
    if locale_code:
        self.language_change_requested.emit(locale_code)


def refresh_prompt_manager(self):
    if not hasattr(self, "prompt_list_widget"):
        return
    prompt_files = self.controller.get_hq_prompt_options()
    selected_prompt_path = self.config_service.get_config().translator.high_quality_prompt_path
    selected_filename = _normalize_asset_filename(selected_prompt_path)
    current_item = self.prompt_list_widget.currentItem()
    current_filename = _get_asset_item_filename(current_item)
    preferred_filename = current_filename or selected_filename

    self.prompt_list_widget.blockSignals(True)
    self.prompt_list_widget.clear()
    for prompt in prompt_files:
        item = _create_asset_list_item(
            self,
            prompt,
            is_current=(prompt == selected_filename),
            tooltip_text=self._t("Current prompt: {filename}", filename=prompt),
        )
        self.prompt_list_widget.addItem(item)
    self.prompt_list_widget.blockSignals(False)

    if preferred_filename:
        matching_item = _find_asset_item(self.prompt_list_widget, preferred_filename)
        if matching_item:
            self.prompt_list_widget.setCurrentItem(matching_item)
    else:
        self.prompt_list_widget.clearSelection()

    if not self.prompt_list_widget.currentItem() and hasattr(self, "prompt_preview_panel"):
        self.prompt_preview_panel.clear()
    _set_prompt_status(self, "Found {count} prompt files.", count=len(prompt_files))


def apply_selected_prompt(self):
    current_item = self.prompt_list_widget.currentItem() if hasattr(self, "prompt_list_widget") else None
    if not current_item:
        return
    filename = _get_asset_item_filename(current_item)
    if not filename:
        return
    selected_path = os.path.join("dict", filename).replace("\\", "/")
    self.setting_changed.emit("translator.high_quality_prompt_path", selected_path)
    self._refresh_prompt_manager()
    _set_prompt_status(self, "Current prompt: {filename}", filename=filename)


def on_prompt_selection_changed(self, current, previous):
    """Prompt 列表选中变化时加载预览。"""
    if not hasattr(self, "prompt_preview_panel"):
        return
    if not current:
        self.prompt_preview_panel.clear()
        return
    filename = _get_asset_item_filename(current)
    if not filename:
        self.prompt_preview_panel.clear()
        return
    dict_dir = resource_path("dict")
    file_path = os.path.join(dict_dir, filename)
    self.prompt_preview_panel.load_file(file_path)


def open_prompt_editor(self, file_path: str):
    """弹出编辑器对话框，关闭后刷新预览。"""
    from ui.secondary_pages.ai_colorizer_prompt_editor import (
        AIColorizerPromptEditorDialog,
        is_ai_colorizer_prompt_file,
    )

    if is_ai_colorizer_prompt_file(file_path):
        dlg = AIColorizerPromptEditorDialog(file_path, t_func=self._t, parent=self)
    else:
        from ui.secondary_pages.prompt_preview import PromptEditorDialog

        dlg = PromptEditorDialog(file_path, t_func=self._t, parent=self)
    dlg.exec()
    # 编辑器关闭后刷新预览
    if dlg.get_was_modified() and hasattr(self, "prompt_preview_panel"):
        self.prompt_preview_panel.load_file(file_path)


def _get_selected_prompt_filename(self) -> str | None:
    current = self.prompt_list_widget.currentItem() if hasattr(self, "prompt_list_widget") else None
    if not current:
        return None
    filename = _get_asset_item_filename(current)
    return filename or None


def _select_prompt_item(self, filename: str):
    if not filename or not hasattr(self, "prompt_list_widget"):
        return
    item = _find_asset_item(self.prompt_list_widget, filename)
    if item:
        self.prompt_list_widget.setCurrentItem(item)


def _prompt_file_path(filename: str) -> str:
    return os.path.join(resource_path("dict"), filename)


def create_new_prompt(self):
    """弹出输入框，创建新的 YAML 提示词文件。"""
    from ui.secondary_pages.themed_text_input_dialog import themed_get_text
    name, ok = themed_get_text(
        self,
        title=self._t("New Prompt"),
        label=self._t("Enter prompt file name (without extension):"),
        ok_text=self._t("OK"),
        cancel_text=self._t("Cancel"),
    )
    if not ok or not name.strip():
        return
    filename = _normalize_prompt_filename(name.strip(), ".yaml")
    if not filename:
        QMessageBox.warning(self, self._t("Warning"), self._t("Invalid file name."))
        return
    dict_dir = resource_path("dict")
    os.makedirs(dict_dir, exist_ok=True)
    file_path = os.path.join(dict_dir, filename)

    if os.path.exists(file_path):
        QMessageBox.warning(self, self._t("Warning"), self._t("File already exists") + f": {filename}")
        return

    # 默认 YAML 模板
    default_content = (
        '# 自定义翻译提示词模板\n'
        '# Custom translation prompt template\n'
        '#\n'
        '# 使用方法：\n'
        '#   1. 复制此文件并重命名（例如 my_manga_prompt.yaml）\n'
        '#   2. 编辑下面的 system_prompt 和 glossary 部分\n'
        '#   3. 在翻译设置中选择此文件\n'
        '#\n'
        '# 提示词中可以使用 {{{target_lang}}} 占位符，会被替换为目标语言名称\n'
        '\n'
        '# 自定义系统提示词（留空则仅使用内置的基础提示词，此处内容会叠加在基础提示词之前）\n'
        'system_prompt: ""\n'
        '\n'
        '# 术语表（确保角色名、地名等翻译一致）\n'
        'glossary:\n'
        '  Person:\n'
        '    - original: ""\n'
        '      translation: ""\n'
        '  Location: []\n'
        '  Org: []\n'
        '  Item: []\n'
        '  Skill: []\n'
        '  Creature: []\n'
    )

    try:
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(default_content)
    except Exception as e:
        QMessageBox.critical(self, self._t("Error"), str(e))
        return

    self._refresh_prompt_manager()
    _select_prompt_item(self, filename)
    _set_prompt_status(self, "Created: {filename}", filename=filename)


def copy_selected_prompt(self):
    """复制选中的提示词文件。"""
    from ui.secondary_pages.themed_text_input_dialog import themed_get_text

    filename = _get_selected_prompt_filename(self)
    if not filename:
        QMessageBox.warning(self, self._t("Warning"), self._t("Please select a prompt file first."))
        return

    source_path = _prompt_file_path(filename)
    if not os.path.isfile(source_path):
        QMessageBox.warning(self, self._t("Warning"), self._t("Selected prompt file does not exist."))
        return

    stem, ext = os.path.splitext(filename)
    default_name = f"{stem}_copy"
    new_name, ok = themed_get_text(
        self,
        title=self._t("Copy Prompt"),
        label=self._t("Enter new prompt file name (without extension):"),
        text=default_name,
        ok_text=self._t("OK"),
        cancel_text=self._t("Cancel"),
    )
    if not ok or not new_name.strip():
        return

    target_filename = _normalize_prompt_filename(new_name.strip(), ext or ".yaml")
    if not target_filename:
        QMessageBox.warning(self, self._t("Warning"), self._t("Invalid file name."))
        return

    target_path = _prompt_file_path(target_filename)
    if os.path.exists(target_path):
        QMessageBox.warning(self, self._t("Warning"), self._t("File already exists") + f": {target_filename}")
        return

    try:
        shutil.copy2(source_path, target_path)
    except Exception as e:
        QMessageBox.critical(self, self._t("Error"), str(e))
        return

    self._refresh_prompt_manager()
    _select_prompt_item(self, target_filename)
    _set_prompt_status(self, "Copied: {filename}", filename=target_filename)


def rename_selected_prompt(self):
    """重命名选中的提示词文件。"""
    from ui.secondary_pages.themed_text_input_dialog import themed_get_text

    filename = _get_selected_prompt_filename(self)
    if not filename:
        QMessageBox.warning(self, self._t("Warning"), self._t("Please select a prompt file first."))
        return

    source_path = _prompt_file_path(filename)
    if not os.path.isfile(source_path):
        QMessageBox.warning(self, self._t("Warning"), self._t("Selected prompt file does not exist."))
        return

    stem, ext = os.path.splitext(filename)
    new_name, ok = themed_get_text(
        self,
        title=self._t("Rename Prompt"),
        label=self._t("Enter new prompt file name (without extension):"),
        text=stem,
        ok_text=self._t("OK"),
        cancel_text=self._t("Cancel"),
    )
    if not ok or not new_name.strip():
        return

    target_filename = _normalize_prompt_filename(new_name.strip(), ext or ".yaml")
    if not target_filename:
        QMessageBox.warning(self, self._t("Warning"), self._t("Invalid file name."))
        return
    if target_filename == filename:
        return

    target_path = _prompt_file_path(target_filename)
    if os.path.exists(target_path):
        QMessageBox.warning(self, self._t("Warning"), self._t("File already exists") + f": {target_filename}")
        return

    try:
        os.replace(source_path, target_path)
    except Exception as e:
        QMessageBox.critical(self, self._t("Error"), str(e))
        return

    current_prompt_path = self.config_service.get_config().translator.high_quality_prompt_path or ""
    if os.path.basename(current_prompt_path) == filename:
        self.setting_changed.emit(
            "translator.high_quality_prompt_path",
            os.path.join("dict", target_filename).replace("\\", "/"),
        )

    self._refresh_prompt_manager()
    _select_prompt_item(self, target_filename)
    _set_prompt_status(self, "Renamed to: {filename}", filename=target_filename)


def delete_selected_prompt(self):
    """删除选中的提示词文件。"""
    filename = _get_selected_prompt_filename(self)
    if not filename:
        QMessageBox.warning(self, self._t("Warning"), self._t("Please select a prompt file first."))
        return

    current_prompt_path = self.config_service.get_config().translator.high_quality_prompt_path or ""
    was_active_prompt = os.path.basename(current_prompt_path) == filename

    reply = QMessageBox.question(
        self, self._t("Confirm Delete"),
        self._t("Are you sure you want to delete this prompt file?") + f"\n\n{filename}",
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        QMessageBox.StandardButton.No,
    )
    if reply != QMessageBox.StandardButton.Yes:
        return

    dict_dir = resource_path("dict")
    file_path = os.path.join(dict_dir, filename)
    try:
        if not os.path.exists(file_path):
            QMessageBox.warning(self, self._t("Warning"), self._t("Selected prompt file does not exist."))
            return
        os.remove(file_path)
    except Exception as e:
        QMessageBox.critical(self, self._t("Error"), str(e))
        return

    if was_active_prompt:
        self.setting_changed.emit("translator.high_quality_prompt_path", None)

    if hasattr(self, "prompt_preview_panel"):
        self.prompt_preview_panel.clear()
    self._refresh_prompt_manager()
    _set_prompt_status(self, "Deleted: {filename}", filename=filename)


def _get_selected_font_filename(self) -> str | None:
    current = self.font_list_widget.currentItem() if hasattr(self, "font_list_widget") else None
    if not current:
        return None
    filename = _get_asset_item_filename(current)
    return filename or None


def _select_font_item(self, filename: str):
    if not filename or not hasattr(self, "font_list_widget"):
        return
    item = _find_asset_item(self.font_list_widget, filename)
    if item:
        self.font_list_widget.setCurrentItem(item)


def import_fonts(self):
    """导入字体文件到 fonts 目录。"""
    fonts_dir = resource_path("fonts")
    os.makedirs(fonts_dir, exist_ok=True)

    file_filter = f"{self._t('Font Files')} (*.ttf *.otf *.ttc);;{self._t('All Files')} (*)"
    file_paths, _ = QFileDialog.getOpenFileNames(
        self,
        self._t("Select Font Files"),
        fonts_dir,
        file_filter,
    )
    if not file_paths:
        return

    imported: list[str] = []
    for source_path in file_paths:
        if not source_path:
            continue
        filename = os.path.basename(source_path)
        if not filename.lower().endswith(_FONT_EXTENSIONS):
            continue

        target_path = os.path.join(fonts_dir, filename)
        same_file = os.path.abspath(source_path) == os.path.abspath(target_path)
        if same_file:
            continue

        if os.path.exists(target_path):
            reply = QMessageBox.question(
                self,
                self._t("Confirm Overwrite"),
                self._t("File already exists. Overwrite?") + f"\n\n{filename}",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.Cancel:
                break
            if reply != QMessageBox.StandardButton.Yes:
                continue

        try:
            shutil.copy2(source_path, target_path)
        except Exception as e:
            QMessageBox.critical(self, self._t("Error"), str(e))
            return
        imported.append(filename)

    self._refresh_font_manager()
    if imported:
        _select_font_item(self, imported[-1])
        _set_font_status(self, "Imported {count} font files.", count=len(imported))
    else:
        _set_font_status(self, "No font files were imported.")


def delete_selected_font(self):
    """删除选中的字体文件。"""
    filename = _get_selected_font_filename(self)
    if not filename:
        QMessageBox.warning(self, self._t("Warning"), self._t("Please select a font file first."))
        return

    reply = QMessageBox.question(
        self,
        self._t("Confirm Delete"),
        self._t("Are you sure you want to delete this font file?") + f"\n\n{filename}",
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        QMessageBox.StandardButton.No,
    )
    if reply != QMessageBox.StandardButton.Yes:
        return

    font_path = os.path.join(resource_path("fonts"), filename)
    try:
        if not os.path.exists(font_path):
            QMessageBox.warning(self, self._t("Warning"), self._t("Selected font file does not exist."))
            return
        os.remove(font_path)
    except Exception as e:
        QMessageBox.critical(self, self._t("Error"), str(e))
        return

    from utils.font_list import font_family_for_file

    current_font = getattr(self.config_service.get_config().render, "font_family", "") or ""
    if current_font == filename or current_font == font_family_for_file(filename):
        self.setting_changed.emit("render.font_family", "")

    self._refresh_font_manager()
    _set_font_status(self, "Deleted: {filename}", filename=filename)


def refresh_font_manager(self):
    if not hasattr(self, "font_list_widget"):
        return
    font_files = []
    try:
        fonts_dir = resource_path("fonts")
        if os.path.isdir(fonts_dir):
            font_files = sorted([
                f for f in os.listdir(fonts_dir)
                if f.lower().endswith((".ttf", ".otf", ".ttc"))
            ])
    except Exception as e:
        print(f"Error scanning fonts directory: {e}")

    from utils.font_list import font_family_for_file

    selected_font = getattr(self.config_service.get_config().render, "font_family", "") or ""
    selected_font_file = ""
    for candidate in font_files:
        if selected_font in (candidate, font_family_for_file(candidate)):
            selected_font_file = candidate
            break
    selected_font = selected_font_file or selected_font
    current_item = self.font_list_widget.currentItem()
    current_font = _get_asset_item_filename(current_item)
    preferred_font = current_font or selected_font
    self.font_list_widget.blockSignals(True)
    self.font_list_widget.clear()
    for font_name in font_files:
        item = _create_asset_list_item(
            self,
            font_name,
            is_current=(font_name == selected_font),
            tooltip_text=self._t("Current font: {filename}", filename=font_name),
        )
        self.font_list_widget.addItem(item)
    self.font_list_widget.blockSignals(False)

    if preferred_font:
        matching_item = _find_asset_item(self.font_list_widget, preferred_font)
        if matching_item:
            self.font_list_widget.setCurrentItem(matching_item)
    else:
        self.font_list_widget.clearSelection()

    if not self.font_list_widget.currentItem():
        _on_font_selection_changed(self, None, None)
    _set_font_status(self, "Found {count} fonts.", count=len(font_files))


def apply_selected_font(self):
    current_item = self.font_list_widget.currentItem() if hasattr(self, "font_list_widget") else None
    if not current_item:
        return
    font_name = _get_asset_item_filename(current_item)
    if not font_name:
        return
    from utils.font_list import font_family_for_file

    self.setting_changed.emit("render.font_family", font_family_for_file(font_name) or font_name)
    self._refresh_font_manager()
    _set_font_status(self, "Current font: {filename}", filename=font_name)


def _on_font_selection_changed(self, current, previous):
    """字体选中变化时更新预览区域"""
    if not hasattr(self, "font_preview_labels"):
        return

    if not current:
        self._current_preview_font_path = None
        if hasattr(self, "font_preview_name_label"):
            self.font_preview_name_label.setText(self._t("Select a font to preview"))
        self._update_font_preview()
        return

    font_filename = _get_asset_item_filename(current)
    if not font_filename:
        return

    # 更新预览标题
    if hasattr(self, "font_preview_name_label"):
        self.font_preview_name_label.setText(font_filename)

    # 后端渲染按真实字体文件路径区分字体，预览也保存文件路径直接渲染 glyph。
    font_path = None
    try:
        fonts_dir = resource_path("fonts")
        font_path = os.path.join(fonts_dir, font_filename)
        if not os.path.isfile(font_path):
            font_path = None
    except Exception:
        font_path = None
        pass

    self._current_preview_font_path = font_path
    self._update_font_preview()


def _update_font_preview(self):
    """根据当前输入的自定义文本、滑块字号、以及选中的字体，动态更新预览文本和大小"""
    if not hasattr(self, "font_preview_labels"):
        return

    # 获取当前滑块的字号
    base_size = 18
    if hasattr(self, "font_preview_slider"):
        base_size = self.font_preview_slider.value()

    # 更新字号指示器
    if hasattr(self, "font_preview_size_indicator"):
        self.font_preview_size_indicator.setText(f"{base_size}pt")

    # 获取自定义输入内容
    custom_text = ""
    if hasattr(self, "font_preview_input"):
        custom_text = self.font_preview_input.text().strip()

    font_path = getattr(self, "_current_preview_font_path", None)

    # 预设的预览文本与缩放比例
    if custom_text:
        preview_texts = [custom_text, custom_text, custom_text]
        size_multipliers = [0.75, 1.1, 1.6]
    else:
        preview_texts = [
            "ABCDEFGHIJKLMNOPQRSTUVWXYZ abcdefghijklmnopqrstuvwxyz 0123456789",
            "你好世界，这是一段华丽的字体预览！ こんにちは 안녕하세요",
            "The quick brown fox jumps over the lazy dog",
        ]
        size_multipliers = [0.75, 1.1, 1.6]

    for i, lbl in enumerate(self.font_preview_labels):
        if i >= len(preview_texts):
            break
        text = preview_texts[i]
        size = max(8, int(round(base_size * size_multipliers[i])))
        
        pixmap = _render_font_preview_pixmap(font_path, text, size)
        if pixmap is not None and not pixmap.isNull():
            lbl.setStyleSheet("background: transparent;")
            lbl.setText("")
            lbl.setPixmap(pixmap)
            lbl.setMinimumSize(pixmap.size())
            continue

        lbl.clear()
        lbl.setMinimumSize(0, 0)
        lbl.setText(text)
        lbl.setStyleSheet(_font_preview_style(size))
        fallback_font = self.font()
        fallback_font.setPointSize(size)
        lbl.setFont(fallback_font)
