"""Split-file TXT tokens: [P0000T0001R] / editor copies [P0000V0001R]."""

from __future__ import annotations

import logging
import os
import re
import subprocess
import sys
from typing import Dict, Iterable, List, Optional, Tuple

from manga_translator.utils.path_manager import (
    get_combined_script_backup_path,
    infer_page_index_from_name,
)

COMBINED_SCRIPT_BACKUP_HEADER = "보존용 원본 TXT입니다. 번역 프로세스에 사용되지 않습니다."
TXT_HELP_TEMPLATE_NAME = "txt_help_template.txt"
_TXT_HELP_FILENAME_FALLBACK = {
    "ko_KR": "도움말.txt",
    "en_US": "Help.txt",
    "ja_JP": "ヘルプ.txt",
    "zh_CN": "帮助.txt",
    "zh_TW": "說明.txt",
    "es_ES": "Ayuda.txt",
}

def apply_token_translations(regions: List[dict], translations: Dict[str, str]) -> Tuple[int, int]:
    """Update region translation fields from token map. Returns (updated, skipped)."""
    updated = 0
    skipped = 0
    for region in regions:
        if not isinstance(region, dict):
            continue
        region_id = str(region.get("region_id") or "")
        if not is_region_id(region_id):
            skipped += 1
            continue
        if region_id not in translations:
            skipped += 1
            logger.info("TXT token not found, keeping existing translation: %s", region_id)
            continue
        new_translation = translations[region_id]
        old_translation = region.get("translation", "")
        old_raw = region.get("translation_raw", "")
        if old_translation != new_translation or old_raw != new_translation:
            region["translation"] = new_translation
            region["translation_raw"] = new_translation
            updated += 1
    return updated, skipped
