"""Plain-text stand-in for the richtext.v1 document helpers."""

from __future__ import annotations

from typing import Any


def is_rich_text_document(value: Any) -> bool:
    return isinstance(value, dict) and ("runs" in value or "content" in value or value.get("format") == "richtext.v1")


def ensure_rich_text_document(value: Any):
    if is_rich_text_document(value):
        return _PlainDocument(value)
    raise TypeError("not a rich text document")


class _PlainDocument:
    def __init__(self, value: Any):
        self._value = value

    def to_dict(self) -> dict:
        return dict(self._value) if isinstance(self._value, dict) else {}
