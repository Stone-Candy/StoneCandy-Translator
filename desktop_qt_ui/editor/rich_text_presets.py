"""Minimal rich-text preset helpers for batch edit."""

from __future__ import annotations

from .rich_text_editing import normalize_text_style


def normalize_rich_text_preset(payload: object) -> dict | None:
    if not isinstance(payload, dict):
        return None
    try:
        style = normalize_text_style(payload.get("style") or {})
    except (TypeError, ValueError):
        return None
    ruby = payload.get("ruby", "")
    if not isinstance(ruby, str):
        return None
    tcy = bool(payload.get("tcy", False))
    if not style and not ruby and not tcy:
        return None
    return {"style": style, "ruby": ruby, "tcy": tcy}
