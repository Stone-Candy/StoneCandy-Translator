"""
资源路径辅助函数
用于处理开发环境和 PyInstaller 打包环境的资源路径
"""
import logging
import os
import sys
from typing import Iterable


def _resource_base_candidates() -> list[str]:
    """Return candidate base directories for bundled and dev environments."""
    base_candidates: list[str] = []

    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            base_candidates.append(meipass)

        exe_dir = os.path.dirname(sys.executable)
        base_candidates.append(os.path.join(exe_dir, "_internal"))
        base_candidates.append(exe_dir)
    else:
        base_candidates.append(
            os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        )

    seen: set[str] = set()
    unique_candidates: list[str] = []
    for candidate in base_candidates:
        normalized = os.path.abspath(candidate)
        if normalized not in seen:
            seen.add(normalized)
            unique_candidates.append(normalized)
    return unique_candidates


def resource_path(relative_path):
    """
    Get absolute path to resource, works for dev and for PyInstaller.

    Args:
        relative_path: 相对于项目根目录的路径

    Returns:
        绝对路径
    """
    return os.path.join(_resource_base_candidates()[0], relative_path)


def iter_existing_resource_paths(relative_paths: Iterable[str]):
    """Yield existing resource files from all known resource bases."""
    seen: set[str] = set()
    for base_path in _resource_base_candidates():
        for relative_path in relative_paths:
            abs_path = os.path.abspath(os.path.join(base_path, relative_path))
            if abs_path in seen:
                continue
            seen.add(abs_path)
            if os.path.exists(abs_path):
                yield abs_path


def load_icon_from_resources(relative_paths: Iterable[str]):
    """
    Load an icon eagerly from resource files to avoid lazy path-based failures.

    Returns:
        (QIcon, source_path) or (None, None) if all candidates fail.
    """
    from PyQt6.QtGui import QIcon

    icon = QIcon()
    loaded_from = None
    target_sizes = (16, 24, 32, 48, 64, 128, 256)

    for abs_path in iter_existing_resource_paths(relative_paths):
        candidate = QIcon(abs_path)
        if candidate.isNull():
            continue

        loaded_any = False
        for size in target_sizes:
            pixmap = candidate.pixmap(size, size)
            if pixmap.isNull():
                continue
            icon.addPixmap(pixmap)
            loaded_any = True

        if not loaded_any:
            continue

        loaded_from = abs_path

    if icon.isNull():
        return None, None
    return icon, loaded_from


def apply_windows_native_window_icon(window, icon_path: str):
    """为 Windows 原生窗口句柄设置大小图标，覆盖 python.exe 默认图标。"""
    try:
        import ctypes
        from ctypes import wintypes

        hwnd = wintypes.HWND(int(window.winId()))
        user32 = ctypes.windll.user32
        user32.GetSystemMetrics.argtypes = [ctypes.c_int]
        user32.GetSystemMetrics.restype = ctypes.c_int
        user32.LoadImageW.argtypes = [
            wintypes.HINSTANCE,
            wintypes.LPCWSTR,
            wintypes.UINT,
            ctypes.c_int,
            ctypes.c_int,
            wintypes.UINT,
        ]
        user32.LoadImageW.restype = wintypes.HANDLE
        user32.SendMessageW.argtypes = [
            wintypes.HWND,
            wintypes.UINT,
            wintypes.WPARAM,
            wintypes.LPARAM,
        ]
        user32.SendMessageW.restype = ctypes.c_ssize_t

        image_icon = 1
        wm_seticon = 0x0080
        icon_small = 0
        icon_big = 1
        lr_loadfromfile = 0x0010

        sm_cxicon = 11
        sm_cyicon = 12
        sm_cxsmicon = 49
        sm_cysmicon = 50

        big_icon_handle = user32.LoadImageW(
            None,
            icon_path,
            image_icon,
            user32.GetSystemMetrics(sm_cxicon),
            user32.GetSystemMetrics(sm_cyicon),
            lr_loadfromfile,
        )
        small_icon_handle = user32.LoadImageW(
            None,
            icon_path,
            image_icon,
            user32.GetSystemMetrics(sm_cxsmicon),
            user32.GetSystemMetrics(sm_cysmicon),
            lr_loadfromfile,
        )

        if big_icon_handle:
            user32.SendMessageW(hwnd, wm_seticon, icon_big, big_icon_handle)
        if small_icon_handle:
            user32.SendMessageW(hwnd, wm_seticon, icon_small, small_icon_handle)

        if big_icon_handle or small_icon_handle:
            window._native_icon_handles = (big_icon_handle, small_icon_handle)
            logging.info(f"Windows native window icon set: {icon_path}")
            return True

        logging.warning(f"Failed to load Windows native window icon: {icon_path}")
    except Exception:
        logging.exception("Failed to set Windows native window icon")
    return False


def apply_app_icon_to_window(window) -> None:
    """Apply the app icon to a Qt window, including the Windows title-bar icon."""
    if window is None or getattr(window, "_app_icon_applied", False):
        return

    from PyQt6.QtWidgets import QApplication

    app = QApplication.instance()
    if app is not None:
        icon = app.windowIcon()
        if icon is not None and not icon.isNull():
            window.setWindowIcon(icon)

    if sys.platform == "win32":
        icon_path = next(
            iter_existing_resource_paths([os.path.join("doc", "images", "icon.ico")]),
            None,
        )
        if icon_path:
            apply_windows_native_window_icon(window, icon_path)

    window._app_icon_applied = True
