#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Pair before/after folders and rewrite stale absolute paths inside JSON."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any, Iterable, Optional


IMAGE_EXTS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
    ".bmp",
    ".gif",
    ".avif",
    ".tif",
    ".tiff",
    ".heic",
    ".heif",
}
SKIP_DIR_NAMES = {
    "__pycache__",
    ".git",
    ".svn",
    "node_modules",
    ".venv",
    "venv",
    "miniconda3",
    "models",
    "build",
    "dist",
    ".idea",
    ".vscode",
}
WORK_DIR_NAME = "manga_translator_work"
WORK_SUBDIRS = {
    "json",
    "translation",
    "translations",
    "script",
    "txt",
    "originals",
    "original",
    "yolo_labels",
    "inpainted",
    "paint_overlay",
    "translated_images",
    "editor_base",
}
MAP_FILENAME = "translation_map.json"
TRANSLATIONS_SUFFIX = "_translations.json"
MAX_WALK_DIRS = 4000


def norm_path(path: str) -> str:
    return os.path.normpath(str(path).strip().strip('"'))


def norm_key(path: str) -> str:
    return os.path.normcase(norm_path(path))


def is_abs_path_string(value: str) -> bool:
    if not isinstance(value, str) or len(value) < 2:
        return False
    text = value.strip()
    if len(text) < 2:
        return False
    if text[1:3] in (":\\", ":/"):
        return True
    if text.startswith("\\\\") or text.startswith("//"):
        return True
    if text.startswith("/") and not text.startswith("//"):
        return True
    return False


def path_variants(path: str) -> list[str]:
    raw = str(path).strip().strip('"')
    variants = [raw, raw.replace("/", "\\"), raw.replace("\\", "/"), norm_path(raw)]
    seen: set[str] = set()
    result: list[str] = []
    for item in variants:
        if item and item not in seen:
            seen.add(item)
            result.append(item)
    return result


def is_under(path: str, root: str) -> bool:
    try:
        rel = os.path.relpath(norm_path(path), norm_path(root))
    except ValueError:
        return False
    return not rel.startswith("..")


def common_parent_dir(paths: Iterable[str]) -> Optional[str]:
    dirs: list[str] = []
    for raw in paths:
        if not raw:
            continue
        item = norm_path(raw)
        dirs.append(item)
    if not dirs:
        return None
    try:
        common = os.path.commonpath(dirs)
    except ValueError:
        return None
    return norm_path(common) if common else None


def remap_path(old_path: str, old_root: str, new_root: str) -> Optional[str]:
    if not old_path or not old_root or not new_root:
        return None
    new_root_n = norm_path(new_root)
    old_root_n = norm_path(old_root)
    for variant in path_variants(old_path):
        variant_n = norm_path(variant)
        if norm_key(variant_n) == norm_key(old_root_n):
            return os.path.normpath(os.path.abspath(new_root_n))
        if is_under(variant_n, old_root_n):
            rel = os.path.relpath(variant_n, old_root_n)
            return os.path.normpath(os.path.abspath(os.path.join(new_root_n, rel)))
    return None


def stem_name(filename: str) -> str:
    return os.path.splitext(os.path.basename(filename))[0].lower()


def relative_stem(path: str, root: str) -> str:
    try:
        rel = os.path.relpath(norm_path(path), norm_path(root))
    except ValueError:
        rel = os.path.basename(path)
    rel_no_ext = os.path.splitext(rel)[0]
    return rel_no_ext.replace("\\", "/").lower()


def is_image_file(name: str) -> bool:
    return os.path.splitext(name)[1].lower() in IMAGE_EXTS


def is_translations_json(name: str) -> bool:
    return name.lower().endswith(TRANSLATIONS_SUFFIX)


def should_skip_dir(name: str) -> bool:
    lowered = name.lower()
    return (
        lowered in SKIP_DIR_NAMES
        or lowered == WORK_DIR_NAME
        or lowered in WORK_SUBDIRS
        or name.startswith(".")
    )


def detect_indent(text: str) -> int:
    for line in text.splitlines()[1:30]:
        stripped = line.lstrip(" \t")
        if not stripped or stripped == stripped.lstrip():
            continue
        prefix = line[: len(line) - len(stripped)]
        if prefix.startswith("\t"):
            return 4
        if prefix.startswith("    "):
            return 4
        if prefix.startswith("  "):
            return 2
    return 4


def unique_existing_dirs(paths: Iterable[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for raw in paths:
        if not raw:
            continue
        path = norm_path(raw)
        if not os.path.isdir(path):
            continue
        key = norm_key(path)
        if key in seen:
            continue
        seen.add(key)
        result.append(path)
    return result


@dataclass
class FolderUnit:
    path: str
    image_stems: set[str] = field(default_factory=set)
    image_basenames: set[str] = field(default_factory=set)
    json_files: list[str] = field(default_factory=list)
    map_path: Optional[str] = None
    map_source_paths: list[str] = field(default_factory=list)
    map_dest_paths: list[str] = field(default_factory=list)
    json_key_paths: list[str] = field(default_factory=list)
    last_export_dirs: list[str] = field(default_factory=list)

    @property
    def name(self) -> str:
        return os.path.basename(self.path.rstrip("\\/")) or self.path


def collect_images(folder: str) -> list[str]:
    images: list[str] = []
    try:
        for dirpath, dirnames, filenames in os.walk(folder):
            dirnames[:] = [name for name in dirnames if not should_skip_dir(name)]
            for filename in filenames:
                if is_image_file(filename):
                    images.append(os.path.join(dirpath, filename))
    except OSError:
        return images
    return images


def collect_json_files(folder: str) -> tuple[Optional[str], list[str]]:
    map_path = None
    json_files: list[str] = []
    try:
        entries = os.listdir(folder)
    except OSError:
        return None, []

    if MAP_FILENAME in entries:
        candidate = os.path.join(folder, MAP_FILENAME)
        if os.path.isfile(candidate):
            map_path = candidate
            json_files.append(candidate)

    for filename in entries:
        if is_translations_json(filename):
            json_files.append(os.path.join(folder, filename))

    work_json_dir = os.path.join(folder, WORK_DIR_NAME, "json")
    if os.path.isdir(work_json_dir):
        try:
            for filename in os.listdir(work_json_dir):
                if is_translations_json(filename):
                    json_files.append(os.path.join(work_json_dir, filename))
        except OSError:
            pass

    unique: list[str] = []
    seen: set[str] = set()
    for path in json_files:
        key = norm_key(path)
        if key in seen:
            continue
        seen.add(key)
        unique.append(path)
    return map_path, unique


def load_json_file(path: str) -> tuple[Any, int]:
    with open(path, "r", encoding="utf-8-sig") as handle:
        text = handle.read()
    indent = detect_indent(text)
    data = json.loads(text) if text.strip() else {}
    return data, indent


def harvest_json_paths(data: Any, json_path: str, unit: FolderUnit) -> None:
    if os.path.basename(json_path).lower() == MAP_FILENAME and isinstance(data, dict):
        for dest, source in data.items():
            if isinstance(dest, str) and is_abs_path_string(dest):
                unit.map_dest_paths.append(dest)
            if isinstance(source, str) and is_abs_path_string(source):
                unit.map_source_paths.append(source)
        return

    if not isinstance(data, dict):
        return
    for key, value in data.items():
        if isinstance(key, str) and is_abs_path_string(key):
            unit.json_key_paths.append(key)
        if isinstance(value, dict):
            export_dir = value.get("last_export_dir")
            if isinstance(export_dir, str) and export_dir.strip():
                unit.last_export_dirs.append(export_dir)


def inspect_folder(folder: str) -> FolderUnit:
    unit = FolderUnit(path=norm_path(folder))
    images = collect_images(unit.path)
    for image in images:
        unit.image_stems.add(relative_stem(image, unit.path))
        unit.image_basenames.add(stem_name(image))

    map_path, json_files = collect_json_files(unit.path)
    unit.map_path = map_path
    unit.json_files = json_files

    for json_path in json_files:
        try:
            data, _indent = load_json_file(json_path)
        except (OSError, json.JSONDecodeError):
            continue
        harvest_json_paths(data, json_path, unit)

    for source in unit.map_source_paths:
        unit.image_basenames.add(stem_name(source))
    for dest in unit.map_dest_paths:
        unit.image_basenames.add(stem_name(dest))
    for key in unit.json_key_paths:
        unit.image_basenames.add(stem_name(key))
    return unit


def is_job_folder(folder: str, filenames: list[str]) -> bool:
    base = os.path.basename(folder).lower()
    if base == WORK_DIR_NAME or base in WORK_SUBDIRS:
        return False
    if MAP_FILENAME in filenames:
        return True
    if any(is_translations_json(name) for name in filenames):
        return True
    if any(is_image_file(name) for name in filenames):
        return True
    work_json = os.path.join(folder, WORK_DIR_NAME, "json")
    if os.path.isdir(work_json):
        try:
            return any(is_translations_json(name) for name in os.listdir(work_json))
        except OSError:
            return False
    return False


def discover_units(roots: list[str]) -> list[FolderUnit]:
    jobs: list[str] = []
    seen: set[str] = set()
    walked = 0

    for root in unique_existing_dirs(roots):
        root_n = norm_path(root)
        for dirpath, dirnames, filenames in os.walk(root_n):
            walked += 1
            if walked > MAX_WALK_DIRS:
                break
            dirnames[:] = [name for name in dirnames if not should_skip_dir(name)]
            if is_job_folder(dirpath, filenames):
                key = norm_key(dirpath)
                if key not in seen:
                    seen.add(key)
                    jobs.append(norm_path(dirpath))
        if walked > MAX_WALK_DIRS:
            break

    if not jobs:
        for root in unique_existing_dirs(roots):
            jobs.append(norm_path(root))

    return [inspect_folder(path) for path in jobs]


def jaccard(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    inter = len(left & right)
    union = len(left | right)
    return inter / union if union else 0.0


def name_bonus(left_name: str, right_name: str) -> float:
    a = left_name.lower()
    b = right_name.lower()
    if not a or not b:
        return 0.0
    if a == b:
        return 0.12
    if a in b or b in a:
        return 0.06
    return 0.0


def score_pair(source: FolderUnit, dest: FolderUnit) -> float:
    dest_names = set(dest.image_basenames)
    source_names = set(source.image_basenames)
    if dest.map_source_paths:
        dest_names |= {stem_name(path) for path in dest.map_source_paths}
    if source.json_key_paths:
        source_names |= {stem_name(path) for path in source.json_key_paths}

    basename_score = jaccard(source_names, dest_names)
    stem_score = jaccard(source.image_stems, dest.image_stems)
    score = max(basename_score, stem_score * 1.05)
    score += name_bonus(source.name, dest.name)

    if dest.map_source_paths and source.image_basenames:
        mapped = {stem_name(path) for path in dest.map_source_paths}
        overlap = len(mapped & source.image_basenames)
        if mapped and overlap == len(mapped):
            score += 0.18
        elif overlap:
            score += 0.08 * (overlap / max(len(mapped), 1))
    return min(score, 1.0)


def pair_units(
    sources: list[FolderUnit], dests: list[FolderUnit]
) -> tuple[list[tuple[FolderUnit, FolderUnit, float]], list[FolderUnit], list[FolderUnit]]:
    if len(sources) == 1 and len(dests) == 1:
        return [(sources[0], dests[0], max(score_pair(sources[0], dests[0]), 0.99))], [], []

    used_sources: set[str] = set()
    pairs: list[tuple[FolderUnit, FolderUnit, float]] = []
    leftover_dests: list[FolderUnit] = []

    ranked_dests = sorted(
        dests, key=lambda unit: (-len(unit.image_basenames), -len(unit.json_files), unit.name.lower())
    )
    for dest in ranked_dests:
        best: Optional[tuple[FolderUnit, float]] = None
        for source in sources:
            if norm_key(source.path) in used_sources:
                continue
            current = score_pair(source, dest)
            if best is None or current > best[1]:
                best = (source, current)
        threshold = 0.28
        if best and len(sources) == len(dests) and best[1] >= 0.18:
            threshold = 0.18
        if best and best[1] >= threshold:
            pairs.append((best[0], dest, best[1]))
            used_sources.add(norm_key(best[0].path))
        else:
            leftover_dests.append(dest)

    leftover_sources = [unit for unit in sources if norm_key(unit.path) not in used_sources]
    pairs.sort(key=lambda item: (-item[2], item[0].name.lower()))
    return pairs, leftover_sources, leftover_dests


@dataclass
class FileChange:
    path: str
    changes: int
    code: str = ""
    error: str = ""


@dataclass
class PairPlan:
    source: FolderUnit
    dest: FolderUnit
    score: float
    old_source_root: Optional[str]
    old_dest_root: Optional[str]
    file_changes: list[FileChange] = field(default_factory=list)

    @property
    def total_changes(self) -> int:
        return sum(item.changes for item in self.file_changes)


@dataclass
class SyncPlan:
    pairs: list[PairPlan] = field(default_factory=list)
    unmatched_sources: list[FolderUnit] = field(default_factory=list)
    unmatched_dests: list[FolderUnit] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def infer_old_roots(source: FolderUnit, dest: FolderUnit) -> tuple[Optional[str], Optional[str]]:
    source_files = [
        path
        for path in (dest.map_source_paths + source.json_key_paths + source.map_source_paths)
        if is_abs_path_string(path)
    ]
    dest_files = [path for path in dest.map_dest_paths if is_abs_path_string(path)]

    old_source = common_parent_dir(os.path.dirname(path) for path in source_files)
    if dest_files:
        old_dest = common_parent_dir(os.path.dirname(path) for path in dest_files)
    else:
        old_dest = common_parent_dir(source.last_export_dirs + dest.last_export_dirs)
    return old_source, old_dest


def rewrite_string(
    value: str, old_source: Optional[str], new_source: str, old_dest: Optional[str], new_dest: str
) -> str:
    if not is_abs_path_string(value):
        return value
    if old_dest:
        remapped = remap_path(value, old_dest, new_dest)
        if remapped:
            return remapped
    if old_source:
        remapped = remap_path(value, old_source, new_source)
        if remapped:
            return remapped
    return value


def rewrite_obj(
    obj: Any,
    old_source: Optional[str],
    new_source: str,
    old_dest: Optional[str],
    new_dest: str,
    counter: list[int],
) -> Any:
    if isinstance(obj, dict):
        rewritten: dict[str, Any] = {}
        for key, value in obj.items():
            new_key = key
            if isinstance(key, str):
                mapped_key = rewrite_string(key, old_source, new_source, old_dest, new_dest)
                if mapped_key != key:
                    new_key = mapped_key
                    counter[0] += 1
            if isinstance(key, str) and key == "last_export_dir" and isinstance(value, str):
                mapped_export = os.path.normpath(os.path.abspath(new_dest))
                if os.path.normcase(value) != os.path.normcase(mapped_export):
                    rewritten[new_key] = mapped_export
                    counter[0] += 1
                else:
                    rewritten[new_key] = value
                continue
            rewritten[new_key] = rewrite_obj(value, old_source, new_source, old_dest, new_dest, counter)
        return rewritten
    if isinstance(obj, list):
        return [rewrite_obj(item, old_source, new_source, old_dest, new_dest, counter) for item in obj]
    if isinstance(obj, str):
        mapped = rewrite_string(obj, old_source, new_source, old_dest, new_dest)
        if mapped != obj:
            counter[0] += 1
        return mapped
    return obj


def plan_json_rewrite(
    json_path: str,
    old_source: Optional[str],
    new_source: str,
    old_dest: Optional[str],
    new_dest: str,
) -> Optional[FileChange]:
    try:
        data, _indent = load_json_file(json_path)
    except (OSError, json.JSONDecodeError) as exc:
        return FileChange(json_path, 0, code="read_failed", error=str(exc))

    counter = [0]
    rewrite_obj(data, old_source, new_source, old_dest, new_dest, counter)
    if counter[0] <= 0:
        return None
    return FileChange(json_path, counter[0], code="paths")


def write_rewritten_json(
    json_path: str,
    old_source: Optional[str],
    new_source: str,
    old_dest: Optional[str],
    new_dest: str,
) -> FileChange:
    try:
        with open(json_path, "r", encoding="utf-8-sig") as handle:
            text = handle.read()
        indent = detect_indent(text)
        data = json.loads(text) if text.strip() else {}
    except (OSError, json.JSONDecodeError) as exc:
        return FileChange(json_path, 0, code="read_failed", error=str(exc))

    counter = [0]
    rewritten = rewrite_obj(data, old_source, new_source, old_dest, new_dest, counter)
    if counter[0] <= 0:
        return FileChange(json_path, 0, code="no_change")

    tmp_path = json_path + ".tmp"
    try:
        with open(tmp_path, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(rewritten, handle, ensure_ascii=False, indent=indent)
            handle.write("\n")
        os.replace(tmp_path, json_path)
    except OSError as exc:
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except OSError:
            pass
        return FileChange(json_path, 0, code="write_failed", error=str(exc))
    return FileChange(json_path, counter[0], code="paths_rewritten")


def _unique_json_targets(source: FolderUnit, dest: FolderUnit) -> list[str]:
    json_targets: list[str] = []
    seen: set[str] = set()
    for path in source.json_files + dest.json_files:
        key = norm_key(path)
        if key in seen:
            continue
        seen.add(key)
        json_targets.append(path)
    return json_targets


def build_sync_plan(source_roots: list[str], dest_roots: list[str]) -> SyncPlan:
    plan = SyncPlan()
    sources = discover_units(source_roots)
    dests = discover_units(dest_roots)
    if not sources:
        plan.warnings.append("Could not find folders on the original side.")
    if not dests:
        plan.warnings.append("Could not find folders on the translated side.")

    pairs, leftover_sources, leftover_dests = pair_units(sources, dests)
    plan.unmatched_sources = leftover_sources
    plan.unmatched_dests = leftover_dests

    for source, dest, score in pairs:
        old_source, old_dest = infer_old_roots(source, dest)
        pair = PairPlan(
            source=source,
            dest=dest,
            score=score,
            old_source_root=old_source,
            old_dest_root=old_dest,
        )
        json_targets = _unique_json_targets(source, dest)
        if not json_targets:
            pair.file_changes.append(FileChange(dest.path, 0, code="no_json"))
        else:
            for json_path in json_targets:
                change = plan_json_rewrite(json_path, old_source, source.path, old_dest, dest.path)
                if change:
                    pair.file_changes.append(change)
        plan.pairs.append(pair)
    return plan


def apply_sync_plan(plan: SyncPlan) -> list[FileChange]:
    results: list[FileChange] = []
    for pair in plan.pairs:
        for json_path in _unique_json_targets(pair.source, pair.dest):
            results.append(
                write_rewritten_json(
                    json_path,
                    pair.old_source_root,
                    pair.source.path,
                    pair.old_dest_root,
                    pair.dest.path,
                )
            )
    return results
