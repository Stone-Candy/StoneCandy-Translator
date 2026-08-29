"""Plain-text compatibility helpers used by batch edit.

This build stores translations as ``[BR]`` strings and does not render
richtext.v1 documents. The functions below keep the batch-edit engine's
import surface, while operating on the visible translation text only.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Optional


_BR_RE = re.compile(r"\[BR\]|<br\s*/?>", re.IGNORECASE)


def editor_text_to_plain_text(text: str) -> str:
    return str(text or "").replace("↵", "\n")


def plain_text_to_storage_text(text: str) -> str:
    return re.sub(r"\n+", "[BR]", str(text or ""))


def storage_text_to_editor_text(text: Any) -> str:
    if isinstance(text, dict):
        return visible_text_from_document(text)
    return _BR_RE.sub("\n", str(text or ""))


def document_from_region(region_data: dict) -> dict:
    return document_from_text(region_data.get("translation", "") if isinstance(region_data, dict) else "")


def document_from_text(text: Any) -> dict:
    return {"text": storage_text_to_editor_text(text)}


def visible_text_from_document(document: Any) -> str:
    if isinstance(document, dict):
        if "text" in document:
            return str(document.get("text") or "")
        return storage_text_to_editor_text(document.get("translation", ""))
    return storage_text_to_editor_text(document)


def document_to_storage_text(document: Any) -> str:
    return plain_text_to_storage_text(visible_text_from_document(document))


def normalize_text_style(style: Any) -> dict:
    if not isinstance(style, dict):
        return {}
    return {key: value for key, value in style.items() if value not in (None, "", False, {}, [])}


def apply_text_change(document: dict, editor_text: str, position: int, chars_removed: int, chars_added: int) -> dict:
    del position, chars_removed, chars_added
    return document_from_text(editor_text)


def apply_style_to_range(document: dict, start: int, end: int, style: dict) -> dict:
    del start, end, style
    return document


def apply_ruby_to_range(document: dict, start: int, end: int, ruby_text: str) -> dict:
    del start, end, ruby_text
    return document


def apply_tcy_to_range(document: dict, start: int, end: int) -> dict:
    del start, end
    return document


def clear_styles_from_range(document: dict, start: int, end: int) -> dict:
    del start, end
    return document


@dataclass
class StyledSegment:
    start: int
    end: int
    style: dict
    node_type: Optional[str] = None
    ruby_text: str = ""


def styled_segments_for_range(document: dict, start: int, end: int, expand_empty: bool = False) -> list[StyledSegment]:
    del document, start, end, expand_empty
    return []
