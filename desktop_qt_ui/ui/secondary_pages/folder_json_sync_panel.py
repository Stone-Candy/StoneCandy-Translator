"""Folder path rewrite panel: pair before/after folders and fix JSON absolute paths."""

from __future__ import annotations

import os
from typing import Callable, Iterable, Optional

from PyQt6.QtCore import QSize, Qt, QUrl
from PyQt6.QtGui import (
    QCursor,
    QDesktopServices,
    QDragEnterEvent,
    QDragLeaveEvent,
    QDropEvent,
    QFont,
    QPainter,
    QPalette,
    QPen,
)
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from services.folder_json_sync import (
    FileChange,
    SyncPlan,
    apply_sync_plan,
    build_sync_plan,
    unique_existing_dirs,
)
from ui.secondary_pages.themed_message_box import themed_critical, themed_information
from ui.theme import get_current_theme_colors

FOLDER_SYNC_LOG_INTRO_KEY = "folder_sync_log_intro"


def _escape_html(text: str) -> str:
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


class FolderList(QListWidget):
    def __init__(self, empty_title_key: str, empty_body_key: str, t_func: Callable, parent=None):
        super().__init__(parent)
        self.empty_title_key = empty_title_key
        self.empty_body_key = empty_body_key
        self._t = t_func
        self.setObjectName("folder_sync_list")
        self.setAcceptDrops(True)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setSpacing(2)
        self.setMinimumHeight(220)
        self.itemDoubleClicked.connect(self._open_folder)

    def paths(self) -> list[str]:
        result = []
        for index in range(self.count()):
            result.append(self.item(index).data(Qt.ItemDataRole.UserRole))
        return result

    def add_folders(self, folders: Iterable[str]) -> int:
        added = 0
        existing = {os.path.normcase(os.path.normpath(path)) for path in self.paths()}
        for folder in unique_existing_dirs(folders):
            key = os.path.normcase(os.path.normpath(folder))
            if key in existing:
                continue
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, folder)
            item.setSizeHint(QSize(0, 58))
            item.setToolTip(folder)
            self.addItem(item)
            widget = QWidget()
            layout = QVBoxLayout(widget)
            layout.setContentsMargins(10, 8, 10, 8)
            layout.setSpacing(2)
            title = QLabel(os.path.basename(folder.rstrip("\\/")) or folder)
            title.setObjectName("folder_sync_item_title")
            font = title.font()
            font.setBold(True)
            title.setFont(font)
            path_label = QLabel(folder)
            path_label.setObjectName("page_subtitle")
            path_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            layout.addWidget(title)
            layout.addWidget(path_label)
            self.setItemWidget(item, widget)
            existing.add(key)
            added += 1
        return added

    def remove_selected(self) -> None:
        for item in self.selectedItems():
            self.takeItem(self.row(item))

    def clear_all(self) -> None:
        self.clear()

    def refresh_item_widgets(self) -> None:
        for index in range(self.count()):
            item = self.item(index)
            folder = item.data(Qt.ItemDataRole.UserRole)
            widget = self.itemWidget(item)
            if widget is None or not folder:
                continue
            labels = widget.findChildren(QLabel)
            if len(labels) >= 2:
                labels[0].setText(os.path.basename(folder.rstrip("\\/")) or folder)
                labels[1].setText(folder)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self.setProperty("dragOver", True)
            self.style().unpolish(self)
            self.style().polish(self)
            return
        event.ignore()

    def dragMoveEvent(self, event) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragLeaveEvent(self, event: QDragLeaveEvent) -> None:
        self.setProperty("dragOver", False)
        self.style().unpolish(self)
        self.style().polish(self)
        super().dragLeaveEvent(event)

    def dropEvent(self, event: QDropEvent) -> None:
        self.setProperty("dragOver", False)
        self.style().unpolish(self)
        self.style().polish(self)
        folders = []
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if not path:
                continue
            if os.path.isdir(path):
                folders.append(path)
            elif os.path.isfile(path):
                folders.append(os.path.dirname(path))
        self.add_folders(folders)
        event.acceptProposedAction()

    def _open_folder(self, item: QListWidgetItem) -> None:
        path = item.data(Qt.ItemDataRole.UserRole)
        if path and os.path.isdir(path):
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    def keyPressEvent(self, event) -> None:
        if event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            self.remove_selected()
            return
        super().keyPressEvent(event)

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        if self.count() != 0:
            return
        painter = QPainter(self.viewport())
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.viewport().rect().adjusted(16, 16, -16, -16)
        placeholder = self.palette().color(QPalette.ColorRole.PlaceholderText)
        painter.setPen(QPen(placeholder, 1, Qt.PenStyle.DashLine))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(rect, 12, 12)
        title_font = QFont(self.font())
        title_font.setPointSize(11)
        title_font.setBold(True)
        painter.setFont(title_font)
        painter.setPen(self.palette().color(QPalette.ColorRole.WindowText))
        painter.drawText(rect.adjusted(0, -12, 0, 0), Qt.AlignmentFlag.AlignCenter, self._t(self.empty_title_key))
        body_font = QFont(self.font())
        body_font.setPointSize(10)
        painter.setFont(body_font)
        painter.setPen(placeholder)
        painter.drawText(
            rect.adjusted(16, 22, -16, 0),
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
            self._t(self.empty_body_key),
        )
        painter.end()


class FolderPanel(QWidget):
    def __init__(
        self,
        kicker: str,
        hint_key: str,
        empty_title_key: str,
        empty_body_key: str,
        t_func: Callable,
        margins: tuple[int, int, int, int] = (10, 0, 10, 0),
        parent=None,
    ):
        super().__init__(parent)
        self._t = t_func
        self._kicker_key = kicker
        self._hint_key = hint_key

        self.list = FolderList(empty_title_key, empty_body_key, t_func)

        root = QVBoxLayout(self)
        root.setContentsMargins(*margins)
        root.setSpacing(10)

        header = QHBoxLayout()
        titles = QVBoxLayout()
        titles.setSpacing(2)
        self.kicker_label = QLabel(self._t(kicker))
        self.kicker_label.setObjectName("folder_sync_kicker")
        self.hint_label = QLabel(self._t(hint_key))
        self.hint_label.setObjectName("page_subtitle")
        self.hint_label.setWordWrap(True)
        titles.addWidget(self.kicker_label)
        titles.addWidget(self.hint_label)
        header.addLayout(titles, 1)
        self.count_label = QLabel("0")
        self.count_label.setObjectName("row_label")
        self.count_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header.addWidget(self.count_label, 0, Qt.AlignmentFlag.AlignTop)
        root.addLayout(header)
        root.addWidget(self.list, 1)

        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        self.add_btn = QPushButton(self._t("Add Folder"))
        self.add_btn.setProperty("chipButton", True)
        self.add_btn.clicked.connect(self._browse)
        self.remove_btn = QPushButton(self._t("Remove Selected"))
        self.remove_btn.setProperty("chipButton", True)
        self.remove_btn.clicked.connect(self.list.remove_selected)
        self.clear_btn = QPushButton(self._t("Clear List"))
        self.clear_btn.setProperty("chipButton", True)
        self.clear_btn.clicked.connect(self.list.clear_all)
        buttons.addWidget(self.add_btn)
        buttons.addWidget(self.remove_btn)
        buttons.addWidget(self.clear_btn)
        buttons.addStretch(1)
        root.addLayout(buttons)

        self.list.model().rowsInserted.connect(self._refresh_count)
        self.list.model().rowsRemoved.connect(self._refresh_count)
        self.list.model().modelReset.connect(self._refresh_count)

    def refresh_ui_texts(self) -> None:
        self.kicker_label.setText(self._t(self._kicker_key))
        self.hint_label.setText(self._t(self._hint_key))
        self.add_btn.setText(self._t("Add Folder"))
        self.remove_btn.setText(self._t("Remove Selected"))
        self.clear_btn.setText(self._t("Clear List"))
        self.list.refresh_item_widgets()
        self.list.viewport().update()

    def _refresh_count(self, *args) -> None:
        self.count_label.setText(str(self.list.count()))

    def _browse(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, self._t("Select Folder"))
        if folder:
            self.list.add_folders([folder])

    def paths(self) -> list[str]:
        return self.list.paths()


class ConfirmDialog(QDialog):
    def __init__(self, plan: SyncPlan, t_func: Callable, parent=None):
        super().__init__(parent)
        self._t = t_func
        self.setWindowTitle(self._t("JSON rewrite preview"))
        self.setMinimumSize(760, 520)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 16)
        layout.setSpacing(12)

        title = QLabel(self._t("Rewrite JSON with these folder pairs?"))
        title.setObjectName("page_title")
        title.setWordWrap(True)
        layout.addWidget(title)

        changed_files = sum(1 for pair in plan.pairs for item in pair.file_changes if item.changes)
        changed_paths = sum(pair.total_changes for pair in plan.pairs)
        summary = QLabel(
            self._t(
                "{pairs} folder pairs  ·  {files} JSON files  ·  {paths} paths",
                pairs=len(plan.pairs),
                files=changed_files,
                paths=changed_paths,
            )
        )
        summary.setObjectName("page_subtitle")
        summary.setWordWrap(True)
        layout.addWidget(summary)

        body = QTextEdit()
        body.setReadOnly(True)
        body.setHtml(self._render(plan))
        layout.addWidget(body, 1)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Ok
        )
        ok_btn = buttons.button(QDialogButtonBox.StandardButton.Ok)
        cancel_btn = buttons.button(QDialogButtonBox.StandardButton.Cancel)
        ok_btn.setText(self._t("Rewrite JSON"))
        ok_btn.setProperty("primaryAction", True)
        cancel_btn.setText(self._t("Cancel"))
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        ok_btn.setEnabled(changed_paths > 0)

    def _format_change(self, change: FileChange) -> str:
        return format_file_change(change, self._t)

    def _render(self, plan: SyncPlan) -> str:
        colors = get_current_theme_colors()
        warning = colors.get("warning_color", "#F59E0B")
        success = colors.get("success_color", "#10B981")
        danger = colors.get("danger_bg", "#EF4444")
        muted = colors.get("text_muted", "#64748B")
        secondary = colors.get("text_secondary", "#94A3B8")
        chunks = ['<div style="line-height:1.55;">']
        if plan.warnings:
            for warning_key in plan.warnings:
                chunks.append(f'<p style="color:{warning};">{_escape_html(self._t(warning_key))}</p>')

        if not plan.pairs:
            chunks.append(
                f'<p style="color:{danger};">{_escape_html(self._t("No pairs found. Try dropping the folders again."))}</p>'
            )

        for pair in plan.pairs:
            score_color = success if pair.score >= 0.5 else warning
            chunks.append(
                f'<p style="margin:14px 0 4px 0;">'
                f'<span style="color:{score_color}; font-weight:700;">{pair.score * 100:.0f}%</span> '
                f'<b>{_escape_html(pair.source.name)}</b>'
                f' <span style="color:{secondary};">→</span> '
                f'<b>{_escape_html(pair.dest.name)}</b></p>'
            )
            chunks.append(
                f'<p style="color:{secondary}; margin:0 0 6px 18px;">'
                f'{_escape_html(self._t("Before Translation"))} {_escape_html(pair.source.path)}<br>'
                f'{_escape_html(self._t("After Translation"))} {_escape_html(pair.dest.path)}</p>'
            )
            if pair.old_source_root:
                chunks.append(
                    f'<p style="color:{muted}; margin:0 0 2px 18px;">'
                    f'{_escape_html(self._t("Old original path: {path}", path=pair.old_source_root))}</p>'
                )
            if pair.old_dest_root:
                chunks.append(
                    f'<p style="color:{muted}; margin:0 0 6px 18px;">'
                    f'{_escape_html(self._t("Old translated path: {path}", path=pair.old_dest_root))}</p>'
                )
            if not pair.file_changes:
                chunks.append(
                    f'<p style="color:{secondary}; margin:0 0 0 18px;">'
                    f'{_escape_html(self._t("Already matched, or no paths to rewrite."))}</p>'
                )
            for change in pair.file_changes:
                color = success if change.changes else secondary
                chunks.append(
                    f'<p style="color:{color}; margin:0 0 2px 18px;">· '
                    f'{_escape_html(os.path.basename(change.path))} — {_escape_html(self._format_change(change))}</p>'
                )

        if plan.unmatched_sources or plan.unmatched_dests:
            chunks.append(
                f'<p style="margin-top:18px; color:{warning}; font-weight:700;">'
                f'{_escape_html(self._t("Unmatched folders"))}</p>'
            )
            for unit in plan.unmatched_sources:
                chunks.append(
                    f'<p style="color:{danger}; margin:2px 0 2px 12px;">'
                    f'{_escape_html(self._t("Before Translation"))} · {_escape_html(unit.path)}</p>'
                )
            for unit in plan.unmatched_dests:
                chunks.append(
                    f'<p style="color:{warning}; margin:2px 0 2px 12px;">'
                    f'{_escape_html(self._t("After Translation"))} · {_escape_html(unit.path)}</p>'
                )
        chunks.append("</div>")
        return "".join(chunks)


def format_file_change(change: FileChange, t_func: Callable) -> str:
    if change.code == "read_failed":
        return t_func("Read failed: {error}", error=change.error)
    if change.code == "write_failed":
        return t_func("Write failed: {error}", error=change.error)
    if change.code == "no_json":
        return t_func("No JSON")
    if change.code == "no_change":
        return t_func("No change")
    if change.code == "paths_rewritten":
        return t_func("{count} paths rewritten", count=change.changes)
    if change.code == "paths":
        return t_func("{count} paths", count=change.changes)
    if change.changes:
        return t_func("{count} paths", count=change.changes)
    return change.error or t_func("No change")


class FolderJsonSyncPanel(QWidget):
    def __init__(self, t_func: Optional[Callable] = None, parent=None):
        super().__init__(parent)
        self._t = t_func or (lambda key, **kwargs: key.format(**kwargs) if kwargs else key)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.setHandleWidth(12)
        self.source_panel = FolderPanel(
            "BEFORE",
            "Original manga folders. You can drop a parent folder that contains episode folders.",
            "Drop original folders here",
            "Drag folders here or add them with the button below",
            self._t,
            margins=(15, 0, 10, 0),
        )
        self.dest_panel = FolderPanel(
            "AFTER",
            "Translated folders. Matching is more accurate when translation_map.json is present.",
            "Drop translated folders here",
            "Drag folders here or add them with the button below",
            self._t,
            margins=(10, 0, 15, 0),
        )
        splitter.addWidget(self.source_panel)
        splitter.addWidget(self.dest_panel)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1)
        layout.addWidget(splitter, 1)

        self.log_label = QLabel(self._t("Run Log"))
        self.log_label.setObjectName("page_subtitle")
        self.log_label.setContentsMargins(0, 5, 0, 0)
        layout.addWidget(self.log_label)
        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setMinimumHeight(140)
        self.log.setMaximumHeight(190)
        self.log.setPlaceholderText(
            self._t("Pairing results and rewrite details appear here.")
        )
        layout.addWidget(self.log)

        self.sync_button = QPushButton(self._t("Match JSON paths to these folders"))
        self.sync_button.setObjectName("folder_sync_button")
        self.sync_button.setProperty("primaryAction", True)
        self.sync_button.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.sync_button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.sync_button.setFixedHeight(54)
        self.sync_button.clicked.connect(self.run_sync)
        layout.addWidget(self.sync_button)

        self._log_pristine = True
        self._reset_intro_log()

    def refresh_ui_texts(self) -> None:
        self.source_panel.refresh_ui_texts()
        self.dest_panel.refresh_ui_texts()
        self.log_label.setText(self._t("Run Log"))
        self.log.setPlaceholderText(self._t("Pairing results and rewrite details appear here."))
        self.sync_button.setText(self._t("Match JSON paths to these folders"))
        if self._log_pristine:
            self._reset_intro_log()

    def _reset_intro_log(self) -> None:
        self.log.clear()
        color = get_current_theme_colors().get("text_secondary", "#94A3B8")
        html_text = _escape_html(self._t(FOLDER_SYNC_LOG_INTRO_KEY)).replace("\n", "<br>")
        self.log.append(f'<span style="color:{color};">{html_text}</span>')
        self._log_pristine = True

    def append_log(self, text: str, color: Optional[str] = None) -> None:
        if not color:
            color = get_current_theme_colors().get("text_secondary", "#94A3B8")
        html_text = _escape_html(text).replace("\n", "<br>")
        self.log.append(f'<span style="color:{color};">{html_text}</span>')
        self._log_pristine = False

    def run_sync(self) -> None:
        source_roots = self.source_panel.paths()
        dest_roots = self.dest_panel.paths()
        if not source_roots or not dest_roots:
            themed_information(
                self,
                self._t("Folders required"),
                self._t("Put folders on both the left and the right."),
            )
            return

        self.sync_button.setEnabled(False)
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        QApplication.processEvents()
        try:
            plan = build_sync_plan(source_roots, dest_roots)
        except Exception as exc:
            QApplication.restoreOverrideCursor()
            self.sync_button.setEnabled(True)
            themed_critical(
                self,
                self._t("Scan error"),
                self._t("A problem occurred while inspecting folders: {error}", error=exc),
            )
            return
        QApplication.restoreOverrideCursor()

        dialog = ConfirmDialog(plan, self._t, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            self.sync_button.setEnabled(True)
            self.append_log(self._t("JSON rewrite cancelled."))
            return

        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        QApplication.processEvents()
        try:
            results = apply_sync_plan(plan)
        except Exception as exc:
            QApplication.restoreOverrideCursor()
            self.sync_button.setEnabled(True)
            themed_critical(
                self,
                self._t("Write error"),
                self._t("A problem occurred while writing JSON: {error}", error=exc),
            )
            return
        QApplication.restoreOverrideCursor()
        self.sync_button.setEnabled(True)

        colors = get_current_theme_colors()
        changed = [item for item in results if item.changes > 0]
        failed = [item for item in results if item.code in {"read_failed", "write_failed"}]
        self.append_log("—" * 28, colors.get("text_muted", "#64748B"))
        self.append_log(
            self._t(
                "Done: {changed} JSON files updated, {failed} failed, {pairs} folder pairs",
                changed=len(changed),
                failed=len(failed),
                pairs=len(plan.pairs),
            ),
            colors.get("success_color", "#10B981"),
        )
        for pair in plan.pairs:
            self.append_log(
                f"  {pair.source.name}  →  {pair.dest.name}  ({pair.score * 100:.0f}%)",
                colors.get("text_primary"),
            )
        for item in changed:
            self.append_log(
                f"  {item.path}  ({format_file_change(item, self._t)})",
                colors.get("success_color"),
            )
        for item in failed:
            self.append_log(
                f"  {item.path}  ({format_file_change(item, self._t)})",
                colors.get("danger_bg"),
            )
        for unit in plan.unmatched_sources:
            self.append_log(
                self._t("Unmatched · Before Translation  {path}", path=unit.path),
                colors.get("warning_color"),
            )
        for unit in plan.unmatched_dests:
            self.append_log(
                self._t("Unmatched · After Translation  {path}", path=unit.path),
                colors.get("warning_color"),
            )

        if changed:
            themed_information(
                self,
                self._t("JSON rewrite complete"),
                self._t(
                    "Rewrote paths in {count} JSON files to the current folders.",
                    count=len(changed),
                ),
            )
        else:
            themed_information(
                self,
                self._t("No changes"),
                self._t("Nothing to rewrite, or the paths already match."),
            )
