#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
路径管理模块
提供统一的文件路径生成和查找功能，支持新的目录结构和向后兼容
"""

import json
import os
import re
from typing import Optional, Tuple

# 工作目录名称常量
WORK_DIR_NAME = "manga_translator_work"
JSON_SUBDIR = "json"
TRANSLATION_SUBDIR = "translation"
TRANSLATIONS_SUBDIR = TRANSLATION_SUBDIR
SCRIPT_SUBDIR = TRANSLATION_SUBDIR
TXT_SUBDIR = TRANSLATION_SUBDIR
LEGACY_SCRIPT_SUBDIR = "script"
LEGACY_TRANSLATIONS_SUBDIR = "translations"
LEGACY_TXT_SUBDIR = "txt"
ORIGINALS_SUBDIR = "originals"
ORIGINAL_SUBDIR = "original"
YOLO_LABELS_SUBDIR = "yolo_labels"
INPAINTED_SUBDIR = "inpainted"
PAINT_OVERLAY_SUBDIR = "paint_overlay"  # 彩色画笔涂鸦图层目录
TRANSLATED_IMAGES_SUBDIR = "translated_images"  # 已翻译图片目录（替换翻译模式使用）
EDITOR_BASE_SUBDIR = "editor_base"
TRANSLATION_MAP_FILENAME = "translation_map.json"
PAGE_SCRIPT_TXT_SUFFIX = " script.txt"
COMBINED_SCRIPT_TXT_NAME = "combined_script.txt"
COMBINED_SCRIPT_BACKUP_TXT_NAME = "combined_script_BACKUP.txt"
RENDER_COMPLETE_NAME = "RENDER_COMPLETE"
COMBINED_ORIGINAL_TXT_NAME = COMBINED_SCRIPT_TXT_NAME
_PAGE_IMAGE_EXTS = frozenset({
    ".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp", ".avif",
    ".tiff", ".tif", ".heic", ".heif",
})
_TRANSLATION_MAP_WALK_SKIP = {
    WORK_DIR_NAME,
    "__pycache__",
    ".git",
    ".svn",
    "node_modules",
    ".venv",
    "venv",
}
_MAX_TRANSLATION_MAP_WALK_DIRS = 4000
WORK_DIR_RESERVED_NAMES = {
    JSON_SUBDIR,
    TRANSLATION_SUBDIR,
    LEGACY_SCRIPT_SUBDIR,
    LEGACY_TRANSLATIONS_SUBDIR,
    LEGACY_TXT_SUBDIR,
    ORIGINALS_SUBDIR,
    ORIGINAL_SUBDIR,
    YOLO_LABELS_SUBDIR,
    INPAINTED_SUBDIR,
    PAINT_OVERLAY_SUBDIR,
    TRANSLATED_IMAGES_SUBDIR,
    EDITOR_BASE_SUBDIR,
}


def normalize_image_path(image_path: str) -> str:
    """规范化图片路径。"""
    return os.path.normpath(os.path.abspath(image_path))


def has_translation_map(path: str, max_walk_dirs: int = _MAX_TRANSLATION_MAP_WALK_DIRS) -> bool:
    """True when this file/folder belongs to a rendered output folder."""
    if not path:
        return False
    try:
        target = os.path.normpath(path)
        if os.path.isfile(target):
            return os.path.isfile(os.path.join(os.path.dirname(target), TRANSLATION_MAP_FILENAME))
        if not os.path.isdir(target):
            return False
        if os.path.isfile(os.path.join(target, TRANSLATION_MAP_FILENAME)):
            return True
        walked = 0
        for root, dirs, files in os.walk(target):
            walked += 1
            if walked > max_walk_dirs:
                break
            dirs[:] = [
                name for name in dirs
                if name.lower() not in _TRANSLATION_MAP_WALK_SKIP and not name.startswith(".")
            ]
            if TRANSLATION_MAP_FILENAME in files:
                return True
    except OSError:
        return False
    return False


def any_path_has_translation_map(paths) -> bool:
    for path in paths or ():
        if has_translation_map(path):
            return True
    return False


def is_work_image_path(image_path: str) -> bool:
    """
    判断路径是否是编辑器专用的上色/超分底图。
    """
    norm_path = normalize_image_path(image_path)
    parent_dir = os.path.dirname(norm_path)
    grandparent_dir = os.path.dirname(parent_dir)

    # 新结构：manga_translator_work/editor_base/xxx.png
    if (
        os.path.basename(parent_dir) == EDITOR_BASE_SUBDIR and
        os.path.basename(grandparent_dir) == WORK_DIR_NAME
    ):
        return True

    # 兼容之前已经落在根目录的临时底图
    if os.path.basename(parent_dir) == WORK_DIR_NAME:
        return os.path.basename(norm_path) not in WORK_DIR_RESERVED_NAMES

    return False


def resolve_original_image_path(image_path: str) -> str:
    """
    将工作目录中的统一底图路径还原为原图路径，其它路径保持原样。
    """
    norm_path = normalize_image_path(image_path)
    if not is_work_image_path(norm_path):
        return norm_path

    parent_dir = os.path.dirname(norm_path)
    grandparent_dir = os.path.dirname(parent_dir)

    if (
        os.path.basename(parent_dir) == EDITOR_BASE_SUBDIR and
        os.path.basename(grandparent_dir) == WORK_DIR_NAME
    ):
        source_dir = os.path.dirname(grandparent_dir)
        return os.path.join(source_dir, os.path.basename(norm_path))

    source_dir = os.path.dirname(parent_dir)
    return os.path.join(source_dir, os.path.basename(norm_path))


def get_work_dir(image_path: str) -> str:
    """
    获取图片对应的工作目录路径
    
    Args:
        image_path: 原图片路径
        
    Returns:
        工作目录的绝对路径
    """
    image_dir = os.path.dirname(resolve_original_image_path(image_path))
    return os.path.join(image_dir, WORK_DIR_NAME)


def get_work_image_path(image_path: str, create_dir: bool = True) -> str:
    """
    获取编辑器专用的上色/超分底图路径。
    """
    if is_work_image_path(image_path):
        work_image_path = normalize_image_path(image_path)
        if create_dir:
            os.makedirs(os.path.dirname(work_image_path), exist_ok=True)
        return work_image_path

    original_path = resolve_original_image_path(image_path)
    work_dir = get_work_dir(original_path)
    editor_base_dir = os.path.join(work_dir, EDITOR_BASE_SUBDIR)
    if create_dir:
        os.makedirs(editor_base_dir, exist_ok=True)
    return os.path.join(editor_base_dir, os.path.basename(original_path))


def find_work_image_path(image_path: str) -> Optional[str]:
    """查找编辑器专用的上色/超分底图。"""
    work_image_path = get_work_image_path(image_path, create_dir=False)
    if os.path.exists(work_image_path):
        return work_image_path

    # 兼容之前可能已经落在根目录的底图
    original_path = resolve_original_image_path(image_path)
    legacy_root_work_image = os.path.join(get_work_dir(original_path), os.path.basename(original_path))
    if os.path.exists(legacy_root_work_image):
        return legacy_root_work_image

    return None


_INPAINTED_LEGACY_EXTS = (
    ".jpg",
    ".jpeg",
    ".webp",
    ".bmp",
    ".gif",
    ".avif",
    ".heic",
    ".heif",
    ".tif",
    ".tiff",
    ".png",
)


def _inpainted_dir_and_stem(image_path: str, create_dir: bool = True) -> Tuple[str, str, str]:
    original_path = resolve_original_image_path(image_path)
    inpainted_dir = os.path.join(get_work_dir(original_path), INPAINTED_SUBDIR)
    if create_dir:
        os.makedirs(inpainted_dir, exist_ok=True)
    base_name = os.path.splitext(os.path.basename(original_path))[0]
    return inpainted_dir, base_name, original_path


def get_legacy_inpainted_path(image_path: str, create_dir: bool = True) -> str:
    """
    구버전 복구 이미지 경로 (manga_translator_work/inpainted/*_inpainted.{원본확장자}).
    """
    inpainted_dir, base_name, original_path = _inpainted_dir_and_stem(image_path, create_dir=create_dir)
    ext = os.path.splitext(original_path)[1]
    return os.path.join(inpainted_dir, f"{base_name}_inpainted{ext}")


def get_json_path(image_path: str, create_dir: bool = True) -> str:
    """
    获取JSON配置文件的路径
    
    Args:
        image_path: 原图片路径
        create_dir: 是否自动创建目录
        
    Returns:
        JSON文件的绝对路径
    """
    work_dir = get_work_dir(image_path)
    json_dir = os.path.join(work_dir, JSON_SUBDIR)
    
    if create_dir:
        os.makedirs(json_dir, exist_ok=True)
    
    base_name = os.path.splitext(os.path.basename(image_path))[0]
    return os.path.join(json_dir, f"{base_name}_translations.json")


def clamp_page_index(page_index) -> Optional[int]:
    try:
        return max(0, min(int(page_index), 9999))
    except (TypeError, ValueError):
        return None


def format_page_script_txt_name(page_index: int) -> str:
    page = clamp_page_index(page_index)
    if page is None:
        page = 0
    return f"{page:04d}{PAGE_SCRIPT_TXT_SUFFIX}"


def _path_natural_sort_key(path: str):
    parts = []
    for part in re.split(r"(\d+)", path.replace("\\", "/")):
        if part.isdigit():
            parts.append((False, int(part)))
        elif part:
            parts.append((True, part.lower()))
    return parts


def _folder_page_images(folder: str) -> list:
    images = []
    try:
        for name in os.listdir(folder):
            path = os.path.join(folder, name)
            ext = os.path.splitext(name)[1].lower()
            if os.path.isfile(path) and ext in _PAGE_IMAGE_EXTS:
                images.append(os.path.normpath(os.path.abspath(path)))
    except OSError:
        return []
    images.sort(key=_path_natural_sort_key)
    return images


def _page_folder_and_stem(source_name: str) -> Tuple[Optional[str], str]:
    """Image folder + stem used for page numbering. Filename digits are not the page."""
    if not source_name:
        return None, ""

    raw = os.path.normpath(source_name)
    stem = os.path.splitext(os.path.basename(raw))[0]
    stem = re.sub(r"_translations$", "", stem)
    stem = re.sub(r"_original$", "", stem)
    stem = re.sub(r"_translated$", "", stem)
    stem = re.sub(r"\s+script$", "", stem, flags=re.IGNORECASE)

    abs_path = os.path.abspath(raw)
    parent = os.path.dirname(abs_path)

    if os.path.basename(parent) in {JSON_SUBDIR, TRANSLATION_SUBDIR, LEGACY_SCRIPT_SUBDIR, LEGACY_TXT_SUBDIR}:
        work = os.path.dirname(parent)
        if os.path.basename(work) == WORK_DIR_NAME:
            return os.path.dirname(work), stem

    if is_work_image_path(abs_path):
        original = resolve_original_image_path(abs_path)
        return os.path.dirname(original), os.path.splitext(os.path.basename(original))[0]

    if os.path.isdir(abs_path):
        return abs_path, stem
    return parent or None, stem


def infer_page_index_from_name(source_name: str) -> int:
    """0-based index among images in the same folder. Filename numbers are ignored.

    Each folder starts at 0. The next image in that folder is 1, then 2, ...
    A different folder starts again at 0.
    """
    folder, stem = _page_folder_and_stem(source_name)
    if not folder:
        return 0

    images = _folder_page_images(folder)
    if not images:
        return 0

    stem_l = stem.lower()
    for index, image_path in enumerate(images):
        image_stem = os.path.splitext(os.path.basename(image_path))[0]
        if image_stem.lower() == stem_l:
            page = clamp_page_index(index)
            return 0 if page is None else page

    try:
        target = os.path.normpath(os.path.abspath(source_name))
    except (TypeError, ValueError, OSError):
        return 0
    for index, image_path in enumerate(images):
        if image_path == target:
            page = clamp_page_index(index)
            return 0 if page is None else page
    return 0


def page_index_from_json_file(json_path: str) -> Optional[int]:
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return None
    if not isinstance(data, dict) or not data:
        return None
    image_data = next(iter(data.values()), None)
    if not isinstance(image_data, dict):
        return None
    page = clamp_page_index(image_data.get("page_index"))
    if page is not None:
        return page
    for region in image_data.get("regions") or []:
        if not isinstance(region, dict):
            continue
        region_id = str(region.get("region_id") or "")
        if (
            len(region_id) == 11
            and region_id[0] == "P"
            and region_id[5] in ("T", "V")
            and region_id.endswith("R")
            and region_id[1:5].isdigit()
            and region_id[6:10].isdigit()
        ):
            return int(region_id[1:5])
    return None


def resolve_script_page_index(
    image_path: str,
    page_index: Optional[int] = None,
    json_path: Optional[str] = None,
) -> int:
    page = clamp_page_index(page_index)
    if page is not None:
        return page
    resolved_json = json_path or find_json_path(image_path)
    if resolved_json:
        page = page_index_from_json_file(resolved_json)
        if page is not None:
            return page
    return infer_page_index_from_name(image_path)


def get_txt_dir(image_path: str, create_dir: bool = True) -> str:
    work_dir = get_work_dir(image_path)
    translation_dir = os.path.join(work_dir, TRANSLATION_SUBDIR)
    if create_dir:
        os.makedirs(translation_dir, exist_ok=True)
    return translation_dir


def get_original_txt_path(
    image_path: str,
    create_dir: bool = True,
    page_index: Optional[int] = None,
) -> str:
    """Return the working script TXT path: translation/0000 script.txt."""
    txt_dir = get_txt_dir(image_path, create_dir=create_dir)
    page = resolve_script_page_index(image_path, page_index)
    return os.path.join(txt_dir, format_page_script_txt_name(page))


def find_original_txt_path(
    image_path: str,
    page_index: Optional[int] = None,
) -> Optional[str]:
    """Find translation/{page} script.txt only. Other folders/names are ignored."""
    new_path = get_original_txt_path(image_path, create_dir=False, page_index=page_index)
    if os.path.exists(new_path):
        return new_path
    return None


def get_translated_txt_path(
    image_path: str,
    create_dir: bool = True,
    page_index: Optional[int] = None,
) -> str:
    return get_original_txt_path(image_path, create_dir=create_dir, page_index=page_index)


COMBINED_TRANSLATED_TXT_NAME = COMBINED_SCRIPT_TXT_NAME


def get_combined_script_backup_path(combined_path: str) -> str:
    return os.path.join(os.path.dirname(os.path.abspath(combined_path)), COMBINED_SCRIPT_BACKUP_TXT_NAME)


def get_render_complete_path(txt_dir: str) -> str:
    return os.path.join(txt_dir, RENDER_COMPLETE_NAME)


def write_render_complete_marker(txt_dir: str) -> str:
    """Create an empty RENDER_COMPLETE file in translation/."""
    if not txt_dir:
        return ""
    os.makedirs(txt_dir, exist_ok=True)
    path = get_render_complete_path(txt_dir)
    with open(path, "w", encoding="utf-8"):
        pass
    return path


def get_combined_original_txt_path(image_path: str, create_dir: bool = True) -> str:
    txt_dir = get_txt_dir(image_path, create_dir=create_dir)
    return os.path.join(txt_dir, COMBINED_SCRIPT_TXT_NAME)


def find_combined_original_txt_path(image_path: str) -> Optional[str]:
    """Find translation/combined_script.txt only. Other folders/names are ignored."""
    new_path = get_combined_original_txt_path(image_path, create_dir=False)
    if os.path.exists(new_path):
        return new_path
    return None


def find_script_txt_for_mode(image_path: str, combine: bool) -> Optional[str]:
    if combine:
        return find_combined_original_txt_path(image_path)
    return find_original_txt_path(image_path)


def get_combined_translated_txt_path(image_path: str, create_dir: bool = True) -> str:
    return get_combined_original_txt_path(image_path, create_dir=create_dir)


def get_combined_txt_path_from_json(json_path: str, original: bool = True, create_dir: bool = True) -> str:
    json_dir = os.path.dirname(os.path.abspath(json_path))
    if json_dir.endswith(os.path.join("manga_translator_work", JSON_SUBDIR)):
        work_dir = os.path.dirname(json_dir)
    else:
        work_dir = json_dir
    target_dir = os.path.join(work_dir, TRANSLATION_SUBDIR)
    if create_dir:
        os.makedirs(target_dir, exist_ok=True)
    return os.path.join(target_dir, COMBINED_SCRIPT_TXT_NAME)


def get_yolo_labels_dir(image_path: str, create_dir: bool = True) -> str:
    """
    获取 YOLO 标注目录路径。

    Args:
        image_path: 原图片路径
        create_dir: 是否自动创建目录

    Returns:
        YOLO 标注目录的绝对路径
    """
    work_dir = get_work_dir(image_path)
    yolo_labels_dir = os.path.join(work_dir, YOLO_LABELS_SUBDIR)

    if create_dir:
        os.makedirs(yolo_labels_dir, exist_ok=True)

    return yolo_labels_dir


def get_yolo_label_path(image_path: str, create_dir: bool = True) -> str:
    """
    获取图片对应的 YOLO 标注文件路径。

    Args:
        image_path: 原图片路径
        create_dir: 是否自动创建目录

    Returns:
        YOLO 标注文件的绝对路径
    """
    yolo_labels_dir = get_yolo_labels_dir(image_path, create_dir=create_dir)
    base_name = os.path.splitext(os.path.basename(resolve_original_image_path(image_path)))[0]
    return os.path.join(yolo_labels_dir, f"{base_name}.txt")


def find_yolo_label_path(image_path: str) -> Optional[str]:
    """
    查找图片对应的 YOLO 标注文件。

    Args:
        image_path: 原图片路径

    Returns:
        找到的 YOLO 标注文件路径，如果不存在返回 None
    """
    original_path = resolve_original_image_path(image_path)
    yolo_label_path = get_yolo_label_path(original_path, create_dir=False)
    if os.path.exists(yolo_label_path):
        return yolo_label_path

    legacy_yolo_label_path = os.path.splitext(original_path)[0] + ".txt"
    if os.path.exists(legacy_yolo_label_path):
        return legacy_yolo_label_path

    return None


def get_inpainted_path(image_path: str, create_dir: bool = True) -> str:
    """
    복구 이미지 저장 경로. 원본 확장자와 무관하게 항상 PNG.
    """
    inpainted_dir, base_name, _ = _inpainted_dir_and_stem(image_path, create_dir=create_dir)
    return os.path.join(inpainted_dir, f"{base_name}_inpainted.png")


def get_translated_images_dir(image_path: str, create_dir: bool = True) -> str:
    """
    获取已翻译图片目录的路径
    
    Args:
        image_path: 原图片路径
        create_dir: 是否自动创建目录
        
    Returns:
        已翻译图片目录的绝对路径
    """
    work_dir = get_work_dir(image_path)
    translated_dir = os.path.join(work_dir, TRANSLATED_IMAGES_SUBDIR)
    
    if create_dir:
        os.makedirs(translated_dir, exist_ok=True)
    
    return translated_dir


def find_translated_source_json(target_image_path: str, translated_dir: str) -> Optional[str]:
    """
    在已翻译图片目录中查找与目标图同名的翻译数据JSON
    
    用于替换翻译模式：根据生肉图的文件名，在已翻译目录中查找同名图片的JSON
    
    Args:
        target_image_path: 目标图片（生肉）的路径
        translated_dir: 已翻译图片所在目录
        
    Returns:
        找到的JSON文件路径，如果不存在返回None
    """
    if not translated_dir or not os.path.isdir(translated_dir):
        return None
    
    # 获取目标图的基础文件名（不含扩展名）
    target_basename = os.path.splitext(os.path.basename(target_image_path))[0]
    
    # 在已翻译目录中查找同名图片
    # 尝试查找 manga_translator_work/json/文件名_translations.json
    translated_work_dir = os.path.join(translated_dir, WORK_DIR_NAME, JSON_SUBDIR)
    if os.path.isdir(translated_work_dir):
        json_path = os.path.join(translated_work_dir, f"{target_basename}_translations.json")
        if os.path.exists(json_path):
            return json_path
    
    # 向后兼容：查找 已翻译目录/文件名_translations.json
    old_json_path = os.path.join(translated_dir, f"{target_basename}_translations.json")
    if os.path.exists(old_json_path):
        return old_json_path
    
    # 尝试匹配任意图片扩展名
    for ext in ['.jpg', '.jpeg', '.png', '.webp', '.bmp', '.gif']:
        # 构造可能的已翻译图片路径
        possible_translated_image = os.path.join(translated_dir, f"{target_basename}{ext}")
        if os.path.exists(possible_translated_image):
            # 查找该图片对应的JSON
            json_path = find_json_path(possible_translated_image)
            if json_path:
                return json_path
    
    return None


def find_json_path(image_path: str) -> Optional[str]:
    """
    查找JSON配置文件，优先查找新位置，支持向后兼容
    
    Args:
        image_path: 原图片路径
        
    Returns:
        找到的JSON文件路径，如果不存在返回None
    """
    original_path = resolve_original_image_path(image_path)

    # 1. 优先查找新位置
    new_json_path = get_json_path(original_path, create_dir=False)
    if os.path.exists(new_json_path):
        return new_json_path
    
    # 2. 向后兼容：查找旧位置（图片同目录）
    old_json_path = os.path.splitext(original_path)[0] + '_translations.json'
    if os.path.exists(old_json_path):
        return old_json_path
    
    return None


def find_inpainted_path(image_path: str) -> Optional[str]:
    """
    복구 이미지를 찾는다. PNG를 우선하고, 예전 원본 확장자 파일은 호환용으로만 조회한다.
    """
    inpainted_path = get_inpainted_path(image_path, create_dir=False)
    if os.path.exists(inpainted_path):
        return inpainted_path

    seen = {os.path.normcase(os.path.normpath(inpainted_path))}
    candidates = [get_legacy_inpainted_path(image_path, create_dir=False)]
    inpainted_dir, base_name, _ = _inpainted_dir_and_stem(image_path, create_dir=False)
    for ext in _INPAINTED_LEGACY_EXTS:
        candidates.append(os.path.join(inpainted_dir, f"{base_name}_inpainted{ext}"))

    for candidate in candidates:
        normalized = os.path.normcase(os.path.normpath(candidate))
        if normalized in seen:
            continue
        seen.add(normalized)
        if os.path.exists(candidate):
            return candidate

    return None


def get_paint_overlay_path(image_path: str, create_dir: bool = True) -> str:
    """
    获取彩色画笔涂鸦图层（paint overlay）的保存路径。

    存放在 manga_translator_work/paint_overlay/<basename>_overlay.png。
    统一使用 PNG 以保留 alpha 通道。

    Args:
        image_path: 原图片路径
        create_dir: 是否自动创建目录

    Returns:
        paint overlay 图片的绝对路径
    """
    original_path = resolve_original_image_path(image_path)
    work_dir = get_work_dir(original_path)
    overlay_dir = os.path.join(work_dir, PAINT_OVERLAY_SUBDIR)

    if create_dir:
        os.makedirs(overlay_dir, exist_ok=True)

    base_name = os.path.splitext(os.path.basename(original_path))[0]
    return os.path.join(overlay_dir, f"{base_name}_overlay.png")


def find_paint_overlay_path(image_path: str) -> Optional[str]:
    """查找已保存的彩色画笔涂鸦图层文件。"""
    overlay_path = get_paint_overlay_path(image_path, create_dir=False)
    if os.path.exists(overlay_path):
        return overlay_path
    return None


def find_txt_files(image_path: str) -> Tuple[Optional[str], Optional[str]]:
    """Find translation/{page} script.txt only. Other folders/names are ignored."""
    script_path = find_original_txt_path(image_path)
    return script_path, None


def get_legacy_json_path(image_path: str) -> str:
    """
    获取旧版JSON文件路径（图片同目录）
    用于向后兼容
    
    Args:
        image_path: 原图片路径
        
    Returns:
        旧版JSON文件路径
    """
    return os.path.splitext(image_path)[0] + '_translations.json'


def migrate_legacy_files(image_path: str, move_files: bool = False) -> dict:
    """
    迁移旧版文件到新目录结构
    
    Args:
        image_path: 原图片路径
        move_files: 是否移动文件（True）还是复制文件（False）
        
    Returns:
        迁移结果字典，包含成功和失败的文件列表
    """
    import shutil
    
    result = {
        'success': [],
        'failed': [],
        'skipped': []
    }
    
    # 检查并迁移JSON文件
    old_json = get_legacy_json_path(image_path)
    if os.path.exists(old_json):
        new_json = get_json_path(image_path, create_dir=True)
        if not os.path.exists(new_json):
            try:
                if move_files:
                    shutil.move(old_json, new_json)
                else:
                    shutil.copy2(old_json, new_json)
                result['success'].append(('json', old_json, new_json))
            except Exception as e:
                result['failed'].append(('json', old_json, str(e)))
        else:
            result['skipped'].append(('json', old_json, 'target exists'))
    
    # 检查并迁移旧版TXT文件
    old_txt = os.path.splitext(image_path)[0] + '_translations.txt'
    if os.path.exists(old_txt):
        new_txt = get_translated_txt_path(image_path, create_dir=True)
        if not os.path.exists(new_txt):
            try:
                if move_files:
                    shutil.move(old_txt, new_txt)
                else:
                    shutil.copy2(old_txt, new_txt)
                result['success'].append(('txt', old_txt, new_txt))
            except Exception as e:
                result['failed'].append(('txt', old_txt, str(e)))
        else:
            result['skipped'].append(('txt', old_txt, 'target exists'))
    
    return result
