"""Plain-text stand-in for rich-text sync used by batch edit."""

from __future__ import annotations

from typing import Any


def document_has_styling(document: Any) -> bool:
    del document
    return False


def sync_region_rich_translation(*_args, **_kwargs) -> None:
    return None
