"""Load and show a JSON-editable startup notice with clickable links."""

from __future__ import annotations

import html
import json
import logging
import os
import sys

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication, QMessageBox

from ui.secondary_pages.themed_message_box import show_error_dialog
from utils.app_version import check_app_update

_NOTICE_FILENAME = "startup_notice.json"
_MSG_LATEST = "현재 최신 버전을 사용하고 있습니다."
_MSG_UPDATE = "새로운 버전을 다운로드할 수 있습니다."
_I18N_LATEST = "You are using the latest version."
_I18N_UPDATE = "A new version is available to download."


def _examples_dir() -> str:
    if getattr(sys, "frozen", False):
        if hasattr(sys, "_MEIPASS"):
            return os.path.join(sys._MEIPASS, "examples")
        return os.path.join(os.path.dirname(sys.executable), "examples")
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    return os.path.join(project_root, "examples")


def startup_notice_path() -> str:
    return os.path.join(_examples_dir(), _NOTICE_FILENAME)


def _load_notice() -> dict | None:
    path = startup_notice_path()
    if not os.path.isfile(path):
        logging.info("Startup notice JSON not found: %s", path)
        return None
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except Exception:
        logging.exception("Failed to read startup notice JSON: %s", path)
        return None
    if not isinstance(data, dict):
        logging.warning("Startup notice JSON must be an object: %s", path)
        return None
    return data


def _notice_html(data: dict) -> str:
    message = str(data.get("message") or "")
    link_text = str(data.get("link_text") or "").strip()
    link_url = str(data.get("link_url") or "").strip()
    if link_text and link_url:
        if message and not message.endswith("\n"):
            message += "\n"
        if message and not message.endswith("\n\n"):
            message += "\n"
        message += f'<a href="{link_url}">{link_text}</a>'
    return message.replace("\r\n", "\n").replace("\r", "\n").replace("\n", "<br>")


def _positive_int(value, minimum: int, maximum: int) -> int | None:
    if value is None or value == "":
        return None
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    if number <= 0:
        return None
    return max(minimum, min(number, maximum))


def _translate(key: str, fallback: str) -> str:
    try:
        from services import get_i18n_manager

        manager = get_i18n_manager()
        if manager is not None:
            translated = manager.translate(key)
            if translated:
                return translated
    except Exception:
        logging.debug("i18n unavailable for startup notice version status", exc_info=True)
    return fallback


def _version_status_html() -> str:
    app = QApplication.instance()
    if app is not None:
        app.setOverrideCursor(Qt.CursorShape.WaitCursor)
    try:
        status = check_app_update()
    finally:
        if app is not None:
            app.restoreOverrideCursor()

    if status == "latest":
        message = _translate(_I18N_LATEST, _MSG_LATEST)
    elif status == "update_available":
        message = _translate(_I18N_UPDATE, _MSG_UPDATE)
    else:
        return ""
    return html.escape(message)


def show_startup_notice_if_enabled(parent=None, *, force: bool = False) -> None:
    data = _load_notice()
    if not data or (not force and not data.get("enabled", True)):
        return
    body_html = _notice_html(data)
    status_html = _version_status_html()
    if status_html and body_html.strip():
        notice_html = f"{status_html}<br><br>{body_html}"
    else:
        notice_html = status_html or body_html
    if not notice_html.strip():
        return
    title = str(data.get("title") or "알림").strip() or "알림"
    show_error_dialog(
        parent,
        title,
        "",
        notice_html,
        icon=QMessageBox.Icon.Information,
        rich_text=True,
        dialog_width=_positive_int(data.get("width", data.get("가로")), 240, 1600),
        dialog_height=_positive_int(data.get("height", data.get("세로")), 140, 1200),
    )
