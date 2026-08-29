"""Overwrite policy helpers for existing translation outputs."""

from __future__ import annotations

import os
from typing import Callable, Iterable, Optional

OVERWRITE_ASK = "ask"
OVERWRITE_ALWAYS = "always"
OVERWRITE_SKIP = "skip"
OVERWRITE_MODES = (OVERWRITE_ASK, OVERWRITE_ALWAYS, OVERWRITE_SKIP)


def normalize_overwrite_mode(value) -> str:
    if isinstance(value, str):
        text = value.strip().lower()
        if text in {OVERWRITE_ASK, "prompt", "1"}:
            return OVERWRITE_ASK
        if text in {OVERWRITE_ALWAYS, "overwrite", "true", "2"}:
            return OVERWRITE_ALWAYS
        if text in {OVERWRITE_SKIP, "never", "false", "3"}:
            return OVERWRITE_SKIP
    if value is True:
        return OVERWRITE_ALWAYS
    if value is False:
        return OVERWRITE_SKIP
    return OVERWRITE_ASK


def overwrite_enabled(value) -> bool:
    return normalize_overwrite_mode(value) == OVERWRITE_ALWAYS


def find_existing_result_name(
    file_path: str,
    cli_config: dict,
    output_path: Optional[str] = None,
) -> Optional[str]:
    """Return the existing result filename, or None if this source can proceed."""
    if cli_config.get("translate_json_only", False):
        return None

    if cli_config.get("template", False) and cli_config.get("save_text", False):
        from manga_translator.utils.path_manager import find_script_txt_for_mode

        txt_path = find_script_txt_for_mode(
            file_path, bool(cli_config.get("combine_txt", True))
        )
        if txt_path:
            return os.path.basename(txt_path)
        return None

    if cli_config.get("generate_and_export", False):
        from manga_translator.utils.path_manager import find_script_txt_for_mode

        txt_path = find_script_txt_for_mode(
            file_path, bool(cli_config.get("combine_txt", True))
        )
        if txt_path:
            return os.path.basename(txt_path)
        return None

    if output_path and os.path.exists(output_path):
        return os.path.basename(output_path)
    return None


def collect_existing_outputs(
    file_paths: Iterable[str],
    cli_config: dict,
    calculate_output_path: Callable[[str], str],
) -> list[tuple[str, str]]:
    existing: list[tuple[str, str]] = []
    for file_path in file_paths:
        try:
            output_path = calculate_output_path(file_path)
            existing_name = find_existing_result_name(file_path, cli_config, output_path)
        except Exception:
            continue
        if existing_name:
            existing.append((file_path, existing_name))
    return existing
