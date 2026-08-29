"""
应用版本号辅助函数。
统一处理开发环境和 PyInstaller 打包环境下的版本读取与显示格式。
"""
from __future__ import annotations

import logging
import urllib.error
import urllib.request

from utils.resource_helper import iter_existing_resource_paths

GITHUB_VERSION_URLS = (
    "https://raw.githubusercontent.com/Stone-Candy/StoneCandy-Translator/main/packaging/VERSION",
    "https://raw.githubusercontent.com/Stone-Candy/StoneCandy-Translator/master/packaging/VERSION",
)
_REMOTE_FETCH_TIMEOUT_SEC = 4.0
_REMOTE_USER_AGENT = "StoneCandy-Translator-VersionCheck"

_remote_version_cache: str | None = None
_remote_version_checked = False


def get_app_version(default: str = "unknown") -> str:
    """从运行时资源中读取版本号。"""
    for version_path in iter_existing_resource_paths(("VERSION", "packaging/VERSION")):
        try:
            with open(version_path, "r", encoding="utf-8") as version_file:
                version = version_file.read().strip()
        except OSError:
            continue
        if version:
            return _normalize_version(version)
    return default


def format_app_title(base_title: str, version: str | None) -> str:
    """生成带版本号的窗口标题。"""
    normalized_version = (version or "").strip()
    if not normalized_version or normalized_version == "unknown":
        return base_title
    return f"{base_title} v{normalized_version}"


def format_version_label(version: str | None) -> str:
    """生成侧边栏显示用的版本标签。"""
    normalized_version = (version or "").strip()
    if not normalized_version or normalized_version == "unknown":
        return ""
    return f"v{normalized_version}"


def fetch_remote_app_version(*, force: bool = False, timeout: float = _REMOTE_FETCH_TIMEOUT_SEC) -> str | None:
    """GitHub에 올라간 packaging/VERSION 내용을 가져온다."""
    global _remote_version_cache, _remote_version_checked
    if _remote_version_checked and not force:
        return _remote_version_cache

    remote_version = None
    last_error: Exception | None = None
    for url in GITHUB_VERSION_URLS:
        try:
            request = urllib.request.Request(
                url,
                headers={"User-Agent": _REMOTE_USER_AGENT},
            )
            with urllib.request.urlopen(request, timeout=timeout) as response:
                raw = response.read().decode("utf-8", errors="replace").strip()
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError, ValueError) as exc:
            last_error = exc
            continue
        normalized = _normalize_version(raw)
        if normalized:
            remote_version = normalized
            break

    if remote_version is None and last_error is not None:
        logging.info("Failed to fetch remote app version: %s", last_error)

    _remote_version_cache = remote_version
    _remote_version_checked = True
    return remote_version


def check_app_update() -> str:
    """로컬 버전과 GitHub 버전을 비교한다.

    Returns:
        "latest", "update_available", or "unknown"
    """
    local_version = get_app_version()
    if not local_version or local_version == "unknown":
        return "unknown"

    remote_version = fetch_remote_app_version()
    if not remote_version:
        return "unknown"

    comparison = compare_versions(local_version, remote_version)
    if comparison is None:
        if local_version == remote_version:
            return "latest"
        return "update_available"
    if comparison < 0:
        return "update_available"
    return "latest"


def compare_versions(left: str, right: str) -> int | None:
    """left < right 이면 -1, 같으면 0, left > right 이면 1. 파싱 실패 시 None."""
    left_parts = _version_tuple(left)
    right_parts = _version_tuple(right)
    if left_parts is None or right_parts is None:
        return None
    length = max(len(left_parts), len(right_parts))
    left_padded = left_parts + (0,) * (length - len(left_parts))
    right_padded = right_parts + (0,) * (length - len(right_parts))
    if left_padded < right_padded:
        return -1
    if left_padded > right_padded:
        return 1
    return 0


def _normalize_version(version: str) -> str:
    return str(version or "").strip().lstrip("vV")


def _version_tuple(version: str) -> tuple[int, ...] | None:
    cleaned = _normalize_version(version)
    if not cleaned:
        return None
    parts: list[int] = []
    for token in cleaned.replace("-", ".").replace("_", ".").split("."):
        digits = []
        for char in token:
            if char.isdigit():
                digits.append(char)
            else:
                break
        if not digits:
            break
        parts.append(int("".join(digits)))
    return tuple(parts) if parts else None
