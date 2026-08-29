"""Qt font catalog shared by settings and the editor.

Catalog/grouping matches v3.0: families are the persisted value, duplicate
Qt names for the same face are merged, and combo items are drawn in that face.
"""
from __future__ import annotations

import logging
import os
import unicodedata
import weakref
from collections import Counter
from collections.abc import Callable
from functools import lru_cache

from PyQt6.QtCore import (
    QAbstractListModel,
    QEvent,
    QLocale,
    QModelIndex,
    QPoint,
    QSignalBlocker,
    QSize,
    QSortFilterProxyModel,
    Qt,
    QTimer,
    pyqtSignal,
)
from PyQt6.QtGui import QFont, QFontDatabase, QFontInfo, QFontMetrics, QGuiApplication, QPainter, QRawFont, QWheelEvent
from PyQt6.QtWidgets import (
    QComboBox,
    QFrame,
    QLineEdit,
    QListView,
    QStyledItemDelegate,
    QVBoxLayout,
)

from manga_translator.rendering.text_render import (
    qt_family_is_ambiguous,
    register_font_file,
    strip_qt_foundry_brackets,
)

from .resource_helper import resource_path

logger = logging.getLogger('manga_translator')

FONT_FILE_EXTENSIONS = ('.ttf', '.otf', '.ttc')
FONT_STYLE_SEPARATOR = '::'
_FONT_SEARCH_PLACEHOLDERS = {
    "zh_CN": "搜索字体…",
    "zh_TW": "搜尋字型…",
    "ja_JP": "フォントを検索…",
    "ko_KR": "글꼴 검색…",
    "es_ES": "Buscar fuentes…",
    "en_US": "Search fonts…",
}
_REGISTERED_FONT_FAMILIES: dict[str, list[str]] = {}
_ORIGINAL_FONT_DISPLAY_NAMES: dict[str, str] = {}
_SYSTEM_FONTS_ENABLED = True
_FONT_COMBO_INSTANCES: weakref.WeakSet = weakref.WeakSet()
_FONT_DIRECTORY_SIGNATURE: tuple | None = None
_FONT_FILE_LIST_CACHE: tuple[tuple[str, str], ...] = ()
_FONT_FAMILY_CACHE: dict[bool, tuple[str, ...]] = {}


def _clear_font_catalog_caches() -> None:
    _FONT_FAMILY_CACHE.clear()
    localized_font_family.cache_clear()
    _list_font_family_entries_cached.cache_clear()
    _font_styles.cache_clear()
    _list_font_style_entries_cached.cache_clear()
    _cached_qfont_for_value.cache_clear()
    _popup_qfont_for_value.cache_clear()


def fonts_directory() -> str:
    return resource_path('fonts')


def list_font_files() -> list[tuple[str, str]]:
    """Enumerate project font files, registering newly discovered faces once."""
    global _FONT_DIRECTORY_SIGNATURE, _FONT_FILE_LIST_CACHE
    try:
        fonts_dir = fonts_directory()
        try:
            stat = os.stat(fonts_dir)
            signature = (stat.st_mtime_ns, stat.st_ctime_ns)
        except OSError:
            signature = None
        if signature != _FONT_DIRECTORY_SIGNATURE:
            font_files: list[tuple[str, str]] = []
            if signature is not None:
                for entry in os.scandir(fonts_dir):
                    if entry.is_file() and entry.name.lower().endswith(FONT_FILE_EXTENSIONS):
                        font_files.append((os.path.splitext(entry.name)[0], entry.name))
            font_files.sort(key=lambda item: (item[0].casefold(), item[1].casefold()))
            _FONT_FILE_LIST_CACHE = tuple(font_files)
            _FONT_DIRECTORY_SIGNATURE = signature
    except OSError as exc:
        logger.warning(f"Failed to scan fonts directory: {exc}")
        _FONT_FILE_LIST_CACHE = ()

    catalog_changed = False
    if QGuiApplication.instance() is not None:
        fonts_dir = fonts_directory()
        for _stem, filename in _FONT_FILE_LIST_CACHE:
            path = os.path.normcase(os.path.abspath(os.path.join(fonts_dir, filename)))
            if path in _REGISTERED_FONT_FAMILIES:
                continue
            _REGISTERED_FONT_FAMILIES[path] = register_font_file(path)
            _remember_original_font_names(path)
            catalog_changed = True
        if catalog_changed:
            _font_family_name_records.cache_clear()
            _resolved_font_identity.cache_clear()
            _clear_font_catalog_caches()
    return list(_FONT_FILE_LIST_CACHE)


def list_font_families(include_system: bool | None = None) -> list[str]:
    if QGuiApplication.instance() is None:
        return []
    list_font_files()
    if include_system is None:
        include_system = _SYSTEM_FONTS_ENABLED
    include_system = bool(include_system)
    cached = _FONT_FAMILY_CACHE.get(include_system)
    if cached is not None:
        return list(cached)
    families = {
        name for name in QFontDatabase.families()
        if name and not qt_family_is_ambiguous(name) and QFontDatabase.isScalable(name)
    }
    if not include_system:
        project_families = {
            family
            for families_for_file in _REGISTERED_FONT_FAMILIES.values()
            for family in families_for_file
        }
        families.intersection_update(project_families)
    result = tuple(sorted(families, key=str.casefold))
    _FONT_FAMILY_CACHE[include_system] = result
    return list(result)


def font_family_for_file(filename: str) -> str:
    if not filename or QGuiApplication.instance() is None:
        return ''
    list_font_files()
    path = os.path.normcase(os.path.abspath(os.path.join(fonts_directory(), os.path.basename(filename))))
    families = _REGISTERED_FONT_FAMILIES.get(path) or []
    return families[0] if families else ''


def register_font_files(paths) -> None:
    """Register extra font files into the same catalog the editor uses."""
    if QGuiApplication.instance() is None:
        return
    catalog_changed = False
    for path in paths or ():
        if not path or not os.path.isfile(path):
            continue
        key = os.path.normcase(os.path.abspath(path))
        if key in _REGISTERED_FONT_FAMILIES:
            continue
        _REGISTERED_FONT_FAMILIES[key] = register_font_file(path)
        _remember_original_font_names(path)
        catalog_changed = True
    if catalog_changed:
        _font_family_name_records.cache_clear()
        _resolved_font_identity.cache_clear()
        _clear_font_catalog_caches()


def font_alias_map(locale_code: str = "en_US", include_system: bool | None = None) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for _display, value, aliases in list_font_style_entries(locale_code, include_system):
        mapping.setdefault(_search_key(value), value)
        for alias in aliases:
            mapping.setdefault(_search_key(alias), value)
    return mapping


def catalog_value_for_path(path: str, locale_code: str = "") -> str:
    """Map a font file to the font_family value the editor combo stores."""
    if not path or QGuiApplication.instance() is None:
        return ""
    list_font_files()
    abs_path = os.path.abspath(path)
    if os.path.isfile(abs_path):
        register_font_files([abs_path])
    raw = QRawFont(abs_path, 32)
    family = (raw.familyName() or "").strip() if raw.isValid() else ""
    style = (raw.styleName() or "").strip() if raw.isValid() else ""
    if not family:
        return font_family_for_file(os.path.basename(abs_path))
    locale_code = locale_code or QLocale.system().name()
    family_key = _search_key(family)
    style_key = _search_key(style)
    try:
        weight = int(raw.weight())
    except Exception:
        weight = 0
    ranked: list[tuple[bool, bool, str]] = []
    for _display, value, aliases in list_font_style_entries(locale_code):
        cat_family, cat_style = split_font_value(value)
        if not cat_style:
            styles = _font_styles(cat_family)
            cat_style = styles[0] if styles else ""
        names = {
            _search_key(cat_family),
            _search_key(value),
            *(_search_key(alias) for alias in aliases),
        }
        if family_key not in names:
            continue
        ident = _resolved_font_identity(cat_family, cat_style)
        ident_weight = ident[0] if ident else None
        weight_ok = ident_weight is None or not weight or ident_weight == weight
        style_ok = (
            not style_key
            or style_key == _search_key(cat_style)
            or style_key in names
        )
        ranked.append((weight_ok, style_ok, value))
    if ranked:
        ranked.sort(key=lambda row: (not row[0], not row[1], len(row[2])))
        return ranked[0][2]
    aliases = font_alias_map(locale_code)
    for candidate in (
        font_value(family, style) if style else "",
        f"{family} {style}" if style else "",
        family,
    ):
        if not candidate:
            continue
        mapped = aliases.get(_search_key(candidate))
        if mapped:
            return mapped
    return font_value(family, style) if style else family


def _search_key(text: str) -> str:
    return unicodedata.normalize("NFKC", str(text or "")).casefold()


def _remember_original_font_names(path: str) -> None:
    if not path.lower().endswith((".ttf", ".otf")):
        return
    try:
        from fontTools.ttLib import TTFont

        font = TTFont(path, lazy=True)
        try:
            for record in font["name"].names:
                if record.nameID not in (1, 16, 21):
                    continue
                try:
                    original = record.toUnicode().strip()
                except UnicodeDecodeError:
                    continue
                sanitized = strip_qt_foundry_brackets(original)
                if original and sanitized != original:
                    _ORIGINAL_FONT_DISPLAY_NAMES.setdefault(_search_key(sanitized), original)
        finally:
            font.close()
    except Exception as exc:
        logger.debug("Failed to read original font name %s: %s", path, exc)


def _original_font_display_name(name: str) -> str:
    return _ORIGINAL_FONT_DISPLAY_NAMES.get(_search_key(name), name)


@lru_cache(maxsize=None)
def _font_family_name_records(family: str) -> tuple[tuple[int, str, str], ...]:
    records: list[tuple[int, str, str]] = []
    try:
        from fontTools.ttLib import TTFont, newTable
        from fontTools.ttLib.tables._n_a_m_e import _MAC_LANGUAGES, _WINDOWS_LANGUAGES

        data = bytes(QRawFont.fromFont(QFont(family)).fontTable("name"))
        if data:
            table = newTable("name")
            table.decompile(data, TTFont())
            for record in table.names:
                if record.nameID not in (1, 16, 21):
                    continue
                try:
                    value = record.toUnicode().strip()
                except UnicodeDecodeError:
                    continue
                if not value:
                    continue
                if record.platformID == 3:
                    language = _WINDOWS_LANGUAGES.get(record.langID, "")
                elif record.platformID == 1:
                    language = _MAC_LANGUAGES.get(record.langID, "")
                elif record.platformID == 0 and record.langID >= 0x8000:
                    tags = getattr(table, "langTagRecord", ())
                    tag_index = record.langID - 0x8000
                    language = tags[tag_index].toUnicode() if tag_index < len(tags) else ""
                else:
                    language = ""
                records.append((record.nameID, language, value))
    except Exception as exc:
        logger.debug("Failed to read localized font name %s: %s", family, exc)
    return tuple(dict.fromkeys(records))


@lru_cache(maxsize=None)
def _resolved_font_identity(family: str, style: str = '') -> tuple:
    try:
        resolved_style = style
        if not resolved_style:
            styles = [str(value) for value in QFontDatabase.styles(family) if str(value)]
            by_key = {style.casefold(): style for style in styles}
            resolved_style = by_key.get('regular') or by_key.get('normal') or (styles[0] if styles else '')
        font = (
            QFontDatabase.font(family, resolved_style, 12)
            if resolved_style
            else QFont(family, 12)
        )
        info = QFontInfo(font)
        qt_style = info.style()
        return (
            int(info.weight()),
            int(getattr(qt_style, 'value', qt_style)),
            int(font.stretch()),
            _search_key(info.styleName() or resolved_style),
        )
    except Exception as exc:
        logger.debug("Failed to resolve font identity %s (%s): %s", family, style, exc)
        return ()


def _font_face_signature(family: str):
    return _resolved_font_identity(family)


def _font_style_signature(family: str, style: str):
    return _resolved_font_identity(family, style)


def _language_score(language: str, locale_code: str) -> int:
    language = str(language or "").replace("_", "-").casefold()
    locale_code = str(locale_code or "").replace("_", "-").casefold()
    locale_language = locale_code.split("-", 1)[0]
    if language == locale_code:
        return 5
    if locale_code.startswith("zh-cn") and language in {"zh", "zh-cn", "zh-hans", "zh-sg"}:
        return 5
    if locale_code.startswith("zh-tw") and language in {"zh-tw", "zh-hant", "zh-hk", "zh-mo"}:
        return 5
    if language.split("-", 1)[0] == locale_language:
        return 4
    if language.split("-", 1)[0] == "en":
        return 2
    return 1 if not language else 0


@lru_cache(maxsize=None)
def localized_font_family(family: str, locale_code: str) -> tuple[str, tuple[str, ...]]:
    records = _font_family_name_records(family)
    if not records:
        return family, (family,)

    family_key = _search_key(family)
    matching_name_ids = {
        name_id for name_id, _language, value in records
        if _search_key(value) == family_key
    }
    candidates = [
        record for record in records
        if not matching_name_ids or record[0] in matching_name_ids
    ]
    name_id_score = {16: 3, 21: 2, 1: 1}
    best = max(
        candidates,
        key=lambda record: (
            _language_score(record[1], locale_code),
            name_id_score.get(record[0], 0),
        ),
    )
    candidate_names = [record[2] for record in candidates]
    aliases = tuple(dict.fromkeys([
        family,
        *candidate_names,
        *(_original_font_display_name(name) for name in candidate_names),
    ]))
    return _original_font_display_name(best[2]), aliases


@lru_cache(maxsize=None)
def _list_font_family_entries_cached(
    locale_code: str,
    include_system: bool,
) -> tuple[tuple[str, str, tuple[str, ...]], ...]:
    entries = []
    for family in list_font_families(include_system=include_system):
        display, aliases = localized_font_family(family, locale_code)
        entries.append((family, display, aliases))

    parents = list(range(len(entries)))

    def find(index: int) -> int:
        while parents[index] != index:
            parents[index] = parents[parents[index]]
            index = parents[index]
        return index

    def union(left: int, right: int) -> None:
        left, right = find(left), find(right)
        if left != right:
            parents[right] = left

    candidate_parents = list(range(len(entries)))

    def candidate_find(index: int) -> int:
        while candidate_parents[index] != index:
            candidate_parents[index] = candidate_parents[candidate_parents[index]]
            index = candidate_parents[index]
        return index

    def candidate_union(left: int, right: int) -> None:
        left, right = candidate_find(left), candidate_find(right)
        if left != right:
            candidate_parents[right] = left

    first_by_name: dict[str, int] = {}
    for index, (family, _display, _aliases) in enumerate(entries):
        complete_names = tuple(dict.fromkeys((
            family,
            *(value for _name_id, _language, value in _font_family_name_records(family)),
        )))
        for name in complete_names:
            key = _search_key(name)
            previous = first_by_name.setdefault(key, index)
            candidate_union(index, previous)

    candidate_groups: dict[int, list[int]] = {}
    for index in range(len(entries)):
        candidate_groups.setdefault(candidate_find(index), []).append(index)
    for indexes in candidate_groups.values():
        if len(indexes) == 1:
            continue
        identities = {}
        for index in indexes:
            identity = _font_face_signature(entries[index][0])
            if identity:
                previous = identities.setdefault(identity, index)
                union(index, previous)
        if not identities:
            for index in indexes[1:]:
                union(indexes[0], index)

    grouped: dict[int, list[tuple[str, str, tuple[str, ...]]]] = {}
    for index, entry in enumerate(entries):
        grouped.setdefault(find(index), []).append(entry)

    merged = []
    for group in grouped.values():
        canonical = min(
            group,
            key=lambda entry: (
                not entry[0].isascii(),
                len(_search_key(entry[0])),
                _search_key(entry[0]),
            ),
        )[0]
        display, _aliases = localized_font_family(canonical, locale_code)
        aliases = tuple(dict.fromkeys(
            alias
            for family, _display, family_aliases in group
            for alias in (family, *family_aliases)
        ))
        merged.append((display, canonical, aliases))

    display_counts = Counter(_search_key(display) for display, _family, _aliases in merged)
    result = [
        (
            f"{display} ({family})" if display_counts[_search_key(display)] > 1 and display != family else display,
            family,
            aliases,
        )
        for display, family, aliases in merged
    ]
    return tuple(sorted(result, key=lambda entry: (_search_key(entry[0]), _search_key(entry[1]))))


def list_font_family_entries(
    locale_code: str,
    include_system: bool | None = None,
) -> list[tuple[str, str, tuple[str, ...]]]:
    if include_system is None:
        include_system = _SYSTEM_FONTS_ENABLED
    return list(_list_font_family_entries_cached(locale_code, bool(include_system)))


@lru_cache(maxsize=None)
def _font_styles(family: str) -> list[str]:
    try:
        styles = [str(style) for style in QFontDatabase.styles(family) if str(style)]
    except Exception:
        styles = []
    if not styles:
        return ['']
    return sorted(styles, key=lambda style: (style.casefold() not in {'regular', 'normal'}, style.casefold()))


def font_value(family: str, style: str = '', default_style: str = '') -> str:
    if not style or style == default_style:
        return family
    return f'{family}{FONT_STYLE_SEPARATOR}{style}'


def split_font_value(value: str) -> tuple[str, str]:
    family, separator, style = str(value or '').rpartition(FONT_STYLE_SEPARATOR)
    if separator and family and style:
        return family, style
    return str(value or ''), ''


@lru_cache(maxsize=None)
def _list_font_style_entries_cached(
    locale_code: str,
    include_system: bool,
) -> tuple[tuple[str, str, tuple[str, ...]], ...]:
    raw_entries = []
    for display, family, family_aliases in list_font_family_entries(locale_code, include_system):
        styles = _font_styles(family)
        default_style = styles[0]
        for style in styles:
            value = font_value(family, style, default_style)
            style_display = f'{display} - {style}' if len(styles) > 1 else display
            raw_entries.append((style_display, value, family_aliases, family, style, default_style))

    known_styles = {
        _search_key(style)
        for _display, _value, _aliases, _family, style, _default in raw_entries
        if style
    } | {'regular', 'normal'}

    def style_hint(family: str, style: str) -> tuple[str, str]:
        family_key = _search_key(family)
        style_key = _search_key(style or 'regular')
        for suffix in sorted(known_styles, key=len, reverse=True):
            marker = f' {suffix}'
            if family_key.endswith(marker):
                family_key = family_key[:-len(marker)]
                if style_key in {'regular', 'normal'}:
                    style_key = suffix
                break
        return family_key, style_key

    def encoded_style_name(family: str) -> str:
        family_key = _search_key(family)
        for suffix in sorted(known_styles, key=len, reverse=True):
            if family_key.endswith(f' {suffix}'):
                _head, sep, tail = family.rpartition(' ')
                if sep and _search_key(tail) == suffix:
                    return tail
                return suffix
        return ''

    entries = []
    for style_display, value, family_aliases, family, style, default_style in raw_entries:
        weight_encoded = bool(encoded_style_name(family))
        alias_style = (
            encoded_style_name(family)
            if weight_encoded and _search_key(style) in {'regular', 'normal'}
            else style
        )
        style_aliases = [value]
        if alias_style:
            for alias in family_aliases:
                style_aliases.append(f'{alias}{FONT_STYLE_SEPARATOR}{alias_style}')
                style_aliases.append(f'{alias} {alias_style}')
        if weight_encoded:
            # "MaruBuri ExtraLight" is a one-style family whose Qt style is
            # Regular. Do not let its typographic name ("MaruBuri") or
            # "MaruBuri Regular" become aliases of ExtraLight.
            for alias in family_aliases:
                _parent, alias_logical = style_hint(alias, '')
                if (
                    alias_logical not in {'regular', 'normal'}
                    or _search_key(alias) == _search_key(family)
                ):
                    style_aliases.append(alias)
        elif _search_key(style) == _search_key(default_style):
            style_aliases.extend(family_aliases)
        entries.append((
            style_display,
            value,
            tuple(dict.fromkeys(alias for alias in style_aliases if alias)),
            family,
            style,
        ))

    candidates: dict[tuple[str, str], list[int]] = {}
    for index, entry in enumerate(entries):
        candidates.setdefault(style_hint(entry[3], entry[4]), []).append(index)

    grouped: dict[tuple, list[tuple[str, str, tuple[str, ...], str, str]]] = {}
    for hint, indexes in candidates.items():
        if len(indexes) == 1:
            grouped[('entry', indexes[0])] = [entries[indexes[0]]]
            continue
        for index in indexes:
            entry = entries[index]
            identity = _font_style_signature(entry[3], entry[4])
            # Keep face identity inside this family hint. Weight+Condensed
            # alone would merge unrelated fonts such as SUIT and KOHI.
            key = ('face', hint, identity) if identity else ('entry', index)
            grouped.setdefault(key, []).append(entry)

    merged = []
    for group in grouped.values():
        canonical = min(
            group,
            key=lambda entry: (
                len(_search_key(entry[3])),
                _search_key(entry[3]),
                _search_key(entry[4]),
            ),
        )
        aliases = tuple(dict.fromkeys(
            alias
            for _display, _value, entry_aliases, _family, _style in group
            for alias in entry_aliases
        ))
        merged.append((canonical[0], canonical[1], aliases))
    return tuple(sorted(merged, key=lambda entry: (_search_key(entry[0]), _search_key(entry[1]))))


def list_font_style_entries(
    locale_code: str,
    include_system: bool | None = None,
) -> list[tuple[str, str, tuple[str, ...]]]:
    if include_system is None:
        include_system = _SYSTEM_FONTS_ENABLED
    return list(_list_font_style_entries_cached(locale_code, bool(include_system)))


@lru_cache(maxsize=4096)
def _cached_qfont_for_value(value: str) -> QFont:
    family, style = split_font_value(value)
    return QFontDatabase.font(family, style, 12) if style else QFont(family)


def qfont_for_value(value: str) -> QFont:
    return QFont(_cached_qfont_for_value(str(value or "")))


_POPUP_FONT_POINT_SIZE = 18


@lru_cache(maxsize=4096)
def _popup_qfont_for_value(value: str) -> QFont:
    font = qfont_for_value(value)
    font.setPointSize(_POPUP_FONT_POINT_SIZE)
    font.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
    font.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
    return font


class _FontPopupDelegate(QStyledItemDelegate):
    """Paint popup rows in the face itself, larger and antialiased."""

    def paint(self, painter, option, index):
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        value = index.data(Qt.ItemDataRole.UserRole)
        option.font = QFont(_popup_qfont_for_value(str(value or "")))
        super().paint(painter, option, index)

    def sizeHint(self, option, index):
        value = index.data(Qt.ItemDataRole.UserRole)
        font = _popup_qfont_for_value(str(value or ""))
        metrics = QFontMetrics(font)
        text = str(index.data(Qt.ItemDataRole.DisplayRole) or "")
        return QSize(max(metrics.horizontalAdvance(text) + 24, 1), metrics.height() + 10)


class _FontMenuModel(QAbstractListModel):
    SearchRole = int(Qt.ItemDataRole.UserRole) + 1

    def __init__(self, entries, parent=None):
        super().__init__(parent)
        self._entries = tuple(entries)

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self._entries)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not 0 <= index.row() < len(self._entries):
            return None
        display, value, search_terms = self._entries[index.row()]
        if role == Qt.ItemDataRole.DisplayRole:
            return display
        if role == Qt.ItemDataRole.UserRole:
            return value
        if role == self.SearchRole:
            return search_terms
        return None


class _FontFilterProxyModel(QSortFilterProxyModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._query = ""

    def set_filter(self, text: str):
        query = _search_key(text.strip())
        if query == self._query:
            return
        self._query = query
        self.invalidateRowsFilter()

    def filterAcceptsRow(self, source_row, source_parent):
        if not self._query:
            return True
        model = self.sourceModel()
        index = model.index(source_row, 0, source_parent)
        return self._query in str(model.data(index, _FontMenuModel.SearchRole) or "")


class _FontPopup(QFrame):
    """Searchable full-height font list, same behavior as v3.0."""

    fontSelected = pyqtSignal(int)

    def __init__(self, entries, placeholder, parent=None):
        super().__init__(parent)
        self._entries = tuple(entries)
        self._was_activated = False
        self.setWindowFlags(
            Qt.WindowType.Popup
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.NoDropShadowWindowHint
        )
        self.setObjectName("font_popup")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        self.search_edit = QLineEdit(self)
        self.search_edit.setPlaceholderText(placeholder)
        self.search_edit.setClearButtonEnabled(True)
        layout.addWidget(self.search_edit)

        self.view = QListView(self)
        self._font_model = _FontMenuModel(self._entries, self.view)
        self._filter_model = _FontFilterProxyModel(self.view)
        self._filter_model.setSourceModel(self._font_model)
        self.view.setModel(self._filter_model)
        self.view.setItemDelegate(_FontPopupDelegate(self.view))
        self.view.setTextElideMode(Qt.TextElideMode.ElideNone)
        self.view.setMouseTracking(True)
        self.view.setUniformItemSizes(True)
        self.view.setVerticalScrollMode(self.view.ScrollMode.ScrollPerPixel)
        self.view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        layout.addWidget(self.view, 1)

        self.search_edit.textChanged.connect(self._filter_items)
        self.view.clicked.connect(self._on_index_clicked)

    def natural_width(self) -> int:
        return max(
            (
                _FontPopupDelegate(None).sizeHint(None, self._font_model.index(row, 0)).width()
                for row in range(self._font_model.rowCount())
            ),
            default=1,
        )

    def set_current_source_row(self, source_row: int) -> None:
        source_index = self._font_model.index(source_row, 0)
        index = self._filter_model.mapFromSource(source_index)
        if not index.isValid():
            self.view.clearSelection()
            self.view.setCurrentIndex(QModelIndex())
            return
        self.view.setCurrentIndex(index)
        self.view.scrollTo(index)

    def _filter_items(self, text: str) -> None:
        self._filter_model.set_filter(text)
        self.view.scrollToTop()

    def _on_index_clicked(self, index: QModelIndex) -> None:
        if not index.isValid():
            return
        row = self._filter_model.mapToSource(index).row()
        if not 0 <= row < len(self._entries):
            return
        self.fontSelected.emit(row)
        self.close()

    def event(self, e):
        result = super().event(e)
        if e.type() == QEvent.Type.WindowActivate:
            self._was_activated = True
        elif e.type() == QEvent.Type.WindowDeactivate and self._was_activated:
            self.close()
        return result

    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_Escape:
            self.close()
            return
        if e.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._on_index_clicked(self.view.currentIndex())
            return
        super().keyPressEvent(e)


def populate_font_combo(combo, current: str | None = None, locale_code: str = "en_US") -> None:
    combo.clear()
    combo._font_search_terms = {}
    combo._font_alias_to_family = {}
    include_system = getattr(combo, "_include_system_fonts", _SYSTEM_FONTS_ENABLED)
    for display, value, aliases in list_font_style_entries(locale_code, include_system=include_system):
        combo.addItem(display, value)
        combo._font_search_terms[value] = _search_key(" ".join((display, *aliases)))
        for alias in aliases:
            combo._font_alias_to_family.setdefault(_search_key(alias), value)
    if not current:
        return
    for index in range(combo.count()):
        if combo.itemData(index) == current:
            combo.setCurrentIndex(index)
            return
    current = combo._font_alias_to_family.get(_search_key(current), current)
    for index in range(combo.count()):
        if combo.itemData(index) == current:
            combo.setCurrentIndex(index)
            return
    family, style = split_font_value(current)
    display, aliases = localized_font_family(family, locale_code)
    if style:
        display = f'{display} - {style}'
    combo.addItem(display, current)
    combo._font_search_terms[current] = _search_key(" ".join((display, *aliases)))
    combo.setCurrentIndex(combo.count() - 1)


class FontComboBox(QComboBox):
    currentFontChanged = pyqtSignal(QFont)

    def __init__(self, parent=None, locale_getter: Callable[[], str] | None = None):
        self._locale_getter = locale_getter
        self._cached_locale_code: str | None = None
        self._include_system_fonts = _SYSTEM_FONTS_ENABLED
        self._font_search_terms: dict[str, str] = {}
        self._font_alias_to_family: dict[str, str] = {}
        self._popup: _FontPopup | None = None
        super().__init__(parent)
        self.setEditable(False)
        self.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.setMinimumContentsLength(10)
        _FONT_COMBO_INSTANCES.add(self)
        self.currentIndexChanged.connect(self._emit_current_font_changed)
        self.refresh("")

    def showPopup(self):
        self.refresh()
        if self.count() <= 0:
            return
        locale_code = self._locale_code()
        entries = [
            (
                self.itemText(index),
                str(self.itemData(index) or self.itemText(index)),
                self._font_search_terms.get(
                    str(self.itemData(index) or ""),
                    _search_key(self.itemText(index)),
                ),
            )
            for index in range(self.count())
        ]
        popup = _FontPopup(
            entries,
            _FONT_SEARCH_PLACEHOLDERS.get(locale_code, _FONT_SEARCH_PLACEHOLDERS["en_US"]),
            self,
        )
        popup.fontSelected.connect(self._on_popup_font_selected)
        popup.destroyed.connect(self._on_popup_destroyed)
        self._popup = popup

        screen = QGuiApplication.screenAt(self.mapToGlobal(self.rect().center()))
        if screen is None:
            screen = QGuiApplication.primaryScreen()
        avail = screen.availableGeometry()
        below = self.mapToGlobal(QPoint(0, self.height()))
        above = self.mapToGlobal(QPoint(0, 0))
        space_below = avail.bottom() - below.y()
        space_above = above.y() - avail.top()
        width = max(self.width(), popup.natural_width() + 32)
        width = min(width, avail.width())
        x = below.x()
        if x + width > avail.right():
            x = avail.right() - width + 1
        if x < avail.left():
            x = avail.left()
        if space_below >= space_above:
            y = below.y()
            height = max(space_below, 120)
        else:
            height = max(space_above, 120)
            y = above.y() - height
        popup.setGeometry(x, y, width, height)
        popup.set_current_source_row(self.currentIndex())
        popup.show()
        QTimer.singleShot(0, popup.search_edit.setFocus)

    def hidePopup(self):
        if self._popup is not None:
            popup = self._popup
            self._popup = None
            popup.close()
        super().hidePopup()

    def _on_popup_font_selected(self, row: int):
        if 0 <= row < self.count():
            self.setCurrentIndex(row)
        self.hidePopup()

    def _on_popup_destroyed(self, *_args):
        self._popup = None

    def refresh(self, current_family: str | None = None) -> None:
        family = self.currentFamily() if current_family is None else str(current_family or "")
        blocker = QSignalBlocker(self)
        try:
            populate_font_combo(self, family or None, self._locale_code())
            if not family:
                self.setCurrentIndex(-1)
        finally:
            del blocker

    def refresh_ui_texts(self) -> None:
        self._cached_locale_code = None
        self.refresh()

    def set_include_system_fonts(self, enabled: bool) -> None:
        enabled = bool(enabled)
        if self._include_system_fonts == enabled:
            return
        current = self.currentFamily()
        self._include_system_fonts = enabled
        self.refresh(current)

    def wheelEvent(self, event: QWheelEvent) -> None:
        event.ignore()

    def _locale_code(self) -> str:
        if self._cached_locale_code is not None:
            return self._cached_locale_code
        locale_code = ""
        if self._locale_getter is not None:
            try:
                locale_code = str(self._locale_getter() or "")
            except RuntimeError:
                pass
        self._cached_locale_code = locale_code or QLocale.system().name()
        return self._cached_locale_code

    def currentFamily(self) -> str:
        return str(self.currentData() or self.currentText() or "")

    def setCurrentFamily(self, family: str) -> None:
        value = str(family or "")
        if not value:
            self.setCurrentIndex(-1)
            return
        index = self.findData(value)
        if index < 0:
            value = self._font_alias_to_family.get(_search_key(value), value)
            index = self.findData(value)
        if index < 0:
            family_name, style = split_font_value(value)
            display, aliases = localized_font_family(family_name, self._locale_code())
            if style:
                display = f"{display} - {style}"
            self.addItem(display, value)
            self._font_search_terms[value] = _search_key(" ".join((display, *aliases, style)))
            index = self.count() - 1
        self.setCurrentIndex(index)

    def currentFont(self) -> QFont:
        return qfont_for_value(self.currentFamily())

    def _emit_current_font_changed(self, _index: int) -> None:
        self.currentFontChanged.emit(self.currentFont())


def set_system_fonts_enabled(enabled: bool) -> None:
    global _SYSTEM_FONTS_ENABLED
    enabled = bool(enabled)
    _SYSTEM_FONTS_ENABLED = enabled
    _clear_font_catalog_caches()
    for combo in list(_FONT_COMBO_INSTANCES):
        try:
            combo.set_include_system_fonts(enabled)
        except RuntimeError:
            continue
