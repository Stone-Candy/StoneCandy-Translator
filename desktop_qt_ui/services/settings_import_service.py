"""Copy user settings from another translator install into the current one.

Release builds keep writable data under ``_internal`` (and ``.env`` next to the
exe). Developer trees keep the same files at the project root. Both layouts are
accepted as a source so a release folder can feed a dev tree and vice versa.
"""
from __future__ import annotations

import os
import shutil
from dataclasses import dataclass, field
from typing import Callable, Iterable, Optional

SKIP_DIR_NAMES = {"__pycache__", ".git", ".svn", ".hg"}
SKIP_FILE_NAMES = {".ds_store", "thumbs.db"}

ProgressCallback = Callable[[int, int, str], None]
CancelCallback = Callable[[], bool]


@dataclass(frozen=True)
class ImportItem:
    id: str
    label_key: str
    hint_key: str
    kind: str  # "files" | "directory"
    rel_paths: tuple[tuple[str, ...], ...]
    location: str  # "resource" | "install"
    large: bool = False


@dataclass
class TranslatorLayout:
    selected_path: str
    install_root: str
    resource_root: str
    env_path: str
    user_config_path: str
    packaged: bool


@dataclass
class ItemAvailability:
    item: ImportItem
    sources: list[str] = field(default_factory=list)

    @property
    def available(self) -> bool:
        return bool(self.sources)


@dataclass(frozen=True)
class CopyJob:
    item_id: str
    src: str
    dst: str


@dataclass
class CopyResult:
    copied: int = 0
    skipped_same: int = 0
    errors: list[str] = field(default_factory=list)
    cancelled: bool = False
    copied_item_ids: list[str] = field(default_factory=list)


IMPORT_ITEMS: tuple[ImportItem, ...] = (
    ImportItem(
        id="config",
        label_key="import_item_config",
        hint_key="import_item_config_hint",
        kind="files",
        rel_paths=(("examples", "config.json"),),
        location="resource",
    ),
    ImportItem(
        id="env",
        label_key="import_item_env",
        hint_key="import_item_env_hint",
        kind="files",
        rel_paths=((".env",),),
        location="install",
    ),
    ImportItem(
        id="presets",
        label_key="import_item_presets",
        hint_key="import_item_presets_hint",
        kind="directory",
        rel_paths=(("presets",),),
        location="resource",
    ),
    ImportItem(
        id="custom_api",
        label_key="import_item_custom_api",
        hint_key="import_item_custom_api_hint",
        kind="files",
        rel_paths=(("examples", "custom_api_params.json"),),
        location="resource",
    ),
    ImportItem(
        id="dict",
        label_key="import_item_dict",
        hint_key="import_item_dict_hint",
        kind="directory",
        rel_paths=(("dict",),),
        location="resource",
    ),
    ImportItem(
        id="text_rules",
        label_key="import_item_text_rules",
        hint_key="import_item_text_rules_hint",
        kind="files",
        rel_paths=(
            ("examples", "text_replacements.yaml"),
            ("examples", "filter_list.json"),
            ("examples", "translation_template.json"),
            ("examples", "txt_help_template.txt"),
        ),
        location="resource",
    ),
    ImportItem(
        id="batch_edit",
        label_key="import_item_batch_edit",
        hint_key="import_item_batch_edit_hint",
        kind="files",
        rel_paths=(("examples", "batch_edit_schemes.yaml"),),
        location="resource",
    ),
    ImportItem(
        id="fonts",
        label_key="import_item_fonts",
        hint_key="import_item_fonts_hint",
        kind="directory",
        rel_paths=(("fonts",),),
        location="resource",
    ),
    ImportItem(
        id="models",
        label_key="import_item_models",
        hint_key="import_item_models_hint",
        kind="directory",
        rel_paths=(("models",),),
        location="resource",
        large=True,
    ),
)


def _norm(path: str) -> str:
    return os.path.normcase(os.path.abspath(os.path.normpath(path)))


def _has_dir(root: str, name: str) -> bool:
    return os.path.isdir(os.path.join(root, name))


def _has_file(root: str, *parts: str) -> bool:
    return os.path.isfile(os.path.join(root, *parts))


def _has_examples_config(root: str) -> bool:
    return _has_file(root, "examples", "config.json") or _has_file(
        root, "examples", "config-example.json"
    )


def _has_translator_exe(root: str) -> bool:
    try:
        for name in os.listdir(root):
            lower = name.lower()
            if lower.endswith(".exe") and (
                "translator" in lower or "stonecandy" in lower
            ):
                return True
    except OSError:
        return False
    return False


def _looks_like_resource_root(root: str) -> bool:
    has_ui = _has_dir(root, "desktop_qt_ui")
    has_config = _has_examples_config(root)
    has_engine = _has_dir(root, "manga_translator")
    has_payload = _has_dir(root, "dict") and _has_dir(root, "examples")
    return has_config and (has_ui or has_engine or has_payload)


def _is_our_translator(install_root: str, resource_root: str) -> bool:
    has_ui = _has_dir(resource_root, "desktop_qt_ui") or _has_dir(
        install_root, "desktop_qt_ui"
    )
    has_config = _has_examples_config(resource_root) or _has_examples_config(
        install_root
    )
    has_exe = _has_translator_exe(install_root)
    if has_config and (has_ui or has_exe):
        return True
    return False


def _env_path_for(install_root: str, resource_root: str) -> str:
    for root in (install_root, resource_root):
        candidate = os.path.join(root, ".env")
        if os.path.isfile(candidate):
            return candidate
    return os.path.join(install_root, ".env")


def _user_config_path_for(resource_root: str, install_root: str) -> str:
    for root in (resource_root, install_root):
        candidate = os.path.join(root, "examples", "config.json")
        if os.path.isfile(candidate):
            return candidate
    return os.path.join(resource_root, "examples", "config.json")


def inspect_translator_folder(path: str) -> Optional[TranslatorLayout]:
    """Return a layout if ``path`` is a release or developer translator folder."""
    if not path or not os.path.isdir(path):
        return None

    selected = os.path.abspath(path)
    basename = os.path.basename(selected)

    if basename.lower() == "_internal":
        install_root = os.path.dirname(selected)
        resource_root = selected
        packaged = True
    elif _looks_like_resource_root(os.path.join(selected, "_internal")):
        install_root = selected
        resource_root = os.path.join(selected, "_internal")
        packaged = True
    elif _looks_like_resource_root(selected):
        install_root = selected
        resource_root = selected
        packaged = os.path.isdir(os.path.join(selected, "_internal"))
    else:
        return None

    if not _is_our_translator(install_root, resource_root):
        return None

    return TranslatorLayout(
        selected_path=selected,
        install_root=install_root,
        resource_root=resource_root,
        env_path=_env_path_for(install_root, resource_root),
        user_config_path=_user_config_path_for(resource_root, install_root),
        packaged=packaged,
    )


def current_dest_layout(config_service) -> TranslatorLayout:
    install_root = os.path.dirname(os.path.abspath(config_service.env_path))
    resource_root = os.path.abspath(config_service.root_dir)
    return TranslatorLayout(
        selected_path=install_root,
        install_root=install_root,
        resource_root=resource_root,
        env_path=os.path.abspath(config_service.env_path),
        user_config_path=os.path.abspath(config_service.user_config_path),
        packaged=_norm(install_root) != _norm(resource_root),
    )


def is_same_install(source: TranslatorLayout, dest: TranslatorLayout) -> bool:
    return (
        _norm(source.install_root) == _norm(dest.install_root)
        or _norm(source.resource_root) == _norm(dest.resource_root)
    )


def _candidate_roots(layout: TranslatorLayout, location: str) -> list[str]:
    if location == "install":
        roots = [layout.install_root, layout.resource_root]
    else:
        roots = [layout.resource_root, layout.install_root]
    seen: set[str] = set()
    unique: list[str] = []
    for root in roots:
        key = _norm(root)
        if key in seen:
            continue
        seen.add(key)
        unique.append(root)
    return unique


def _path_exists_and_usable(path: str) -> bool:
    if os.path.isfile(path):
        return True
    if os.path.isdir(path):
        try:
            with os.scandir(path) as entries:
                for entry in entries:
                    name = entry.name.lower()
                    if name in SKIP_DIR_NAMES or name in SKIP_FILE_NAMES:
                        continue
                    return True
        except OSError:
            return False
    return False


def resolve_source_path(layout: TranslatorLayout, item: ImportItem, rel: tuple[str, ...]) -> Optional[str]:
    for root in _candidate_roots(layout, item.location):
        candidate = os.path.join(root, *rel)
        if _path_exists_and_usable(candidate):
            return candidate
    return None


def inspect_item_availability(layout: TranslatorLayout) -> list[ItemAvailability]:
    result: list[ItemAvailability] = []
    for item in IMPORT_ITEMS:
        sources: list[str] = []
        seen: set[str] = set()
        for rel in item.rel_paths:
            path = resolve_source_path(layout, item, rel)
            if not path:
                continue
            key = _norm(path)
            if key in seen:
                continue
            seen.add(key)
            sources.append(path)
        result.append(ItemAvailability(item=item, sources=sources))
    return result


def _dest_for_rel(dest: TranslatorLayout, item: ImportItem, rel: tuple[str, ...]) -> str:
    if item.id == "env" and rel == (".env",):
        return dest.env_path
    if item.id == "config" and rel == ("examples", "config.json"):
        return dest.user_config_path
    if item.location == "install":
        return os.path.join(dest.install_root, *rel)
    return os.path.join(dest.resource_root, *rel)


def _should_skip_file(name: str) -> bool:
    lower = name.lower()
    return lower in SKIP_FILE_NAMES or lower.endswith(".pyc")


def _iter_directory_files(src_dir: str) -> Iterable[str]:
    for root, dirs, files in os.walk(src_dir):
        dirs[:] = [name for name in dirs if name.lower() not in SKIP_DIR_NAMES]
        for filename in files:
            if _should_skip_file(filename):
                continue
            yield os.path.join(root, filename)


def collect_copy_jobs(
    source: TranslatorLayout,
    dest: TranslatorLayout,
    item_ids: Iterable[str],
) -> list[CopyJob]:
    selected = set(item_ids)
    jobs: list[CopyJob] = []
    for item in IMPORT_ITEMS:
        if item.id not in selected:
            continue
        for rel in item.rel_paths:
            src = resolve_source_path(source, item, rel)
            if not src:
                continue
            dst = _dest_for_rel(dest, item, rel)
            if os.path.isdir(src):
                for src_file in _iter_directory_files(src):
                    rel_file = os.path.relpath(src_file, src)
                    jobs.append(
                        CopyJob(
                            item_id=item.id,
                            src=src_file,
                            dst=os.path.join(dst, rel_file),
                        )
                    )
            else:
                jobs.append(CopyJob(item_id=item.id, src=src, dst=dst))
    return jobs


def execute_copy_jobs(
    jobs: list[CopyJob],
    *,
    progress: Optional[ProgressCallback] = None,
    should_cancel: Optional[CancelCallback] = None,
) -> CopyResult:
    result = CopyResult()
    total = len(jobs)
    copied_ids: set[str] = set()

    for index, job in enumerate(jobs, start=1):
        if should_cancel and should_cancel():
            result.cancelled = True
            break
        if progress:
            progress(index - 1, total, os.path.basename(job.src))
        try:
            if os.path.exists(job.dst) and os.path.samefile(job.src, job.dst):
                result.skipped_same += 1
                continue
        except OSError:
            pass
        try:
            os.makedirs(os.path.dirname(job.dst), exist_ok=True)
            shutil.copy2(job.src, job.dst)
            result.copied += 1
            copied_ids.add(job.item_id)
        except OSError as exc:
            result.errors.append(f"{job.src} -> {job.dst}: {exc}")

    if progress:
        progress(total if not result.cancelled else result.copied, total, "")
    result.copied_item_ids = sorted(copied_ids)
    return result
