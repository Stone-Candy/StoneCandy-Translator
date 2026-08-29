import os
import sys
import time
from typing import Iterable, List, Optional, Set

from editor.file_list_model import SUPPORTED_IMAGE_EXTENSIONS, FileListModel, FileType
from manga_translator.utils.path_manager import any_path_has_translation_map, find_json_path, has_translation_map
from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot
from PyQt6.QtWidgets import QFileDialog, QMessageBox
from services import get_config_service, get_i18n_manager, get_logger
from ui.secondary_pages.folder_dialog import select_folders
from ui.widgets.file_list_view import natural_sort_key

_WINDOWS_EPOCH_DIFF = 11644473600  # seconds between 1601-01-01 and 1970-01-01


def _set_file_times(path: str, timestamp: float) -> None:
    """Set atime/mtime, and on Windows also creation time, to timestamp."""
    if sys.platform == "win32":
        if _set_windows_file_times(path, timestamp):
            return
    os.utime(path, (timestamp, timestamp))


def _set_windows_file_times(path: str, timestamp: float) -> bool:
    import ctypes
    from ctypes import wintypes

    class FILETIME(ctypes.Structure):
        _fields_ = [("dwLowDateTime", wintypes.DWORD), ("dwHighDateTime", wintypes.DWORD)]

    ft_value = int((timestamp + _WINDOWS_EPOCH_DIFF) * 10_000_000)
    filetime = FILETIME(ft_value & 0xFFFFFFFF, ft_value >> 32)

    FILE_WRITE_ATTRIBUTES = 0x0100
    FILE_SHARE_READ = 0x00000001
    FILE_SHARE_WRITE = 0x00000002
    FILE_SHARE_DELETE = 0x00000004
    OPEN_EXISTING = 3
    FILE_FLAG_BACKUP_SEMANTICS = 0x02000000
    INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateFileW.restype = wintypes.HANDLE
    kernel32.SetFileTime.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(FILETIME),
        ctypes.POINTER(FILETIME),
        ctypes.POINTER(FILETIME),
    ]
    kernel32.SetFileTime.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]

    handle = kernel32.CreateFileW(
        path,
        FILE_WRITE_ATTRIBUTES,
        FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE,
        None,
        OPEN_EXISTING,
        FILE_FLAG_BACKUP_SEMANTICS,
        None,
    )
    handle_value = getattr(handle, "value", handle)
    if handle_value in (None, 0, INVALID_HANDLE_VALUE, -1):
        return False
    try:
        ok = kernel32.SetFileTime(
            handle,
            ctypes.byref(filetime),
            ctypes.byref(filetime),
            ctypes.byref(filetime),
        )
        return bool(ok)
    finally:
        kernel32.CloseHandle(handle)


class EditorLogic(QObject):
    """
    Handles the business logic for the editor view, including file list management.
    """
    file_list_changed = pyqtSignal(list)
    file_list_with_tree_changed = pyqtSignal(list, dict)  # (files, folder_map)
    image_loaded_in_editor = pyqtSignal(str)  # resolved_path — 에디터 file_list selection 동기화용

    def __init__(self, controller, parent=None):
        super().__init__(parent)
        self.controller = controller
        self.config_service = get_config_service()
        self.logger = get_logger(__name__)
        self.i18n = get_i18n_manager()
        
        # 使用新的文件列表模型
        self.file_model = FileListModel()
        
        # 保留树形结构支持
        self.folder_tree: dict = {}  # 保存文件夹树结构

    def _t(self, key: str, **kwargs) -> str:
        if self.i18n:
            return self.i18n.translate(key, **kwargs)
        return key

    def _warn_completed_translation_folder_added(self):
        QMessageBox.warning(
            None,
            self._t("Notice"),
            self._t(
                "You have loaded already translated images.\nTo edit the translation, clear the list and add the original folder instead."
            ),
        )

    # --- File Management Methods ---

    @pyqtSlot()
    def open_and_add_files(self):
        """Opens a file dialog to add files to the editor's list."""
        last_dir = self.config_service.get_config().app.last_open_dir
        file_paths, _ = QFileDialog.getOpenFileNames(
            None, 
            "添加文件到编辑器", 
            last_dir, 
            "Image Files (*.png *.jpg *.jpeg *.bmp *.webp *.avif *.heic *.heif)"
        )
        if file_paths:
            self.add_files(file_paths)
            # TODO: Find a way to save last_open_dir back to config service

    @pyqtSlot()
    def open_and_add_folder(self):
        """Opens a dialog to select folders (supports multiple selection) and adds all containing images to the list."""
        last_dir = self.config_service.get_config().app.last_open_dir

        # 使用自定义的现代化文件夹选择器
        folders = select_folders(
            parent=None,
            start_dir=last_dir,
            multi_select=True,
            config_service=self.config_service
        )

        if folders:
            found_completed = False
            for folder_path in folders:
                if has_translation_map(folder_path):
                    found_completed = True
                self.add_folder(folder_path, notify_completed=False)
            if found_completed:
                self._warn_completed_translation_folder_added()

    def add_files(self, files: List[str], notify_completed: bool = True):
        """添加文件到列表"""
        if not files:
            return
        
        # 统一进行自然排序
        files = sorted(files, key=natural_sort_key)
        found_completed = notify_completed and any_path_has_translation_map(files)
        
        # 使用新模型添加文件
        added_items = self.file_model.add_files(files)
        
        if added_items:
            # 检查是否是第一次添加文件
            is_first_add = len(self.file_model.files) == len(added_items)
            
            # 发射信号更新UI
            file_paths = [item.path for item in self.file_model.files]
            self.file_list_changed.emit(file_paths)
            
            # 如果是第一次添加文件，自动加载第一个
            if is_first_add and len(added_items) > 0:
                try:
                    self.load_image_into_editor(added_items[0].path)
                except Exception:
                    pass  # 静默失败，避免崩溃

        if found_completed:
            self._warn_completed_translation_folder_added()

    def add_folder(self, folder_path: str, notify_completed: bool = True):
        """添加文件夹到列表"""
        if not folder_path or not os.path.isdir(folder_path):
            return

        found_completed = notify_completed and has_translation_map(folder_path)
        
        # 检查是否是第一次添加文件
        is_first_add = len(self.file_model.files) == 0
        
        # 扫描文件夹中的所有图片
        image_extensions = SUPPORTED_IMAGE_EXTENSIONS
        files_to_add = []
        
        try:
            for root, dirs, files in os.walk(folder_path):
                # 跳过 manga_translator_work 目录
                if 'manga_translator_work' in root:
                    continue
                    
                dirs.sort(key=natural_sort_key)
                
                for f in sorted(files, key=natural_sort_key):
                    if os.path.splitext(f)[1].lower() in image_extensions:
                        file_path = os.path.join(root, f)
                        files_to_add.append(file_path)
        except OSError as e:
            self.logger.error(f"폴더 스캔 실패: {e}")
            return
        
        if files_to_add:
            # 添加文件
            added_items = self.file_model.add_files(files_to_add)
            
            # 发射信号更新UI
            file_paths = [item.path for item in self.file_model.files]
            self.file_list_changed.emit(file_paths)
            
            # 如果是第一次添加，自动加载第一个图片
            if is_first_add and added_items:
                try:
                    self.load_image_into_editor(added_items[0].path)
                except Exception:
                    pass  # 静默失败，避免崩溃

        if found_completed:
            self._warn_completed_translation_folder_added()

    @pyqtSlot(list)
    def add_files_from_paths(self, paths: List[str]):
        """
        从拖放的路径列表中添加文件和文件夹
        
        Args:
            paths: 拖放的文件或文件夹路径列表
        """
        found_completed = any_path_has_translation_map(paths)
        files_to_add = []
        for path in paths:
            if os.path.isfile(path):
                # 验证是否是图片文件
                if os.path.splitext(path)[1].lower() in SUPPORTED_IMAGE_EXTENSIONS:
                    files_to_add.append(path)
            elif os.path.isdir(path):
                # 添加文件夹中的所有图片
                self.add_folder(path, notify_completed=False)
        
        # 添加单独的文件
        if files_to_add:
            self.add_files(files_to_add, notify_completed=False)

        if found_completed:
            self._warn_completed_translation_folder_added()

    @pyqtSlot(str)
    def remove_file(self, file_path: str, emit_signal: bool = False):
        """
        移除文件或文件夹
        
        Args:
            file_path: 要移除的文件或文件夹路径
            emit_signal: 是否发射 file_list_changed 信号（默认 False，由视图自己处理）
        """
        norm_path = os.path.normpath(file_path)
        paths_to_check = [norm_path]
        
        # 检查是否是文件夹（在 folder_tree 中）
        if norm_path in self.folder_tree:
            # 移除文件夹下的所有文件
            files_to_remove = []
            for file_item in self.file_model.files:
                item_norm_path = os.path.normpath(file_item.path)
                try:
                    # 检查文件是否在该文件夹内
                    if item_norm_path.startswith(norm_path + os.sep) or item_norm_path == norm_path:
                        files_to_remove.append(file_item.path)
                except Exception:
                    pass
            
            # 批量移除文件
            for file_to_remove in files_to_remove:
                self.file_model.remove_file(file_to_remove)
                # 释放缓存
                if hasattr(self.controller, 'resource_manager'):
                    self.controller.resource_manager.release_image_from_cache(file_to_remove)
            
            # 从 folder_tree 中删除
            del self.folder_tree[norm_path]
            
            # 检查当前加载的图片是否在被删除的文件夹内
            current_image_path = self.controller.model.get_source_image_path()
            if current_image_path:
                norm_current = os.path.normpath(current_image_path)
                try:
                    if norm_current.startswith(norm_path + os.sep) or norm_current == norm_path:
                        self.controller._clear_editor_state(release_image_cache=True)
                except Exception:
                    pass
        else:
            # 移除单个文件
            removed = self.file_model.remove_file(file_path)
            
            if not removed:
                return
            
            # 检查当前加载的图片是否是被移除的文件（或其关联文件）
            current_image_path = self.controller.model.get_source_image_path()
            if current_image_path:
                norm_current = os.path.normpath(current_image_path)
                
                # 检查当前图片是否匹配要删除的文件或其关联文件
                if norm_current in paths_to_check:
                    self.controller._clear_editor_state(release_image_cache=True)
            
            # 从资源管理器的缓存中释放被移除的图片及其关联文件
            if hasattr(self.controller, 'resource_manager'):
                for path in paths_to_check:
                    self.controller.resource_manager.release_image_from_cache(path)
        
        # 检查是否还有文件，如果没有了就清空画布
        if len(self.file_model.files) == 0:
            self.controller._clear_editor_state(release_image_cache=True)
            
            # 清空所有图片缓存
            if hasattr(self.controller, 'resource_manager'):
                self.controller.resource_manager.clear_image_cache()
        
        # 如果需要发射信号，更新UI
        if emit_signal:
            file_paths = [item.path for item in self.file_model.files]
            if self.folder_tree:
                self.file_list_with_tree_changed.emit(file_paths, self.folder_tree)
            else:
                self.file_list_changed.emit(file_paths)

    @pyqtSlot()
    def clear_list(self):
        """清空文件列表"""
        self.file_model.clear()
        self.folder_tree.clear()
        
        # 清空列表时发射空列表
        self.file_list_changed.emit([])
        
        # 先清空画布图片，这样后台任务会检测到图片为None而提前返回
        # 然后清空编辑器状态（包括取消后台任务）
        self.controller._clear_editor_state(release_image_cache=True)
        
        # 清空所有图片缓存
        if hasattr(self.controller, 'resource_manager'):
            self.controller.resource_manager.clear_image_cache()

    def _read_json_result_folder(self, source_path: str) -> Optional[str]:
        json_path = find_json_path(source_path)
        if not json_path or not os.path.isfile(json_path):
            return None

        try:
            import json as _json

            with open(json_path, "r", encoding="utf-8") as f:
                data = _json.load(f)
        except Exception:
            return None

        if not isinstance(data, dict) or not data:
            return None

        image_data = None
        image_key = os.path.abspath(source_path)
        candidate = data.get(image_key)
        if isinstance(candidate, dict):
            image_data = candidate
        else:
            image_key_norm = os.path.normcase(image_key)
            for key, value in data.items():
                if not isinstance(key, str) or not isinstance(value, dict):
                    continue
                try:
                    if os.path.normcase(os.path.abspath(key)) == image_key_norm:
                        image_data = value
                        break
                except Exception:
                    continue
            if image_data is None and len(data) == 1:
                only = next(iter(data.values()))
                if isinstance(only, dict):
                    image_data = only

        if not isinstance(image_data, dict):
            return None

        saved_dir = image_data.get("last_export_dir")
        if isinstance(saved_dir, str) and saved_dir.strip():
            return os.path.normpath(saved_dir)
        return None

    def _open_os_folder(self, folder: str) -> None:
        import subprocess
        import sys

        try:
            if sys.platform == "win32":
                os.startfile(os.path.realpath(folder))
            elif sys.platform == "darwin":
                subprocess.run(["open", folder], check=False)
            else:
                subprocess.run(["xdg-open", folder], check=False)
        except Exception as e:
            self.logger.error(f"Failed to open result folder: {e}")

    def open_selected_result_folder(
        self,
        source_path: str,
        is_folder: bool,
        parent=None,
    ) -> None:
        if is_folder:
            if source_path and os.path.isdir(source_path):
                self._open_os_folder(source_path)
                return
            QMessageBox.information(parent, self._t("Information"), self._t("Work is pending."))
            return

        result_dir = self._read_json_result_folder(source_path)
        if result_dir and os.path.isdir(result_dir):
            self._open_os_folder(result_dir)
            return

        QMessageBox.information(parent, self._t("Information"), self._t("Work is pending."))

    def sync_result_file_dates(self) -> int:
        """현재 목록의 렌더된 결과 파일 날짜를 같은 시각(현재)으로 맞춘다.

        결과 파일이 없으면 아무 것도 하지 않는다. 개별 파일 실패는 무시한다.
        """
        result_files = self._collect_rendered_result_files()
        if not result_files:
            return 0

        timestamp = time.time()
        synced = 0
        for path in result_files:
            try:
                _set_file_times(path, timestamp)
                synced += 1
            except Exception as e:
                self.logger.debug(f"Failed to sync file date: {path}: {e}")
        if synced:
            self.logger.info(f"Synchronized dates for {synced} output file(s)")
        return synced

    def _collect_rendered_result_files(self) -> List[str]:
        source_paths = [os.path.normpath(item.path) for item in self.file_model.files]
        if not source_paths:
            return []

        source_normcase: Set[str] = {os.path.normcase(path) for path in source_paths}

        found: dict[str, str] = {}

        def add_result(path: str) -> None:
            if not path or not os.path.isfile(path):
                return
            norm = os.path.normpath(path)
            key = os.path.normcase(norm)
            if key in source_normcase:
                return
            found[key] = norm

        candidate_dirs = self._collect_result_candidate_dirs(source_paths)
        for directory in candidate_dirs:
            map_path = os.path.join(directory, "translation_map.json")
            if os.path.isfile(map_path):
                try:
                    import json as _json

                    with open(map_path, "r", encoding="utf-8") as f:
                        data = _json.load(f)
                    if isinstance(data, dict):
                        for translated_path, mapped_source in data.items():
                            if not isinstance(translated_path, str) or not isinstance(mapped_source, str):
                                continue
                            try:
                                mapped_key = os.path.normcase(os.path.normpath(mapped_source))
                            except Exception:
                                continue
                            if mapped_key in source_normcase:
                                add_result(translated_path)
                except Exception as e:
                    self.logger.debug(f"Failed reading translation_map {map_path}: {e}")

        for source_path in source_paths:
            export_dir = self._read_json_result_folder(source_path)
            if not export_dir or not os.path.isdir(export_dir):
                export_dir = os.path.join(
                    os.path.dirname(source_path), "manga_translator_work", "result"
                )
                if not os.path.isdir(export_dir):
                    continue
            stem = os.path.splitext(os.path.basename(source_path))[0]
            try:
                for name in os.listdir(export_dir):
                    name_stem, name_ext = os.path.splitext(name)
                    if os.path.normcase(name_stem) != os.path.normcase(stem):
                        continue
                    if name_ext.lower() not in SUPPORTED_IMAGE_EXTENSIONS:
                        continue
                    add_result(os.path.join(export_dir, name))
            except OSError as e:
                self.logger.debug(f"Failed listing result dir {export_dir}: {e}")

        return list(found.values())

    def _collect_result_candidate_dirs(self, source_paths: Iterable[str]) -> List[str]:
        candidate_dirs: List[str] = []
        seen: Set[str] = set()

        def add_dir(path: Optional[str]) -> None:
            if not path or not isinstance(path, str):
                return
            norm = os.path.normpath(path)
            if not os.path.isdir(norm):
                return
            key = os.path.normcase(norm)
            if key in seen:
                return
            seen.add(key)
            candidate_dirs.append(norm)

        for source_path in source_paths:
            add_dir(self._read_json_result_folder(source_path))
            add_dir(os.path.join(os.path.dirname(source_path), "manga_translator_work", "result"))

        last_output = None
        try:
            config = self.config_service.get_config()
            last_output = getattr(getattr(config, "app", None), "last_output_path", None)
        except Exception:
            last_output = None
        add_dir(last_output)
        if last_output and os.path.isdir(last_output):
            try:
                for name in os.listdir(last_output):
                    add_dir(os.path.join(last_output, name))
                    if len(candidate_dirs) >= 300:
                        break
            except OSError:
                pass

        return candidate_dirs

    # --- Image Loading Methods ---

    def _adjacent_image_paths(self, resolved_path: str) -> List[str]:
        norm_current = os.path.normcase(os.path.normpath(resolved_path))
        file_paths = [item.path for item in self.file_model.files]
        norm_paths = [os.path.normcase(os.path.normpath(path)) for path in file_paths]
        if norm_current not in norm_paths:
            return []

        index = norm_paths.index(norm_current)
        adjacent = []
        for next_index in (index + 1, index - 1):
            if 0 <= next_index < len(file_paths):
                adjacent.append(file_paths[next_index])
        return adjacent

    def load_file_lists(self, source_files: List[str], folder_tree: dict = None):
        """
        从主窗口接收文件列表（用于翻译完成后进入编辑器）
        
        Args:
            source_files: 源文件列表
            folder_tree: 文件夹树结构
        """
        self.folder_tree = folder_tree if folder_tree else {}

        # 清空文件模型
        self.file_model.clear()
        
        # 批量添加文件，避免一次性处理过多文件导致UI卡顿
        batch_size = 50  # 每批处理50个文件
        for i in range(0, len(source_files), batch_size):
            batch = source_files[i:i + batch_size]
            self.file_model.add_files(batch)
            
            # 处理事件，保持UI响应
            from PyQt6.QtWidgets import QApplication
            QApplication.processEvents()
        
        # 只向UI发送模型实际接收的图片文件，避免 PDF/压缩包残留在编辑器列表中
        accepted_files = [item.path for item in self.file_model.files]

        # 如果有folder_tree，使用树形结构显示
        if folder_tree:
            self.file_list_with_tree_changed.emit(accepted_files, folder_tree)
        else:
            # 否则使用平铺列表
            self.file_list_changed.emit(accepted_files)

    @pyqtSlot(str)
    def load_image_into_editor(self, file_path: str):
        """
        加载图片到编辑器（统一接口）
        """
        resolved_path = self.file_model.resolve_entry_path(file_path)

        # 获取文件项
        if not FileListModel.is_supported_image_file(resolved_path):
            self.logger.warning(f"지원하지 않는 에디터 파일 형식이라 무시했습니다: {file_path}")
            return

        file_item = self.file_model.get_file_item(resolved_path)
        
        if not file_item:
            # 文件不在列表中，尝试识别
            self.file_model.add_files([resolved_path])
            file_item = self.file_model.get_file_item(resolved_path)
        
        if not file_item:
            self.logger.error(f"파일을 인식할 수 없습니다: {resolved_path}")
            return

        if file_item.file_type == FileType.UNTRANSLATED:
            self.logger.warning(f"번역되지 않은 이미지: {resolved_path}")

        self.controller._pending_editor_prefetch_paths = self._adjacent_image_paths(resolved_path)
        self.controller.load_image_and_regions(resolved_path)

        # 파일 리스트 selection을 실제로 로드된 이미지와 동기화한다.
        # (메인 리스트에서 특정 페이지로 바로 진입했을 때 selection이
        #  맞춰지지 않아 A/D 단축키가 엉뚱한 페이지 기준으로 동작하는 문제 수정)
        self.image_loaded_in_editor.emit(resolved_path)
