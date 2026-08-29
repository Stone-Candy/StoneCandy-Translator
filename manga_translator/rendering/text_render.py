import logging
import math
import os
import re
import sys
import threading
from collections import OrderedDict
from dataclasses import dataclass, field
from time import perf_counter
from typing import Optional, Tuple

import cv2
import numpy as np
from hyphen import Hyphenator
from hyphen.dictools import LANGUAGES as HYPHENATOR_LANGUAGES
from langcodes import standardize_tag
from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QColor, QFont, QFontDatabase, QFontMetricsF, QGuiApplication, QImage, QPainter, QPainterPath, QPainterPathStroker, QRawFont, QTextLayout, QTransform

from ..utils import BASE_PATH

try:
    HYPHENATOR_LANGUAGES.remove('fr')
    HYPHENATOR_LANGUAGES.append('fr_FR')
except Exception:
    pass

DEFAULT_FONT = os.path.join(BASE_PATH, 'fonts', 'Arial-Unicode-Regular.ttf')
DEFAULT_FONT_FAMILY = 'Microsoft YaHei UI'
FONT_STYLE_SEPARATOR = '::'
FONT_SIZE_STEP = 0.1


def quantize_font_size(value, minimum: float = 1.0) -> float:
    """Clamp and round font size to 0.1px."""
    try:
        font_size = float(value)
    except (TypeError, ValueError):
        font_size = float(minimum)
    return max(float(minimum), round(font_size / FONT_SIZE_STEP) * FONT_SIZE_STEP)


def _px(value, minimum: int = 0) -> int:
    """Integer pixel size for numpy/Qt APIs that reject floats."""
    try:
        return max(int(minimum), int(round(float(value))))
    except (TypeError, ValueError):
        return int(minimum)


FALLBACK_FONTS = [
    os.path.join(BASE_PATH, 'fonts/Arial-Unicode-Regular.ttf'),
    os.path.join(BASE_PATH, 'fonts/msyh.ttc'),
    os.path.join(BASE_PATH, 'fonts/msgothic.ttc'),
]
_H_BLOCK_RE = re.compile(r'(<H>.*?</H>)', re.IGNORECASE | re.DOTALL)
_BR_RE = re.compile(r'(?:\[BR\]|<br\s*/?>|【BR】|\r\n|\r|\n)', re.IGNORECASE)


def split_layout_lines(text: str) -> list:
    """Split on [BR]/newlines. Keep empty lines and surrounding spaces."""
    if not text:
        return []
    raw = _BR_RE.sub('\n', str(text))
    return re.sub(r'\r\n?|\n', '\n', raw).split('\n')


def join_layout_lines(lines) -> str:
    return '[BR]'.join(str(line) for line in (lines or []) if line is not None)


def strip_edge_layout_breaks(text: str) -> str:
    return join_layout_lines(split_layout_lines(text))
_HORIZONTAL_SYMBOL_HALFWIDTH_MAP = str.maketrans({'！': '!', '？': '?'})
_VERTICAL_OPEN_BRACKETS = {'「', '『', '（', '《', '〈', '【', '〔', '［', '｛', '(', '“', '‘', '﹁', '﹃', '︵', '︷', '︹', '︻', '︽', '︿', '﹇'}
_VERTICAL_CLOSE_BRACKETS = {'」', '』', '）', '》', '〉', '】', '〕', '］', '｝', ')', '”', '’', '﹂', '﹄', '︶', '︸', '︺', '︼', '︾', '﹀', '﹈'}
_VERTICAL_PUNCT_UP = {'。', '．', '，', '、', '·', '：', '；', '！', '？', '︒', '︐', '︑', '︓', '︔', '︕', '︖', '﹅', '﹆'}
_VERTICAL_COMPACT_SLOT = _VERTICAL_OPEN_BRACKETS | _VERTICAL_CLOSE_BRACKETS | _VERTICAL_PUNCT_UP
_VERTICAL_HALF_ADVANCE = _VERTICAL_OPEN_BRACKETS | _VERTICAL_CLOSE_BRACKETS

_VERTICAL_ALIGN_TOP_RIGHT = {'﹁', '﹃'}
_VERTICAL_ALIGN_BOTTOM_LEFT = {'﹂', '﹄'}
_VERTICAL_ALIGN_TOP_CENTER = {'︵', '︷', '︹', '︻', '︽', '︿', '﹇'}
_VERTICAL_ALIGN_BOTTOM_CENTER = {'︶', '︸', '︺', '︼', '︾', '﹀', '﹈'}


def _profile_add(profile_stats: Optional[dict], key: str, start_time: Optional[float]) -> None:
    if profile_stats is not None and start_time is not None:
        profile_stats[key] = profile_stats.get(key, 0.0) + (perf_counter() - start_time) * 1000.0

_QT_FONT_PROBE_SIZE = 32.0
_thread_state = threading.local()
_qt_runtime_lock = threading.Lock()
_qt_runtime_app = None
_font_descriptor_cache = {}
_font_registration_cache = {}
_font_families_cache = {}
_font_family_aliases = {}
_hyphenator_cache = {}
_system_fonts_registered = False
_RAW_FONT_CACHE_MAX = 128
_QFONT_CACHE_MAX = 192
_GLYPH_SPEC_CACHE_MAX = 4096
_GLYPH_RASTER_CACHE_MAX = 2048
_STROKE_CACHE_MAX = 1024
_VERTICAL_CACHE_MAX = 2048
logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())


@dataclass(frozen=True)
class GlyphSpec:
    raw_font: QRawFont
    glyph_id: int
    cache_key: Tuple


@dataclass(frozen=True)
class GlyphRaster:
    alpha: np.ndarray
    left: int
    top: int
    advance_x: int
    advance_y: int
    vert_bearing_y: int
    frame_width: int


@dataclass(frozen=True)
class LayoutFontDescriptor:
    family: str
    style: str = ''


@dataclass
class FontState:
    font: str = ''
    font_family: str = ''
    font_style: str = ''
    font_selection: list = field(default_factory=list)
    raw_fonts: dict = field(default_factory=OrderedDict)
    qfonts: dict = field(default_factory=OrderedDict)
    glyph_specs: dict = field(default_factory=OrderedDict)
    glyphs: dict = field(default_factory=OrderedDict)
    strokes: dict = field(default_factory=OrderedDict)
    measures: dict = field(default_factory=dict)
    vertical: dict = field(default_factory=OrderedDict)
    # 글자 가로폭 배율(1.0=원본). 측정/렌더가 동일 스레드 상태를 공유한다.
    char_width: float = 1.0
    # 박스 기하를 건드리지 않는 글리프 강조(합성 italic).
    italic: bool = False
    # QFont.setBold — 실제 Bold 페이스(없으면 엔진 합성). 경로 팽창이 아니다.
    bold: bool = False


def CJK_Compatibility_Forms_translate(cdpt: str, direction: int):
    """渲染层不再做字符替换，全部交给翻译后处理阶段。"""
    if cdpt == 'ー' and direction == 1:
        return 'ー', 90
    return cdpt, 0


def compact_special_symbols(text: str, *, convert_ascii_ellipsis: bool = True) -> str:
    # 渲染层不再做字符替换，统一交给外部的 text_replacements.yaml 规则处理
    return text or ''


def normalize_vertical_ellipsis_text(text: str) -> str:
    # 渲染层不再做字符替换，统一交给外部的 text_replacements.yaml 规则处理
    return text or ''


def auto_add_horizontal_tags(text: str) -> str:
    if not text or '<H>' in text or '<h>' in text.lower():
        return text

    br_tokens = []

    def _mask_br(match):
        br_tokens.append(match.group(0))
        return chr(0xE000 + len(br_tokens) - 1)

    seg = _BR_RE.sub(_mask_br, text)
    word_chars = r'a-zA-Z0-9\uff21-\uff3a\uff41-\uff5a\uff10-\uff19_-'
    seg = re.sub(fr'[{word_chars}]+(?:\s+[{word_chars}]+)+', r'<H>\g<0></H>', seg)

    def _wrap_word(match):
        prefix = seg[:match.start()]
        if prefix.rfind('<H>') > prefix.rfind('</H>'):
            return match.group(0)
        return f'<H>{match.group(1)}</H>'

    seg = re.sub(fr'(?<![{word_chars}])([{word_chars}]{{2,}})(?![{word_chars}])', _wrap_word, seg)
    seg = re.sub(r'[!?！？]{2,4}', r'<H>\g<0></H>', seg)
    for i, token in enumerate(br_tokens):
        seg = seg.replace(chr(0xE000 + i), token)
    pair_re = re.compile(r'<H>([!?！？]{2,4})</H>\s*(\r\n|\r|\n|\[BR\]|<br\s*/?>|【BR】)\s*<H>([!?！？]{2,4})</H>', re.IGNORECASE)
    while True:
        updated = pair_re.sub(lambda m: f'{m.group(1)}{m.group(2)}{m.group(3)}', seg)
        if updated == seg:
            break
        seg = updated
    merge_re = re.compile(
        r'<H>([a-zA-Z0-9\uff21-\uff3a\uff41-\uff5a\uff10-\uff19]+)</H>\s*(?:\r\n|\r|\n|\[BR\]|<br\s*/?>|【BR】)\s*<H>([a-zA-Z0-9\uff21-\uff3a\uff41-\uff5a\uff10-\uff19]+)</H>',
        re.IGNORECASE,
    )
    while True:
        updated = merge_re.sub(r'<H>\1[BR]\2</H>', seg)
        if updated == seg:
            break
        seg = updated
    seg = re.sub(
        r'(?<![a-zA-Z0-9\uff21-\uff3a\uff41-\uff5a\uff10-\uff19])([a-zA-Z0-9\uff21-\uff3a\uff41-\uff5a\uff10-\uff19])\s*(?:\r\n|\r|\n|\[BR\]|<br\s*/?>|【BR】)\s*([a-zA-Z0-9\uff21-\uff3a\uff41-\uff5a\uff10-\uff19])(?![a-zA-Z0-9\uff21-\uff3a\uff41-\uff5a\uff10-\uff19])',
        r'<H>\1[BR]\2</H>',
        seg,
        flags=re.IGNORECASE,
    )
    return re.sub(
        r'<H>(.*?)</H>',
        lambda m: f"<H>{m.group(1).replace(chr(13)+chr(10), '[BR]').replace(chr(13), '[BR]').replace(chr(10), '[BR]')}</H>",
        seg,
        flags=re.IGNORECASE | re.DOTALL,
    )


def _normalize_horizontal_block_content(content: str) -> str:
    content = _BR_RE.sub('', content or '').replace('\r', '').replace('\n', '')
    return content.translate(_HORIZONTAL_SYMBOL_HALFWIDTH_MAP) if re.fullmatch(r'[!?！？]+', content) else content


def prepare_text_for_direction_rendering(text: str, is_horizontal: bool, auto_rotate_symbols: bool = False) -> str:
    text = text or ''
    if is_horizontal:
        return re.sub(r'<H>(.*?)</H>', r'\1', text, flags=re.IGNORECASE | re.DOTALL)
    _ = auto_rotate_symbols
    return text


def _convert_br_outside_h_tags(text: str) -> str:
    converted = []
    for part in _H_BLOCK_RE.split(text or ''):
        if not part:
            continue
        if part.lower().startswith('<h>') and part.lower().endswith('</h>'):
            chunks = [c for c in _BR_RE.split(part[3:-4]) if c]
            normalized = [f'<H>{clean}</H>' for clean in (_normalize_horizontal_block_content(c) for c in chunks) if clean]
            converted.append('\n'.join(normalized) or part)
        else:
            converted.append(_BR_RE.sub('\n', part))
    return ''.join(converted)


def should_rotate_horizontal_block_90(content: str) -> bool:
    content = _normalize_horizontal_block_content(content).strip()
    return bool(content and re.fullmatch(r'[a-zA-Z0-9\uff21-\uff3a\uff41-\uff5a\uff10-\uff19_-]+(?:[ \t]+[a-zA-Z0-9\uff21-\uff3a\uff41-\uff5a\uff10-\uff19_-]+)*', content))


def add_color(bw_char_map, color, stroke_char_map, stroke_color):
    """合成文字和描边为 RGBA 图层。

    关键做法（解决灰边/脏边）：
    1. 强制 stroke_alpha = max(stroke_alpha, text_alpha)，保证描边在空间上完全
       覆盖文字的所有抗锯齿像素，消除因两次独立光栅化造成的对齐偏差。
    2. 将描边视作文字的"底色"，抗锯齿过渡像素直接在描边纯色上混合，而不是
       两个半透明层的 over 叠加 —— 这是原来灰边的根源。
    3. 全程 float32 计算 + np.clip，避免 uint8 溢出导致的脏点。
    """
    H, W = bw_char_map.shape[:2]
    if bw_char_map.size == 0:
        return np.zeros((H, W, 4), dtype=np.uint8)

    out = np.zeros((H, W, 4), dtype=np.uint8)
    color_arr = np.asarray(color, dtype=np.float32).reshape(1, 1, 3)

    # 无描边：直接输出文字图层
    if stroke_color is None or stroke_char_map is None:
        out[:, :, :3] = np.clip(color_arr, 0, 255).astype(np.uint8)
        out[:, :, 3] = bw_char_map
        return out

    stroke_color_arr = np.asarray(stroke_color, dtype=np.float32).reshape(1, 1, 3)

    # 1) 强制 stroke_alpha >= text_alpha —— 关键修复
    text_alpha_u8 = bw_char_map
    stroke_alpha_u8 = np.maximum(stroke_char_map, text_alpha_u8)

    # 2) 文字在描边纯色底上混合（局部不透明，无半透明层叠加）
    text_af = (text_alpha_u8.astype(np.float32) / 255.0)[:, :, None]
    rgb = color_arr * text_af + stroke_color_arr * (1.0 - text_af)

    out[:, :, :3] = np.clip(rgb, 0, 255).astype(np.uint8)
    out[:, :, 3] = stroke_alpha_u8
    return out


_EDGE_WHITESPACE = ' \t\u00a0\u3000'


def _edge_whitespace_widths(text: str, font_size: int, letter_spacing: float = 1.0) -> Tuple[float, float]:
    """Advance of leading/trailing spaces. Space-only text is treated as leading."""
    if not text:
        return 0.0, 0.0
    if not str(text).strip(_EDGE_WHITESPACE):
        return float(_measure_horizontal_text_width(text, font_size, letter_spacing)), 0.0
    lead_n = len(text) - len(text.lstrip(_EDGE_WHITESPACE))
    trail_n = len(text) - len(text.rstrip(_EDGE_WHITESPACE))
    lead_w = _measure_horizontal_text_width(text[:lead_n], font_size, letter_spacing) if lead_n else 0
    trail_w = _measure_horizontal_text_width(text[len(text) - trail_n:], font_size, letter_spacing) if trail_n else 0
    return float(lead_w), float(trail_w)


def _crop_and_color(
    canvas_text: np.ndarray,
    canvas_border: np.ndarray,
    fg,
    bg,
    keep_left=None,
    keep_right=None,
    keep_top=None,
    keep_bottom=None,
):
    """按有效 alpha 区域裁剪后再上色，避免给大面积透明 padding 做无用合成。

    keep_* 는 유저 스페이스 폭처럼 남겨야 하는 논리 박스다. 캔버스 가터만
    자르고 그 안쪽 투명 여백은 유지한다.
    """
    combined = cv2.add(canvas_text, canvas_border)
    x, y, w, h = cv2.boundingRect(combined)
    if w == 0 or h == 0:
        return None
    x2, y2 = x + w, y + h
    if keep_left is not None:
        x = min(x, int(round(keep_left)))
    if keep_top is not None:
        y = min(y, int(round(keep_top)))
    if keep_right is not None:
        x2 = max(x2, int(round(keep_right)))
    if keep_bottom is not None:
        y2 = max(y2, int(round(keep_bottom)))
    x = max(0, x)
    y = max(0, y)
    x2 = min(canvas_text.shape[1], x2)
    y2 = min(canvas_text.shape[0], y2)
    w, h = x2 - x, y2 - y
    if w <= 0 or h <= 0:
        return None
    text_crop = canvas_text[y:y + h, x:x + w]
    border_crop = canvas_border[y:y + h, x:x + w]
    return add_color(text_crop, fg, border_crop, bg)


def _bootstrap_qt_fontdir_for_offscreen() -> None:
    """Help Qt's offscreen/freetype font database find bundled fonts.

    Qt's offscreen plugin may rely on QT_QPA_FONTDIR or Qt6/lib/fonts. Our
    packaged fonts live under the project fonts/ directory, so expose that as a
    default font directory when running in offscreen mode and the caller did not
    already provide one.
    """
    if os.environ.get('QT_QPA_FONTDIR'):
        return
    if os.environ.get('QT_QPA_PLATFORM') != 'offscreen':
        return
    font_dir = os.path.join(BASE_PATH, 'fonts')
    if os.path.isdir(font_dir):
        os.environ['QT_QPA_FONTDIR'] = font_dir
        logger.info('Using bundled fonts for Qt offscreen mode: %s', font_dir)


def _ensure_qt_runtime():
    global _qt_runtime_app
    app = QGuiApplication.instance()
    if app is not None:
        return app
    with _qt_runtime_lock:
        app = QGuiApplication.instance()
        if app is None:
            os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
            _bootstrap_qt_fontdir_for_offscreen()
            _qt_runtime_app = QGuiApplication([])
            return _qt_runtime_app
        return app


def _normalize_font_path(path: str) -> str:
    return path.replace('\\', '/')


def _cache_get(cache: dict, key):
    if key not in cache:
        return None
    value = cache.pop(key)
    cache[key] = value
    return value


def _cache_put(cache: dict, key, value, max_entries: int):
    if key in cache:
        cache.pop(key)
    cache[key] = value
    while len(cache) > max_entries:
        cache.popitem(last=False)
    return value


def _clear_shape_caches(state: FontState):
    state.glyph_specs.clear()
    state.glyphs.clear()
    state.strokes.clear()
    state.measures.clear()
    state.vertical.clear()


def _resolve_existing_font_path(path: str) -> str:
    if not path:
        return ''
    path = _normalize_font_path(path)
    candidates = [path]
    if not os.path.isabs(path):
        candidates.extend([
            _normalize_font_path(os.path.join(BASE_PATH, 'fonts', os.path.basename(path))),
            _normalize_font_path(os.path.join(BASE_PATH, path)),
        ])
    return next((candidate for candidate in candidates if candidate and os.path.exists(candidate)), '')


def _font_registration_key(path: str) -> str:
    return _normalize_font_path(os.path.normcase(os.path.abspath(path)))


_QT_FOUNDRY_SENSITIVE_NAME_IDS = (1, 3, 4, 16, 21)


def qt_family_is_ambiguous(family: str) -> bool:
    """Return True when Qt's "Family [Foundry]" parsing yields an empty family."""
    name = (family or '').strip()
    return name.startswith('[') and name.rfind(']') > 0


def strip_qt_foundry_brackets(family: str) -> str:
    return (family or '').replace('[', '').replace(']', '').strip()


def _sanitized_font_bytes(path: str):
    if not path.lower().endswith(('.ttf', '.otf')):
        return None, []
    try:
        import io
        from fontTools.ttLib import TTFont
    except ImportError:
        logger.warning('fontTools unavailable; cannot rewrite bracketed font names: %s', path)
        return None, []
    try:
        font = TTFont(path, lazy=True)
        try:
            name_table = font['name']
            changed = False
            original_names = []
            for record in name_table.names:
                if record.nameID not in _QT_FOUNDRY_SENSITIVE_NAME_IDS:
                    continue
                try:
                    value = record.toUnicode()
                except UnicodeDecodeError:
                    continue
                if record.nameID in (1, 4, 16) and value:
                    original_names.append(value)
                if '[' in value or ']' in value:
                    record.string = strip_qt_foundry_brackets(value)
                    changed = True
            if not changed:
                return None, []
            en_family = name_table.getName(1, 3, 1, 0x409)
            if en_family is not None and name_table.getName(16, 3, 1, 0x409) is None:
                name_table.setName(en_family.toUnicode(), 16, 3, 1, 0x409)
            if 'DSIG' in font:
                del font['DSIG']
            buffer = io.BytesIO()
            font.save(buffer)
            return buffer.getvalue(), original_names
        finally:
            font.close()
    except Exception:
        logger.exception('Failed to sanitize font name table: %s', path)
        return None, []


def register_font_file(path: str) -> list:
    """Register a font file and return families that are safe for QFont matching."""
    key = _font_registration_key(path)
    cached = _font_families_cache.get(key)
    if cached is not None:
        return cached
    if QGuiApplication.instance() is None:
        return []

    families = []
    font_id = -1
    try:
        font_id = QFontDatabase.addApplicationFont(path)
        families = list(QFontDatabase.applicationFontFamilies(font_id)) if font_id >= 0 else []
        if any(qt_family_is_ambiguous(name) for name in families):
            sanitized, original_names = _sanitized_font_bytes(path)
            if sanitized is not None:
                QFontDatabase.removeApplicationFont(font_id)
                font_id = QFontDatabase.addApplicationFontFromData(sanitized)
                families = list(QFontDatabase.applicationFontFamilies(font_id)) if font_id >= 0 else []
                if font_id >= 0:
                    for name in original_names:
                        for variant in (name, strip_qt_foundry_brackets(name)):
                            if variant:
                                _font_family_aliases.setdefault(variant.casefold(), path)
                logger.info(
                    'Registered bracketed font with sanitized families: %s -> %s',
                    os.path.basename(path), families,
                )
            else:
                logger.warning(
                    'Font family uses Qt foundry brackets and could not be rewritten; '
                    'QFont matching may pick a wrong font: %s', path,
                )
    except Exception:
        logger.exception('Failed to register font: %s', path)

    families = [name for name in families if name and not qt_family_is_ambiguous(name)]
    _font_registration_cache[key] = font_id
    _font_families_cache[key] = families
    return families


def _register_project_fonts() -> None:
    font_dir = os.path.join(BASE_PATH, 'fonts')
    if not os.path.isdir(font_dir):
        return
    for root, _, filenames in os.walk(font_dir):
        for filename in filenames:
            if not filename.lower().endswith(('.ttf', '.otf', '.ttc', '.pfb')):
                continue
            register_font_file(os.path.join(root, filename))


def _system_font_dirs() -> list:
    if sys.platform == 'win32':
        dirs = [os.path.join(os.environ.get('WINDIR', r'C:\Windows'), 'Fonts')]
        local_appdata = os.environ.get('LOCALAPPDATA')
        if local_appdata:
            dirs.append(os.path.join(local_appdata, 'Microsoft', 'Windows', 'Fonts'))
    elif sys.platform == 'darwin':
        dirs = ['/System/Library/Fonts', '/Library/Fonts', os.path.expanduser('~/Library/Fonts')]
    else:
        dirs = [
            '/usr/share/fonts',
            '/usr/local/share/fonts',
            os.path.expanduser('~/.local/share/fonts'),
            os.path.expanduser('~/.fonts'),
        ]
    return [font_dir for font_dir in dirs if os.path.isdir(font_dir)]


def _register_system_fonts() -> bool:
    """Headless Qt does not enumerate installed fonts; register them once."""
    global _system_fonts_registered
    if _system_fonts_registered:
        return False
    _system_fonts_registered = True
    app = QGuiApplication.instance()
    if app is None or app.platformName() not in ('offscreen', 'minimal'):
        return False
    count = 0
    for font_dir in _system_font_dirs():
        for root, _, filenames in os.walk(font_dir):
            for filename in filenames:
                if not filename.lower().endswith(('.ttf', '.otf', '.ttc', '.otc')):
                    continue
                register_font_file(os.path.join(root, filename))
                count += 1
    logger.info('Registered system fonts for headless Qt: %d files', count)
    return count > 0


def _split_font_value(value: str) -> tuple:
    family, separator, style = str(value or '').rpartition(FONT_STYLE_SEPARATOR)
    if separator and family and style:
        return family, style
    return str(value or ''), ''


def region_font_value(obj, fallback: str = '') -> str:
    """Read the font family from a region object or dict."""
    if obj is None:
        return fallback or ''
    if isinstance(obj, dict):
        return str(obj.get('font_family') or fallback or '')
    return str(getattr(obj, 'font_family', '') or fallback or '')


def _state() -> FontState:
    state = getattr(_thread_state, 'value', None)
    if state is None:
        state = FontState()
        _thread_state.value = state
        set_font(DEFAULT_FONT_FAMILY)
    return _thread_state.value


def _raw_font(path: str, pixel_size: float) -> QRawFont:
    state = _state()
    _ensure_qt_runtime()
    norm_path = _normalize_font_path(path)
    pixel_size = float(max(pixel_size, 1.0))
    key = (norm_path, pixel_size)
    font = _cache_get(state.raw_fonts, key)
    if font is not None:
        return font
    # 复用已有实例：找同路径任意 size 的 font，拷贝后 setPixelSize
    for cached_key in reversed(state.raw_fonts):
        if cached_key[0] == norm_path:
            base = state.raw_fonts[cached_key]
            font = QRawFont(base)
            font.setPixelSize(pixel_size)
            return _cache_put(state.raw_fonts, key, font, _RAW_FONT_CACHE_MAX)
    # 首次加载：从文件创建
    font = QRawFont(norm_path, pixel_size)
    if not font.isValid():
        raise RuntimeError(f'Could not load Qt font: {norm_path}')
    return _cache_put(state.raw_fonts, key, font, _RAW_FONT_CACHE_MAX)


def _font_descriptor(path: str) -> LayoutFontDescriptor:
    _ensure_qt_runtime()
    path = _normalize_font_path(path)
    descriptor = _font_descriptor_cache.get(path)
    if descriptor:
        return descriptor

    registered_families = register_font_file(path)

    family = ''
    style = ''
    try:
        raw = _raw_font(path, _QT_FONT_PROBE_SIZE)
        if raw.isValid():
            family = raw.familyName() or ''
            style = raw.styleName() or ''
    except Exception:
        pass

    if (not family or qt_family_is_ambiguous(family)) and registered_families:
        family = registered_families[0]

    if not family:
        raw = QRawFont(path, _QT_FONT_PROBE_SIZE)
        if raw.isValid():
            family = raw.familyName() or ''
            style = style or raw.styleName() or ''

    if not family:
        raise RuntimeError(f'Could not resolve Qt font family: {path}')
    if qt_family_is_ambiguous(family):
        logger.warning('Bracketed font family may not match correctly in Qt: %s (%s)', family, path)
    descriptor = LayoutFontDescriptor(family=family, style=style)
    _font_descriptor_cache[path] = descriptor
    return descriptor


def _refresh_font_selection(state: FontState):
    selection = [state.font] if state.font else []
    for font_path in FALLBACK_FONTS:
        try:
            resolved = _resolve_existing_font_path(font_path)
            if resolved:
                _raw_font(resolved, _QT_FONT_PROBE_SIZE)
                if resolved not in selection:
                    selection.append(resolved)
        except Exception as exc:
            logger.error(f'Failed to load fallback font: {font_path} - {exc}')
    if selection != state.font_selection:
        state.font_selection = selection
        state.qfonts.clear()
        # glyph_specs/glyphs/strokes 的 key 含字体路径，切换字体时无需清空，
        # 保留缓存避免重复解析大字体文件的字形数据
        state.measures.clear()
        state.vertical.clear()


def _set_family(state: FontState, family: str, style: str = ''):
    if state.font_family == family and state.font_style == style:
        return
    state.font_family = family
    state.font_style = style
    state.qfonts.clear()
    state.measures.clear()
    state.vertical.clear()


def _match_family(requested: str):
    if not requested:
        return None
    available = {name.casefold(): name for name in QFontDatabase.families()}
    family = available.get(requested.casefold())
    if family is None or qt_family_is_ambiguous(family):
        stripped = strip_qt_foundry_brackets(requested)
        stripped_family = available.get(stripped.casefold()) if stripped else None
        if stripped_family and not qt_family_is_ambiguous(stripped_family):
            return stripped_family
        alias_path = _font_family_aliases.get(requested.casefold()) or (
            _font_family_aliases.get(stripped.casefold()) if stripped else None)
        if alias_path and os.path.exists(alias_path):
            try:
                return _font_descriptor(alias_path).family
            except Exception:
                logger.exception('Could not load font file: %s', alias_path)
    return family


def set_font(font: str):
    """Select a Qt family/style. A project font file path is mapped to its face."""
    state = getattr(_thread_state, 'value', None) or FontState()
    _thread_state.value = state
    requested = str(font or '').strip()
    resolved = _resolve_existing_font_path(requested)
    if resolved:
        try:
            descriptor = _font_descriptor(resolved)
            _set_family(state, descriptor.family, descriptor.style)
            state.font = resolved
            _refresh_font_selection(state)
            return
        except Exception:
            logger.exception('Could not load font file: %s', resolved)

    _ensure_qt_runtime()
    _register_project_fonts()
    requested_family, requested_style = _split_font_value(requested)
    family = _match_family(requested_family)
    if family is None and requested and _register_system_fonts():
        family = _match_family(requested_family)
    if family is not None and qt_family_is_ambiguous(family):
        logger.warning('Bracketed font family may not match correctly in Qt: %s', family)
    if family is None:
        family = DEFAULT_FONT_FAMILY
        if requested:
            logger.warning('Qt font family not found: %s; using %s', requested, family)
        fallback_path = _resolve_existing_font_path(DEFAULT_FONT)
        if fallback_path:
            try:
                descriptor = _font_descriptor(fallback_path)
                family = descriptor.family or family
                if not requested_style:
                    requested_style = descriptor.style
                state.font = fallback_path
                _set_family(state, family, requested_style)
                _refresh_font_selection(state)
                return
            except Exception:
                logger.exception('Could not load default font file: %s', fallback_path)
    _set_family(state, family, requested_style)
    state.font = ''
    state.font_selection = []


def load_font_file(path: str) -> str:
    """Register a font file and return its Qt family without persisting the path."""
    resolved = _resolve_existing_font_path(path)
    if not resolved:
        raise FileNotFoundError(path)
    return _font_descriptor(resolved).family


def _layout_font(font_size: int, letter_spacing: float) -> QFont:
    state = _state()
    family = state.font_family or DEFAULT_FONT_FAMILY
    style = state.font_style
    pixel_size = max(1, int(round(float(font_size))))
    bold = bool(getattr(state, 'bold', False))
    key = (family, style, bold, pixel_size, round(float(letter_spacing), 4))
    qfont = _cache_get(state.qfonts, key)
    if qfont is None:
        qfont = QFontDatabase.font(family, style, 12) if style else QFont()
        if not style:
            qfont.setFamilies([family])
        if bold or not style:
            qfont.setBold(bold)
        qfont.setPixelSize(pixel_size)
        qfont.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
        qfont.setStyleStrategy(QFont.StyleStrategy.PreferOutline)
        qfont.setKerning(True)
        qfont.setLetterSpacing(QFont.SpacingType.PercentageSpacing, float(letter_spacing) * 100.0)
        _cache_put(state.qfonts, key, qfont, _QFONT_CACHE_MAX)
    return QFont(qfont)


def _create_text_layout(text: str, font_size: int, letter_spacing: float = 1.0):
    qfont = _layout_font(font_size, letter_spacing)
    if not text:
        return text, qfont, None, None
    layout = QTextLayout(text, qfont)
    layout.beginLayout()
    line = layout.createLine()
    if not line.isValid():
        layout.endLayout()
        return text, qfont, None, None
    line.setLineWidth(1_000_000.0)
    line.setPosition(QPointF(0.0, 0.0))
    layout.endLayout()
    return text, qfont, layout, line


def _font_supports_character(raw_font: QRawFont, cdpt: str) -> bool:
    try:
        return bool(raw_font.supportsCharacter(cdpt))
    except Exception:
        return True


def _glyph_has_advance(raw_font: QRawFont, glyph_id: int) -> bool:
    if not glyph_id:
        return False
    try:
        advances = raw_font.advancesForGlyphIndexes([glyph_id])
    except Exception:
        return False
    return bool(advances and (advances[0].x() or advances[0].y()))


def _glyph_renderable(raw_font: QRawFont, glyph_id: int, cdpt: str = '') -> bool:
    if not glyph_id:
        return False
    if cdpt.isspace() and _glyph_has_advance(raw_font, glyph_id):
        return True
    try:
        if not raw_font.pathForGlyph(glyph_id).isEmpty():
            return True
    except Exception:
        pass
    try:
        alpha = raw_font.alphaMapForGlyph(glyph_id)
        return not alpha.isNull() and alpha.width() > 0 and alpha.height() > 0
    except Exception:
        return False


def _raw_font_key(raw_font: QRawFont) -> Tuple[str, str, str]:
    try:
        family = raw_font.familyName() or ''
    except Exception:
        family = ''
    try:
        style = raw_font.styleName() or ''
    except Exception:
        style = ''
    try:
        weight = raw_font.weight()
        weight = getattr(weight, 'value', weight)
        weight = str(int(weight))
    except Exception:
        weight = ''
    return family, style, weight


def _glyph_spec_via_layout(cdpt: str, font_size: int) -> Optional[GlyphSpec]:
    _, _, layout, _ = _create_text_layout(cdpt, font_size, 1.0)
    if layout is None:
        return None
    whitespace = None
    for run in layout.glyphRuns():
        raw_font = run.rawFont()
        for glyph_id in run.glyphIndexes():
            if _glyph_renderable(raw_font, glyph_id, cdpt):
                return GlyphSpec(raw_font, int(glyph_id), ('qt-layout',) + _raw_font_key(raw_font))
            if whitespace is None and cdpt.isspace() and _glyph_has_advance(raw_font, glyph_id):
                whitespace = GlyphSpec(raw_font, int(glyph_id), ('qt-layout',) + _raw_font_key(raw_font))
    return whitespace


def _glyph_spec_from_selection(cdpt: str, font_size: int) -> Optional[GlyphSpec]:
    state = _state()
    for path in state.font_selection:
        raw_font = _raw_font(path, font_size)
        # Avoid raw_font.supportsCharacter() because it freezes on some fonts
        glyphs = raw_font.glyphIndexesForString(cdpt)
        glyph_id = glyphs[0] if glyphs else 0
        # glyph_id > 0 足以判断字体支持该字符，跳过 _glyph_renderable 避免
        # 对复杂字形调 pathForGlyph 导致首次渲染极慢
        if glyph_id > 0:
            return GlyphSpec(raw_font, int(glyph_id), ('font-path', _normalize_font_path(path)))
        # Space character might legitimately have glyph_id == 0 or map to advance
        if glyph_id == 0 and cdpt.isspace() and _glyph_has_advance(raw_font, glyph_id):
            return GlyphSpec(raw_font, int(glyph_id), ('font-path', _normalize_font_path(path)))
    return None


def _glyph_spec(cdpt: str, font_size: int) -> GlyphSpec:
    state = _state()
    # 缓存 key 含当前字体家族，避免切换字体后命中旧缓存
    key = (cdpt, quantize_font_size(font_size), state.font_family, state.font_style, bool(getattr(state, 'bold', False)))
    cached = _cache_get(state.glyph_specs, key)
    if cached is not None:
        return cached
    spec = _glyph_spec_via_layout(cdpt, font_size) or _glyph_spec_from_selection(cdpt, font_size)
    if spec is None:
        if cdpt in (' ', '?', '□'):
            raise RuntimeError(f"Character '{cdpt}' not found in any font.")
        for placeholder in ('?', '□', ' '):
            if placeholder != cdpt:
                try:
                    spec = _glyph_spec(placeholder, font_size)
                    break
                except RuntimeError:
                    continue
    if spec is None:
        raise RuntimeError('No placeholder character found in any font.')
    return _cache_put(state.glyph_specs, key, spec, _GLYPH_SPEC_CACHE_MAX)


def _qimage_alpha_to_array(image: QImage) -> np.ndarray:
    ptr = image.bits()
    ptr.setsize(image.sizeInBytes())
    arr = np.frombuffer(ptr, dtype=np.uint8).reshape((image.height(), image.bytesPerLine() // 4, 4))
    return arr[:, :image.width(), 3].copy()


def _rasterize_path(path: QPainterPath, supersample: float = 1.0) -> Tuple[np.ndarray, int, int]:
    if path.isEmpty():
        return np.zeros((0, 0), dtype=np.uint8), 0, 0
    ss = float(supersample) if supersample and supersample > 0 else 1.0
    if abs(ss - 1.0) >= 1e-6:
        transform = QTransform()
        transform.scale(ss, ss)
        mapped = transform.map(path)
        mapped.setFillRule(path.fillRule())
        path = mapped
    rect = path.boundingRect()
    left, top = math.floor(rect.left()), math.floor(rect.top())
    width = max(0, math.ceil(rect.right()) - left)
    height = max(0, math.ceil(rect.bottom()) - top)
    if width <= 0 or height <= 0:
        return np.zeros((0, 0), dtype=np.uint8), left, top
    image = QImage(width, height, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(0)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(255, 255, 255, 255))
    painter.translate(-left, -top)
    painter.drawPath(path)
    painter.end()
    return _qimage_alpha_to_array(image), left, top


def _stroke_path(path: QPainterPath, stroke_px: int) -> QPainterPath:
    if path.isEmpty() or stroke_px <= 0:
        return QPainterPath()
    stroker = QPainterPathStroker()
    stroker.setWidth(float(stroke_px * 2))
    stroker.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    stroker.setCapStyle(Qt.PenCapStyle.RoundCap)
    # 不要使用 subtracted(path)，否则会导致内部中空，在抗锯齿边缘产生脏边
    return stroker.createStroke(path).united(path)


def _glyph_raster(cdpt: str, font_size: int) -> GlyphRaster:
    font_size = quantize_font_size(font_size)
    spec = _glyph_spec(cdpt, font_size)
    state = _state()
    italic = get_text_emphasis()
    key = (spec.cache_key, spec.glyph_id, font_size, italic, get_bold())
    cached = _cache_get(state.glyphs, key)
    if cached is not None:
        return cached
    raw_font = spec.raw_font
    if abs(float(raw_font.pixelSize()) - font_size) > 0.049:
        raw_font = QRawFont(raw_font)
        raw_font.setPixelSize(font_size)
    path = _apply_emphasis_to_path(raw_font.pathForGlyph(spec.glyph_id), font_size)
    alpha, left, top = _rasterize_path(path)
    advances = raw_font.advancesForGlyphIndexes([spec.glyph_id]) if spec.glyph_id else []
    advance = advances[0] if advances else QPointF(float(font_size), float(font_size))
    metrics = path.boundingRect()
    fallback = _px(font_size, 1)
    advance_x = int(round(advance.x())) if advance.x() else max(int(round(metrics.width())), fallback)
    advance_y = int(round(advance.y())) if advance.y() else max(int(round(metrics.height())), fallback)
    raster = GlyphRaster(alpha, int(left), int(-top), int(advance_x), int(advance_y), int(top), max(int(round(metrics.width())), int(advance_x), 1))
    return _cache_put(state.glyphs, key, raster, _GLYPH_RASTER_CACHE_MAX)


def _glyph_stroke_alpha(cdpt: str, font_size: int, stroke_ratio: float) -> np.ndarray:
    spec = _glyph_spec(cdpt, font_size)
    state = _state()
    key = (spec.cache_key, spec.glyph_id, quantize_font_size(font_size), round(float(stroke_ratio), 4), get_text_emphasis(), get_bold())
    cached = _cache_get(state.strokes, key)
    if cached is not None:
        return cached
    raster = _glyph_raster(cdpt, font_size)
    if raster.alpha.size == 0:
        return _cache_put(state.strokes, key, np.zeros((0, 0), dtype=np.uint8), _STROKE_CACHE_MAX)
    stroke_px = max(int(stroke_ratio * font_size), 1)
    # 距离变换描边：比椭圆膨胀更贴合字形轮廓，比矢量路径描边快得多。
    # 原理：对二值化 alpha 图计算每像素到最近前景像素的欧氏距离，
    # 距离 <= stroke_px 的区域即为描边，再用原始 alpha 做抗锯齿过渡。
    src = raster.alpha
    pad = stroke_px + 1
    padded = cv2.copyMakeBorder(src, pad, pad, pad, pad, cv2.BORDER_CONSTANT, value=0)
    # 前景 mask（二值化，阈值 128 避免抗锯齿半透明像素干扰距离计算）
    fg_mask = (padded >= 128).astype(np.uint8) * 255
    # 对背景像素计算到最近前景的距离
    bg_mask = cv2.bitwise_not(fg_mask)
    dist = cv2.distanceTransform(bg_mask, cv2.DIST_L2, cv2.DIST_MASK_PRECISE)
    # 描边区域：距离 <= stroke_px，平滑过渡避免硬边
    stroke_region = np.clip((stroke_px + 0.5 - dist), 0.0, 1.0)
    stroke_alpha = (stroke_region * 255).astype(np.uint8)
    # 合并描边与原始 alpha（保留文字内部抗锯齿），保留 padding 以包含扩展区域
    full_alpha = np.maximum(stroke_alpha, padded)
    nz = cv2.findNonZero(full_alpha)
    if nz is None:
        return _cache_put(state.strokes, key, np.zeros((0, 0), dtype=np.uint8), _STROKE_CACHE_MAX)
    x, y, w, h = cv2.boundingRect(nz)
    result = full_alpha[y:y + h, x:x + w]
    return _cache_put(state.strokes, key, result, _STROKE_CACHE_MAX)


def _paste_bitmap(canvas: np.ndarray, bitmap_arr: np.ndarray, x: int, y: int, mode: str = 'max'):
    if bitmap_arr is None or bitmap_arr.size == 0:
        return
    rows, width = bitmap_arr.shape
    x2, y2 = x + width, y + rows
    sx1, sy1, sx2, sy2 = max(0, x), max(0, y), min(canvas.shape[1], x2), min(canvas.shape[0], y2)
    if sx1 >= sx2 or sy1 >= sy2:
        return
    bx1, by1 = sx1 - x, sy1 - y
    bitmap = bitmap_arr[by1:by1 + (sy2 - sy1), bx1:bx1 + (sx2 - sx1)]
    target = canvas[sy1:sy2, sx1:sx2]
    if mode == 'add':
        # 使用 cv2.add 避免 numpy uint8 加法溢出导致的脏斑点
        cv2.add(target, bitmap, dst=target)
    else:
        np.maximum(target, bitmap, out=target)


def _paste_surface(canvas_text: np.ndarray, canvas_border: np.ndarray, surface: dict, x: int, y: int):
    _paste_bitmap(canvas_text, surface['text'], int(round(x)), int(round(y)))
    _paste_bitmap(canvas_border, surface['border'], int(round(x)), int(round(y)))


def _paste_glyph_pair(
    canvas_text: np.ndarray,
    canvas_border: np.ndarray,
    bitmap_char: np.ndarray,
    draw_x: int,
    draw_y: int,
    bitmap_border: Optional[np.ndarray] = None,
):
    _paste_bitmap(canvas_text, bitmap_char, draw_x, draw_y, mode='max')
    if bitmap_border is None or bitmap_border.size == 0:
        return
    border_x = draw_x - round((bitmap_border.shape[1] - bitmap_char.shape[1]) / 2.0)
    border_y = draw_y - round((bitmap_border.shape[0] - bitmap_char.shape[0]) / 2.0)
    _paste_bitmap(canvas_border, bitmap_border, border_x, border_y, mode='add')


def _normalize_letter_spacing(letter_spacing: float) -> float:
    try:
        value = float(letter_spacing)
    except (TypeError, ValueError):
        return 1.0
    return value if value > 0 else 1.0


def _normalize_char_width(char_width: float) -> float:
    """글자 가로폭 배율. 1.0=원본, <1 좌우 압축, >1 좌우 확장."""
    try:
        value = float(char_width)
    except (TypeError, ValueError):
        return 1.0
    return value if value > 0 else 1.0


def set_char_width(char_width: float = 1.0) -> None:
    """현재 스레드 렌더 상태에 글자 가로폭 배율을 설정한다."""
    _state().char_width = _normalize_char_width(char_width)


def get_char_width() -> float:
    return _normalize_char_width(getattr(_state(), 'char_width', 1.0))


def set_text_emphasis(italic: bool = False) -> None:
    """합성 italic 플래그. 박스 기하가 아니라 글리프 경로에만 적용된다."""
    _state().italic = bool(italic)


def get_text_emphasis() -> bool:
    return bool(getattr(_state(), 'italic', False))


def set_bold(bold: bool = False) -> None:
    """QFont.setBold. 실제 Bold 페이스를 쓰고, 없으면 엔진 합성 볼드를 쓴다."""
    state = _state()
    value = bool(bold)
    if bool(getattr(state, 'bold', False)) == value:
        return
    state.bold = value
    state.measures.clear()
    state.vertical.clear()


def get_bold() -> bool:
    return bool(getattr(_state(), 'bold', False))


# Synthetic italic shear (~12.5°). Qt y-down: x' = x + sh*y with sh < 0 leans right.
_ITALIC_SHEAR = -0.22


def _apply_emphasis_to_path(path: QPainterPath, font_size: int) -> QPainterPath:
    """글리프 경로에 합성 italic을 적용. 레터박스 좌표는 변경하지 않는다."""
    _ = font_size
    if path is None or path.isEmpty() or not get_text_emphasis():
        return path

    transform = QTransform()
    transform.shear(_ITALIC_SHEAR, 0.0)
    result = transform.map(path)
    result.setFillRule(Qt.FillRule.WindingFill)
    return result


# 가로 비율 > 1 일 때 1x 비트맵을 늘리지 않는다. 4점 distort 의 dest 재래스터와 같이
# dest 이상으로 찍은 뒤 줄인다. distort_source_font_size 주석의 2배 해상도를 하한으로 둔다.
_CHAR_WIDTH_STRETCH_MIN_SUPERSAMPLE = 2.0
_OPENCV_RASTER_LIMIT = 32767


def _char_width_supersample_factor(char_width: float, src_w: float = 0.0, src_h: float = 0.0) -> float:
    """가로 비율 > 1 이면 슈퍼샘플 배율, 아니면 1.0."""
    cw = _normalize_char_width(char_width)
    if cw <= 1.0 + 1e-6:
        return 1.0
    ss = max(float(cw), _CHAR_WIDTH_STRETCH_MIN_SUPERSAMPLE)
    long_edge = max(float(src_w), float(src_h), 1.0)
    if long_edge * ss > _OPENCV_RASTER_LIMIT:
        ss = _OPENCV_RASTER_LIMIT / long_edge
    return max(ss, 1.0)


def _resize_alpha_char_width(alpha: np.ndarray, char_width: float, src_supersample: float = 1.0) -> np.ndarray:
    """슈퍼샘플된 알파를 (원본너비 * char_width, 원본높이) 로 맞춘다.

    src_supersample >= char_width 이면 가로·세로 모두 축소(INTER_AREA)라 비트맵을 늘리지 않는다.
    """
    cw = _normalize_char_width(char_width)
    ss = float(src_supersample) if src_supersample and src_supersample > 0 else 1.0
    if alpha is None or alpha.size == 0:
        return alpha
    if abs(cw - 1.0) < 1e-6 and abs(ss - 1.0) < 1e-6:
        return alpha
    h, w = alpha.shape[:2]
    target_w = max(1, int(round(w * cw / ss)))
    target_h = max(1, int(round(h / ss)))
    if target_w == w and target_h == h:
        return alpha
    interp = cv2.INTER_AREA if target_w <= w and target_h <= h else cv2.INTER_LINEAR
    return cv2.resize(alpha, (target_w, target_h), interpolation=interp)


def _scale_alpha_horizontal(alpha: np.ndarray, scale: float) -> np.ndarray:
    """알파 비트맵을 가로로만 균일 스케일한다. 세로(글자 높이)는 유지."""
    return _resize_alpha_char_width(alpha, scale, src_supersample=1.0)


def _stroke_alpha_from_fill(fill_alpha: np.ndarray, stroke_px: int) -> Tuple[np.ndarray, int, int]:
    """축소된 fill 알파 기준으로 거리변환 테두리를 생성한다.

    Returns:
        (border_alpha_padded, border_left_offset, border_top_offset)
        border_*_offset 은 fill 원점 대비 pad 만큼 음수 오프셋.
    """
    if fill_alpha is None or fill_alpha.size == 0:
        return np.zeros((0, 0), dtype=np.uint8), 0, 0
    stroke_px = max(int(stroke_px), 1)
    pad = stroke_px + 1
    padded = cv2.copyMakeBorder(fill_alpha, pad, pad, pad, pad, cv2.BORDER_CONSTANT, value=0)
    fg_mask = (padded >= 128).astype(np.uint8) * 255
    bg_mask = cv2.bitwise_not(fg_mask)
    dist = cv2.distanceTransform(bg_mask, cv2.DIST_L2, cv2.DIST_MASK_PRECISE)
    stroke_region = np.clip((stroke_px + 0.5 - dist), 0.0, 1.0)
    stroke_alpha_padded = (stroke_region * 255).astype(np.uint8)
    border_alpha = np.maximum(stroke_alpha_padded, padded)
    return border_alpha, -pad, -pad


def _normalize_line_spacing(line_spacing: float) -> float:
    try:
        value = float(line_spacing)
    except (TypeError, ValueError):
        return 1.0
    return value if value > 0 else 1.0


def resolve_horizontal_line_spacing_multiplier(line_spacing: float) -> float:
    return _normalize_line_spacing(line_spacing)

def calc_horizontal_line_spacing_px(font_size: int, line_spacing: float) -> int:
    value = _normalize_line_spacing(line_spacing)
    return int(font_size * (value - 1.0))


def _scale_advance(advance: int, letter_spacing: float) -> int:
    if advance <= 0:
        return int(advance)
    return max(1, int(round(advance * _normalize_letter_spacing(letter_spacing))))


def _normalize_horizontal_measure_text(text: str) -> str:
    return ''.join(c if c in '\r\n' else CJK_Compatibility_Forms_translate(c, 0)[0] for c in (text or ''))


def _horizontal_line(text: str, font_size: int, letter_spacing: float = 1.0):
    return _create_text_layout(_normalize_horizontal_measure_text(text), font_size, letter_spacing)


def _line_logical_width(line, text_length: int) -> float:
    cursor_x = line.cursorToX(text_length)
    return float(cursor_x[0] if isinstance(cursor_x, tuple) else cursor_x)


def _sorted_glyph_positions(layout, reversed_direction: bool):
    positions = [pos for run in layout.glyphRuns() for pos in run.positions()]
    positions.sort(key=lambda p: p.x(), reverse=reversed_direction)
    return positions


def _horizontal_ellipsis_tracking_offsets(
    text: str,
    font_size: int,
    letter_spacing: float,
    positions: list,
    reversed_direction: bool = False,
) -> list:
    if reversed_direction or _normalize_letter_spacing(letter_spacing) == 1.0 or '……' not in (text or ''):
        return [0.0] * len(positions)
    _, _, base_layout, _ = _horizontal_line(text, font_size, 1.0)
    if base_layout is None:
        return [0.0] * len(positions)
    base_positions = _sorted_glyph_positions(base_layout, False)
    limit = min(len(text), len(positions), len(base_positions))
    offsets = [0.0] * len(positions)
    idx = 0
    while idx < limit:
        if text[idx] != '…':
            idx += 1
            continue
        run_start = idx
        while idx < limit and text[idx] == '…':
            idx += 1
        if idx - run_start < 2:
            continue
        start_spaced_x = positions[run_start].x()
        start_base_x = base_positions[run_start].x()
        for run_idx in range(run_start + 1, idx):
            spaced_delta = positions[run_idx].x() - start_spaced_x
            base_delta = base_positions[run_idx].x() - start_base_x
            offsets[run_idx] = spaced_delta - base_delta
    return offsets


def _line_metrics(text: str, font_size: int, letter_spacing: float = 1.0) -> dict:
    normalized, qfont, _, line = _horizontal_line(text, font_size, letter_spacing)
    metrics = QFontMetricsF(qfont)
    cw = get_char_width()
    if line is None:
        return {'text': normalized, 'logical_width': 0.0, 'ascent': float(metrics.ascent()), 'height': float(metrics.height()), 'descent': float(metrics.descent())}
    return {
        'text': normalized,
        'logical_width': _line_logical_width(line, len(normalized)) * cw,
        'ascent': float(line.ascent()),
        'height': float(line.height()),
        'descent': float(line.descent()),
    }


def _crop_pair(text_canvas: np.ndarray, border_canvas: np.ndarray):
    combined = cv2.add(text_canvas, border_canvas)
    if not np.any(combined):
        return None
    x, y, w, h = cv2.boundingRect(combined)
    return None if w == 0 or h == 0 else (text_canvas[y:y+h, x:x+w], border_canvas[y:y+h, x:x+w], x, y, w, h)


def _get_fallback_glyph(glyph_id: int, run_font: QRawFont, char: str, font_size: int) -> Tuple[QRawFont, int]:
    if glyph_id > 0 or not char:
        return run_font, glyph_id
    try:
        spec = _glyph_spec(char, font_size)
        return spec.raw_font, spec.glyph_id
    except Exception:
        return run_font, glyph_id


def _line_surface(
    line_text: str,
    font_size: int,
    border_size: int,
    stroke_ratio: float = 0.07,
    reversed_direction: bool = False,
    letter_spacing: float = 1.0,
    profile_stats: Optional[dict] = None,
):
    stage_t0 = perf_counter() if profile_stats is not None else None
    normalized, _, layout, line = _horizontal_line(line_text, font_size, letter_spacing)
    _profile_add(profile_stats, "tr_layout_ms", stage_t0)
    if not line_text or line is None:
        return None
    path = QPainterPath()
    path.setFillRule(Qt.FillRule.WindingFill)
    # Qt/DirectWrite 把 family name 以 '[' 开头的字体归入同一字体集合，
    # 导致 shaping 时 character-to-glyph 映射返回错误的 glyph_id。
    # 修复：用 _glyph_spec 查字形路径（走 font_selection 直接加载的 QRawFont，
    # 绕开 Qt 字体数据库），位置（pos）仍从 QTextLayout 取。
    # glyphRuns() 返回的 run 顺序不保证与字符串字符顺序一致（混合脚本时
    # 如 CJK + ASCII 会分成多个 run，run 顺序不定），按 x 坐标排序以
    # 确保位置与字符的逻辑顺序匹配
    stage_t0 = perf_counter() if profile_stats is not None else None
    all_positions = _sorted_glyph_positions(layout, reversed_direction)
    position_offsets = _horizontal_ellipsis_tracking_offsets(
        normalized,
        font_size,
        letter_spacing,
        all_positions,
        reversed_direction,
    )
    for idx, char in enumerate(normalized):
        if idx >= len(all_positions):
            break
        pos = all_positions[idx]
        try:
            spec = _glyph_spec(char, font_size)
        except Exception:
            continue
        glyph_path = spec.raw_font.pathForGlyph(spec.glyph_id)
        if not glyph_path.isEmpty():
            offset_x = position_offsets[idx] if idx < len(position_offsets) else 0.0
            glyph_path.translate(pos.x() - offset_x, pos.y())
            path.addPath(glyph_path)
    _profile_add(profile_stats, "tr_path_ms", stage_t0)
                
    if path.isEmpty():
        return None
    # 줄 전체 경로에 합성 italic 적용 (박스 경계는 그대로, 글자만 강조)
    path = _apply_emphasis_to_path(path, font_size)
    cw = get_char_width()
    src_rect = path.boundingRect() if not path.isEmpty() else None
    ss = _char_width_supersample_factor(
        cw,
        float(src_rect.width()) if src_rect is not None else 0.0,
        float(src_rect.height()) if src_rect is not None else 0.0,
    )
    stage_t0 = perf_counter() if profile_stats is not None else None
    fill_alpha, fill_left, fill_top = _rasterize_path(path, supersample=ss)
    _profile_add(profile_stats, "tr_raster_ms", stage_t0)
    if fill_alpha.size == 0:
        return None

    # 글자+자간 전체를 좌우 균일 스케일한 뒤, 그 결과를 기준으로 테두리를 그린다.
    # 가로 비율 > 1 은 1x 비트맵을 늘리지 않고 4점 distort 와 같이 슈퍼샘플 후 축소한다.
    if ss > 1.0 + 1e-6 or abs(cw - 1.0) >= 1e-6:
        fill_alpha = _resize_alpha_char_width(fill_alpha, cw, src_supersample=ss)
        fill_left = int(round(fill_left / ss))
        fill_top = int(round(fill_top / ss))

    if border_size > 0:
        stage_t0 = perf_counter() if profile_stats is not None else None
        stroke_px = max(int(stroke_ratio * font_size), 1)
        border_alpha, border_dx, border_dy = _stroke_alpha_from_fill(fill_alpha, stroke_px)
        border_left, border_top = fill_left + border_dx, fill_top + border_dy
        left = min(fill_left, border_left)
        top = min(fill_top, border_top)
        right = max(fill_left + fill_alpha.shape[1], border_left + border_alpha.shape[1])
        bottom = max(fill_top + fill_alpha.shape[0], border_top + border_alpha.shape[0])
        text_canvas = np.zeros((_px(bottom - top), _px(right - left)), dtype=np.uint8)
        border_canvas = np.zeros((_px(bottom - top), _px(right - left)), dtype=np.uint8)
        _paste_bitmap(text_canvas, fill_alpha, fill_left - left, fill_top - top)
        _paste_bitmap(border_canvas, border_alpha, border_left - left, border_top - top)
        _profile_add(profile_stats, "tr_stroke_ms", stage_t0)
    else:
        left, top = fill_left, fill_top
        text_canvas, border_canvas = fill_alpha, np.zeros_like(fill_alpha)
    stage_t0 = perf_counter() if profile_stats is not None else None
    cropped = _crop_pair(text_canvas, border_canvas)
    if cropped is None:
        return None
    text_bitmap, border_bitmap, x, y, w, h = cropped
    logical_width = _line_logical_width(line, len(normalized)) * cw
    origin_x = -logical_width if reversed_direction else 0.0
    ascent, height = float(line.ascent()), float(line.height())
    result = {
        'text': text_bitmap, 'border': border_bitmap, 'left_rel': left + x - origin_x,
        'right_rel': left + x - origin_x + w, 'top_rel': top + y - ascent, 'width': w, 'height': h,
        'logical_width': logical_width,
        'line_ascent': ascent, 'line_descent': float(line.descent()), 'line_height': height,
        'ink_top': float(top + y), 'ink_bottom': float(top + y + h),
    }
    _profile_add(profile_stats, "tr_crop_ms", stage_t0)
    return result


def _block_surface(
    font_size: int,
    content: str,
    border_size: int,
    stroke_ratio: float = 0.07,
    rotate_90: bool = False,
    letter_spacing: float = 1.0,
    profile_stats: Optional[dict] = None,
):
    content = _normalize_horizontal_block_content(content)
    surface = _line_surface(content, font_size, border_size, stroke_ratio, False, letter_spacing, profile_stats)
    if surface is None:
        return None
    text_bitmap, border_bitmap = surface['text'], surface['border']
    if rotate_90:
        text_bitmap = cv2.rotate(text_bitmap, cv2.ROTATE_90_CLOCKWISE)
        border_bitmap = cv2.rotate(border_bitmap, cv2.ROTATE_90_CLOCKWISE)
        cropped = _crop_pair(text_bitmap, border_bitmap)
        if cropped is None:
            return None
        text_bitmap, border_bitmap, _, _, w, h = cropped
    else:
        h, w = text_bitmap.shape
    return {'text': text_bitmap, 'border': border_bitmap, 'width': int(w), 'height': int(h)}


def _resolve_stroke_ratio(config=None, stroke_width: Optional[float] = None) -> float:
    if stroke_width is not None:
        return float(stroke_width)
    render_cfg = getattr(config, 'render', None)
    return float(getattr(render_cfg, 'stroke_width', 0.07))


def _bitmap_ink_rect(bitmap: Optional[np.ndarray]) -> Optional[Tuple[int, int, int, int]]:
    if bitmap is None or bitmap.size == 0:
        return None
    nz = cv2.findNonZero(bitmap)
    return None if nz is None else tuple(map(int, cv2.boundingRect(nz)))


def _is_vertical_ellipsis_char(cdpt: str) -> bool:
    return cdpt in ('︙', '⋮', '⋯', '…')


def _estimate_ellipsis_gap(bitmap_char: np.ndarray) -> Optional[float]:
    if bitmap_char is None or bitmap_char.size == 0:
        return None
    labels, _, stats, centers = cv2.connectedComponentsWithStats((bitmap_char > 0).astype(np.uint8), connectivity=8)
    ys = sorted(float(centers[i][1]) for i in range(1, labels) if stats[i, cv2.CC_STAT_AREA] > 0)
    return None if len(ys) < 3 else (ys[1] - ys[0] + ys[2] - ys[1]) / 2.0


def _vertical_ellipsis_advance(glyph: GlyphRaster, font_size: int, bitmap_char: Optional[np.ndarray] = None) -> int:
    raw = bitmap_char.shape[0] + glyph.vert_bearing_y if bitmap_char is not None and bitmap_char.size else glyph.advance_y
    raw = raw if raw > 0 else font_size
    gap = _estimate_ellipsis_gap(bitmap_char)
    return max(1, int(round(3.0 * gap))) if gap and gap > 0 else _px(raw, 1)


def _vertical_base(font_size: int, cdpt: str, letter_spacing: float = 1.0) -> dict:
    state = _state()
    cw = get_char_width()
    italic = get_text_emphasis()
    key = (quantize_font_size(font_size), cdpt, round(_normalize_letter_spacing(letter_spacing), 4), round(cw, 4), italic, get_bold())
    cached = _cache_get(state.vertical, key)
    if cached is not None:
        return cached
    translated, rot = CJK_Compatibility_Forms_translate(cdpt, 1)
    glyph = _glyph_raster(translated, font_size)
    ss = _char_width_supersample_factor(cw, font_size, font_size)
    if ss > 1.0 + 1e-6:
        spec = _glyph_spec(translated, font_size)
        raw_font = spec.raw_font
        pixel_size = quantize_font_size(font_size)
        if abs(float(raw_font.pixelSize()) - pixel_size) > 0.049:
            raw_font = QRawFont(raw_font)
            raw_font.setPixelSize(pixel_size)
        glyph_path = _apply_emphasis_to_path(raw_font.pathForGlyph(spec.glyph_id), pixel_size)
        bitmap, _, _ = _rasterize_path(glyph_path, supersample=ss)
        if bitmap.size == 0:
            bitmap = None
    else:
        bitmap = glyph.alpha if glyph.alpha.size else None
    if bitmap is not None and rot == 90:
        bitmap = cv2.rotate(bitmap, cv2.ROTATE_90_CLOCKWISE)
    # 세로쓰기에서도 글자 가로폭 배율을 적용 (글리프 폭만 좌우 스케일)
    if bitmap is not None and (ss > 1.0 + 1e-6 or abs(cw - 1.0) >= 1e-6):
        bitmap = _resize_alpha_char_width(bitmap, cw, src_supersample=ss)
    advance_y = _vertical_ellipsis_advance(glyph, font_size, bitmap) if _is_vertical_ellipsis_char(translated) else (glyph.advance_y if glyph.advance_y > 0 else font_size)
    if translated in _VERTICAL_HALF_ADVANCE:
        advance_y = font_size * 0.5
    advance_y = _scale_advance(int(advance_y), letter_spacing)
    slot_height = advance_y if translated in _VERTICAL_HALF_ADVANCE else max(1, advance_y)
    ink_x, ink_y = 0.0, 0.0
    ink_w = float(bitmap.shape[1]) if bitmap is not None else 0.0
    ink_h = float(bitmap.shape[0]) if bitmap is not None else 0.0
    if bitmap is not None:
        rect = _bitmap_ink_rect(bitmap)
        if rect is not None:
            ink_x, ink_y, ink_w, ink_h = rect
    frame_width = max(int(round(font_size * cw)), int(round(glyph.advance_x * cw)), int(round(ink_w)) if ink_w else 0, 1)
    slot_origin_y = max(0, int(round((advance_y - slot_height) / 2.0)))
    
    # 默认居中对齐真实墨迹（考虑到 ink_y 和 ink_h）
    y = slot_origin_y + max(0, int(round((slot_height - ink_h) / 2.0))) - ink_y
    
    padding = max(1, int(round(font_size * 0.05)))
    if translated in _VERTICAL_ALIGN_TOP_RIGHT or translated in _VERTICAL_ALIGN_TOP_CENTER:
        y = padding - ink_y
    elif translated in _VERTICAL_ALIGN_BOTTOM_LEFT or translated in _VERTICAL_ALIGN_BOTTOM_CENTER:
        y = advance_y - ink_h - padding - ink_y

    base = {
        'translated': translated, 'rot_degree': rot, 'bitmap': bitmap, 'advance_y': int(advance_y),
        'ink_x': float(ink_x), 'ink_w': float(ink_w), 'y': int(round(y)),
        'frame_width': int(frame_width),
    }
    return _cache_put(state.vertical, key, base, _VERTICAL_CACHE_MAX)


def get_vertical_char_bitmap_width(font_size: int, cdpt: str, letter_spacing: float = 1.0) -> int:
    bitmap = _vertical_base(font_size, cdpt, letter_spacing)['bitmap']
    return _px(font_size, 1) if bitmap is None or bitmap.size == 0 else int(bitmap.shape[1])


def _measure_horizontal_text_width(text: str, font_size: int, letter_spacing: float = 1.0) -> int:
    normalized = _normalize_horizontal_measure_text(text)
    if not normalized:
        return 0
    if '\n' in normalized or '\r' in normalized:
        return max((_measure_horizontal_text_width(part, font_size, letter_spacing) for part in normalized.splitlines()), default=0)
    font_size = quantize_font_size(font_size)
    int_fs = max(1, int(round(font_size)))
    state = _state()
    cw = get_char_width()
    key = (
        'logical-width',
        tuple(state.font_selection),
        font_size,
        round(_normalize_letter_spacing(letter_spacing), 4),
        round(cw, 4),
        get_bold(),
        normalized,
    )
    cached = state.measures.get(key)
    if cached is not None:
        return cached
    _, _, _, line = _horizontal_line(normalized, int_fs, letter_spacing)
    width = 0 if line is None else int(round(_line_logical_width(line, len(normalized)) * cw))
    if abs(font_size - int_fs) >= 1e-9:
        width = max(0, int(round(width * (font_size / float(int_fs)))))
    if len(state.measures) >= 4096:
        state.measures.clear()
    state.measures[key] = width
    return width


def calc_horizontal_block_height(font_size: int, content: str, letter_spacing: float = 1.0) -> int:
    surface = _block_surface(font_size, content, 0, 0.0, should_rotate_horizontal_block_90(content), letter_spacing)
    return _px(font_size, 1) if surface is None or surface['height'] <= 0 else int(surface['height'])


def get_char_offset_x(font_size: int, cdpt: str, letter_spacing: float = 1.0):
    return _measure_horizontal_text_width('　' if cdpt == '＿' else cdpt, font_size, letter_spacing)


def get_string_width(font_size: int, text: str, letter_spacing: float = 1.0):
    return _measure_horizontal_text_width(text, font_size, letter_spacing)


def get_char_offset_y(font_size: int, cdpt: str, letter_spacing: float = 1.0):
    return _vertical_base(font_size, '　' if cdpt == '＿' else cdpt, letter_spacing)['advance_y']


def get_string_height(font_size: int, text: str, letter_spacing: float = 1.0):
    text = normalize_vertical_ellipsis_text(compact_special_symbols(text))
    total = 0
    for part in _H_BLOCK_RE.split(re.sub(r'\s*(?:\[BR\]|<br>|【BR】)\s*', '', text or '', flags=re.IGNORECASE)):
        if not part:
            continue
        if part.lower().startswith('<h>') and part.lower().endswith('</h>'):
            total += calc_horizontal_block_height(font_size, part[3:-4], letter_spacing)
        else:
            total += sum(get_char_offset_y(font_size, c, letter_spacing) for c in part)
    return total


def _vertical_border_bitmap(translated: str, font_size: int, stroke_ratio: float, rot_degree: int):
    bitmap = _glyph_stroke_alpha(translated, font_size, stroke_ratio)
    if bitmap.size == 0:
        return None
    return cv2.rotate(bitmap, cv2.ROTATE_90_CLOCKWISE) if rot_degree == 90 else bitmap


def _build_vertical_layout(
    font_size: int,
    line_text: str,
    border_size: int,
    stroke_ratio: float,
    letter_spacing: float,
    block_cache: dict,
    profile_stats: Optional[dict] = None,
) -> dict:
    line_width, items = _px(font_size, 1), []
    for part in _H_BLOCK_RE.split(line_text):
        if not part:
            continue
        if part.lower().startswith('<h>') and part.lower().endswith('</h>'):
            raw = part[3:-4]
            key = (font_size, raw, border_size, round(float(stroke_ratio), 4), round(_normalize_letter_spacing(letter_spacing), 4))
            surface = block_cache.get(key)
            if surface is None:
                surface = _block_surface(
                    font_size,
                    raw,
                    border_size,
                    stroke_ratio,
                    should_rotate_horizontal_block_90(raw),
                    letter_spacing,
                    profile_stats,
                )
                block_cache[key] = surface
            if surface is not None:
                line_width = max(line_width, int(surface['width']))
                items.append(('block', surface))
            continue
        for char in part:
            if char == '＿':
                items.append(('placeholder', _scale_advance(font_size, letter_spacing)))
                continue
            base = _vertical_base(font_size, char, letter_spacing)
            line_width = max(line_width, int(base['frame_width']))
            items.append(('char', base))
    cursor, laid = 0, []
    for kind, value in items:
        if kind == 'block':
            laid.append({'kind': kind, 'surface': value, 'width': int(value['width']), 'height': int(value['height']), 'cursor_y': cursor})
            cursor += int(value['height'])
        elif kind == 'placeholder':
            laid.append({'kind': kind, 'advance_y': int(value), 'cursor_y': cursor})
            cursor += int(value)
        else:
            char_t = value['translated']
            ink_w = value['ink_w']
            ink_x = value['ink_x']
            
            x = round((line_width - ink_w) / 2.0) - ink_x
            
            padding = max(1, int(round(font_size * 0.05)))
            if char_t in _VERTICAL_ALIGN_TOP_RIGHT:
                x = line_width - ink_w - ink_x - padding
            elif char_t in _VERTICAL_ALIGN_BOTTOM_LEFT:
                x = -ink_x + padding

            laid.append({
                'kind': kind, 'translated': char_t, 'rot_degree': value['rot_degree'], 'bitmap': value['bitmap'],
                'cursor_y': cursor, 'x': int(round(x)), 'y': int(value['y']),
            })
            cursor += int(value['advance_y'])
    return {'width': int(line_width), 'height': max(0, int(cursor)), 'items': laid}


def put_char_horizontal(font_size: int, cdpt: str, pen_l: Tuple[int, int], canvas_text: np.ndarray, canvas_border: np.ndarray, border_size: int, config=None, stroke_width: float = None, letter_spacing: float = 1.0):
    char = '　' if cdpt == '＿' else CJK_Compatibility_Forms_translate(cdpt, 0)[0]
    char_offset_x = get_char_offset_x(font_size, char, letter_spacing)
    surface = _line_surface(char, font_size, border_size, _resolve_stroke_ratio(config, stroke_width), False, letter_spacing)
    if surface is not None:
        _paste_surface(canvas_text, canvas_border, surface, pen_l[0] + surface['left_rel'], pen_l[1] + surface['top_rel'])
    return char_offset_x


def put_text_horizontal(
    font_size: int,
    text: str,
    width: int,
    height: int,
    alignment: str,
    reversed_direction: bool,
    fg: Tuple[int, int, int],
    bg: Tuple[int, int, int],
    lang: str = 'en_US',
    hyphenate: bool = True,
    line_spacing: int = 0,
    config=None,
    region_count: int = 1,
    stroke_width: float = None,
    letter_spacing: float = 1.0,
    char_width: float = 1.0,
    italic: bool = False,
    bold: bool = False,
    profile_stats: Optional[dict] = None,
    **_unused_kwargs,
):
    _ = _unused_kwargs
    prev_cw = get_char_width()
    prev_italic = get_text_emphasis()
    prev_bold = get_bold()
    set_char_width(char_width)
    set_text_emphasis(italic)
    set_bold(bold)
    try:
        return _put_text_horizontal_impl(
            font_size, text, width, height, alignment, reversed_direction,
            fg, bg, lang, hyphenate, line_spacing, config, region_count,
            stroke_width, letter_spacing, profile_stats,
        )
    finally:
        set_bold(prev_bold)
        set_text_emphasis(prev_italic)
        set_char_width(prev_cw)


def _put_text_horizontal_impl(
    font_size: int,
    text: str,
    width: int,
    height: int,
    alignment: str,
    reversed_direction: bool,
    fg: Tuple[int, int, int],
    bg: Tuple[int, int, int],
    lang: str = 'en_US',
    hyphenate: bool = True,
    line_spacing: int = 0,
    config=None,
    region_count: int = 1,
    stroke_width: float = None,
    letter_spacing: float = 1.0,
    profile_stats: Optional[dict] = None,
):
    text = compact_special_symbols(text, convert_ascii_ellipsis=False)
    if not text:
        return None
    _ = (width, height, lang, hyphenate, region_count)
    stroke_ratio = _resolve_stroke_ratio(config, stroke_width)
    bg_size = int(max(font_size * stroke_ratio, 1)) if bg is not None else 0
    spacing_y = calc_horizontal_line_spacing_px(font_size, line_spacing)
    line_texts = split_layout_lines(text)
    if not line_texts:
        return None
    surfaces, metrics, tops, extents, logical_widths, edge_ws = [], [], [], [], [], []
    logical_y = min_ink_top = max_ink_bottom = 0.0
    for idx, line_text in enumerate(line_texts):
        surface = _line_surface(line_text, font_size, bg_size, stroke_ratio, reversed_direction, letter_spacing, profile_stats)
        frame = {'ascent': surface['line_ascent'], 'height': surface['line_height'], 'descent': surface['line_descent']} if surface else _line_metrics(line_text, font_size, letter_spacing)
        surfaces.append(surface)
        metrics.append(frame)
        tops.append(logical_y)
        left, right = (surface['left_rel'], surface['right_rel']) if surface else (0.0, 0.0)
        logical_widths.append(float(surface['logical_width']) if surface else float(frame.get('logical_width', 0.0)))
        edge_ws.append(_edge_whitespace_widths(line_text, font_size, letter_spacing))
        if surface:
            min_ink_top = min(min_ink_top, logical_y + surface['ink_top'])
            max_ink_bottom = max(max_ink_bottom, logical_y + surface['ink_bottom'])
        extents.append((left, right))
        logical_y += frame['height'] + (spacing_y if idx < len(line_texts) - 1 else 0)
    slot_widths = [
        max(0.0, right - left) + lead_w + trail_w
        for (left, right), (lead_w, trail_w) in zip(extents, edge_ws)
    ]
    max_visual_width = max(slot_widths, default=0.0)
    canvas_w = int(math.ceil(max(max_visual_width, max(logical_widths, default=0.0)) + (font_size + bg_size) * 2))
    canvas_h = int(math.ceil(logical_y + max(0.0, -min_ink_top) + max(0.0, max_ink_bottom - logical_y) + bg_size * 2))
    canvas_text = np.zeros((canvas_h, canvas_w), dtype=np.uint8)
    canvas_border = np.zeros_like(canvas_text)
    base_x = canvas_w - bg_size - 10 if reversed_direction else font_size + bg_size
    base_y = bg_size + max(0.0, -min_ink_top)
    stage_t0 = perf_counter() if profile_stats is not None else None
    for i, surface in enumerate(surfaces):
        if surface is None:
            continue
        left, right = extents[i]
        lead_w, trail_w = edge_ws[i]
        line_width = max(0.0, right - left) + lead_w + trail_w
        if reversed_direction:
            slot_right = base_x
            slot_left = slot_right - max_visual_width
            target_left = slot_left if alignment == 'left' else slot_left + round((max_visual_width - line_width) / 2.0) if alignment == 'center' else slot_right - line_width
            pen_x = round(target_left + line_width - right - trail_w)
        else:
            slot_left = base_x
            target_left = slot_left if alignment == 'left' else slot_left + round((max_visual_width - line_width) / 2.0) if alignment == 'center' else slot_left + (max_visual_width - line_width)
            pen_x = round(target_left - left + lead_w)
        baseline_y = base_y + tops[i] + metrics[i]['ascent']
        _paste_surface(canvas_text, canvas_border, surface, pen_x + surface['left_rel'], baseline_y + surface['top_rel'])
    _profile_add(profile_stats, "tr_paste_ms", stage_t0)
    stage_t0 = perf_counter() if profile_stats is not None else None
    any_lead = any(lead_w > 0 for lead_w, _ in edge_ws)
    any_trail = any(trail_w > 0 for _, trail_w in edge_ws)
    keep_left = None if reversed_direction else (base_x if any_lead else None)
    keep_right = (base_x if any_lead else None) if reversed_direction else (base_x + max_visual_width if any_trail else None)
    lead_blank = 0
    for surface in surfaces:
        if surface is None:
            lead_blank += 1
        else:
            break
    trail_blank = 0
    for surface in reversed(surfaces):
        if surface is None:
            trail_blank += 1
        else:
            break
    keep_top = base_y if lead_blank else None
    keep_bottom = (base_y + logical_y) if trail_blank else None
    result = _crop_and_color(
        canvas_text, canvas_border, fg, bg,
        keep_left=keep_left, keep_right=keep_right,
        keep_top=keep_top, keep_bottom=keep_bottom,
    )
    _profile_add(profile_stats, "tr_color_ms", stage_t0)
    return result


def put_text_vertical(
    font_size: int,
    text: str,
    h: int,
    alignment: str,
    fg: Tuple[int, int, int],
    bg: Optional[Tuple[int, int, int]],
    line_spacing: int,
    config=None,
    region_count: int = 1,
    stroke_width: float = None,
    letter_spacing: float = 1.0,
    char_width: float = 1.0,
    italic: bool = False,
    bold: bool = False,
    profile_stats: Optional[dict] = None,
    **_unused_kwargs,
):
    _ = _unused_kwargs
    prev_cw = get_char_width()
    prev_italic = get_text_emphasis()
    prev_bold = get_bold()
    set_char_width(char_width)
    set_text_emphasis(italic)
    set_bold(bold)
    try:
        return _put_text_vertical_impl(
            font_size, text, h, alignment, fg, bg, line_spacing, config,
            region_count, stroke_width, letter_spacing, profile_stats,
        )
    finally:
        set_bold(prev_bold)
        set_text_emphasis(prev_italic)
        set_char_width(prev_cw)


def _put_text_vertical_impl(
    font_size: int,
    text: str,
    h: int,
    alignment: str,
    fg: Tuple[int, int, int],
    bg: Optional[Tuple[int, int, int]],
    line_spacing: int,
    config=None,
    region_count: int = 1,
    stroke_width: float = None,
    letter_spacing: float = 1.0,
    profile_stats: Optional[dict] = None,
):
    text = normalize_vertical_ellipsis_text(compact_special_symbols(text))
    if not text:
        return None
    _ = (h, region_count)
    stroke_ratio = _resolve_stroke_ratio(config, stroke_width)
    bg_size = int(max(font_size * stroke_ratio, 1)) if bg is not None else 0
    
    val_ls = _normalize_line_spacing(line_spacing)
    if val_ls >= 1.0:
        spacing_x = int(font_size * 0.2 * val_ls)
    else:
        spacing_x = int(font_size * (val_ls - 0.8))
    block_cache = {}
    stage_t0 = perf_counter() if profile_stats is not None else None
    vertical_lines = _convert_br_outside_h_tags(text).split('\n')
    if not vertical_lines:
        return None
    layouts = [
        _build_vertical_layout(font_size, line, bg_size, stroke_ratio, letter_spacing, block_cache, profile_stats)
        for line in vertical_lines
    ]
    _profile_add(profile_stats, "tr_vertical_layout_ms", stage_t0)
    line_widths = [layout['width'] for layout in layouts]
    max_height = max((layout['height'] for layout in layouts), default=0)
    content_width = sum(line_widths) + spacing_x * max(0, len(line_widths) - 1)
    pad = int(math.ceil(float(font_size) + float(bg_size)))
    canvas_h = int(max_height) + pad * 2
    canvas_w = int(math.ceil(float(content_width))) + pad * 2
    if canvas_h <= 0 or canvas_w <= 0:
        return None
    canvas_text = np.zeros((canvas_h, canvas_w), dtype=np.uint8)
    canvas_border = np.zeros_like(canvas_text)
    current_edge = pad + int(math.ceil(float(content_width)))
    columns = []
    for width in line_widths:
        columns.append((current_edge - width / 2.0, current_edge))
        current_edge -= width + spacing_x
    stage_t0 = perf_counter() if profile_stats is not None else None
    for idx, layout in enumerate(layouts):
        line_width = layout['width']
        center_x, _ = columns[idx]
        line_start_x = int(round(center_x - line_width / 2.0))
        line_origin_y = pad
        if alignment == 'center':
            line_origin_y += round((max_height - layout['height']) / 2.0)
        elif alignment == 'right':
            line_origin_y += max_height - layout['height']
        for item in layout['items']:
            if item['kind'] == 'block':
                surface = item['surface']
                _paste_surface(canvas_text, canvas_border, surface, line_start_x + round((line_width - item['width']) / 2.0), line_origin_y + item['cursor_y'])
            elif item['kind'] == 'char' and item['bitmap'] is not None:
                draw_x = line_start_x + int(item['x'])
                draw_y = line_origin_y + item['cursor_y'] + int(item['y'])
                sub_t0 = perf_counter() if profile_stats is not None else None
                # 테두리는 가로폭 적용된 글리프(bitmap) 기준으로 생성
                if bg_size > 0:
                    stroke_px = max(int(stroke_ratio * font_size), 1)
                    border_bitmap, _, _ = _stroke_alpha_from_fill(item['bitmap'], stroke_px)
                else:
                    border_bitmap = None
                _profile_add(profile_stats, "tr_vborder_ms", sub_t0)
                sub_t0 = perf_counter() if profile_stats is not None else None
                _paste_glyph_pair(canvas_text, canvas_border, item['bitmap'], draw_x, draw_y, border_bitmap)
                _profile_add(profile_stats, "tr_vpaste_ms", sub_t0)
    _profile_add(profile_stats, "tr_paste_ms", stage_t0)
    stage_t0 = perf_counter() if profile_stats is not None else None
    any_lead = any(bool(line) and line[0] in _EDGE_WHITESPACE for line in vertical_lines)
    any_trail = any(bool(line) and line[-1] in _EDGE_WHITESPACE for line in vertical_lines)
    lead_blank_col = bool(vertical_lines) and not str(vertical_lines[0]).strip()
    trail_blank_col = bool(vertical_lines) and not str(vertical_lines[-1]).strip()
    content_top = pad
    content_left = pad
    content_right = pad + int(math.ceil(float(content_width)))
    result = _crop_and_color(
        canvas_text, canvas_border, fg, bg,
        keep_top=content_top if any_lead else None,
        keep_bottom=(content_top + max_height) if any_trail else None,
        keep_right=content_right if lead_blank_col else None,
        keep_left=content_left if trail_blank_col else None,
    )
    _profile_add(profile_stats, "tr_color_ms", stage_t0)
    return result


def select_hyphenator(lang: str):
    lang = standardize_tag(lang or 'en_US')
    if lang not in HYPHENATOR_LANGUAGES:
        lang = next((avail for avail in reversed(HYPHENATOR_LANGUAGES) if avail.startswith(lang)), '')
    if not lang:
        return None
    if lang not in _hyphenator_cache:
        try:
            _hyphenator_cache[lang] = Hyphenator(lang)
        except Exception:
            _hyphenator_cache[lang] = None
    return _hyphenator_cache[lang]


def calc_horizontal(font_size: int, text: str, max_width: int, max_height: int, language: str = 'en_US', hyphenate: bool = True, letter_spacing: float = 1.0):
    from .auto_linebreak import _calc_horizontal_layout
    _ = max_height
    return _calc_horizontal_layout(font_size, text, max_width, language, hyphenate, letter_spacing=letter_spacing)


def calc_vertical(font_size: int, text: str, max_height: int, config=None, letter_spacing: float = 1.0):
    from .auto_linebreak import _calc_vertical_layout
    return _calc_vertical_layout(font_size, text, max_height, config, letter_spacing=letter_spacing)


def calc_vertical_metrics(font_size: int, text: str, max_height: int, config=None, letter_spacing: float = 1.0):
    from .auto_linebreak import _layout_vertical_metrics
    return _layout_vertical_metrics(font_size, text, max_height, config, letter_spacing=letter_spacing)
