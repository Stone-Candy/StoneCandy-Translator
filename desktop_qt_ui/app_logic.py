
"""
应用业务逻辑层
处理应用的核心业务逻辑，与UI层分离
"""
import asyncio
import base64
import io
import logging
import os
import textwrap
import threading
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from PIL import Image
from PyQt6.QtCore import (
    QObject,
    QRunnable,
    Qt,
    QTimer,
    pyqtSignal,
    pyqtSlot,
)
from PyQt6.QtWidgets import QFileDialog
from services import (
    get_config_service,
    get_file_service,
    get_i18n_manager,
    get_logger,
    get_preset_service,
    get_state_manager,
    get_translation_service,
)
from services.state_manager import AppStateKey
from utils.asyncio_cleanup import shutdown_event_loop

from manga_translator.config import (
    Alignment,
    Colorizer,
    Detector,
    Direction,
    Inpainter,
    InpaintPrecision,
    Ocr,
    Renderer,
    Translator,
    Upscaler,
)
from manga_translator.save import OUTPUT_FORMATS
from manga_translator.utils.openai_compat import resolve_openai_compatible_api_key
from manga_translator.utils import open_pil_image, save_pil_image
from manga_translator.utils.path_manager import any_path_has_translation_map
from utils.overwrite_policy import (
    OVERWRITE_ALWAYS,
    OVERWRITE_ASK,
    OVERWRITE_SKIP,
    collect_existing_outputs,
    normalize_overwrite_mode,
    overwrite_enabled,
)


@dataclass
class AppConfig:
    """应用配置信息"""
    window_size: tuple = (1230, 768)
    theme: str = "dark"
    language: str = "zh_CN"
    auto_save: bool = True
    max_recent_files: int = 10


ARCHIVE_EXTRACT_IMAGE_DIRNAME = 'original_images'
ARCHIVE_EXTRACT_META_FILENAME = '.extract_meta.json'
_OPENAI_BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8,ja;q=0.7",
    "Connection": "keep-alive",
    "Sec-Ch-Ua": '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"Windows"',
}
_GEMINI_BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8,ja;q=0.7",
    "Origin": "https://aistudio.google.com",
    "Referer": "https://aistudio.google.com/",
}


def _resolve_archive_output_dir_from_extracted_image(image_path: str, output_folder: str) -> Optional[str]:
    """
    如果 image_path 指向输出目录中的压缩包解压图片，返回对应压缩包输出目录。
    例如: <output>/A/B/1/original_images/page.png -> <output>/A/B/1
    """
    if not image_path or not output_folder:
        return None

    image_parent = os.path.normpath(os.path.dirname(image_path))
    if os.path.basename(image_parent) != ARCHIVE_EXTRACT_IMAGE_DIRNAME:
        return None

    meta_path = os.path.join(image_parent, ARCHIVE_EXTRACT_META_FILENAME)
    if not os.path.isfile(meta_path):
        return None

    archive_output_dir = os.path.normpath(os.path.dirname(image_parent))
    output_root_abs = os.path.normcase(os.path.abspath(output_folder))
    archive_output_abs = os.path.normcase(os.path.abspath(archive_output_dir))

    try:
        common = os.path.commonpath([output_root_abs, archive_output_abs])
    except ValueError:
        return None

    if common != output_root_abs:
        return None

    return archive_output_dir


def _normalize_compare_path(path: str) -> str:
    """Compare directories in a case-stable, slash-stable way."""
    if not path:
        return ""
    return os.path.normcase(os.path.normpath(os.path.abspath(os.path.expanduser(path))))


def _is_same_directory(path_a: str, path_b: str) -> bool:
    left = _normalize_compare_path(path_a)
    right = _normalize_compare_path(path_b)
    return bool(left and right and left == right)


class MainAppLogic(QObject):
    """主页面业务逻辑控制器"""
    files_added = pyqtSignal(list)
    files_cleared = pyqtSignal()
    file_removed = pyqtSignal(str)
    config_loaded = pyqtSignal(dict)
    output_path_updated = pyqtSignal(str)
    task_completed = pyqtSignal(list)
    task_file_completed = pyqtSignal(dict)
    error_dialog_requested = pyqtSignal(str)
    render_setting_changed = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.logger = get_logger(__name__)
        self.config_service = get_config_service()
        self.translation_service = get_translation_service()
        self.file_service = get_file_service()
        self.state_manager = get_state_manager()
        self.i18n = get_i18n_manager()
        self.preset_service = get_preset_service()

        # ✅ 使用普通线程替代线程池
        self.current_thread = None  # 当前运行的线程
        self.current_worker = None  # 当前运行的worker
        self._shutdown_started = False
        self.current_task_id = 0  # 任务ID，用于区分不同的翻译任务
        self.saved_files_count = 0
        self.saved_files_list = []  # 收集所有保存的文件路径
        self._task_failures: List[Dict[str, str]] = []
        self._task_failure_keys: set[str] = set()

        self.source_files: List[str] = [] # Holds both files and folders
        self.file_to_folder_map: Dict[str, Optional[str]] = {} # 记录文件来自哪个文件夹
        self.archive_to_temp_map: Dict[str, str] = {} # 记录压缩包解压的临时目录
        self.excluded_subfolders: set = set() # 记录被删除的子文件夹路径
        self.folder_tree_cache: Dict[str, dict] = {} # 缓存文件夹的完整树结构 {top_folder: tree_structure}

        self.app_config = AppConfig()
        self._ui_log("Main page business logic initialized")
    
    def _t(self, key: str, **kwargs) -> str:
        """翻译辅助方法"""
        if self.i18n:
            return self.i18n.translate(key, **kwargs)
        return key
    
    def _ui_log(self, message: str, level: str = "INFO"):
        """
        输出到日志文件
        使用 root logger 确保写入 main.py 配置的日志文件
        """
        try:
            root_logger = logging.getLogger()
            if level == "ERROR":
                root_logger.error(message)
            elif level == "DEBUG":
                root_logger.debug(message)
            elif level == "WARNING":
                root_logger.warning(message)
            else:
                root_logger.info(message)
        except Exception:
            print(f"{level} - {message}")

    def _collect_runtime_env_values(self) -> Dict[str, str]:
        env_vars = self.config_service.load_env_vars()
        if hasattr(self, "main_view") and self.main_view and getattr(self.main_view, "env_widgets", None):
            for key, pair in self.main_view.env_widgets.items():
                if not pair or len(pair) < 2:
                    continue
                widget = pair[1]
                try:
                    if hasattr(widget, "currentData"):
                        data = widget.currentData()
                        env_vars[key] = str(data if data is not None else widget.currentText()).strip()
                    else:
                        env_vars[key] = widget.text().strip()
                except Exception:
                    continue
        return env_vars

    def _format_missing_api_requirement_label(self, item: Dict[str, Any]) -> str:
        section = item.get("section")
        setting = item.get("setting")
        if section == "translator":
            section_label = self._t("label_translator")
        elif section == "ocr" and setting == "secondary_ocr":
            section_label = self._t("label_secondary_ocr")
        elif section == "ocr" and setting == "novelai_ocr":
            section_label = self._t("label_novelai_ocr")
        elif section == "ocr" and setting == "novelai_secondary_ocr":
            section_label = self._t("label_novelai_secondary_ocr")
        elif section == "ocr":
            section_label = self._t("label_ocr")
        elif section == "colorizer":
            section_label = self._t("label_colorizer")
        elif section == "render":
            section_label = self._t("label_renderer")
        else:
            section_label = str(section or self._t("Settings"))

        display_name = str(item.get("display_name") or item.get("selected_value") or "").strip()
        if display_name:
            return f"{section_label}: {display_name}"
        return section_label

    def _validate_runtime_api_requirements(self, config) -> bool:
        from PyQt6.QtWidgets import QMessageBox

        env_vars = self._collect_runtime_env_values()
        missing = self.config_service.get_missing_runtime_api_requirements(config, env_vars)
        if not missing:
            return True

        details = "\n".join(
            f"- {self._format_missing_api_requirement_label(item)} -> {' / '.join(item.get('accepted_env_vars', []))}"
            for item in missing
        )
        log_summary = "; ".join(
            f"{self._format_missing_api_requirement_label(item)} -> {' / '.join(item.get('accepted_env_vars', []))}"
            for item in missing
        )
        self._ui_log(f"필수 API 설정이 없어 번역을 시작하지 않았습니다: {log_summary}", "WARNING")
        QMessageBox.warning(
            None,
            self._t("API Keys Required"),
            self._t(
                "The selected features are missing required API Keys (.env):\n{details}\n\nPlease fill one of the listed API key fields in API Keys (.env) and try again.",
                details=details,
            ),
        )
        return False

    def _reset_task_failures(self):
        self._task_failures = []
        self._task_failure_keys = set()

    def _normalize_task_error_summary(self, error_message: str, limit: int = 160) -> str:
        raw = str(error_message or "").replace("\r\n", "\n").replace("\r", "\n")
        lines = [line.strip() for line in raw.split("\n") if line.strip()]
        summary = lines[0] if lines else "자세한 오류가 기록되지 않았습니다"
        return textwrap.shorten(summary, width=limit, placeholder="...")

    def _record_task_failure(self, original_path: str, error_message: str):
        normalized_path = os.path.normpath(str(original_path or "Unknown"))
        raw_error = str(error_message or "").strip() or "자세한 오류가 기록되지 않았습니다"
        failure_key = f"{normalized_path}\n{raw_error}"
        if failure_key in self._task_failure_keys:
            return

        self._task_failure_keys.add(failure_key)
        self._task_failures.append(
            {
                "original_path": normalized_path,
                "file_name": os.path.basename(normalized_path) or normalized_path,
                "error": raw_error,
                "summary": self._normalize_task_error_summary(raw_error),
            }
        )

    def _record_task_failure_from_result(self, result: Dict[str, Any]):
        if not result or result.get("success"):
            return
        self._record_task_failure(result.get("original_path"), result.get("error"))

    def _build_task_failure_dialog_message(self) -> str:
        failed_count = len(self._task_failures)
        if failed_count == 0:
            return ""

        first_failure = self._task_failures[0]
        return TranslationWorker._build_friendly_error_message(
            first_failure["error"],
            "",
            first_failure.get("file_name", ""),
        )


    @pyqtSlot(dict)
    def _refresh_file_list_json_status(self, file_path: str | None = None) -> None:
        if not hasattr(self, "main_view") or not self.main_view:
            return
        file_list = getattr(self.main_view, "file_list", None)
        if file_list is None:
            return
        if file_path:
            from ui.widgets.file_list_view import FileItemWidget
            FileItemWidget.refresh_json_status_for_path(file_path)
            return
        if hasattr(file_list, "refresh_json_status"):
            file_list.refresh_json_status()

    def on_file_completed(self, result):
        """处理单个文件处理完成的信号并保存"""
        if not result.get('success'):
            self._record_task_failure_from_result(result)
            self.logger.error(f"Skipping save for failed item: {result.get('original_path')}")
            return

        try:
            # 检查是否是批量模式（后端已保存，有 output_path 但没有 image_data）
            if result.get('output_path') and not result.get('image_data'):
                # 批量模式：文件已由后端保存
                final_output_path = result['output_path']
                self.saved_files_count += 1
                self.saved_files_list.append(final_output_path)
                self.logger.info(self._t("log_file_saved_successfully", path=final_output_path))
                self.task_file_completed.emit({'path': final_output_path})
                self._refresh_file_list_json_status(result.get('original_path'))
                return
            
            # 顺序模式：需要前端保存
            if not result.get('image_data'):
                self.logger.error(f"No image_data for: {result.get('original_path')}")
                return
            config = self.config_service.get_config()
            output_format = config.cli.format
            save_quality = config.cli.save_quality
            output_folder = config.app.last_output_path
            save_to_source_dir = config.cli.save_to_source_dir

            original_path = result['original_path']
            base_filename = os.path.basename(original_path)

            # 检查是否启用了"输出到原图目录"模式
            if save_to_source_dir:
                # 输出到原图所在目录的 manga_translator_work/result 子目录
                source_dir = os.path.dirname(original_path)
                final_output_folder = os.path.join(source_dir, 'manga_translator_work', 'result')
            else:
                # 原有逻辑：使用配置的输出目录
                if not output_folder:
                    self.logger.error(self._t("log_output_dir_not_set"))
                    self.state_manager.set_status_message(self._t("error_output_dir_not_set"))
                    return

                # 检查文件是否来自文件夹或压缩包
                source_folder = self.file_to_folder_map.get(original_path)

                if source_folder:
                    # 检查是否来自压缩包
                    if self.file_service.is_archive_file(source_folder):
                        # 文件来自压缩包：
                        # 优先复用解压目录的上级输出目录，避免文件夹扫描时被平铺到输出根目录
                        archive_output_dir = _resolve_archive_output_dir_from_extracted_image(
                            original_path, output_folder
                        )
                        if archive_output_dir:
                            final_output_folder = archive_output_dir
                        else:
                            archive_name = os.path.splitext(os.path.basename(source_folder))[0]
                            final_output_folder = os.path.join(output_folder, archive_name)
                    else:
                        # 文件来自文件夹，保持相对路径结构
                        parent_dir = os.path.normpath(os.path.dirname(original_path))
                        relative_path = os.path.relpath(parent_dir, source_folder)
                        
                        # Normalize path and avoid adding '.' as a directory component
                        if relative_path == '.':
                            final_output_folder = os.path.join(output_folder, os.path.basename(source_folder))
                        else:
                            final_output_folder = os.path.join(output_folder, os.path.basename(source_folder), relative_path)
                    final_output_folder = os.path.normpath(final_output_folder)
                else:
                    # 文件是单独添加的，直接保存到输出目录
                    final_output_folder = output_folder

            # 确定文件扩展名
            if output_format and output_format != self._t("format_not_specified"):
                file_extension = f".{output_format}"
                output_filename = os.path.splitext(base_filename)[0] + file_extension
            else:
                # 保持原扩展名
                output_filename = base_filename

            final_output_path = os.path.join(final_output_folder, output_filename)

            os.makedirs(final_output_folder, exist_ok=True)

            image_to_save = result['image_data']
            self._save_image_with_source_metadata(
                image_to_save,
                final_output_path,
                original_path,
                save_quality,
            )

            # 更新translation_map.json
            self._update_translation_map(original_path, final_output_path)

            self.saved_files_count += 1
            self.saved_files_list.append(final_output_path)  # 收集保存的文件路径
            self.logger.info(self._t("log_file_saved_successfully", path=final_output_path))
            self.task_file_completed.emit({'path': final_output_path})
            self._refresh_file_list_json_status(original_path)

        except Exception as e:
            self.logger.error(self._t("log_file_save_error", path=result['original_path'], error=e))

    def _save_image_with_source_metadata(
        self,
        image: Image.Image,
        output_path: str,
        source_path: Optional[str],
        save_quality: int,
    ):
        source_image = None
        try:
            if source_path and os.path.exists(source_path):
                try:
                    source_image = open_pil_image(source_path, eager=True)
                except Exception as exc:
                    self.logger.warning(f"원본 이미지 메타데이터를 읽지 못했습니다. ICC 없이 저장을 계속합니다: {source_path}, error={exc}")
            from manga_translator.utils.stealth_pngcomp import resolve_stealth_pngcomp_for_image

            save_pil_image(
                image,
                output_path,
                source_image=source_image,
                quality=save_quality,
                stealth_pngcomp=resolve_stealth_pngcomp_for_image(source_path),
            )
        finally:
            if source_image is not None:
                try:
                    source_image.close()
                except Exception:
                    pass

    def _update_translation_map(self, source_path: str, translated_path: str):
        """在输出目录创建或更新 translation_map.json"""
        try:
            import json
            output_dir = os.path.dirname(translated_path)
            map_path = os.path.join(output_dir, 'translation_map.json')

            # 规范化路径以确保一致性
            source_path_norm = os.path.normpath(source_path)
            translated_path_norm = os.path.normpath(translated_path)

            translation_map = {}
            if os.path.exists(map_path):
                with open(map_path, 'r', encoding='utf-8') as f:
                    try:
                        translation_map = json.load(f)
                    except json.JSONDecodeError:
                        self.logger.warning(f"Could not decode {map_path}, creating a new one.")

            # 使用翻译后的路径作为键，确保唯一性
            translation_map[translated_path_norm] = source_path_norm

            with open(map_path, 'w', encoding='utf-8') as f:
                json.dump(translation_map, f, ensure_ascii=False, indent=4)

            self.logger.info(f"Updated translation_map.json: {translated_path_norm} -> {source_path_norm}")
        except Exception as e:
            self.logger.error(f"Failed to update translation_map.json: {e}")

    def _calculate_output_path(self, image_path: str, save_info: dict) -> str:
        """
        计算输出文件的完整路径（用于预检查文件是否存在）
        
        Args:
            image_path: 输入图片的路径
            save_info: 包含输出配置的字典
                - output_folder: 输出文件夹
                - format: 输出格式（可选）
                - save_to_source_dir: 是否输出到原图目录
                
        Returns:
            str: 计算后的输出文件完整路径
        """
        output_folder = save_info.get('output_folder')
        output_format = save_info.get('format')
        save_to_source_dir = save_info.get('save_to_source_dir', False)
        
        file_path = image_path
        parent_dir = os.path.normpath(os.path.dirname(file_path))
        
        # 检查是否启用了"输出到原图目录"模式
        if save_to_source_dir:
            # 输出到原图所在目录的 manga_translator_work/result 子目录
            final_output_dir = os.path.join(parent_dir, 'manga_translator_work', 'result')
        else:
            # 原有逻辑：使用配置的输出目录
            final_output_dir = output_folder
            
            # 检查文件是否来自文件夹
            source_folder = self.file_to_folder_map.get(image_path)
            if source_folder:
                # 检查是否来自压缩包
                if self.file_service.is_archive_file(source_folder):
                    archive_output_dir = _resolve_archive_output_dir_from_extracted_image(
                        image_path, output_folder
                    )
                    if archive_output_dir:
                        final_output_dir = archive_output_dir
                    else:
                        archive_name = os.path.splitext(os.path.basename(source_folder))[0]
                        final_output_dir = os.path.join(output_folder, archive_name)
                else:
                    # 文件来自文件夹，保持相对路径结构
                    relative_path = os.path.relpath(parent_dir, source_folder)
                    # Normalize path and avoid adding '.' as a directory component
                    if relative_path == '.':
                        final_output_dir = os.path.join(output_folder, os.path.basename(source_folder))
                    else:
                        final_output_dir = os.path.join(output_folder, os.path.basename(source_folder), relative_path)
                final_output_dir = os.path.normpath(final_output_dir)
        
        # 处理输出文件名和格式
        base_filename, _ = os.path.splitext(os.path.basename(file_path))
        if output_format and output_format.strip() and output_format.lower() not in ['none', '不指定']:
            output_filename = f"{base_filename}.{output_format}"
        else:
            output_filename = os.path.basename(file_path)
        
        final_output_path = os.path.join(final_output_dir, output_filename)
        return final_output_path

    def _is_archive_source_path(self, path: str) -> bool:
        try:
            return bool(path and self.file_service.is_archive_file(path))
        except Exception:
            return False

    def _source_item_is_folder(self, path: str) -> bool:
        if os.path.isdir(path):
            return True
        if os.path.isfile(path) or self._is_archive_source_path(path):
            return False
        return not os.path.splitext(path)[1]

    def find_source_output_conflict(
        self,
        output_folder: Optional[str] = None,
        resolved_files: Optional[List[str]] = None,
    ) -> Optional[str]:
        """
        Return a conflicting directory when originals and rendered output would share a folder.
        `save_to_source_dir` writes to manga_translator_work/result, which is a different place.
        """
        try:
            config = self.config_service.get_config()
        except Exception:
            config = None

        if config is not None and getattr(getattr(config, "cli", None), "save_to_source_dir", False):
            return None

        if output_folder is None:
            output_folder = getattr(getattr(config, "app", None), "last_output_path", "") if config else ""
        output_folder = (output_folder or "").strip()
        if not output_folder:
            return None

        if resolved_files:
            save_info = {
                "output_folder": output_folder,
                "format": None,
                "save_to_source_dir": False,
            }
            for file_path in resolved_files:
                if not file_path:
                    continue
                dest_path = self._calculate_output_path(file_path, save_info)
                source_dir = os.path.dirname(file_path)
                dest_dir = os.path.dirname(dest_path)
                if _is_same_directory(file_path, dest_path) or _is_same_directory(source_dir, dest_dir):
                    return os.path.normpath(source_dir)
            return None

        for item in self.source_files:
            if not item:
                continue
            if self._source_item_is_folder(item):
                if _is_same_directory(item, output_folder):
                    return os.path.normpath(item)
                predicted_dest = os.path.join(output_folder, os.path.basename(os.path.normpath(item)))
                if _is_same_directory(item, predicted_dest):
                    return os.path.normpath(item)
                continue
            if self._is_archive_source_path(item):
                continue
            source_dir = os.path.dirname(item) or item
            if _is_same_directory(source_dir, output_folder):
                return os.path.normpath(source_dir)
        return None

    def _block_start_if_source_matches_output(
        self,
        output_folder: str,
        resolved_files: Optional[List[str]] = None,
    ) -> bool:
        conflict_dir = self.find_source_output_conflict(output_folder, resolved_files)
        if not conflict_dir:
            return False

        from PyQt6.QtWidgets import QMessageBox

        self._ui_log(
            f"원본 폴더와 출력 폴더가 같아 작업을 시작하지 않습니다: {conflict_dir}",
            "WARNING",
        )
        QMessageBox.warning(
            None,
            self._t("Same Source and Output Directory"),
            self._t(
                "The original image folder and the translated output folder are the same:\n{path}\n\nStarting now would overwrite the original images or mix them with JSON/inpaint work files. Choose a different output folder, then start again.",
                path=conflict_dir,
            ),
        )
        return True

    @pyqtSlot(str)
    def on_worker_log(self, message):
        message = str(message).rstrip()
        if not message:
            return
        self.logger.info(message)

    def _nearest_existing_directory(self, path: str) -> str:
        if not path:
            return ''
        path = os.path.abspath(os.path.expanduser(path))
        current = path if os.path.isdir(path) else os.path.dirname(path)
        while current:
            if os.path.isdir(current):
                return current
            parent = os.path.dirname(current)
            if parent == current:
                break
            current = parent
        return ''

    def _typed_output_folder_text(self) -> str:
        main_view = getattr(self, 'main_view', None)
        input_widget = getattr(main_view, 'output_folder_input', None) if main_view else None
        if input_widget is None:
            return ''
        return (input_widget.text() or '').strip()

    def _normalize_output_folder_path(self, path: str) -> str:
        path = (path or '').strip().strip('"').strip("'").strip()
        if not path:
            return ''
        return os.path.normpath(os.path.abspath(os.path.expanduser(path)))

    def _persist_output_folder_path(self, folder: str) -> None:
        try:
            current = self.config_service.get_config().app.last_output_path or ''
        except Exception:
            current = ''
        if current != folder:
            self.update_single_config('app.last_output_path', folder)
        self.output_path_updated.emit(folder)

    def apply_output_folder_path(self, path: Optional[str] = None) -> str:
        """Use the typed output path as the configured folder. Does not create directories."""
        if path is None:
            path = self._typed_output_folder_text()
        folder = self._normalize_output_folder_path(path) if path else ''
        self._persist_output_folder_path(folder)
        return folder

    @pyqtSlot()
    def apply_output_folder_from_input(self) -> str:
        return self.apply_output_folder_path()

    def _offer_create_output_folder(self, folder: str) -> str:
        """Ask to create a missing output folder. No keeps the typed path and does not create it.

        Returns:
            ready: folder exists as a directory
            declined: user refused to create it
            unavailable: empty, not a directory, or create failed
        """
        if os.path.isdir(folder):
            return 'ready'
        if not folder or os.path.exists(folder):
            return 'unavailable'

        from PyQt6.QtWidgets import QMessageBox

        parent = getattr(self, 'main_view', None)
        reply = QMessageBox.question(
            parent,
            self._t("Create Output Directory"),
            self._t(
                "The output folder does not exist:\n{path}\n\nCreate this folder?",
                path=folder,
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return 'declined'
        try:
            os.makedirs(folder, exist_ok=True)
        except OSError as e:
            self.logger.error(f"Failed to create output folder {folder}: {e}")
            QMessageBox.warning(
                parent,
                self._t("Invalid Output Directory"),
                self._t(
                    "Failed to create output folder:\n{path}\n\n{error}",
                    path=folder,
                    error=e,
                ),
            )
            return 'unavailable'
        return 'ready' if os.path.isdir(folder) else 'unavailable'

    def _current_output_dir_for_dialog(self) -> str:
        candidates = []
        typed = self._typed_output_folder_text()
        if typed:
            candidates.append(typed)
        try:
            configured = (self.config_service.get_config().app.last_output_path or '').strip()
            if configured:
                candidates.append(configured)
        except Exception:
            pass
        for path in candidates:
            existing = self._nearest_existing_directory(path)
            if existing:
                return existing
        return ''

    @pyqtSlot()
    def select_output_folder(self):
        start_dir = self._current_output_dir_for_dialog()
        folder = QFileDialog.getExistingDirectory(
            None,
            self._t("Select Output Directory"),
            start_dir,
        )
        if folder:
            self.apply_output_folder_path(folder)

    @pyqtSlot()
    def open_output_folder(self):
        import subprocess
        import sys
        from PyQt6.QtWidgets import QMessageBox
        output_dir = self.apply_output_folder_path()
        if not output_dir or not os.path.isdir(output_dir):
            self.logger.warning(f"Output path is not a valid directory: {output_dir}")
            parent = getattr(self, 'main_view', None)
            missing_text = self._t("The output folder does not exist.")
            message = f"{output_dir}\n\n{missing_text}" if output_dir else missing_text
            QMessageBox.information(
                parent,
                self._t("Information"),
                message,
            )
            return
        try:
            if sys.platform == "win32":
                os.startfile(os.path.realpath(output_dir))
            elif sys.platform == "darwin":
                subprocess.run(["open", output_dir])
            else:
                subprocess.run(["xdg-open", output_dir])
        except Exception as e:
            self.logger.error(f"Failed to open output folder: {e}")

    def open_font_directory(self):
        import subprocess
        import sys
        # fonts目录在_internal里（打包后）或项目根目录（开发时）
        fonts_dir = os.path.join(self.config_service.root_dir, 'fonts')
        try:
            if not os.path.exists(fonts_dir):
                os.makedirs(fonts_dir)
            if sys.platform == "win32":
                os.startfile(fonts_dir)
            elif sys.platform == "darwin":
                subprocess.run(["open", fonts_dir])
            else:
                subprocess.run(["xdg-open", fonts_dir])
        except Exception as e:
            self.logger.error(f"Error opening font directory: {e}")

    def open_dict_directory(self):
        import subprocess
        import sys
        # dict目录在_internal里（打包后）或项目根目录（开发时）
        dict_dir = os.path.join(self.config_service.root_dir, 'dict')
        try:
            if not os.path.exists(dict_dir):
                os.makedirs(dict_dir)
            if sys.platform == "win32":
                os.startfile(dict_dir)
            elif sys.platform == "darwin":
                subprocess.run(["open", dict_dir])
            else:
                subprocess.run(["xdg-open", dict_dir])
        except Exception as e:
            self.logger.error(f"Error opening dict directory: {e}")

    def get_hq_prompt_options(self) -> List[str]:
        try:
            # dict目录在_internal里（打包后）或项目根目录（开发时）
            dict_dir = os.path.join(self.config_service.root_dir, 'dict')
            if not os.path.isdir(dict_dir):
                return []
            # 系统提示词文件的 stem（不含扩展名），排除这些文件
            system_prompt_stems = {
                'system_prompt_hq',
                'system_prompt_hq_format',
                'system_prompt_line_break',
                'glossary_extraction_prompt',
                'ai_ocr_prompt',
                'ai_colorizer_prompt',
                'ai_renderer_prompt',
            }
            prompt_extensions = ('.yaml', '.yml', '.json')
            prompt_files = sorted([
                f for f in os.listdir(dict_dir)
                if f.lower().endswith(prompt_extensions)
                and os.path.splitext(f)[0] not in system_prompt_stems
            ])
            return prompt_files
        except Exception as e:
            self.logger.error(f"Error scanning prompt directory: {e}")
            return []

    @pyqtSlot(str, str)
    def save_env_var(self, key: str, value: str):
        self.config_service.save_env_var(key, value)
        # 不再输出日志，避免刷屏

    # region 预设管理
    def get_presets_list(self) -> List[str]:
        """获取所有预设名称列表"""
        return self.preset_service.get_presets_list()
    
    @pyqtSlot(str)
    def save_preset(self, preset_name: str, copy_current: bool = False) -> bool:
        """保存预设
        
        Args:
            preset_name: 预设名称
            copy_current: 是否复制当前配置。False=创建空白预设，True=复制当前配置
        """
        try:
            preset_env_keys = self.config_service.get_all_preset_env_vars()
            if copy_current:
                # 复制当前配置模式：保存全部 API 相关的环境变量
                current_env_vars = self.config_service.load_env_vars()
                all_env_vars = {key: current_env_vars.get(key, "") for key in preset_env_keys}
                
                # 保存所有环境变量，包括空值，以准确反映当前配置状态
                success = self.preset_service.save_preset(preset_name, all_env_vars)
                if success:
                    # 不输出日志，避免刷屏
                    pass
            else:
                # 创建空白预设模式：为全部 API 环境变量创建空白结构
                empty_env_vars = {key: "" for key in preset_env_keys}
                
                success = self.preset_service.save_preset(preset_name, empty_env_vars)
                if success:
                    self._ui_log(f"프리셋이 생성되었습니다: {preset_name} (빈 프리셋)")
            
            if not success:
                self._ui_log(f"프리셋 저장 실패: {preset_name}", "ERROR")
            return success
        except Exception as e:
            self.logger.error(f"프리셋 저장 실패: {e}")
            self._ui_log(f"프리셋 저장 실패: {e}", "ERROR")
            return False
    
    @pyqtSlot(str)
    def load_preset(self, preset_name: str) -> bool:
        """加载预设并完全替换.env文件"""
        try:
            # 加载预设文件
            preset_env_vars = self.preset_service.load_preset(preset_name)
            if preset_env_vars is None:
                self._ui_log(f"프리셋 불러오기 실패: {preset_name}", "ERROR")
                return False
            
            # 完全替换.env文件，只保留预设中的字段
            success = self.config_service.replace_env_file(preset_env_vars)
            if not success:
                self._ui_log(f"프리셋 적용 실패: {preset_name}", "ERROR")
            return success
        except Exception as e:
            self.logger.error(f"프리셋 불러오기 실패: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
            self._ui_log(f"프리셋 불러오기 실패: {e}", "ERROR")
            return False
    
    @pyqtSlot(str)
    def delete_preset(self, preset_name: str) -> bool:
        """删除预设"""
        try:
            success = self.preset_service.delete_preset(preset_name)
            if success:
                self._ui_log(f"프리셋이 삭제되었습니다: {preset_name}")
            else:
                self._ui_log(f"프리셋 삭제 실패: {preset_name}", "ERROR")
            return success
        except Exception as e:
            self.logger.error(f"프리셋 삭제 실패: {e}")
            self._ui_log(f"프리셋 삭제 실패: {e}", "ERROR")
            return False
    # endregion
    
    # region API测试
    @staticmethod
    def _normalize_api_test_target(translator_key: str) -> str:
        return (translator_key or "").strip().lower()

    @staticmethod
    def _is_openai_compatible_target(normalized_key: str) -> bool:
        return any(
            token in normalized_key
            for token in ("openai", "custom_openai", "deepseek", "groq")
        )

    @staticmethod
    def _build_api_test_image_bytes() -> bytes:
        buffer = io.BytesIO()
        Image.new("RGB", (50, 50), (255, 255, 255)).save(buffer, format="PNG")
        return buffer.getvalue()

    @staticmethod
    def _extract_gemini_image_bytes(response) -> bytes | None:
        raw = getattr(response, "raw", None) or {}

        def _get_field(obj, *names):
            if obj is None:
                return None
            for name in names:
                if isinstance(obj, dict):
                    if name in obj:
                        return obj[name]
                elif hasattr(obj, name):
                    return getattr(obj, name)
            return None

        candidates = raw.get("candidates") or _get_field(response, "candidates") or []
        for candidate in candidates:
            content = _get_field(candidate, "content") or {}
            parts = _get_field(content, "parts") or []
            for part in parts:
                inline_data = _get_field(part, "inlineData", "inline_data")
                if inline_data is None and hasattr(part, "inline_data"):
                    inline_data = getattr(part, "inline_data")
                data = _get_field(inline_data, "data") if inline_data is not None else None
                if data:
                    return base64.b64decode(data)
        return None

    @staticmethod
    def _get_default_model_for_test(normalized_key: str) -> str | None:
        defaults = {
            "openai_ocr": "gpt-4o",
            "gemini_ocr": "gemini-1.5-flash",
            "openai_colorizer": "gpt-image-1",
            "gemini_colorizer": "gemini-2.0-flash-preview-image-generation",
            "openai_renderer": "gpt-image-1",
            "gemini_renderer": "gemini-2.0-flash-preview-image-generation",
        }
        return defaults.get(normalized_key)

    async def _test_openai_text_api(self, api_key: str, api_base: str | None, model: str | None) -> tuple[bool, str]:
        resolved_api_key = resolve_openai_compatible_api_key(api_key, api_base or "https://api.openai.com/v1")
        try:
            from manga_translator.translators.common import AsyncOpenAICurlCffi
            client = AsyncOpenAICurlCffi(
                api_key=resolved_api_key,
                base_url=api_base or "https://api.openai.com/v1",
                default_headers=_OPENAI_BROWSER_HEADERS,
                impersonate="chrome110",
                timeout=30.0,
                stream_timeout=30.0,
            )
        except ImportError:
            from openai import AsyncOpenAI
            client = AsyncOpenAI(
                api_key=resolved_api_key,
                base_url=api_base or "https://api.openai.com/v1",
                timeout=30.0,
            )

        try:
            if model and model.strip():
                await client.chat.completions.create(
                    model=model.strip(),
                    messages=[{"role": "user", "content": "test"}],
                )
                return True, f"연결 성공, 모델 {model.strip()} 사용 가능"
            await client.models.list()
            return True, "연결 성공"
        finally:
            await client.close()

    async def _test_openai_ocr_api(self, api_key: str, api_base: str | None, model: str | None) -> tuple[bool, str]:
        model_name = (model or "").strip() or self._get_default_model_for_test("openai_ocr")
        image_b64 = base64.b64encode(self._build_api_test_image_bytes()).decode("ascii")
        resolved_api_key = resolve_openai_compatible_api_key(api_key, api_base or "https://api.openai.com/v1")

        try:
            from manga_translator.translators.common import AsyncOpenAICurlCffi
            client = AsyncOpenAICurlCffi(
                api_key=resolved_api_key,
                base_url=api_base or "https://api.openai.com/v1",
                default_headers=_OPENAI_BROWSER_HEADERS,
                impersonate="chrome110",
                timeout=30.0,
                stream_timeout=30.0,
            )
        except ImportError:
            from openai import AsyncOpenAI
            client = AsyncOpenAI(
                api_key=resolved_api_key,
                base_url=api_base or "https://api.openai.com/v1",
                timeout=30.0,
            )

        try:
            await client.chat.completions.create(
                model=model_name,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": "Read the image and reply with OK."},
                            {
                                "type": "image_url",
                                "image_url": {"url": f"data:image/png;base64,{image_b64}"},
                            },
                        ],
                    }
                ],
            )
            return True, f"연결 성공, OCR 모델 {model_name} 사용 가능"
        finally:
            await client.close()

    async def _test_openai_image_api(self, api_key: str, api_base: str | None, model: str | None, target_label: str) -> tuple[bool, str]:
        model_name = (model or "").strip() or self._get_default_model_for_test(target_label)
        resolved_api_key = resolve_openai_compatible_api_key(api_key, api_base or "https://api.openai.com/v1")

        try:
            from manga_translator.translators.common import AsyncOpenAICurlCffi
            from manga_translator.utils.openai_image_interface import (
                request_openai_image_with_fallback,
            )

            client = AsyncOpenAICurlCffi(
                api_key=resolved_api_key,
                base_url=api_base or "https://api.openai.com/v1",
                default_headers=_OPENAI_BROWSER_HEADERS,
                impersonate="chrome110",
                timeout=60.0,
                stream_timeout=60.0,
            )

            async def fetch_remote_image(url: str):
                response = await client.session.get(url, timeout=60.0)
                if response.status_code != 200:
                    raise RuntimeError(f"Failed to download generated image: HTTP {response.status_code}")
                return Image.open(io.BytesIO(response.content)).convert("RGB")

            try:
                await request_openai_image_with_fallback(
                    session=client.session,
                    base_url=(api_base or "https://api.openai.com/v1").rstrip("/"),
                    api_key=resolved_api_key,
                    default_headers=_OPENAI_BROWSER_HEADERS,
                    model_name=model_name,
                    prompt_text="Return a simple test image.",
                    image_bytes=self._build_api_test_image_bytes(),
                    filename="test.png",
                    timeout=60.0,
                    fetch_remote_image=fetch_remote_image,
                    provider_name="OpenAI API Test",
                    logger=self.logger,
                )
                return True, f"연결 성공, 이미지 모델 {model_name} 사용 가능"
            finally:
                await client.close()
        except ImportError:
            from openai import AsyncOpenAI

            client = AsyncOpenAI(
                api_key=resolved_api_key,
                base_url=api_base or "https://api.openai.com/v1",
                timeout=60.0,
            )
            try:
                await client.images.generate(
                    model=model_name,
                    prompt="Generate a simple test image.",
                    size="1024x1024",
                )
                return True, f"연결 성공, 이미지 모델 {model_name} 사용 가능"
            finally:
                await client.close()

    async def _test_gemini_text_api(self, api_key: str, api_base: str | None, model: str | None) -> tuple[bool, str]:
        base_url = api_base.strip() if api_base and api_base.strip() else "https://generativelanguage.googleapis.com"

        try:
            from manga_translator.translators.common import AsyncGeminiCurlCffi
            client = AsyncGeminiCurlCffi(
                api_key=api_key,
                base_url=base_url,
                default_headers=_GEMINI_BROWSER_HEADERS,
                impersonate="chrome110",
                timeout=30.0,
                stream_timeout=30.0,
            )
            try:
                if model and model.strip():
                    await client.models.generate_content(model=model.strip(), contents="test")
                    return True, f"연결 성공, 모델 {model.strip()} 사용 가능"
                await client.models.list()
                return True, "연결 성공"
            finally:
                await client.close()
        except ImportError:
            from google import genai
            from google.genai import types

            def sync_test():
                if base_url != "https://generativelanguage.googleapis.com":
                    client = genai.Client(
                        api_key=api_key,
                        http_options=types.HttpOptions(base_url=base_url),
                    )
                else:
                    client = genai.Client(api_key=api_key)

                if model and model.strip():
                    client.models.generate_content(model=model.strip(), contents="test")
                    return True, f"연결 성공, 모델 {model.strip()} 사용 가능"
                list(client.models.list())
                return True, "연결 성공"

            return await asyncio.get_running_loop().run_in_executor(None, sync_test)

    async def _test_gemini_ocr_api(self, api_key: str, api_base: str | None, model: str | None) -> tuple[bool, str]:
        model_name = (model or "").strip() or self._get_default_model_for_test("gemini_ocr")
        base_url = api_base.strip() if api_base and api_base.strip() else "https://generativelanguage.googleapis.com"
        image_b64 = base64.b64encode(self._build_api_test_image_bytes()).decode("ascii")
        contents = [
            {
                "role": "user",
                "parts": [
                    {"text": "Read the image and reply with OK."},
                    {"inlineData": {"mimeType": "image/png", "data": image_b64}},
                ],
            }
        ]

        try:
            from manga_translator.translators.common import AsyncGeminiCurlCffi
            client = AsyncGeminiCurlCffi(
                api_key=api_key,
                base_url=base_url,
                default_headers=_GEMINI_BROWSER_HEADERS,
                impersonate="chrome110",
                timeout=30.0,
                stream_timeout=30.0,
            )
            try:
                await client.models.generate_content(model=model_name, contents=contents)
                return True, f"연결 성공, OCR 모델 {model_name} 사용 가능"
            finally:
                await client.close()
        except ImportError:
            from google import genai
            from google.genai import types

            def sync_test():
                if base_url != "https://generativelanguage.googleapis.com":
                    client = genai.Client(
                        api_key=api_key,
                        http_options=types.HttpOptions(base_url=base_url),
                    )
                else:
                    client = genai.Client(api_key=api_key)
                client.models.generate_content(model=model_name, contents=contents)
                return True, f"연결 성공, OCR 모델 {model_name} 사용 가능"

            return await asyncio.get_running_loop().run_in_executor(None, sync_test)

    async def _test_gemini_image_api(self, api_key: str, api_base: str | None, model: str | None, target_label: str) -> tuple[bool, str]:
        model_name = (model or "").strip() or self._get_default_model_for_test(target_label)
        base_url = api_base.strip() if api_base and api_base.strip() else "https://generativelanguage.googleapis.com"
        image_b64 = base64.b64encode(self._build_api_test_image_bytes()).decode("ascii")
        request_kwargs = {
            "model": model_name,
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {"text": "Return a simple test image."},
                        {"inlineData": {"mimeType": "image/png", "data": image_b64}},
                    ],
                }
            ],
            "generationConfig": {"responseModalities": ["TEXT", "IMAGE"]},
            "safetySettings": [
                {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "OFF"},
                {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "OFF"},
                {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "OFF"},
                {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "OFF"},
            ],
        }

        try:
            from manga_translator.translators.common import AsyncGeminiCurlCffi
            client = AsyncGeminiCurlCffi(
                api_key=api_key,
                base_url=base_url,
                default_headers=_GEMINI_BROWSER_HEADERS,
                impersonate="chrome110",
                timeout=60.0,
                stream_timeout=60.0,
            )
            try:
                response = await client.models.generate_content(**request_kwargs)
                if not self._extract_gemini_image_bytes(response):
                    raise RuntimeError("Gemini image response did not contain an image.")
                return True, f"연결 성공, 이미지 모델 {model_name} 사용 가능"
            finally:
                await client.close()
        except ImportError:
            from google import genai
            from google.genai import types

            def sync_test():
                if base_url != "https://generativelanguage.googleapis.com":
                    client = genai.Client(
                        api_key=api_key,
                        http_options=types.HttpOptions(base_url=base_url),
                    )
                else:
                    client = genai.Client(api_key=api_key)
                response = client.models.generate_content(
                    model=model_name,
                    contents=request_kwargs["contents"],
                    config=types.GenerateContentConfig(
                        response_modalities=["TEXT", "IMAGE"],
                        safety_settings=[
                            types.SafetySetting(category=item["category"], threshold=item["threshold"])
                            for item in request_kwargs["safetySettings"]
                        ],
                    ),
                )
                if not self._extract_gemini_image_bytes(response):
                    raise RuntimeError("Gemini image response did not contain an image.")
                return True, f"연결 성공, 이미지 모델 {model_name} 사용 가능"

            return await asyncio.get_running_loop().run_in_executor(None, sync_test)

    async def test_api_connection_async(self, translator_key: str, api_key: str, api_base: str = None, model: str = None) -> tuple[bool, str]:
        """异步测试API连接（如果指定了模型，会测试该模型是否可用）"""
        try:
            normalized_key = self._normalize_api_test_target(translator_key)

            if normalized_key == "openai_ocr":
                return await self._test_openai_ocr_api(api_key, api_base, model)
            if normalized_key in {"openai_colorizer", "openai_renderer"}:
                return await self._test_openai_image_api(api_key, api_base, model, normalized_key)
            if normalized_key == "gemini_ocr":
                return await self._test_gemini_ocr_api(api_key, api_base, model)
            if normalized_key in {"gemini_colorizer", "gemini_renderer"}:
                return await self._test_gemini_image_api(api_key, api_base, model, normalized_key)
            if self._is_openai_compatible_target(normalized_key):
                return await self._test_openai_text_api(api_key, api_base, model)
            if "gemini" in normalized_key:
                return await self._test_gemini_text_api(api_key, api_base, model)
            if "sakura" in normalized_key:
                # Sakura使用OpenAI兼容API
                from openai import AsyncOpenAI
                if not api_base:
                    return False, "먼저 SAKURA_API_BASE를 설정하세요"
                client = AsyncOpenAI(
                    api_key="sk-114514",  # Sakura使用固定密钥
                    base_url=api_base
                )
                
                try:
                    # 如果指定了模型，测试该模型
                    if model and model.strip():
                        try:
                            # 不传递 max_tokens 以兼容所有模型
                            await client.chat.completions.create(
                                model=model,
                                messages=[{"role": "user", "content": "test"}]
                            )
                            return True, f"연결 성공, 모델 {model} 사용 가능"
                        except Exception as e:
                            return False, f"연결은 되었지만 모델 {model}을(를) 사용할 수 없습니다: {str(e)}"
                    else:
                        await client.models.list()
                        return True, "연결 성공"
                finally:
                    await client.close()
            
            else:
                return False, "이 번역기는 API 테스트를 지원하지 않습니다"
                
        except Exception as e:
            return False, f"연결 실패: {str(e)}"
    
    async def get_available_models_async(self, translator_key: str, api_key: str, api_base: str = None) -> tuple[bool, List[str], str]:
        """异步获取可用模型列表"""
        try:
            normalized_key = self._normalize_api_test_target(translator_key)

            if self._is_openai_compatible_target(normalized_key):
                resolved_api_key = resolve_openai_compatible_api_key(api_key, api_base or "https://api.openai.com/v1")
                # 尝试使用 curl_cffi 客户端绕过 TLS 指纹检测
                try:
                    from manga_translator.translators.common import AsyncOpenAICurlCffi
                    client = AsyncOpenAICurlCffi(
                        api_key=resolved_api_key,
                        base_url=api_base or "https://api.openai.com/v1",
                        impersonate="chrome110",
                        timeout=60.0
                    )
                except ImportError:
                    from openai import AsyncOpenAI
                    client = AsyncOpenAI(
                        api_key=resolved_api_key,
                        base_url=api_base or "https://api.openai.com/v1",
                        timeout=60.0,
                    )
                
                try:
                    models_response = await client.models.list()
                    
                    # 获取所有模型ID，不过滤
                    model_ids = [m.id for m in models_response.data]
                    model_ids.sort(reverse=True)  # 新模型在前
                    
                    return True, model_ids, "가져오기 성공"
                finally:
                    await client.close()
            
            elif "gemini" in normalized_key:
                # Gemini API - 使用 curl_cffi 绕过 TLS 指纹检测，使用 Google Gemini 认证格式
                try:
                    from manga_translator.translators.common import AsyncGeminiCurlCffi

                    # 确定 base_url
                    base_url = api_base.strip() if api_base and api_base.strip() else "https://generativelanguage.googleapis.com"

                    client = AsyncGeminiCurlCffi(
                        api_key=api_key,
                        base_url=base_url,
                        impersonate="chrome110",
                        timeout=60.0
                    )
                    try:
                        models_response = await client.models.list()
                        model_ids = [m.id for m in models_response]
                        return True, model_ids, "가져오기 성공"
                    finally:
                        await client.close()
                except ImportError:
                    # 如果 curl_cffi 不可用，回退到标准客户端
                    import asyncio

                    from google import genai
                    from google.genai import types
                    loop = asyncio.get_event_loop()

                    # 检查是否是自定义API
                    is_custom_api = (
                        api_base
                        and api_base.strip()
                        and api_base.strip() not in ["https://generativelanguage.googleapis.com", "https://generativelanguage.googleapis.com/"]
                    )

                    if is_custom_api:
                        # 自定义 API 使用 http_options
                        def sync_get_models():
                            client = genai.Client(
                                api_key=api_key,
                                http_options=types.HttpOptions(base_url=api_base.strip())
                            )
                            models = list(client.models.list())
                            model_names = [m.name.replace("models/", "") for m in models]
                            return True, model_names, "가져오기 성공"
                    else:
                        def sync_get_models():
                            client = genai.Client(api_key=api_key)
                            models = list(client.models.list())
                            model_names = [m.name.replace("models/", "") for m in models]
                            return True, model_names, "가져오기 성공"

                    return await loop.run_in_executor(None, sync_get_models)
            
            elif "sakura" in normalized_key:
                # Sakura使用OpenAI兼容API
                from openai import AsyncOpenAI
                if not api_base:
                    return False, [], "먼저 SAKURA_API_BASE를 설정하세요"
                client = AsyncOpenAI(
                    api_key="sk-114514",
                    base_url=api_base
                )
                try:
                    models_response = await client.models.list()
                    model_ids = [m.id for m in models_response.data]
                    return True, model_ids, "가져오기 성공"
                finally:
                    await client.close()
            
            else:
                return False, [], "이 번역기는 모델 목록 조회를 지원하지 않습니다"
                
        except Exception as e:
            return False, [], f"가져오기 실패: {str(e)}"
    # endregion

    # region 配置管理
    def load_config_file(self, config_path: str) -> bool:
        try:
            success = self.config_service.load_config_file(config_path)
            if success:
                config = self.config_service.get_config()
                self.state_manager.set_current_config(config)
                self.state_manager.set_state(AppStateKey.CONFIG_PATH, config_path)
                self.logger.info(self._t("log_config_loaded_successfully", path=config_path))
                self.config_loaded.emit(config.model_dump())
                if config.app.last_output_path:
                    self.output_path_updated.emit(config.app.last_output_path)
                return True
            else:
                self.logger.error(self._t("log_config_load_failed", path=config_path))
                return False
        except Exception as e:
            self.logger.error(self._t("log_config_load_exception", error=e))
            return False
    
    def save_config_file(self, config_path: str = None) -> bool:
        try:
            success = self.config_service.save_config_file(config_path)
            if success:
                self.logger.info(self._t("log_config_saved_successfully"))
                return True
            return False
        except Exception as e:
            self.logger.error(self._t("log_config_save_exception", error=e))
            return False
    
    def update_config(self, config_updates: Dict[str, Any]) -> bool:
        try:
            self.config_service.update_config(config_updates)
            updated_config = self.config_service.get_config()
            self.state_manager.set_current_config(updated_config)
            self.logger.info(self._t("log_config_updated_successfully"))
            return True
        except Exception as e:
            self.logger.error(self._t("log_config_update_exception", error=e))
            return False

    def update_single_config(self, full_key: str, value: Any):
        self.logger.debug(f"update_single_config: '{full_key}' = '{value}'")
        try:
            config_obj = self.config_service.get_config()
            keys = full_key.split('.')
            parent_obj = config_obj
            for key in keys[:-1]:
                parent_obj = getattr(parent_obj, key)
            setattr(parent_obj, keys[-1], value)
            
            self.config_service.set_config(config_obj)
            self.config_service.save_config_file()
            self.logger.debug(self._t("log_config_saved", config_key=full_key, value=value))

            # 当翻译器设置被更改时，直接更新翻译服务的内部状态
            if full_key == 'translator.translator':
                self.logger.debug(self._t("log_translator_switched", value=value))
                self.translation_service.set_translator(value)
            
            # 当目标语言被更改时，更新翻译服务的目标语言
            if full_key == 'translator.target_lang':
                self.logger.debug(f"Target language switched to: {value}")
                self.translation_service.set_target_language(value)

            # 当渲染设置被更改时，通知编辑器刷新
            if full_key.startswith('render.'):
                self.logger.debug(self._t("log_render_setting_changed", config_key=full_key))
                self.render_setting_changed.emit()

        except Exception as e:
            self.logger.error(f"Error saving single config change for {full_key}: {e}")
    # endregion

    # region UI数据提供
    def get_display_mapping(self, key: str) -> Optional[Dict[str, str]]:
        # 每次都动态生成翻译映射，确保语言切换时能正确更新
        display_name_maps = {
            "overwrite": {
                OVERWRITE_ASK: self._t("overwrite_ask"),
                OVERWRITE_ALWAYS: self._t("overwrite_always"),
                OVERWRITE_SKIP: self._t("overwrite_skip"),
            },
            "alignment": {
                "auto": self._t("alignment_auto"),
                "left": self._t("alignment_left"),
                "center": self._t("alignment_center"),
                "right": self._t("alignment_right")
            },
            "direction": {
                "auto": self._t("direction_auto"),
                "h": self._t("direction_horizontal"),
                "v": self._t("direction_vertical")
            },
            "upscaler": {
                "waifu2x": "Waifu2x",
                "esrgan": "ESRGAN",
                "4xultrasharp": "4x UltraSharp",
                "realcugan": "Real-CUGAN",
                "mangajanai": "MangaJaNai"
            },
            "renderer": {
                "default": "Default",
                "openai_renderer": "OpenAI Renderer",
                "gemini_renderer": "Gemini Renderer",
                "none": self._t("translator_none"),
            },
            "colorizer": {
                "none": self._t("translator_none"),
                "mc2": "Manga Colorization v2",
                "openai_colorizer": "OpenAI Colorizer",
                "gemini_colorizer": "Gemini Colorizer",
            },
            "layout_mode": {
                'smart_scaling': self._t("layout_mode_smart_scaling"),
                'strict': self._t("layout_mode_strict"),
                'balloon_fill': self._t("layout_mode_balloon_fill")
            },
                "realcugan_model": {
                    "2x-conservative": self._t("realcugan_2x_conservative"),
                    "2x-conservative-pro": self._t("realcugan_2x_conservative_pro"),
                    "2x-no-denoise": self._t("realcugan_2x_no_denoise"),
                    "2x-denoise1x": self._t("realcugan_2x_denoise1x"),
                    "2x-denoise2x": self._t("realcugan_2x_denoise2x"),
                    "2x-denoise3x": self._t("realcugan_2x_denoise3x"),
                    "2x-denoise3x-pro": self._t("realcugan_2x_denoise3x_pro"),
                    "3x-conservative": self._t("realcugan_3x_conservative"),
                    "3x-conservative-pro": self._t("realcugan_3x_conservative_pro"),
                    "3x-no-denoise": self._t("realcugan_3x_no_denoise"),
                    "3x-no-denoise-pro": self._t("realcugan_3x_no_denoise_pro"),
                    "3x-denoise3x": self._t("realcugan_3x_denoise3x"),
                    "3x-denoise3x-pro": self._t("realcugan_3x_denoise3x_pro"),
                    "4x-conservative": self._t("realcugan_4x_conservative"),
                    "4x-no-denoise": self._t("realcugan_4x_no_denoise"),
                    "4x-denoise3x": self._t("realcugan_4x_denoise3x"),
                },
                "translator": {
                    "openai": "OpenAI",
                    "openai_hq": self._t("translator_openai_hq"),
                    "gemini": "Google Gemini",
                    "gemini_hq": self._t("translator_gemini_hq"),
                    "sakura": "Sakura",
                    "none": self._t("translator_none"),
                    "original": self._t("translator_original"),
                },
                "target_lang": self.translation_service.get_target_languages(),
                "keep_lang": {
                    "none": self._t("lang_filter_disabled"),
                    **self.translation_service.get_keep_languages(),
                },
                "novelai_ocr": {
                    "none": self._t("ocr_override_none"),
                    **{member.value: member.value for member in Ocr},
                },
                "novelai_secondary_ocr": {
                    "none": self._t("ocr_override_none"),
                    **{member.value: member.value for member in Ocr},
                },
                "ocr_vl_language_hint": {
                    "auto": self._t("ocr_lang_auto"),
                    "multilingual": self._t("ocr_lang_multilingual"),
                    "Arabic": self._t("ocr_lang_arabic"),
                    "Simplified Chinese": self._t("ocr_lang_simplified_chinese"),
                    "Traditional Chinese": self._t("ocr_lang_traditional_chinese"),
                    "English": self._t("ocr_lang_english"),
                    "Japanese": self._t("ocr_lang_japanese"),
                    "Korean": self._t("ocr_lang_korean"),
                    "Spanish": self._t("ocr_lang_spanish"),
                    "French": self._t("ocr_lang_french"),
                    "German": self._t("ocr_lang_german"),
                    "Russian": self._t("ocr_lang_russian"),
                    "Portuguese": self._t("ocr_lang_portuguese"),
                    "Italian": self._t("ocr_lang_italian"),
                    "Thai": self._t("ocr_lang_thai"),
                    "Vietnamese": self._t("ocr_lang_vietnamese"),
                    "Indonesian": self._t("ocr_lang_indonesian"),
                    "Turkish": self._t("ocr_lang_turkish"),
                    "Polish": self._t("ocr_lang_polish"),
                    "Ukrainian": self._t("ocr_lang_ukrainian"),
                },
                "novelai_ocr_vl_language_hint": {
                    "none": self._t("ocr_override_none"),
                    "auto": self._t("ocr_lang_auto"),
                    "multilingual": self._t("ocr_lang_multilingual"),
                    "Arabic": self._t("ocr_lang_arabic"),
                    "Simplified Chinese": self._t("ocr_lang_simplified_chinese"),
                    "Traditional Chinese": self._t("ocr_lang_traditional_chinese"),
                    "English": self._t("ocr_lang_english"),
                    "Japanese": self._t("ocr_lang_japanese"),
                    "Korean": self._t("ocr_lang_korean"),
                    "Spanish": self._t("ocr_lang_spanish"),
                    "French": self._t("ocr_lang_french"),
                    "German": self._t("ocr_lang_german"),
                    "Russian": self._t("ocr_lang_russian"),
                    "Portuguese": self._t("ocr_lang_portuguese"),
                    "Italian": self._t("ocr_lang_italian"),
                    "Thai": self._t("ocr_lang_thai"),
                    "Vietnamese": self._t("ocr_lang_vietnamese"),
                    "Indonesian": self._t("ocr_lang_indonesian"),
                    "Turkish": self._t("ocr_lang_turkish"),
                    "Polish": self._t("ocr_lang_polish"),
                    "Ukrainian": self._t("ocr_lang_ukrainian"),
                },
                "labels": {
                    "filter_text_enabled": self._t("label_filter_text_enabled"),
                    "kernel_size": self._t("label_kernel_size"),
                    "mask_dilation_offset": self._t("label_mask_dilation_offset"),
                    "bubble_mask_dilation_offset": self._t("label_bubble_mask_dilation_offset"),
                    "inpaint_to_overlay_dilation_offset": self._t("label_inpaint_to_overlay_dilation_offset"),
                    "translator": self._t("label_translator"),
                    "target_lang": self._t("label_target_lang"),
                    "keep_lang": self._t("label_keep_lang"),
                    "enable_streaming": self._t("label_enable_streaming"),
                    "no_text_lang_skip": self._t("label_no_text_lang_skip"),
                    "high_quality_prompt_path": self._t("label_high_quality_prompt_path"),
                    "extract_glossary": self._t("label_extract_glossary"),
                    "remove_trailing_period": self._t("label_remove_trailing_period"),
                    "convert_to_traditional": self._t("label_convert_to_traditional"),
                    "convert_to_simplified": self._t("label_convert_to_simplified"),
                    "use_custom_api_params": self._t("label_use_custom_api_params"),
                    "ocr": self._t("label_ocr"),
                    "use_hybrid_ocr": self._t("label_use_hybrid_ocr"),
                    "secondary_ocr": self._t("label_secondary_ocr"),
                    "novelai_ocr": self._t("label_novelai_ocr"),
                    "novelai_secondary_ocr": self._t("label_novelai_secondary_ocr"),
                    "novelai_ocr_vl_language_hint": self._t("label_novelai_ocr_vl_language_hint"),
                    "min_text_length": self._t("label_min_text_length"),
                    "ignore_bubble": self._t("label_ignore_bubble"),
                    "use_model_bubble_filter": self._t("label_use_model_bubble_filter"),
                    "model_bubble_overlap_threshold": self._t("label_model_bubble_overlap_threshold"),
                    "use_model_bubble_repair_intersection": self._t("label_use_model_bubble_repair_intersection"),
                    "limit_mask_dilation_to_bubble_mask": self._t("label_limit_mask_dilation_to_bubble_mask"),
                    "prob": self._t("label_prob"),
                    "merge_gamma": self._t("label_merge_gamma"),
                    "merge_sigma": self._t("label_merge_sigma"),
                    "merge_edge_ratio_threshold": self._t("label_merge_edge_ratio_threshold"),
                    "merge_special_require_full_wrap": self._t("label_merge_special_require_full_wrap"),
                    "ai_ocr_concurrency": self._t("label_ai_ocr_concurrency"),
                    "ai_ocr_custom_prompt": self._t("label_ai_ocr_custom_prompt"),
                    "ocr_vl_language_hint": self._t("label_ocr_vl_language_hint"),
                    "ocr_vl_custom_prompt": self._t("label_ocr_vl_custom_prompt"),
                    "detector": self._t("label_detector"),
                    "detection_size": self._t("label_detection_size"),
                    "text_threshold": self._t("label_text_threshold"),
                    "import_yolo_labels": self._t("label_import_yolo_labels"),
                    "use_yolo_obb": self._t("label_use_yolo_obb"),
                    "yolo_obb_conf": self._t("label_yolo_obb_conf"),
                    "yolo_obb_overlap_threshold": self._t("label_yolo_obb_overlap_threshold"),
                    "box_threshold": self._t("label_box_threshold"),
                    "unclip_ratio": self._t("label_unclip_ratio"),
                    "min_box_area_ratio": self._t("label_min_box_area_ratio"),
                    "inpainter": self._t("label_inpainter"),
                    "inpainting_size": self._t("label_inpainting_size"),
                    "inpainting_precision": self._t("label_inpainting_precision"),
                    "force_use_torch_inpainting": self._t("label_force_use_torch_inpainting"),
                    "renderer": self._t("label_renderer"),
                    "alignment": self._t("label_alignment"),
                    "disable_font_border": self._t("label_disable_font_border"),
                    "disable_auto_wrap": self._t("label_disable_auto_wrap"),
                    "font_size_offset": self._t("label_font_size_offset"),
                    "font_size_minimum": self._t("label_font_size_minimum"),
                    "max_font_size": self._t("label_max_font_size"),
                    "font_scale_ratio": self._t("label_font_scale_ratio"),
                    "stroke_width": self._t("label_stroke_width"),
                    "center_text_in_bubble": self._t("label_center_text_in_bubble"),
                    "optimize_line_breaks": self._t("label_optimize_line_breaks"),
                    "check_br_and_retry": self._t("label_check_br_and_retry"),
                    "strict_smart_scaling": self._t("label_strict_smart_scaling"),
                    "enable_template_alignment": self._t("label_enable_template_alignment"),
                    "paste_mask_dilation_pixels": self._t("label_paste_mask_dilation_pixels"),
                    "ai_renderer_concurrency": self._t("label_ai_renderer_concurrency"),
                    "direction": self._t("label_direction"),
                    "uppercase": self._t("label_uppercase"),
                    "lowercase": self._t("label_lowercase"),
                    "font_family": self._t("label_font_family"),
                    "disable_system_fonts": self._t("label_disable_system_fonts"),
                    "no_hyphenation": self._t("label_no_hyphenation"),
                    "bubble_layout_english": self._t("label_bubble_layout_english"),
                    "font_color": self._t("label_font_color"),
                    "auto_rotate_symbols": self._t("label_auto_rotate_symbols"),
                    "rtl": self._t("label_rtl"),
                    "layout_mode": self._t("label_layout_mode"),
                    "upscaler": self._t("label_upscaler"),
                    "upscale_ratio": self._t("label_upscale_ratio"),
                    "realcugan_model": self._t("label_realcugan_model"),
                    "tile_size": self._t("label_tile_size"),
                    "revert_upscaling": self._t("label_revert_upscaling"),
                    "colorization_size": self._t("label_colorization_size"),
                    "denoise_sigma": self._t("label_denoise_sigma"),
                    "colorizer": self._t("label_colorizer"),
                    "ai_colorizer_history_pages": self._t("label_ai_colorizer_history_pages"),
                    "verbose": self._t("label_verbose"),
                    "attempts": self._t("label_attempts"),
                    "max_requests_per_minute": self._t("label_max_requests_per_minute"),
                    "ignore_errors": self._t("label_ignore_errors"),
                    "use_gpu": self._t("label_use_gpu"),
                    "disable_onnx_gpu": self._t("label_disable_onnx_gpu"),
                    "context_size": self._t("label_context_size"),
                    "format": self._t("label_format"),
                    "overwrite": self._t("label_overwrite"),
                    "skip_no_text": self._t("label_skip_no_text"),
                    "save_text": self._t("label_save_text"),
                    "load_text": self._t("label_load_text"),
                    "rerender_only": self._t("label_rerender_only"),
                    "translate_json_only": self._t("label_translate_json_only"),
                    "template": self._t("label_template"),
                    "save_quality": self._t("label_save_quality"),
                    "batch_size": self._t("label_batch_size"),
                    "batch_concurrent": self._t("label_batch_concurrent"),
                    "generate_and_export": self._t("label_generate_and_export"),
                    "combine_txt": self._t("label_combine_txt"),
                    "backup_combined_txt": self._t("label_backup_combined_txt"),
                    "write_txt_help": self._t("label_write_txt_help"),
                    "export_editable_psd": self._t("label_export_editable_psd"),
                    "last_output_path": self._t("label_last_output_path"),
                    "save_to_source_dir": self._t("label_save_to_source_dir"),
                    "show_colorize_upscale_inpaint_modes": self._t("label_show_colorize_upscale_inpaint_modes"),
                    "show_novelai_mode": self._t("label_show_novelai_mode"),
                    "psd_font": self._t("label_psd_font"),
                    "psd_launch_photoshop": self._t("label_psd_launch_photoshop"),
                    "line_spacing": self._t("label_line_spacing"),
                    "letter_spacing": self._t("label_letter_spacing"),
                    "char_width": self._t("label_char_width"),
                    "font_size": self._t("label_font_size"),
                    "OPENAI_API_KEY": self._t("label_OPENAI_API_KEY"),
                    "OPENAI_MODEL": self._t("label_OPENAI_MODEL"),
                    "OPENAI_API_BASE": self._t("label_OPENAI_API_BASE"),
                    "OPENAI_GLOSSARY_PATH": self._t("label_OPENAI_GLOSSARY_PATH"),
                    "GEMINI_API_KEY": self._t("label_GEMINI_API_KEY"),
                    "GEMINI_MODEL": self._t("label_GEMINI_MODEL"),
                    "GEMINI_API_BASE": self._t("label_GEMINI_API_BASE"),
                    "OCR_OPENAI_API_KEY": self._t("label_OCR_OPENAI_API_KEY"),
                    "OCR_OPENAI_MODEL": self._t("label_OCR_OPENAI_MODEL"),
                    "OCR_OPENAI_API_BASE": self._t("label_OCR_OPENAI_API_BASE"),
                    "OCR_GEMINI_API_KEY": self._t("label_OCR_GEMINI_API_KEY"),
                    "OCR_GEMINI_MODEL": self._t("label_OCR_GEMINI_MODEL"),
                    "OCR_GEMINI_API_BASE": self._t("label_OCR_GEMINI_API_BASE"),
                    "COLOR_OPENAI_API_KEY": self._t("label_COLOR_OPENAI_API_KEY"),
                    "COLOR_OPENAI_MODEL": self._t("label_COLOR_OPENAI_MODEL"),
                    "COLOR_OPENAI_API_BASE": self._t("label_COLOR_OPENAI_API_BASE"),
                    "COLOR_GEMINI_API_KEY": self._t("label_COLOR_GEMINI_API_KEY"),
                    "COLOR_GEMINI_MODEL": self._t("label_COLOR_GEMINI_MODEL"),
                    "COLOR_GEMINI_API_BASE": self._t("label_COLOR_GEMINI_API_BASE"),
                    "RENDER_OPENAI_API_KEY": self._t("label_RENDER_OPENAI_API_KEY"),
                    "RENDER_OPENAI_MODEL": self._t("label_RENDER_OPENAI_MODEL"),
                    "RENDER_OPENAI_API_BASE": self._t("label_RENDER_OPENAI_API_BASE"),
                    "RENDER_GEMINI_API_KEY": self._t("label_RENDER_GEMINI_API_KEY"),
                    "RENDER_GEMINI_MODEL": self._t("label_RENDER_GEMINI_MODEL"),
                    "RENDER_GEMINI_API_BASE": self._t("label_RENDER_GEMINI_API_BASE"),
                    "SAKURA_API_BASE": self._t("label_SAKURA_API_BASE"),
                    "SAKURA_DICT_PATH": self._t("label_SAKURA_DICT_PATH"),
                    "CUSTOM_OPENAI_API_BASE": self._t("label_CUSTOM_OPENAI_API_BASE"),
                    "CUSTOM_OPENAI_MODEL": self._t("label_CUSTOM_OPENAI_MODEL"),
                    "CUSTOM_OPENAI_API_KEY": self._t("label_CUSTOM_OPENAI_API_KEY"),
                    "CUSTOM_OPENAI_MODEL_CONF": self._t("label_CUSTOM_OPENAI_MODEL_CONF")
                }
            }
        return display_name_maps.get(key)

    def get_options_for_key(self, key: str) -> Optional[List[str]]:
        options_map = {
            "overwrite": [OVERWRITE_ASK, OVERWRITE_ALWAYS, OVERWRITE_SKIP],
            "format": [self._t("format_not_specified")] + [fmt for fmt in OUTPUT_FORMATS.keys() if fmt not in ['xcf', 'psd', 'pdf']],
            "renderer": [member.value for member in Renderer],
            "alignment": [member.value for member in Alignment],
            "direction": [member.value for member in Direction],
            "upscaler": [member.value for member in Upscaler],
            "upscale_ratio": [self._t("upscale_ratio_not_use"), "2", "3", "4"],
            "realcugan_model": [
                "2x-conservative",
                "2x-conservative-pro",
                "2x-no-denoise",
                "2x-denoise1x",
                "2x-denoise2x",
                "2x-denoise3x",
                "2x-denoise3x-pro",
                "3x-conservative",
                "3x-conservative-pro",
                "3x-no-denoise",
                "3x-no-denoise-pro",
                "3x-denoise3x",
                "3x-denoise3x-pro",
                "4x-conservative",
                "4x-no-denoise",
                "4x-denoise3x",
            ],
            "translator": [member.value for member in Translator],
            "keep_lang": ["none"] + list(self.translation_service.get_keep_languages().keys()),
            "detector": [member.value for member in Detector],
            "colorizer": [member.value for member in Colorizer],
            "inpainter": [member.value for member in Inpainter],
            "inpainting_precision": [member.value for member in InpaintPrecision],
            "ocr": [member.value for member in Ocr],
            "secondary_ocr": [member.value for member in Ocr],
            "novelai_ocr": ["none"] + [member.value for member in Ocr],
            "novelai_secondary_ocr": ["none"] + [member.value for member in Ocr],
            "ocr_vl_language_hint": [
                "auto",
                "multilingual",
                "Arabic",
                "Simplified Chinese",
                "Traditional Chinese",
                "English",
                "Japanese",
                "Korean",
                "Spanish",
                "French",
                "German",
                "Russian",
                "Portuguese",
                "Italian",
                "Thai",
                "Vietnamese",
                "Indonesian",
                "Turkish",
                "Polish",
                "Ukrainian",
            ],
            "novelai_ocr_vl_language_hint": [
                "none",
                "auto",
                "multilingual",
                "Arabic",
                "Simplified Chinese",
                "Traditional Chinese",
                "English",
                "Japanese",
                "Korean",
                "Spanish",
                "French",
                "German",
                "Russian",
                "Portuguese",
                "Italian",
                "Thai",
                "Vietnamese",
                "Indonesian",
                "Turkish",
                "Polish",
                "Ukrainian",
            ],
        }
        return options_map.get(key)
    @pyqtSlot()
    def export_config(self):
        """导出配置（排除敏感信息）"""
        import json

        from PyQt6.QtWidgets import QFileDialog, QMessageBox
        
        try:
            # 选择保存位置
            file_path, _ = QFileDialog.getSaveFileName(
                None,
                self._t("Export Config"),
                "manga_translator_config.json",
                "JSON Files (*.json)"
            )
            
            if not file_path:
                return
            
            # 获取当前配置
            config = self.config_service.get_config()
            config_dict = config.model_dump()
            
            # 排除敏感信息和临时状态
            # 1. 排除 app 配置（包含路径等临时信息）
            if 'app' in config_dict:
                del config_dict['app']
            
            # 2. 排除 CLI 中的临时状态
            if 'cli' in config_dict:
                # 保留 CLI 配置，但排除某些临时字段
                cli_exclude = ['verbose']  # 可以根据需要添加更多
                for key in cli_exclude:
                    if key in config_dict['cli']:
                        del config_dict['cli'][key]
            
            # 保存到文件
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(config_dict, f, indent=2, ensure_ascii=False)
            
            self.logger.info(self._t("log_config_exported", path=file_path))
            QMessageBox.information(
                None,
                self._t("Export Success"),
                self._t("Config exported successfully to:\n{path}\n\nNote: Sensitive information like API keys are not included.", path=file_path)
            )
            
        except Exception as e:
            self.logger.error(self._t("log_config_export_failed", error=e))
            QMessageBox.critical(
                None,
                self._t("Export Failed"),
                self._t("Error occurred while exporting config:\n{error}", error=str(e))
            )
    
    @pyqtSlot()
    def import_config(self):
        """Import user files from a previous translator folder."""
        from PyQt6.QtWidgets import QDialog, QMessageBox

        from ui.secondary_pages.settings_import_dialog import SettingsImportDialog
        from ui.secondary_pages.themed_message_box import themed_information, themed_warning

        parent = getattr(self, "main_view", None)
        if self.state_manager.is_translating():
            themed_warning(
                parent,
                self._t("Import Config"),
                self._t("import_settings_busy"),
            )
            return

        dialog = SettingsImportDialog(
            parent,
            t_func=self._t,
            config_service=self.config_service,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        result = dialog.imported_result()
        source_path = dialog.source_path()
        if result is None:
            return

        try:
            self._apply_imported_settings(result.copied_item_ids)
        except Exception as e:
            self.logger.error(self._t("log_config_import_failed", error=e))
            QMessageBox.critical(
                parent,
                self._t("Import Failed"),
                self._t(
                    "Error occurred while importing config:\n{error}\n\nPlease ensure the file format is correct.",
                    error=str(e),
                ),
            )
            return

        self.logger.info(self._t("log_config_imported", path=source_path))
        summary = self._t(
            "import_settings_success",
            path=source_path,
            count=result.copied,
        )
        if result.errors:
            summary = (
                f"{summary}\n\n"
                + self._t(
                    "import_settings_partial_errors",
                    error="\n".join(result.errors[:8]),
                )
            )
        themed_information(parent, self._t("Import Success"), summary)

    def _apply_imported_settings(self, copied_item_ids: list[str]) -> None:
        copied = set(copied_item_ids or [])
        main_view = getattr(self, "main_view", None)
        if main_view is not None and hasattr(main_view, "_env_debounce_timer"):
            main_view._env_debounce_timer.stop()

        if "config" in copied or "env" in copied:
            self.config_service.reload_config()
            config = self.config_service.get_config()
            self.config_loaded.emit(config.model_dump())
        elif copied:
            self.config_service.reload_config()

        if "text_rules" in copied:
            try:
                from manga_translator.utils.text_filter import load_filter_list

                load_filter_list(force_reload=True)
            except Exception as exc:
                self.logger.warning(f"Failed to reload filter list after import: {exc}")
            try:
                from manga_translator.rendering.text_replacements import (
                    invalidate_replacements_cache,
                )

                invalidate_replacements_cache()
            except Exception as exc:
                self.logger.warning(f"Failed to reload text replacements after import: {exc}")

        if main_view is None:
            return

        if "env" in copied or "config" in copied:
            if hasattr(main_view, "_refresh_env_api_groups"):
                main_view._refresh_env_api_groups()
            if hasattr(main_view, "_refresh_api_status_sidebar"):
                main_view._refresh_api_status_sidebar()

        if "presets" in copied or "env" in copied:
            if hasattr(main_view, "_refresh_preset_list"):
                main_view._refresh_preset_list()

        if "fonts" in copied:
            try:
                from utils.font_list import _clear_font_catalog_caches

                _clear_font_catalog_caches()
            except Exception:
                pass
            if hasattr(main_view, "_refresh_font_manager"):
                main_view._refresh_font_manager()

        if "batch_edit" in copied and hasattr(main_view, "batch_edit_panel"):
            load_schemes = getattr(main_view.batch_edit_panel, "_load_schemes", None)
            if callable(load_schemes):
                load_schemes()

        if "config" in copied:
            config = self.config_service.get_config()
            output_path = getattr(getattr(config, "app", None), "last_output_path", "") or ""
            if output_path and hasattr(main_view, "update_output_path_display"):
                main_view.update_output_path_display(output_path)
            theme = getattr(getattr(config, "app", None), "theme", "") or ""
            if theme:
                main_view.theme_change_requested.emit(theme)
            language = getattr(getattr(config, "app", None), "ui_language", "") or ""
            if language and language != "auto":
                main_view.language_change_requested.emit(language)
    # endregion

    # region 文件管理
    def add_files(self, file_paths: List[str]):
        """
        Adds files/folders to the list for processing.
        """
        new_paths = []
        for path in file_paths:
            norm_path = os.path.normpath(path)
            if norm_path not in self.source_files:
                new_paths.append(norm_path)

        if new_paths:
            self.source_files.extend(new_paths)
            self.logger.info(f"Added {len(new_paths)} files/folders to the list.")
            self.files_added.emit(new_paths)
            if any_path_has_translation_map(new_paths):
                self._warn_completed_translation_folder_added()

    def _warn_completed_translation_folder_added(self):
        from PyQt6.QtWidgets import QMessageBox

        QMessageBox.warning(
            None,
            self._t("Notice"),
            self._t(
                "You have loaded already translated images.\nTo edit the translation, clear the list and add the original folder instead."
            ),
        )

    def get_last_open_dir(self) -> str:
        path = self.config_service.get_config().app.last_open_dir
        self.logger.info(f"Retrieved last open directory: {path}")
        return path

    def set_last_open_dir(self, path: str):
        self.logger.info(f"Saving last open directory: {path}")
        self.update_single_config('app.last_open_dir', path)

    def add_folder(self):
        """Opens a dialog to select folders (supports multiple selection) and adds their paths to the list."""
        last_dir = self.get_last_open_dir()

        # 使用自定义的现代化文件夹选择器
        from ui.secondary_pages.folder_dialog import select_folders

        folders = select_folders(
            parent=None,
            start_dir=last_dir,
            multi_select=True,
            config_service=self.config_service
        )

        if folders:
            self.set_last_open_dir(folders[0])  # 保存第一个文件夹的路径
            self.add_files(folders)
    
    def add_folders(self):
        """Alias for add_folder for backward compatibility."""
        self.add_folder()

    def remove_file(self, file_path: str):
        try:
            norm_file_path = os.path.normpath(file_path)
            
            # 尝试在 source_files 中找到匹配的路径（不区分大小写，处理路径分隔符）
            matched_path = None
            for source_path in self.source_files:
                if os.path.normpath(source_path).lower() == norm_file_path.lower():
                    matched_path = source_path
                    break
            
            # 情况1：直接在 source_files 中（文件夹或单独添加的文件）
            if matched_path:
                self.source_files.remove(matched_path)
                # 如果是文件，清理 file_to_folder_map
                if matched_path in self.file_to_folder_map:
                    del self.file_to_folder_map[matched_path]
                
                # 如果是文件夹，清理排除列表中该文件夹下的所有子文件夹
                if os.path.isdir(matched_path):
                    excluded_to_remove = set()
                    for excluded_folder in self.excluded_subfolders:
                        try:
                            # 检查 excluded_folder 是否在被删除的文件夹内
                            common = os.path.commonpath([matched_path, excluded_folder])
                            if common == os.path.normpath(matched_path):
                                excluded_to_remove.add(excluded_folder)
                        except ValueError:
                            continue
                    self.excluded_subfolders -= excluded_to_remove
                
                self.file_removed.emit(file_path)
                return
            
            # 情况2：文件夹路径（可能是顶层文件夹或子文件夹）
            if os.path.isdir(norm_file_path):
                # 检查是否是某个顶层文件夹的子文件夹
                parent_folder = None
                for folder in self.source_files:
                    if os.path.isdir(folder):
                        try:
                            # 检查 norm_file_path 是否是 folder 的子文件夹
                            common = os.path.commonpath([folder, norm_file_path])
                            if common == os.path.normpath(folder) and norm_file_path != os.path.normpath(folder):
                                parent_folder = folder
                                break
                        except ValueError:
                            continue
                
                if parent_folder:
                    # 这是子文件夹，添加到排除列表
                    self.excluded_subfolders.add(norm_file_path)
                    # 发射删除信号让 FileListView 处理
                    # FileListView 会自动更新树形结构和文件数量
                    self.file_removed.emit(file_path)
                    return
                
                # 不是子文件夹，可能是通过单独添加文件自动分组的文件夹
                # 删除该文件夹下的所有文件
                files_to_remove = []
                for source_file in self.source_files:
                    if os.path.isfile(source_file):
                        try:
                            # 检查文件是否在这个文件夹内
                            common = os.path.commonpath([norm_file_path, source_file])
                            if common == norm_file_path:
                                files_to_remove.append(source_file)
                        except ValueError:
                            # 不同驱动器，跳过
                            continue
                
                # 移除所有找到的文件
                for f in files_to_remove:
                    self.source_files.remove(f)
                    # 同时清理 file_to_folder_map
                    if f in self.file_to_folder_map:
                        del self.file_to_folder_map[f]
                
                if files_to_remove:
                    self.file_removed.emit(file_path)
                    return
            
            # 情况3：文件夹内的单个文件（只处理文件，不处理文件夹）
            if os.path.isfile(norm_file_path):
                # 检查这个文件是否来自某个文件夹
                parent_folder = None
                for folder in self.source_files:
                    if os.path.isdir(folder):
                        # 检查文件是否在这个文件夹内
                        try:
                            common = os.path.commonpath([folder, norm_file_path])
                            # 确保文件在文件夹内，而不是文件夹本身
                            if common == os.path.normpath(folder) and norm_file_path != os.path.normpath(folder):
                                parent_folder = folder
                                break
                        except ValueError:
                            # 不同驱动器，跳过
                            continue
                
                if parent_folder:
                    # 这是文件夹内的文件，需要将其添加到排除列表
                    # 由于当前架构不支持排除单个文件，我们需要：
                    # 1. 移除整个文件夹
                    # 2. 添加文件夹内的其他文件
                    
                    # 获取文件夹内的所有图片文件
                    folder_files = self.file_service.get_image_files_from_folder(parent_folder, recursive=True)
                    
                    # 移除要删除的文件
                    remaining_files = [f for f in folder_files if os.path.normpath(f) != norm_file_path]
                    
                    # 从 source_files 中移除文件夹
                    self.source_files.remove(parent_folder)
                    
                    # 如果还有剩余文件，将它们作为单独的文件添加回去
                    if remaining_files:
                        self.source_files.extend(remaining_files)
                        # 更新 file_to_folder_map：这些文件现在仍然属于原文件夹
                        # 保持文件夹映射关系，以便输出路径计算正确
                        for f in remaining_files:
                            self.file_to_folder_map[f] = parent_folder
                    
                    self.file_removed.emit(file_path)
                    return
            
            # 如果到这里还没有处理，说明路径不存在
            self.logger.warning(f"Path not found in list for removal: {file_path}")
        except Exception as e:
            self._ui_log(f"경로 제거 중 예외가 발생했습니다: {e}", "ERROR")

    def clear_file_list(self):
        if not self.source_files:
            return
        # TODO: Add confirmation dialog
        self.source_files.clear()
        self.file_to_folder_map.clear()  # 清空文件夹映射
        self.excluded_subfolders.clear()  # 清空排除列表
        self.files_cleared.emit()
        self.logger.info("File list cleared by user.")
    # endregion

    # region 核心任务逻辑
    def get_folder_tree_structure(self) -> dict:
        """
        获取完整的文件夹树结构
        返回: {
            'files': [所有文件列表],
            'tree': {
                'folder_path': {
                    'files': [该文件夹直接包含的文件],
                    'subfolders': [子文件夹路径列表]
                }
            }
        }
        """
        tree = {}
        all_files = []
        folders = []
        individual_files = []

        for source_path in self.source_files:
            if os.path.isdir(source_path):
                folders.append(os.path.normpath(source_path))
            elif os.path.isfile(source_path):
                individual_files.append(source_path)

        folders.sort(key=self.file_service._natural_sort_key)
        individual_files.sort(key=self.file_service._natural_sort_key)

        for norm_folder in folders:
            folder_files = self._build_folder_tree(norm_folder, tree)
            all_files.extend(folder_files)
        all_files.extend(individual_files)
        
        return {
            'files': all_files,
            'tree': tree
        }
    
    def _build_folder_tree(self, folder_path: str, tree: dict) -> List[str]:
        """
        递归构建文件夹树结构
        返回该文件夹及其子文件夹中的所有文件列表
        """
        # 检查是否被排除
        if folder_path in self.excluded_subfolders:
            return []
        
        norm_folder = os.path.normpath(folder_path)
        
        # 初始化该文件夹的树节点
        if norm_folder not in tree:
            tree[norm_folder] = {
                'files': [],
                'subfolders': []
            }
        
        all_files = []
        image_extensions = {'.png', '.jpg', '.jpeg', '.bmp', '.webp', '.avif'}
        
        try:
            items = os.listdir(folder_path)
            subdirs = []
            files = []
            
            for item in items:
                if item == 'manga_translator_work':
                    continue
                
                item_path = os.path.join(folder_path, item)
                norm_item_path = os.path.normpath(item_path)
                
                if os.path.isdir(item_path):
                    # 检查是否被排除
                    if norm_item_path not in self.excluded_subfolders:
                        subdirs.append(norm_item_path)
                        tree[norm_folder]['subfolders'].append(norm_item_path)
                elif os.path.splitext(item)[1].lower() in image_extensions:
                    files.append(norm_item_path)
            
            # 排序
            subdirs.sort(key=self.file_service._natural_sort_key)
            files.sort(key=self.file_service._natural_sort_key)
            
            # 添加该文件夹直接包含的文件
            tree[norm_folder]['files'] = files
            all_files.extend(files)
            
            # 递归处理子文件夹
            for subdir in subdirs:
                subdir_files = self._build_folder_tree(subdir, tree)
                all_files.extend(subdir_files)
        
        except Exception as e:
            self.logger.error(f"Error building tree for folder {folder_path}: {e}")
        
        return all_files
    
    def start_file_scanning(self):
        """启动后台文件扫描任务"""
        self.state_manager.set_translating(True)
        self.state_manager.set_status_message(self._t("Preparing files..."))
        
        # ✅ 使用线程池运行扫描任务
        scanner_worker = FileScannerRunnable(
            source_files=self.source_files,
            excluded_subfolders=self.excluded_subfolders,
            file_service=self.file_service,
            finished_callback=self.on_scanning_finished,
            error_callback=self.on_scanning_error,
            progress_callback=self.on_worker_log
        )
        
        self.current_worker = scanner_worker
        
        # 使用普通线程启动
        thread = threading.Thread(target=scanner_worker.run, daemon=True)
        self.current_thread = thread
        thread.start()
        
        self._ui_log("파일 검색 작업이 시작되었습니다")

    def on_scanning_finished(self, resolved_files, file_map, archive_map, excluded):
        """文件扫描完成，启动翻译任务"""
        self._ui_log(f"파일 검색 완료, 총 {len(resolved_files)}개 파일을 찾았습니다")
        
        # ✅ 清理worker引用
        self.current_worker = None
        
        # 更新状态
        # 此时我们需要合并旧的文件映射（如果有必要），但在这种重扫模式下，
        # worker返回的已经是全量数据的最新状态（除了单独添加的文件可能丢失原有映射关系）
        # FileScannerWorker 已处理了大部分映射，这里我们需要处理"单独文件保留旧映射"的逻辑
        # 但由于Worker中无法访问旧map，我们在Worker中对单独文件设为None。
        # 如果需要保留旧映射（例如单独添加的文件其实属于某个被移除的文件夹），
        # 这里的逻辑可能比较复杂。鉴于UI逻辑重构，我们暂时接受Worker的全新结果。
        
        self.file_to_folder_map = file_map
        self.archive_to_temp_map = archive_map
        self.excluded_subfolders = excluded
        
        # 检查文件列表是否为空
        if not resolved_files:
            self._ui_log("유효한 이미지 파일을 찾지 못해 작업을 중단했습니다", "WARNING")
            self.state_manager.set_translating(False)
            self.state_manager.set_status_message(self._t("Ready"))
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(
                None,
                self._t("File List Empty"),
                self._t("Please add image files to translate!")
            )
            return

        output_path = self.config_service.get_config().app.last_output_path
        if self._block_start_if_source_matches_output(output_path, resolved_files):
            self.state_manager.set_translating(False)
            self.state_manager.set_status_message(self._t("Ready"))
            return

        resolved = self._apply_overwrite_policy(resolved_files)
        if resolved is None:
            return
        files_to_process, allow_overwrite = resolved
        if not files_to_process:
            self._ui_log("기존 결과 파일만 있어 처리할 항목이 없습니다", "WARNING")
            self.state_manager.set_translating(False)
            self.state_manager.set_status_message(self._t("Ready"))
            return

        self._start_translation_worker(files_to_process, allow_overwrite)

    def on_scanning_error(self, error_msg):
        self._ui_log(f"파일 검색 중 오류: {error_msg}", "ERROR")
        self.current_worker = None
        self.state_manager.set_translating(False)
        self.state_manager.set_status_message(self._t("Scan failed"))
        from PyQt6.QtWidgets import QMessageBox
        QMessageBox.critical(
            None,
            self._t("Scan failed"),
            self._t("Error scanning files:\n{error}", error=error_msg),
        )

    def _preview_save_info(self) -> dict:
        config = self.config_service.get_config()
        output_format = getattr(config.cli, "format", None)
        if not output_format or output_format == "不指定":
            output_format = None
        if getattr(config.cli, "inpaint_only", False):
            output_format = "png"
        return {
            "output_folder": config.app.last_output_path,
            "format": output_format,
            "save_to_source_dir": getattr(config.cli, "save_to_source_dir", False),
        }

    def _ask_existing_output_choice(
        self,
        existing_name: str,
        *,
        show_continue: bool = True,
        simple_confirm: bool = False,
    ) -> str:
        from ui.widgets.overwrite_dialog import ExistingOutputDialog

        if simple_confirm:
            dialog = ExistingOutputDialog(
                getattr(self, "main_view", None),
                title="",
                body=self._t("overwrite_dialog_rerender_body"),
                prompt="",
                continue_text=self._t("overwrite_dialog_continue"),
                overwrite_all_text=self._t("OK"),
                overwrite_current_text=self._t("overwrite_dialog_overwrite_current"),
                cancel_text=self._t("overwrite_dialog_cancel"),
                show_continue=False,
                show_overwrite_current=False,
                show_prompt=False,
            )
        else:
            dialog = ExistingOutputDialog(
                getattr(self, "main_view", None),
                title=self._t("overwrite_dialog_title", name=existing_name),
                body=self._t("overwrite_dialog_body"),
                prompt=self._t("overwrite_dialog_prompt"),
                continue_text=self._t("overwrite_dialog_continue"),
                overwrite_all_text=self._t("overwrite_dialog_overwrite_all"),
                overwrite_current_text=self._t("overwrite_dialog_overwrite_current"),
                cancel_text=self._t("overwrite_dialog_cancel"),
                show_continue=show_continue,
            )
        dialog.exec()
        return dialog.choice

    def _apply_overwrite_policy(self, resolved_files: List[str]):
        from ui.widgets.overwrite_dialog import ExistingOutputDialog

        config = self.config_service.get_config()
        cli_config = config.model_dump().get("cli", {})
        mode = normalize_overwrite_mode(getattr(config.cli, "overwrite", OVERWRITE_ASK))
        save_info = self._preview_save_info()
        existing_pairs = collect_existing_outputs(
            resolved_files,
            cli_config,
            lambda file_path: self._calculate_output_path(file_path, save_info),
        )
        if not existing_pairs:
            return resolved_files, False

        existing_files = [file_path for file_path, _ in existing_pairs]
        existing_names = {file_path: name for file_path, name in existing_pairs}
        simple_confirm = bool(cli_config.get("rerender_only", False))

        if not simple_confirm and mode == OVERWRITE_ALWAYS:
            self._ui_log(self._t("overwrite_log_overwrite_all", count=len(existing_files)))
            return resolved_files, True

        if not simple_confirm and mode == OVERWRITE_SKIP:
            keep = [file_path for file_path in resolved_files if file_path not in existing_names]
            self._ui_log(self._t("overwrite_log_skip_existing", count=len(existing_files)))
            return keep, False

        selected_existing: set[str] = set()
        # TXT export has no resume-from-unfinished path; hide that button only here.
        show_continue = not bool(cli_config.get("template", False))
        index = 0
        while index < len(existing_files):
            file_path = existing_files[index]
            choice = self._ask_existing_output_choice(
                existing_names[file_path],
                show_continue=show_continue,
                simple_confirm=simple_confirm,
            )
            if choice == ExistingOutputDialog.CANCEL:
                self._ui_log(self._t("overwrite_log_cancelled"), "WARNING")
                self.state_manager.set_translating(False)
                self.state_manager.set_status_message(self._t("Ready"))
                return None
            if choice == ExistingOutputDialog.CONTINUE:
                self._ui_log(self._t("overwrite_log_continue_incomplete"))
                break
            if choice == ExistingOutputDialog.OVERWRITE_ALL:
                selected_existing.update(existing_files[index:])
                self._ui_log(self._t("overwrite_log_overwrite_all", count=len(existing_files) - index))
                break
            selected_existing.add(file_path)
            index += 1

        keep = [
            file_path
            for file_path in resolved_files
            if file_path not in existing_names or file_path in selected_existing
        ]
        return keep, bool(selected_existing)

    def _start_translation_worker(self, files_to_process, allow_overwrite: bool = False):
        """启动翻译工作线程（内部方法，由扫描完成后调用）"""
        self.saved_files_count = 0
        self.saved_files_list = []
        self._reset_task_failures()
        
        # 生成新的任务ID
        self.current_task_id += 1
        task_id = self.current_task_id
        config_dict = self.config_service.get_config().model_dump()
        config_dict.setdefault("cli", {})["overwrite"] = allow_overwrite
        
        # ✅ 使用线程池运行翻译任务
        translation_worker = TranslationRunnable(
            files=files_to_process,
            config_dict=config_dict,
            output_folder=self.config_service.get_config().app.last_output_path,
            root_dir=self.config_service.root_dir,
            file_to_folder_map=self.file_to_folder_map.copy(),
            finished_callback=lambda results: self.on_task_finished(results, task_id),
            error_callback=lambda error: self.on_task_error(error, task_id),
            progress_callback=self.on_task_progress,
            file_processed_callback=self.on_file_completed
        )
        
        self.current_worker = translation_worker
        
        # 使用普通线程启动
        thread = threading.Thread(target=translation_worker.run, daemon=True)
        self.current_thread = thread
        thread.start()
        
        self._ui_log(f"번역 작업이 시작되었습니다 (작업 ID: {task_id})")
        self.state_manager.set_translating(True)
        self.state_manager.set_status_message(self._t("Translating..."))

    def _resolve_input_files(self) -> List[str]:
        """
        DEPRECATED: Use FileScannerWorker instead.
        Kept for compatibility if needed, but logic moved to worker.
        """
        # ... logic ...
        return []

    def start_backend_task(self):
        """
        Resolves input paths and uses a 'Worker-to-Thread' model to start the translation task.
        """
        pending_output_folder = self._typed_output_folder_text()

        # 通过调用配置服务的 reload_config 方法，强制全面重新加载所有配置
        try:
            self._ui_log("백그라운드 작업을 시작하기 전에 모든 설정을 다시 불러옵니다...")
            self.config_service.reload_config()
            self._ui_log("설정을 새로고침했습니다. 작업을 계속합니다.")
        except Exception as e:
            self._ui_log(f"설정을 다시 불러오는 중 심각한 오류가 발생했습니다: {e}", "ERROR")

        # 强制保存所有待保存的 API Key
        if hasattr(self, 'main_view') and self.main_view and hasattr(self.main_view, '_flush_all_pending_env_vars'):
            self.main_view._flush_all_pending_env_vars()

        # 检查是否有任务在运行
        if self.state_manager.is_translating():
            self._ui_log("이미 실행 중인 작업이 있습니다.", "WARNING")
            return
        
        # ✅ 等待旧线程完全结束（防止ONNX Runtime冲突）
        if self.current_thread is not None and self.current_thread.is_alive():
            self._ui_log("이전 작업이 끝날 때까지 기다리는 중...")
            self.current_thread.join(timeout=3.0)  # 最多等3秒
            if self.current_thread.is_alive():
                self._ui_log("이전 작업이 3초 안에 끝나지 않아 강제 진행합니다", "WARNING")
            self.current_thread = None
            self.current_worker = None

        # 检查源文件列表是否为空 (初步检查，具体以扫描结果为准)
        if not self.source_files:
            self._ui_log("파일 목록이 비어 있습니다", "WARNING")
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(
                None,
                self._t("File List Empty"),
                self._t("Please add image files to translate!")
            )
            return

        # 检查输出目录是否合法 (提前检查)
        output_path = self.apply_output_folder_path(pending_output_folder)
        if output_path:
            create_result = self._offer_create_output_folder(output_path)
            if create_result == 'declined':
                self._ui_log(f"출력 폴더 생성을 거부해 작업을 중단했습니다: {output_path}", "WARNING")
                from PyQt6.QtWidgets import QMessageBox
                QMessageBox.warning(
                    None,
                    self._t("Notice"),
                    self._t("The task has been aborted."),
                )
                return
        if not output_path or not os.path.isdir(output_path):
            self._ui_log(f"출력 폴더가 올바르지 않습니다: {output_path}", "WARNING")
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(
                None,
                self._t("Invalid Output Directory"),
                self._t("Please set a valid output directory!")
            )
            return

        if self._block_start_if_source_matches_output(output_path):
            return

        # 按当前所选功能精确校验 API Keys
        try:
            if not self._validate_runtime_api_requirements(self.config_service.get_config()):
                return
        except Exception as e:
            from PyQt6.QtWidgets import QMessageBox

            self._ui_log(f"API 키 확인에 실패해 번역을 시작하지 않았습니다: {e}", "ERROR")
            QMessageBox.warning(
                None,
                self._t("API Keys Required"),
                self._t("Unable to validate API Keys (.env). Please check the log and try again."),
            )
            return

        # 启动后台文件扫描
        self.start_file_scanning()

    def on_task_finished(self, results, task_id):
        """处理任务完成信号，并根据需要保存批量任务的结果"""
        # 检查任务ID是否匹配，防止已停止的任务更新状态
        if task_id != self.current_task_id:
            return
        
        saved_files = []
        # The `results` list will only contain items from a batch job now.
        # Sequential jobs handle saving in `on_file_completed`.
        if results:
            self._ui_log(f"일괄 번역이 끝났습니다. 결과 {len(results)}개를 받아 저장하는 중...")
            try:
                config = self.config_service.get_config()
                output_format = config.cli.format
                save_quality = config.cli.save_quality
                output_folder = config.app.last_output_path

                if not output_folder:
                    self._ui_log("출력 폴더가 설정되지 않아 파일을 저장할 수 없습니다.", "ERROR")
                    self.state_manager.set_status_message(self._t("Error: output directory not set!"))
                else:
                    for result in results:
                        if result.get('success'):
                            # 检查是否有 output_path（批量模式下后端已保存）
                            if result.get('output_path'):
                                # 批量模式：直接使用后端保存的路径
                                translated_file = result.get('output_path')
                                saved_files.append(translated_file)
                            elif result.get('image_data') is None:
                                # 兼容旧代码：构造翻译后的图片路径
                                original_path = result.get('original_path')
                                effective_format = output_format
                                if not effective_format or effective_format == "不指定":
                                    effective_format = None
                                save_info = {
                                    'output_folder': output_folder,
                                    'format': effective_format,
                                    'save_to_source_dir': config.cli.save_to_source_dir
                                }
                                translated_file = self._calculate_output_path(original_path, save_info)

                                # 规范化路径，避免混合斜杠
                                translated_file = os.path.normpath(translated_file)
                                saved_files.append(translated_file)
                            else:
                                # This handles cases where a result with image_data is present in a batch
                                try:
                                    base_filename = os.path.splitext(os.path.basename(result['original_path']))[0]
                                    file_extension = f".{output_format}" if output_format and output_format != "不指定" else ".png"
                                    output_filename = f"{base_filename}_translated{file_extension}"
                                    final_output_path = os.path.join(output_folder, output_filename)
                                    os.makedirs(output_folder, exist_ok=True)
                                    
                                    image_to_save = result['image_data']
                                    self._save_image_with_source_metadata(
                                        image_to_save,
                                        final_output_path,
                                        result.get('original_path'),
                                        save_quality,
                                    )
                                    saved_files.append(final_output_path)
                                    self._ui_log(f"파일 저장 성공: {final_output_path}")
                                except Exception as e:
                                    self._ui_log(f"파일 {result['original_path']} 저장 중 오류: {e}", "ERROR")
                        else:
                            self._record_task_failure_from_result(result)
                 
                # In batch mode, the saved_files_count is the length of this list
                self.saved_files_count = len(saved_files)

            except Exception as e:
                self._ui_log(f"일괄 작업 결과를 처리하는 중 심각한 오류가 발생했습니다: {e}", "ERROR")

        failed_count = len(self._task_failures)
        if failed_count > 0:
            self._ui_log(f"번역 작업이 끝났습니다. 성공 {self.saved_files_count}개, 실패 {failed_count}개.", "WARNING")
        else:
            self._ui_log(f"번역 작업이 끝났습니다. 총 {self.saved_files_count}개 파일을 처리했습니다.")
        
        # 对于顺序处理模式，使用累积的 saved_files_list
        if not saved_files and self.saved_files_list:
            saved_files = self.saved_files_list.copy()
        
        try:
            self.state_manager.set_translating(False)
            if failed_count > 0:
                self.state_manager.set_status_message(
                    self._t(
                        "Task completed: {success} files succeeded, {failed} failed.",
                        success=self.saved_files_count,
                        failed=failed_count,
                    )
                )
            else:
                self.state_manager.set_status_message(
                    self._t(
                        "Task completed: {success} files processed successfully.",
                        success=self.saved_files_count,
                    )
                )
            
            # 重置主视图的进度条
            if hasattr(self, 'main_view') and self.main_view:
                self.main_view.reset_progress()
                file_list = getattr(self.main_view, "file_list", None)
                if file_list is not None and hasattr(file_list, "refresh_json_status"):
                    file_list.refresh_json_status()
            
            # 播放系统提示音
            try:
                from PyQt6.QtWidgets import QApplication
                QApplication.beep()
            except Exception:
                pass
            
            # 使用列表副本发送信号，避免引用问题
            self.task_completed.emit(list(saved_files))
            if failed_count > 0:
                self.error_dialog_requested.emit(self._build_task_failure_dialog_message())
        except Exception as e:
            self._ui_log(f"작업 상태 업데이트 중 치명적 오류가 발생했습니다: {e}", "ERROR")
            import traceback
            traceback.print_exc()
        
        # 注意：将清理逻辑移出 finally 块，使用 QTimer 延迟执行
        # 这样可以确保信号有足够时间被主线程处理
        QTimer.singleShot(100, self._cleanup_after_task)
    
    def _cleanup_after_task(self):
        """延迟清理任务相关资源"""
        try:
            # 清理线程引用（线程应该已经通过deleteLater自动清理）
            # ✅ 线程池自动管理，无需手动清理线程
            
            # 清理压缩包解压的临时文件
            if hasattr(self, 'archive_to_temp_map') and self.archive_to_temp_map:
                try:
                    from desktop_qt_ui.utils.archive_extractor import (
                        cleanup_archive_temp,
                    )
                    for archive_path in list(self.archive_to_temp_map.keys()):
                        cleanup_archive_temp(archive_path)
                    self.archive_to_temp_map.clear()
                    self._ui_log("압축 파일 임시 파일을 정리했습니다")
                except Exception as cleanup_error:
                    self._ui_log(f"임시 파일 정리 중 오류: {cleanup_error}", "WARNING")

            # 翻译任务完成后释放 CUDA 缓存
            try:
                import torch
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
                    self._ui_log("번역 후 torch.cuda.empty_cache()를 호출했습니다", "DEBUG")
            except Exception as memory_cleanup_error:
                self._ui_log(f"torch.cuda.empty_cache() 호출 실패: {memory_cleanup_error}", "WARNING")
        except Exception as e:
            # 忽略 C++ 对象已删除的错误
            if "has been deleted" not in str(e):
                self._ui_log(f"작업 리소스 정리 중 오류: {e}", "WARNING")
        finally:
            # ✅ 清理worker引用
            self.current_worker = None
    
    def on_task_error(self, error_message, task_id):
        # 检查任务ID是否匹配，防止已停止的任务更新状态
        if task_id != self.current_task_id:
            return
        
        self.state_manager.set_translating(False)
        self.state_manager.set_status_message(self._t("Task failed"))
        
        # 重置主视图的进度条
        if hasattr(self, 'main_view') and self.main_view:
            self.main_view.reset_progress()
        
        # 弹出错误提示框
        self.error_dialog_requested.emit(error_message)
        
        # 清理worker引用
        self.current_worker = None

    def on_task_progress(self, current, total, message):
        self._ui_log(f"[진행] {current}/{total}: {message}")
        percentage = (current / total) * 100 if total > 0 else 0
        self.state_manager.set_translation_progress(percentage)
        self.state_manager.set_status_message(f"[{current}/{total}] {message}")
        
        # 更新主视图的进度条
        if hasattr(self, 'main_view') and self.main_view:
            self.main_view.update_progress(current, total, message)
            self._refresh_file_list_json_status()

    def stop_task(self) -> bool:
        """停止翻译任务"""
        if self.current_worker and hasattr(self.current_worker, 'stop'):
            self._ui_log("작업 중지를 요청하는 중...")
            self.state_manager.set_status_message(self._t("Stopping..."))
            if hasattr(self, 'main_view') and self.main_view:
                self.main_view.set_stopping_state()
            
            # 增加任务ID，使旧任务的回调失效
            self.current_task_id += 1
            
            # 通知worker停止
            self.current_worker.stop()
            
            # ✅ 在后台线程中等待任务真正结束
            def wait_for_thread_finish():
                if self.current_thread and self.current_thread.is_alive():
                    self._ui_log("번역 프로세스가 끝나기를 기다리는 중...")
                    self.current_thread.join(timeout=10.0)  # 增加到10秒
                    if self.current_thread.is_alive():
                        self._ui_log("번역 프로세스가 10초 안에 끝나지 않아 계속 기다립니다...", "WARNING")
                        # 继续等待，直到线程真正结束
                        self.current_thread.join(timeout=30.0)  # 再等30秒
                        if self.current_thread.is_alive():
                            self._ui_log("번역 프로세스가 40초 안에 끝나지 않아 중지된 것으로 표시합니다", "ERROR")
                        else:
                            self._ui_log("번역 프로세스가 종료되었습니다")
                    else:
                        self._ui_log("번역 프로세스가 종료되었습니다")
                
                # 在主线程中更新UI
                from PyQt6.QtCore import QMetaObject, Qt
                QMetaObject.invokeMethod(
                    self,
                    "_finish_stop_task",
                    Qt.ConnectionType.QueuedConnection
                )
            
            # 在后台线程中等待
            wait_thread = threading.Thread(target=wait_for_thread_finish, daemon=True)
            wait_thread.start()
            
            return True
        
        self._ui_log("중지할 실행 중인 작업이 없습니다", "WARNING")
        self.state_manager.set_translating(False)
        return False
    
    @pyqtSlot()
    def _finish_stop_task(self):
        """在主线程中完成停止任务的清理工作"""
        self.state_manager.set_translating(False)
        self.state_manager.set_status_message(self._t("Task stopped"))
        if hasattr(self, 'main_view') and self.main_view:
            self.main_view.reset_progress()
        self._cleanup_after_task()
        self.current_thread = None
        self.current_worker = None
    # endregion

    # region 应用生命周期
    def initialize(self) -> bool:
        try:
            # The config is already loaded at startup. We just need to ensure the UI
            # reflects the loaded state without triggering a full, blocking rebuild.
            
            # Get the already loaded config
            config = self.config_service.get_config()

            # Manually emit the signal to populate UI options
            self.config_loaded.emit(config.model_dump())

            # Manually emit the signal to update the output path display in the UI
            if config.app.last_output_path:
                self.output_path_updated.emit(config.app.last_output_path)
            
            # Ensure the config path is stored in the state manager
            default_config_path = self.config_service.get_default_config_path()
            if os.path.exists(default_config_path):
                self.state_manager.set_state(AppStateKey.CONFIG_PATH, default_config_path)

            self.state_manager.set_app_ready(True)
            self.state_manager.set_status_message(self._t("Ready"))
            self._ui_log("Application initialized")
            return True
        except Exception as e:
            self._ui_log(f"앱 초기화 오류: {e}", "ERROR")
            return False
    
    def shutdown(self):
        """应用关闭时的清理"""
        if self._shutdown_started:
            return

        self._shutdown_started = True

        try:
            if self.state_manager.is_translating() and self.current_worker:
                self._ui_log("앱을 종료하는 중이며 작업을 중지합니다...")
                
                # 通知worker停止
                if hasattr(self.current_worker, 'stop'):
                    try:
                        self.current_worker.stop()
                    except Exception as e:
                        self._ui_log(f"워커 중지 중 오류: {e}", "WARNING")
                
                # ✅ 等待线程完成（最多5秒）
                if self.current_thread and self.current_thread.is_alive():
                    self.current_thread.join(timeout=5.0)
                    if self.current_thread.is_alive():
                        self._ui_log("스레드가 5초 안에 작업을 끝내지 못했습니다", "WARNING")
                    else:
                        self._ui_log("모든 작업이 정상적으로 중지되었습니다")
                
                self.current_thread = None
                self.current_worker = None
                self.state_manager.set_translating(False)
            
            # 关闭缩略图加载线程池
            try:
                from ui.widgets.file_list_view import (
                    shutdown_thumbnail_executor,
                )
                shutdown_thumbnail_executor()
            except Exception:
                pass
            
            # 关闭轻量级修复器线程池
            try:
                from desktop_qt_ui.services.lightweight_inpainter import (
                    get_lightweight_inpainter,
                )
                inpainter = get_lightweight_inpainter()
                if inpainter:
                    inpainter.shutdown()
            except Exception:
                pass
            except Exception:
                pass
            
            if self.translation_service:
                pass
        except Exception as e:
            self._ui_log(f"앱 종료 중 오류: {e}", "ERROR")
    # endregion

class FileScannerWorker(QObject):
    """
    Worker for scanning files and folders in a background thread.
    Replaces the synchronous _resolve_input_files method.
    """
    finished = pyqtSignal(list, dict, dict, set) # resolved_files, file_to_folder_map, archive_to_temp_map, excluded_subfolders
    error = pyqtSignal(str)
    progress = pyqtSignal(str)

    def __init__(self, source_files, excluded_subfolders, file_service):
        super().__init__()
        self.source_files = source_files
        self.excluded_subfolders = excluded_subfolders.copy()
        self.file_service = file_service
        self.file_to_folder_map = {}
        self.archive_to_temp_map = {}

    def _t(self, key: str, **kwargs) -> str:
        i18n = get_i18n_manager()
        if i18n:
            return i18n.translate(key, **kwargs)
        return key

    def process(self):
        try:
            self.progress.emit(self._t("Scanning files..."))
            resolved_files = []
            processed_archives = set()
             
            # 分离文件和文件夹
            folders = []
            individual_files = []
            archive_files = []
            
            for path in self.source_files:
                if os.path.isdir(path):
                    folders.append(path)
                elif os.path.isfile(path):
                    if self.file_service.is_archive_file(path):
                        archive_files.append(path)
                    elif self.file_service.validate_image_file(path):
                        individual_files.append(path)

            from desktop_qt_ui.utils.archive_extractor import (
                check_output_extract_conflict,
                clear_output_extract_root,
                extract_images_from_archive,
                get_output_extract_dir,
                write_output_extract_marker,
            )

            output_base_dir = ''
            overwrite_extract = False
            try:
                cfg = self.file_service.config_service.get_config()
                output_base_dir = cfg.app.last_output_path
                overwrite_extract = overwrite_enabled(getattr(cfg.cli, 'overwrite', OVERWRITE_SKIP))
            except Exception:
                output_base_dir = ''
                overwrite_extract = False

            def _is_excluded(file_path: str) -> bool:
                if not self.excluded_subfolders:
                    return False
                for excluded_folder in self.excluded_subfolders:
                    try:
                        common = os.path.commonpath([excluded_folder, file_path])
                        if common == excluded_folder:
                            return True
                    except ValueError:
                        continue
                return False

            def _get_archive_output_base_dir(archive_path: str, scan_root: str = None) -> str:
                if not (output_base_dir and os.path.isdir(output_base_dir)):
                    return ''
                if not scan_root:
                    return output_base_dir

                archive_parent = os.path.normpath(os.path.dirname(archive_path))
                scan_root_norm = os.path.normpath(scan_root)
                try:
                    relative_parent = os.path.relpath(archive_parent, scan_root_norm)
                except ValueError:
                    return output_base_dir

                nested_base = os.path.join(output_base_dir, os.path.basename(scan_root_norm))
                if relative_parent != '.':
                    nested_base = os.path.join(nested_base, relative_parent)
                return os.path.normpath(nested_base)

            def _extract_archive(archive_path: str, scan_root: str = None) -> None:
                norm_archive = os.path.normcase(os.path.abspath(archive_path))
                if norm_archive in processed_archives:
                    return
                processed_archives.add(norm_archive)

                try:
                    self.progress.emit(
                        self._t("Extracting: {name}", name=os.path.basename(archive_path))
                    )
                    archive_output_base_dir = _get_archive_output_base_dir(archive_path, scan_root)
                    if archive_output_base_dir:
                        if check_output_extract_conflict(archive_output_base_dir, archive_path):
                            if not overwrite_extract:
                                self.progress.emit(
                                    self._t(
                                        "Skipping extract (name conflict, overwrite disabled): {name}",
                                        name=os.path.basename(archive_path),
                                    )
                                )
                                return
                            clear_output_extract_root(archive_output_base_dir, archive_path)
                        extract_dir = get_output_extract_dir(archive_output_base_dir, archive_path)
                        images, extracted_dir = extract_images_from_archive(archive_path, extract_dir)
                        if images:
                            write_output_extract_marker(archive_output_base_dir, archive_path)
                    else:
                        images, extracted_dir = extract_images_from_archive(archive_path)

                    if images:
                        self.archive_to_temp_map[archive_path] = extracted_dir
                        for img_path in images:
                            resolved_files.append(img_path)
                            self.file_to_folder_map[img_path] = archive_path
                        self.progress.emit(
                            self._t(
                                "Extracted {count} images from {name}",
                                count=len(images),
                                name=os.path.basename(archive_path),
                            )
                        )
                    else:
                        self.progress.emit(
                            self._t(
                                "Warning: no images found in {name}",
                                name=os.path.basename(archive_path),
                            )
                        )
                except Exception as e:
                    self.progress.emit(
                        self._t(
                            "Failed to extract {name}: {error}",
                            name=os.path.basename(archive_path),
                            error=e,
                        )
                    )

            # 处理顶层压缩包文件
            for archive_path in archive_files:
                _extract_archive(archive_path)
            
            # 清理排除列表
            if self.excluded_subfolders:
                excluded_to_remove = set()
                for excluded_folder in self.excluded_subfolders:
                    is_valid = False
                    for folder in folders:
                        try:
                            common = os.path.commonpath([folder, excluded_folder])
                            if common == os.path.normpath(folder):
                                is_valid = True
                                break
                        except ValueError:
                            continue
                    if not is_valid:
                        excluded_to_remove.add(excluded_folder)
                self.excluded_subfolders -= excluded_to_remove
            
            # 对文件夹进行自然排序
            folders.sort(key=self.file_service._natural_sort_key)
            
            # 按文件夹分组处理
            for folder in folders:
                self.progress.emit(
                    self._t("Scanning folder: {name}", name=os.path.basename(folder))
                )
                # 获取文件夹中的所有图片
                folder_files = self.file_service.get_image_files_from_folder(folder, recursive=True)
                folder_archives = self.file_service.get_archive_files_from_folder(folder, recursive=True)
                 
                # 过滤掉被排除的子文件夹中的文件
                if self.excluded_subfolders:
                    folder_files = [f for f in folder_files if not _is_excluded(f)]
                    folder_archives = [f for f in folder_archives if not _is_excluded(f)]

                # 处理文件夹内的压缩包文件
                for archive_path in folder_archives:
                    _extract_archive(archive_path, folder)
                 
                resolved_files.extend(folder_files)
                # 记录这些文件来自这个文件夹
                for file_path in folder_files:
                    self.file_to_folder_map[file_path] = folder
            
            # 处理单独添加的文件
            individual_files.sort(key=self.file_service._natural_sort_key)
            for file_path in individual_files:
                resolved_files.append(file_path)
                # 单独添加的文件，映射为None（除非在MainAppLogic中有旧映射，但这里我们无法访问旧映射，
                # 不过MainAppLogic可以在接收结果时合并）
                self.file_to_folder_map[file_path] = None

            unique_files = list(dict.fromkeys(resolved_files))
            self.finished.emit(unique_files, self.file_to_folder_map, self.archive_to_temp_map, self.excluded_subfolders)
            
        except Exception as e:
            self.error.emit(str(e))


class TranslationWorker(QObject):
    finished = pyqtSignal(list)
    error = pyqtSignal(str)
    progress = pyqtSignal(int, int, str)
    file_processed = pyqtSignal(dict)

    def __init__(self, files, config_dict, output_folder, root_dir, file_to_folder_map=None):
        super().__init__()
        self.files = files
        self.config_dict = config_dict
        self.output_folder = output_folder
        self.root_dir = root_dir
        self.file_to_folder_map = file_to_folder_map or {}  # 文件到文件夹的映射
        self._is_running = True
        self._current_task = None  # 保存当前运行的异步任务
        self.i18n = get_i18n_manager()
        self.logger = get_logger(__name__)
        self.file_service = get_file_service()
    
    def _t(self, key: str, **kwargs) -> str:
        """翻译辅助方法"""
        if self.i18n:
            return self.i18n.translate(key, **kwargs)
        return key

    def _log(self, level: int, message: str):
        message = str(message).rstrip()
        if not message:
            return
        self.logger.log(level, message)

    def _log_info(self, message: str):
        self._log(logging.INFO, message)

    def _log_warning(self, message: str):
        self._log(logging.WARNING, message)

    def _log_error(self, message: str):
        self._log(logging.ERROR, message)

    def _collect_exported_script_folders(self, translator) -> list[str]:
        folders: list[str] = []
        seen: set[str] = set()

        def _add(folder: str) -> None:
            if not folder:
                return
            real = os.path.realpath(folder)
            if real in seen or not os.path.isdir(real):
                return
            seen.add(real)
            folders.append(real)

        combined_paths = getattr(translator, "_combined_original_txt_paths", None) or set()
        for combined_path in combined_paths:
            _add(os.path.dirname(os.path.abspath(combined_path)))

        if folders:
            return folders

        from manga_translator.utils.path_manager import get_txt_dir

        for image_path in self.files:
            try:
                _add(get_txt_dir(image_path, create_dir=False))
            except Exception:
                continue
        return folders

    def _open_one_script_folder(self, folder: str) -> None:
        import subprocess
        import sys

        if not folder:
            return
        real = os.path.realpath(folder)
        if not os.path.isdir(real):
            self._log_warning(f"script 폴더를 열지 못했습니다: {folder}")
            return
        try:
            if sys.platform == "win32":
                os.startfile(real)
            elif sys.platform == "darwin":
                subprocess.run(["open", real], check=False)
            else:
                subprocess.run(["xdg-open", real], check=False)
            self._log_info(f"📂 script 폴더를 열었습니다: {real}")
        except Exception as e:
            self._log_warning(f"script 폴더를 열지 못했습니다: {folder} ({e})")

    def _open_exported_script_folders(self, translator) -> None:
        folders = self._collect_exported_script_folders(translator)
        if not folders:
            self._log_warning("내보낸 script 폴더를 찾지 못해 열 수 없습니다")
            return

        opened = getattr(translator, "_finalized_txt_export_folders", None) or set()
        opened_keys = {os.path.normcase(os.path.normpath(os.path.abspath(path))) for path in opened}
        for folder in folders:
            if os.path.normcase(os.path.normpath(os.path.abspath(folder))) in opened_keys:
                continue
            self._open_one_script_folder(folder)

    def _on_txt_folder_finalized(self, folder: str) -> None:
        self._open_one_script_folder(folder)

    def _prepare_txt_export_folder_hooks(self, translator, *, enabled: bool) -> None:
        if not enabled:
            return
        translator._txt_export_job_paths = [os.path.abspath(path) for path in self.files]
        translator.on_txt_folder_finalized = self._on_txt_folder_finalized

    def _finalize_original_text_export(self, translator, *, write_backup: bool) -> None:
        if hasattr(translator, "_flush_completed_txt_export_folders"):
            translator._flush_completed_txt_export_folders(force=bool(write_backup))
        elif write_backup and hasattr(translator, "_write_combined_script_backups"):
            translator._write_combined_script_backups()
        # Each folder is opened as soon as it finishes. Avoid opening them all again.
        if not callable(getattr(translator, "on_txt_folder_finalized", None)):
            self._open_exported_script_folders(translator)

    def _get_context_value(self, ctx, key: str, default=None):
        if ctx is None:
            return default
        if isinstance(ctx, dict):
            return ctx.get(key, default)
        return getattr(ctx, key, default)

    def _normalize_error_summary(self, message: str, limit: int = 240) -> str:
        raw = str(message or "").replace("\r\n", "\n").replace("\r", "\n")
        lines = [line.strip() for line in raw.split("\n") if line.strip()]
        summary = lines[0] if lines else ""
        if not summary:
            return "자세한 오류가 기록되지 않았습니다"
        return textwrap.shorten(summary, width=limit, placeholder="...")

    def _extract_context_error_message(self, ctx) -> str:
        candidates = (
            "translation_error",
            "error",
            "critical_error_msg",
            "exception",
            "message",
        )
        for key in candidates:
            value = self._get_context_value(ctx, key)
            if value is None:
                continue
            text = str(value).strip()
            if text:
                return text
        return ""

    def _build_batch_failure_log_message(self, failed_items: list[dict], total_failed: int) -> str:
        lines = [
            f"\n⚠️ 일괄 번역 완료: 실패 {total_failed}장"
        ]
        for item in failed_items[:5]:
            lines.append(f"- {item['file_name']}: {item['summary']}")
        remaining = total_failed - min(len(failed_items), 5)
        if remaining > 0:
            lines.append(f"- 그 외 {remaining}장이 더 실패했습니다. 자세한 이유는 위 개별 로그를 확인하세요")
        return "\n".join(lines)

    def _format_eta_duration(self, seconds: float) -> str:
        total_seconds = max(0, int(round(seconds)))
        hours, remainder = divmod(total_seconds, 3600)
        minutes, secs = divmod(remainder, 60)
        if hours > 0:
            return self._t("eta_hours_minutes", hours=hours, minutes=minutes)
        if minutes > 0:
            return self._t("eta_minutes_seconds", minutes=minutes, seconds=secs)
        return self._t("eta_seconds", seconds=secs)

    def _build_eta_progress_message(
        self,
        completed_count: int,
        remaining_count: int,
        elapsed_seconds: float,
        skipped_count: int = 0,
        failed_count: int = 0,
        detail: str = "",
    ) -> str:
        parts = [detail] if detail else []
        if completed_count <= 0:
            if skipped_count > 0:
                parts.append(self._t("Skipped {count} images", count=skipped_count))
            if failed_count > 0:
                parts.append(self._t("Failed {count} images", count=failed_count))
            if remaining_count <= 0:
                parts.append(self._t("Nothing to process"))
                return " | ".join(parts)
            parts.append(self._t("Waiting for first image to estimate remaining time"))
            return " | ".join(parts)

        average_seconds = elapsed_seconds / max(completed_count, 1)
        parts.append(self._t("Avg {seconds:.1f} s/image", seconds=average_seconds))
        parts.append(
            self._t(
                "ETA {duration}",
                duration=self._format_eta_duration(average_seconds * max(remaining_count, 0)),
            )
        )
        if skipped_count > 0:
            parts.append(self._t("Skipped {count} images", count=skipped_count))
        if failed_count > 0:
            parts.append(self._t("Failed {count} images", count=failed_count))
        return " | ".join(parts)
    
    def _calculate_output_path(self, image_path: str, save_info: dict) -> str:
        """
        计算输出文件的完整路径（用于预检查文件是否存在）
        
        Args:
            image_path: 输入图片的路径
            save_info: 包含输出配置的字典
                
        Returns:
            str: 计算后的输出文件完整路径
        """
        output_folder = save_info.get('output_folder')
        output_format = save_info.get('format')
        save_to_source_dir = save_info.get('save_to_source_dir', False)
        
        file_path = image_path
        parent_dir = os.path.normpath(os.path.dirname(file_path))
        
        # 检查是否启用了"输出到原图目录"模式
        if save_to_source_dir:
            # 输出到原图所在目录的 manga_translator_work/result 子目录
            final_output_dir = os.path.join(parent_dir, 'manga_translator_work', 'result')
        else:
            # 原有逻辑：使用配置的输出目录
            final_output_dir = output_folder
            
            # 检查文件是否来自文件夹
            source_folder = self.file_to_folder_map.get(image_path)
            if source_folder:
                # 检查是否来自压缩包
                if self.file_service.is_archive_file(source_folder):
                    archive_output_dir = _resolve_archive_output_dir_from_extracted_image(
                        image_path, output_folder
                    )
                    if archive_output_dir:
                        final_output_dir = archive_output_dir
                    else:
                        archive_name = os.path.splitext(os.path.basename(source_folder))[0]
                        final_output_dir = os.path.join(output_folder, archive_name)
                else:
                    # 文件来自文件夹，保持相对路径结构
                    relative_path = os.path.relpath(parent_dir, source_folder)
                    # Normalize path and avoid adding '.' as a directory component
                    if relative_path == '.':
                        final_output_dir = os.path.join(output_folder, os.path.basename(source_folder))
                    else:
                        final_output_dir = os.path.join(output_folder, os.path.basename(source_folder), relative_path)
                final_output_dir = os.path.normpath(final_output_dir)
        
        # 处理输出文件名和格式
        base_filename, _ = os.path.splitext(os.path.basename(file_path))
        if output_format and output_format.strip() and output_format.lower() not in ['none', '不指定']:
            output_filename = f"{base_filename}.{output_format}"
        else:
            output_filename = os.path.basename(file_path)
        
        final_output_path = os.path.join(final_output_dir, output_filename)
        return final_output_path

    def stop(self):
        self._log_info("--- Stop request received.")
        self._is_running = False
        # 取消当前运行的异步任务
        if self._current_task and not self._current_task.done():
            self._current_task.cancel()
        
        # 使用统一的内存清理模块
        try:
            from desktop_qt_ui.utils.memory_cleanup import full_memory_cleanup
            # 使用配置中的卸载模型开关
            unload_models = self.config_dict.get('app', {}).get('unload_models_after_translation', False)
            full_memory_cleanup(log_callback=self._log_info, unload_models=unload_models)
        except Exception as e:
            self._log_warning(f"--- [CLEANUP] Warning: Failed to cleanup: {e}")

    @staticmethod
    def _build_friendly_error_message(
        error_message: str,
        error_traceback: str,
        file_name: str = "",
    ) -> str:
        """
        오류 정보를 바탕으로 읽기 쉬운 한국어 안내를 만듭니다.
        """
        def _wrap_error_text(text: str, width: int = 88) -> str:
            wrapped_lines = []
            for line in (text or "").splitlines():
                if not line:
                    wrapped_lines.append("")
                    continue
                wrapped_lines.extend(
                    textwrap.wrap(
                        line,
                        width=width,
                        break_long_words=True,
                        break_on_hyphens=False,
                    )
                    or [""]
                )
            return "\n".join(wrapped_lines)

        friendly_msg = ""

        real_error = error_message
        if ("达到最大尝试次数" in error_message and "最后一次错误:" in error_message) or (
            "최대 재시도 횟수에 도달" in error_message and "마지막 오류:" in error_message
        ):
            try:
                if "最后一次错误:" in error_message:
                    real_error = error_message.split("最后一次错误:")[1].strip()
                else:
                    real_error = error_message.split("마지막 오류:")[1].strip()
            except Exception:
                pass

        if ("BR markers missing" in real_error or
            "AI断句检查" in error_message or
            "AI 줄바꿈 검사" in error_message or
            "BRMarkersValidationException" in error_traceback or
            "_validate_br_markers" in error_traceback):
            friendly_msg += "원인: AI 줄바꿈 검사 실패\n\n"
            friendly_msg += "상세 설명:\n"
            friendly_msg += "   AI가 번역 시 줄바꿈 표시 [BR]를 올바르게 넣지 못해 여러 번 재시도 후에도 실패했습니다.\n\n"
            friendly_msg += "해결 방법 (하나만 선택):\n"
            friendly_msg += "   1. ⭐ 「AI 줄바꿈 검사」옵션 끄기 (권장)\n"
            friendly_msg += "      - 위치: 고급 설정 → 렌더링 설정 → AI 줄바꿈 검사\n"
            friendly_msg += "      - 설명: 일부 경우에 AI가 줄바꿈 표시를 넣지 않아도 통과시킵니다\n\n"
            friendly_msg += "   2. 「재시도 횟수」늘리기\n"
            friendly_msg += "      - 위치: 일반 설정 → 재시도 횟수\n"
            friendly_msg += "      - 권장: 10 이상 (-1은 무제한 재시도)\n\n"
            friendly_msg += "   3. 번역 모델 바꾸기\n"
            friendly_msg += "      - 일부 모델은 줄바꿈 표시를 더 잘 이해합니다\n"
            friendly_msg += "      - 권장: gpt-5.2, gemini-3-pro, grok-4.2\n\n"
            friendly_msg += "   4. 「AI 줄바꿈」기능 끄기\n"
            friendly_msg += "      - 위치: 고급 설정 → 렌더링 설정 → AI 줄바꿈\n"
            friendly_msg += "      - 설명: 기존 자동 줄바꿈을 사용합니다 (조판이 덜 정확할 수 있음)\n\n"
            friendly_msg += "   5. 배치 크기 줄이기\n"
            friendly_msg += "      - 위치: 고급 설정 → 배치 크기\n"
            friendly_msg += "      - 권장: 3에서 1 또는 2로 줄이기\n"
            friendly_msg += "      - 설명: 한 번에 처리하는 텍스트가 적을수록 AI가 줄바꿈 표시를 넣기 쉽습니다\n\n"

        elif (
            "翻译数量不匹配" in real_error
            or "Translation count mismatch" in real_error
            or "번역 개수가 일치하지 않습니다" in real_error
        ):
            friendly_msg += "원인: 번역 개수가 일치하지 않음\n\n"
            friendly_msg += "상세 설명:\n"
            friendly_msg += "   AI가 돌려준 번역 개수가 원문 개수와 다릅니다.\n"
            friendly_msg += "   보통 AI가 여러 줄을 합쳐 번역하거나 일부를 빠뜨렸을 때 발생합니다.\n\n"
            friendly_msg += "해결 방법 (하나만 선택):\n"
            friendly_msg += "   1. ⭐ 「재시도 횟수」늘리기 (권장)\n"
            friendly_msg += "      - 위치: 일반 설정 → 재시도 횟수\n"
            friendly_msg += "      - 권장: 10 이상 (-1은 무제한 재시도)\n"
            friendly_msg += "      - 설명: 여러 번 다시 시도하면 올바른 개수로 돌아오는 경우가 많습니다\n\n"
            friendly_msg += "   2. 번역 모델 바꾸기\n"
            friendly_msg += "      - 일부 모델은 지시 사항을 더 잘 따릅니다\n"
            friendly_msg += "      - 권장: gpt-5.2, gemini-3-pro, grok-4.2\n\n"
            friendly_msg += "   3. 배치 크기 줄이기\n"
            friendly_msg += "      - 위치: 고급 설정 → 배치 크기\n"
            friendly_msg += "      - 권장: 3에서 1 또는 2로 줄이기\n"
            friendly_msg += "      - 설명: 한 번에 처리하는 텍스트가 적을수록 오류가 줄어듭니다\n\n"

        elif (
            "翻译质量检查失败" in real_error
            or "Quality check failed" in real_error
            or "번역 품질 검사 실패" in real_error
        ):
            friendly_msg += "원인: 번역 품질 검사 실패\n\n"
            friendly_msg += "상세 설명:\n"
            friendly_msg += "   AI가 돌려준 번역에 빈 번역, 합친 번역, 이상한 기호 같은 품질 문제가 있습니다.\n\n"
            friendly_msg += "해결 방법 (하나만 선택):\n"
            friendly_msg += "   1. ⭐ 「재시도 횟수」늘리기 (권장)\n"
            friendly_msg += "      - 위치: 일반 설정 → 재시도 횟수\n"
            friendly_msg += "      - 권장: 10 이상 (-1은 무제한 재시도)\n\n"
            friendly_msg += "   2. 번역 모델 바꾸기\n"
            friendly_msg += "      - 일부 모델은 번역 품질이 더 안정적입니다\n"
            friendly_msg += "      - 권장: gpt-5.2, gemini-3-pro, grok-4.2\n\n"
            friendly_msg += "   3. 배치 크기 줄이기\n"
            friendly_msg += "      - 위치: 고급 설정 → 배치 크기\n"
            friendly_msg += "      - 권장: 3에서 1 또는 2로 줄이기\n"
            friendly_msg += "      - 설명: 한 번에 처리하는 텍스트가 적을수록 품질이 더 안정적입니다\n\n"

        elif (
            (("NoneType" in real_error or "NoneType" in error_traceback) and
             ("strip" in real_error.lower() or "strip" in error_traceback.lower()))
            or ("returned empty content" in real_error.lower())
            or ("returned empty text" in real_error.lower())
            or ("响应text为空" in real_error)
            or ("응답 text가 비어" in real_error)
        ):
            friendly_msg += "원인: AI가 빈 텍스트를 반환함\n\n"
            friendly_msg += "상세 설명:\n"
            friendly_msg += "   이번 요청에서 해석할 수 있는 텍스트가 오지 않았습니다 (OpenAI/Gemini 모두 가능).\n"
            friendly_msg += "   콘텐츠 심사에 걸리거나 서버가 바빠서 일시적으로 빈 응답이 올 수 있습니다.\n\n"
            friendly_msg += "해결 방법:\n"
            friendly_msg += "   1. ⭐ 모델 바꾸기 (권장)\n"
            friendly_msg += "      - OpenAI: gpt-5.2, gpt-5.2-mini\n"
            friendly_msg += "      - Gemini: gemini-3-pro, gemini-3-flash\n\n"
            friendly_msg += "   2. 사이트(API 주소) 바꾸기\n"
            friendly_msg += "      - Gemini 공식 주소: https://generativelanguage.googleapis.com\n"
            friendly_msg += "      - OpenAI 공식 주소: https://api.openai.com/v1\n"
            friendly_msg += "      - 서드파티 중계를 쓰는 경우 다른 업체나 공식 API로 바꿔 보세요\n\n"
            friendly_msg += "   3. 번역할 이미지 내용을 바꾼 뒤 다시 시도\n"
            friendly_msg += "      - 민감한 장면이나 고위험 단어를 피하면 심사에 걸릴 확률이 낮아집니다\n\n"
            friendly_msg += "   4. 잠시 후 다시 시도 (서버가 바쁠 때 흔함)\n\n"

        elif ("不支持多模态" in real_error or
              "멀티모달 입력을 지원하지 않습니다" in real_error or
              ("multimodal" in real_error.lower() and "renderer" not in real_error.lower()) or
              ("vision" in real_error.lower() and "renderer" not in real_error.lower()) or
              ("image_url" in real_error.lower() and "renderer" not in real_error.lower()) or
              ("expected `text`" in real_error.lower() and "renderer" not in real_error.lower()) or
              ("unknown variant" in real_error.lower() and "renderer" not in real_error.lower())):
            friendly_msg += "원인: 모델이 멀티모달 입력을 지원하지 않음\n\n"
            friendly_msg += "상세 설명:\n"
            friendly_msg += "   현재 「고품질 번역기」(OpenAI 고품질 또는 Gemini 고품질)를 사용 중입니다.\n"
            friendly_msg += "   이 번역기는 이미지를 AI에 보내 분석하는데, 지금 모델은 이미지 입력을 지원하지 않습니다.\n\n"
            friendly_msg += "해결 방법 (하나만 선택):\n"
            friendly_msg += "   1. ⭐ 일반 번역기로 바꾸기 (권장)\n"
            friendly_msg += "      - 위치: 번역 설정 → 번역기\n"
            friendly_msg += "      - 「OpenAI 고품질 번역」을 「OpenAI」로 변경\n"
            friendly_msg += "      - 「Gemini 고품질 번역」을 「Google Gemini」로 변경\n"
            friendly_msg += "      - 설명: 일반 번역기는 이미지를 보내지 않고 텍스트만 번역합니다\n\n"
            friendly_msg += "   2. 멀티모달을 지원하는 모델로 바꾸기\n"
            friendly_msg += "      - OpenAI: gpt-5.2, gpt-5.2-mini\n"
            friendly_msg += "      - Gemini: gemini-3-pro, gemini-3-flash\n"
            friendly_msg += "      - Grok: grok-4.2\n"
            friendly_msg += "      - 주의: DeepSeek 모델은 멀티모달을 지원하지 않습니다\n\n"

        elif (
            "code=20012" in real_error.lower()
            or "model does not exist" in real_error.lower()
            or ("does not exist" in real_error.lower() and "model" in real_error.lower())
            or "model not found" in real_error.lower()
            or "invalid model" in real_error.lower()
            or "no such model" in real_error.lower()
            or "模型不存在" in real_error
            or "模型名称不存在" in real_error
            or "모델이 존재하지 않습니다" in real_error
            or "모델 이름이 존재하지 않습니다" in real_error
        ):
            friendly_msg += "원인: 모델이 없거나 현재 API 사이트에서 이 모델을 지원하지 않음\n\n"
            friendly_msg += "상세 설명:\n"
            friendly_msg += "   API 연결은 되었지만, 서버가 입력한 모델 이름을 찾지 못했습니다.\n"
            friendly_msg += "   보통 철자/대소문자가 다르거나, 모델이 내려갔거나, 중계/채널에서 그 모델을 제공하지 않을 때 발생합니다.\n\n"
            friendly_msg += "해결 방법:\n"
            friendly_msg += "   1. ⭐ 모델 이름이 서비스 제공 이름과 완전히 같은지 확인 (가장 흔함)\n"
            friendly_msg += "      - 위치: 번역 설정 → 환경 변수 → MODEL\n"
            friendly_msg += "      - 주의: 모델 이름은 보통 대소문자를 구분하며, 접두어나 버전을 빼면 안 됩니다\n\n"
            friendly_msg += "   2. 「연결 테스트」또는 모델 목록으로 이 사이트에서 실제 지원하는 모델 확인\n"
            friendly_msg += "      - API 관리 → 연결 테스트 / 모델 목록 가져오기\n"
            friendly_msg += "      - 먼저 해당 사이트가 쓰려는 모델을 정말 제공하는지 확인하세요\n\n"
            friendly_msg += "   3. 서드파티 OpenAI 호환 사이트(중계, 채널, SiliconFlow 등)를 쓰는 경우\n"
            friendly_msg += "      - OpenAI 공식의 모든 모델 이름을 지원한다고 가정하지 마세요\n"
            friendly_msg += "      - 그 업체의 실제 모델 ID로 바꿔야 합니다\n\n"
            friendly_msg += "   4. API 주소와 번역기 종류가 맞는지 확인\n"
            friendly_msg += "      - OpenAI 호환 인터페이스는 「OpenAI」또는 「OpenAI 고품질」번역기를 사용하세요\n"
            friendly_msg += "      - 사이트와 번역기 종류가 맞지 않으면 모델 판정이 잘못될 수 있습니다\n\n"
            friendly_msg += "   5. 모델이 최근 이름이 바뀌었거나 내려갔거나 채널이 이동한 경우\n"
            friendly_msg += "      - 해당 업체의 모델 광장이나 공식 문서를 확인하세요\n"
            friendly_msg += "      - 지금 사용 가능한 모델 이름으로 바꾼 뒤 다시 시도하세요\n\n"

        elif "API_404_ERROR" in real_error or "404" in real_error or "HTML错误页面" in real_error or "HTML 오류 페이지" in real_error:
            friendly_msg += "원인: API가 404 오류를 반환함\n\n"
            friendly_msg += "상세 설명:\n"
            friendly_msg += "   API가 정상적인 JSON이 아니라 HTML 형식의 404 오류 페이지를 돌려줬습니다.\n"
            friendly_msg += "   보통 API 주소가 잘못되었거나 모델 이름이 없을 때 발생합니다.\n\n"
            friendly_msg += "해결 방법:\n"
            friendly_msg += "   1. ⭐ API 주소 설정 확인 (가장 흔함)\n"
            friendly_msg += "      - 위치: 번역 설정 → 환경 변수 → OPENAI_API_BASE\n"
            friendly_msg += "      - 올바른 형식: https://api.openai.com/v1\n"
            friendly_msg += "      - 주의: 주소 끝은 반드시 /v1 이어야 하며, 경로를 더하거나 빼지 마세요\n\n"
            friendly_msg += "   2. 모델 이름이 맞는지 확인\n"
            friendly_msg += "      - 위치: 번역 설정 → 환경 변수 → OPENAI_MODEL\n"
            friendly_msg += "      - 모델 이름이 API가 제공하는 것과 완전히 같은지 확인\n"
            friendly_msg += "      - 주의: 모델 이름은 대소문자를 구분합니다\n"
            friendly_msg += "      - 팁: 「연결 테스트」로 사용 가능한 모델 목록을 볼 수 있습니다\n\n"
            friendly_msg += "   3. 사용자 지정 API(중계, 서드파티)를 쓰는 경우\n"
            friendly_msg += "      - 중계 서비스의 API 주소 형식을 확인하세요\n"
            friendly_msg += "      - 중계 서비스가 사용 중인 모델을 지원하는지 확인하세요\n"
            friendly_msg += "      - 중계 업체에 설정을 문의하세요\n\n"

        elif "api key" in real_error.lower() or "authentication" in real_error.lower() or "unauthorized" in real_error.lower() or "401" in real_error:
            friendly_msg += "원인: API 키 인증 실패\n\n"
            friendly_msg += "상세 설명:\n"
            friendly_msg += "   API 키가 잘못되었거나, 만료되었거나, 올바르게 설정되지 않았습니다.\n\n"
            friendly_msg += "해결 방법:\n"
            friendly_msg += "   1. API 키가 올바른지 확인\n"
            friendly_msg += "      - 위치: 번역 설정 → 환경 변수 설정 영역\n"
            friendly_msg += "      - 키에 불필요한 공백이나 줄바꿈이 없는지 확인\n\n"
            friendly_msg += "   2. API 키가 유효한지 확인\n"
            friendly_msg += "      - OpenAI: https://platform.openai.com/api-keys\n"
            friendly_msg += "      - Gemini: https://aistudio.google.com/app/apikey\n\n"
            friendly_msg += "   3. API 한도가 소진되었는지 확인\n"
            friendly_msg += "      - 해당 플랫폼에 로그인해서 잔액과 사용량을 확인하세요\n\n"

        elif (
            "connection" in real_error.lower()
            or "connect" in real_error.lower()
            or "failed to connect" in real_error.lower()
            or "could not connect to server" in real_error.lower()
            or "connection timed out" in real_error.lower()
            or "timed out after" in real_error.lower()
            or "连接" in real_error
            or "timeout" in real_error.lower()
            or "超时" in real_error
            or "network" in real_error.lower()
            or "网络" in real_error
            or "curl: (7)" in real_error.lower()
            or "curl: (28)" in real_error.lower()
            or "host" in real_error.lower()
            or "hostname" in real_error.lower()
            or "dns" in real_error.lower()
            or "getaddrinfo" in real_error.lower()
            or "failed to resolve" in real_error.lower()
            or "temporary failure in name resolution" in real_error.lower()
            or "name or service not known" in real_error.lower()
            or "no address associated with hostname" in real_error.lower()
            or "nodename nor servname provided" in real_error.lower()
            or "主机" in real_error
            or "解析" in real_error
            or "연결" in real_error
            or "시간 초과" in real_error
            or "네트워크" in real_error
            or "호스트" in real_error
            or "해석" in real_error
        ):
            friendly_msg += "원인: 네트워크 연결 또는 Host 해석 실패\n\n"
            friendly_msg += "상세 설명:\n"
            friendly_msg += "   API 서버에 연결할 수 없습니다. 네트워크 이상, 시간 초과, 또는 Host/DNS 해석 실패일 수 있습니다.\n\n"
            friendly_msg += "해결 방법:\n"
            friendly_msg += "   1. 네트워크 연결 확인\n"
            friendly_msg += "      - 컴퓨터가 인터넷에 정상적으로 접속되는지 확인하세요\n\n"
            friendly_msg += "   2. TUN(가상 네트워크 어댑터 모드) 켜기\n"
            friendly_msg += "      - 일부 프록시 환경에서는 TUN을 켜면 도메인 해석이 더 안정적입니다\n\n"
            friendly_msg += "   3. API 주소가 올바른지 확인\n"
            friendly_msg += "      - 위치: 번역 설정 → 환경 변수 → API_BASE\n"
            friendly_msg += "      - 기본값: https://api.openai.com/v1\n\n"

        elif "rate limit" in real_error.lower() or "429" in real_error or "too many requests" in real_error.lower():
            friendly_msg += "원인: API 요청이 거부됨 (HTTP 429)\n\n"
            friendly_msg += "상세 설명:\n"
            friendly_msg += "   HTTP 429 오류에는 여러 원인이 있습니다:\n"
            friendly_msg += "   • API 키가 잘못되었거나 유효하지 않음\n"
            friendly_msg += "   • 계정 잔액 부족 또는 미납\n"
            friendly_msg += "   • 요청 속도가 한도(RPM/TPM)를 초과함\n"
            friendly_msg += "   • 현재 계정 등급에서 해당 모델을 지원하지 않음\n\n"
            friendly_msg += "해결 방법 (순서대로 확인):\n"
            friendly_msg += "   1. ⭐ API 키가 올바른지 확인 (가장 흔함)\n"
            friendly_msg += "      - 위치: 번역 설정 → 환경 변수 설정 영역\n"
            friendly_msg += "      - 키에 불필요한 공백이나 줄바꿈이 없는지 확인\n"
            friendly_msg += "      - 「연결 테스트」로 키가 유효한지 확인\n\n"
            friendly_msg += "   2. 계정 잔액과 상태 확인\n"
            friendly_msg += "      - OpenAI: https://platform.openai.com/usage\n"
            friendly_msg += "      - Gemini: https://aistudio.google.com/app/apikey\n"
            friendly_msg += "      - 잔액이 충분하고 미납이 아닌지 확인\n"
            friendly_msg += "      - 계정이 제한되지 않았는지 확인\n\n"
            friendly_msg += "   3. 모델을 사용할 수 있는지 확인\n"
            friendly_msg += "      - 일부 모델은 특정 계정 등급이나 유료 요금제가 필요합니다\n"
            friendly_msg += "      - 예: GPT-4는 유료 계정이 필요하고, 무료 계정은 GPT-3.5만 사용할 수 있습니다\n"
            friendly_msg += "      - 계정이 지원하는 모델로 바꿔 보세요\n\n"
            friendly_msg += "   4. 요청 속도 낮추기\n"
            friendly_msg += "      - 위치: 일반 설정 → 분당 최대 요청 수\n"
            friendly_msg += "      - 권장: 3-10 (API 요금제에 따라 다름)\n"
            friendly_msg += "      - 무료 계정은 3을 권장합니다\n\n"
            friendly_msg += "   5. 잠시 후 다시 시도\n"
            friendly_msg += "      - 몇 분 기다린 뒤 다시 번역해 보세요\n\n"
            friendly_msg += "   6. API 요금제 업그레이드\n"
            friendly_msg += "      - API 제공 업체에 더 높은 요금제를 문의하세요\n\n"

        elif "403" in real_error or "forbidden" in real_error.lower():
            friendly_msg += "원인: 접근이 거부됨 (HTTP 403)\n\n"
            friendly_msg += "상세 설명:\n"
            friendly_msg += "   서버가 접근을 거부했습니다. 권한이 부족하거나 지역 제한일 수 있습니다.\n\n"
            friendly_msg += "해결 방법:\n"
            friendly_msg += "   1. API 키 권한 확인\n"
            friendly_msg += "      - 해당 서비스에 접근할 권한이 있는지 확인하세요\n\n"
            friendly_msg += "   2. 계정 상태 확인\n"
            friendly_msg += "      - 계정이 정지되거나 제한되지 않았는지 확인하세요\n\n"

        elif "Translation file not found" in real_error:
            json_name = ""
            marker = "Translation file not found or invalid:"
            if marker in real_error:
                json_name = os.path.basename(real_error.split(marker, 1)[1].strip())
            display_name = file_name or json_name
            if display_name:
                friendly_msg += f"{display_name}\n\n"
            friendly_msg += "원인: 이 이미지에 대응하는 번역 JSON이 없음\n\n"
            friendly_msg += "상세 설명:\n"
            friendly_msg += "   「TXT 가져온 후 번역 완료」는 이미 있는 JSON에 대사를 얹어 렌더하는 모드입니다.\n"
            if json_name:
                friendly_msg += f"   이 이미지는 JSON을 찾지 못했습니다. ({json_name})\n\n"
            else:
                friendly_msg += "   이 이미지는 JSON을 찾지 못했습니다.\n\n"

        elif "404" in real_error or "not found" in real_error.lower():
            friendly_msg += "원인: 리소스를 찾을 수 없음 (HTTP 404)\n\n"
            friendly_msg += "상세 설명:\n"
            friendly_msg += "   요청한 API 엔드포인트가 없거나 모델 이름이 잘못되었습니다.\n"
            friendly_msg += "   번역기 종류와 API 주소가 맞지 않을 수도 있습니다.\n\n"
            friendly_msg += "해결 방법:\n"
            friendly_msg += "   1. ⭐ 번역기 종류가 API 주소와 맞는지 확인 (가장 흔함)\n"
            friendly_msg += "      - API 주소가 xxxx/v1 형식(OpenAI 호환)이면\n"
            friendly_msg += "        → 「OpenAI」또는 「OpenAI 고품질」번역기를 선택하세요\n"
            friendly_msg += "      - Gemini 공식 API (generativelanguage.googleapis.com)를 쓰면\n"
            friendly_msg += "        → 「Gemini」또는 「Gemini 고품질」번역기를 선택하세요\n"
            friendly_msg += "      - 위치: 번역 설정 → 번역기\n\n"
            friendly_msg += "   2. API 주소가 올바른지 확인\n"
            friendly_msg += "      - 위치: 번역 설정 → 환경 변수 → API_BASE\n"
            friendly_msg += "      - OpenAI 기본값: https://api.openai.com/v1\n"
            friendly_msg += "      - Gemini 기본값: https://generativelanguage.googleapis.com\n"
            friendly_msg += "      - 주의: 주소 끝의 /v1 을 더하거나 빼지 마세요\n\n"
            friendly_msg += "   3. 모델 이름 확인\n"
            friendly_msg += "      - 위치: 번역 설정 → 환경 변수 → MODEL\n"
            friendly_msg += "      - 철자가 맞는지 확인 (예: gpt-5.2 이지 gpt52가 아님)\n"
            friendly_msg += "      - 「연결 테스트」로 사용 가능한 모델 목록 확인\n\n"
            friendly_msg += "   4. 모델 사용 가능 여부 확인\n"
            friendly_msg += "      - 일부 모델은 내려갔거나 이름이 바뀌었을 수 있습니다\n"
            friendly_msg += "      - 공식 문서에서 사용 가능한 모델 목록을 확인하세요\n\n"

        elif "500" in real_error or "internal server error" in real_error.lower():
            friendly_msg += "원인: 서버 내부 오류 (HTTP 500)\n\n"
            friendly_msg += "상세 설명:\n"
            friendly_msg += "   API 서버에서 내부 오류가 났습니다. 보통 일시적인 문제입니다.\n\n"
            friendly_msg += "해결 방법:\n"
            friendly_msg += "   1. ⭐ 재시도 횟수 늘리기 (권장)\n"
            friendly_msg += "      - 위치: 일반 설정 → 재시도 횟수\n"
            friendly_msg += "      - 권장: 10 이상\n"
            friendly_msg += "      - 서버 오류는 일시적인 경우가 많아 재시도하면 성공할 수 있습니다\n\n"
            friendly_msg += "   2. 잠시 후 다시 시도\n"
            friendly_msg += "      - 몇 분 기다려 서버가 회복되도록 하세요\n\n"
            friendly_msg += "   3. API 서비스 상태 확인\n"
            friendly_msg += "      - OpenAI: https://status.openai.com/\n"
            friendly_msg += "      - 대규모 장애가 있는지 확인하세요\n\n"

        elif any(code in real_error for code in ["502", "503", "504"]) or "bad gateway" in real_error.lower() or "service unavailable" in real_error.lower() or "gateway timeout" in real_error.lower():
            error_code = "502/503/504"
            if "502" in real_error:
                error_code = "502"
            elif "503" in real_error:
                error_code = "503"
            elif "504" in real_error:
                error_code = "504"

            friendly_msg += f"원인: 게이트웨이/서비스를 사용할 수 없음 (HTTP {error_code})\n\n"
            friendly_msg += "상세 설명:\n"
            friendly_msg += "   - 502: 게이트웨이가 잘못된 응답을 받음\n"
            friendly_msg += "   - 503: 서비스가 일시적으로 사용 불가 (보통 점검 또는 과부하)\n"
            friendly_msg += "   - 504: 게이트웨이 시간 초과\n\n"
            friendly_msg += "해결 방법:\n"
            friendly_msg += "   1. ⭐ 기다렸다가 다시 시도 (권장)\n"
            friendly_msg += "      - 이런 오류는 보통 일시적입니다\n"
            friendly_msg += "      - 5-10분 기다린 뒤 다시 번역하세요\n\n"
            friendly_msg += "   2. 재시도 횟수 늘리기\n"
            friendly_msg += "      - 위치: 일반 설정 → 재시도 횟수\n"
            friendly_msg += "      - 권장: 10 이상\n\n"
            friendly_msg += "   3. API 서비스 상태 확인\n"
            friendly_msg += "      - API 제공 업체의 상태 페이지를 확인하세요\n"
            friendly_msg += "      - OpenAI: https://status.openai.com/\n\n"
            friendly_msg += "   4. API 주소 바꾸기\n"
            friendly_msg += "      - 서드파티 API 중계를 쓰는 경우 주소를 바꿔 보세요\n\n"

        elif "content filter" in real_error.lower() or "content_filter" in real_error:
            friendly_msg += "원인: 콘텐츠가 보안 정책에 의해 차단됨\n\n"
            friendly_msg += "상세 설명:\n"
            friendly_msg += "   AI가 사용 정책을 위반할 수 있는 콘텐츠로 판단했습니다.\n\n"
            friendly_msg += "해결 방법:\n"
            friendly_msg += "   1. 이미지 내용 확인\n"
            friendly_msg += "      - 일부 민감한 콘텐츠는 API가 처리를 거부할 수 있습니다\n\n"
            friendly_msg += "   2. 번역기 바꾸기\n"
            friendly_msg += "      - 다른 번역기(Gemini, DeepL 등)를 사용해 보세요\n\n"
            friendly_msg += "   3. 재시도 횟수 늘리기\n"
            friendly_msg += "      - 위치: 일반 설정 → 재시도 횟수\n"
            friendly_msg += "      - 가끔 재시도하면 일시적인 필터 문제가 해결됩니다\n\n"

        elif "language not supported" in real_error.lower() or "LanguageUnsupportedException" in error_traceback:
            friendly_msg += "원인: 번역기가 현재 언어를 지원하지 않음\n\n"
            friendly_msg += "해결 방법:\n"
            friendly_msg += "   1. 번역기 바꾸기\n"
            friendly_msg += "      - 위치: 번역 설정 → 번역기\n"
            friendly_msg += "      - 권장: 더 많은 언어를 지원하는 번역기 (OpenAI, Gemini)\n\n"
            friendly_msg += "   2. 대상 언어 설정 확인\n"
            friendly_msg += "      - 위치: 번역 설정 → 대상 언어\n"
            friendly_msg += "      - 선택한 언어를 현재 번역기가 지원하는지 확인하세요\n\n"

        elif "blocked" in real_error.lower() or "request was blocked" in real_error.lower():
            friendly_msg += "원인: 요청이 API 제공 업체에 의해 차단됨\n\n"
            friendly_msg += "상세 설명:\n"
            friendly_msg += "   API 제공 업체(서드파티 중계일 수 있음)가 요청을 차단했습니다.\n"
            friendly_msg += "   보통 중계 서비스의 남용 방지 또는 콘텐츠 심사 때문입니다.\n\n"
            friendly_msg += "해결 방법:\n"
            friendly_msg += "   1. ⭐ API 제공 업체 바꾸기 (권장)\n"
            friendly_msg += "      - 서드파티 중계 API를 쓰는 경우 다른 업체로 바꿔 보세요\n"
            friendly_msg += "      - 또는 공식 API(api.openai.com)를 사용하세요\n\n"
            friendly_msg += "   2. 일반 번역기로 전환\n"
            friendly_msg += "      - 위치: 번역 설정 → 번역기\n"
            friendly_msg += "      - openai_hq를 openai로 변경 (이미지를 보내지 않음)\n"
            friendly_msg += "      - 일부 중계는 멀티모달(이미지+텍스트) 요청을 지원하지 않습니다\n\n"
            friendly_msg += "   3. API 키 상태 확인\n"
            friendly_msg += "      - API 키가 정지되거나 제한되지 않았는지 확인하세요\n"
            friendly_msg += "      - API 제공 업체에 계정 상태를 문의하세요\n\n"

        else:
            friendly_msg += "원인:\n"
            friendly_msg += f"   {error_message}\n\n"
            friendly_msg += "일반적인 해결 방법:\n"
            friendly_msg += "   1. 설정이 올바른지 확인\n"
            friendly_msg += "      - 번역기, API 키, 모델 이름 등\n\n"
            friendly_msg += "   2. 재시도 횟수 늘리기\n"
            friendly_msg += "      - 위치: 일반 설정 → 재시도 횟수\n"
            friendly_msg += "      - 권장: 10 이상\n\n"
            friendly_msg += "   3. 자세한 로그 확인\n"
            friendly_msg += "      - 로그 창에서 추가 오류 정보를 찾아보세요\n\n"

        friendly_msg += "원본 오류 정보:\n"
        friendly_msg += f"{_wrap_error_text(error_message)}\n"
        if error_traceback and "Traceback" in error_traceback:
            lines = error_traceback.split('\n')
            api_error_lines = []

            for line in lines:
                if line.strip() and any(keyword in line for keyword in ['BadRequest', 'Error code:', "'error':", "'message':", "{'error':"]):
                    api_error_lines.append(line.strip())

            if api_error_lines:
                friendly_msg += "\n"
                friendly_msg += _wrap_error_text('\n'.join(api_error_lines)) + "\n"

        for marker in ("🔍 ", "📝 ", "📋 "):
            friendly_msg = friendly_msg.replace(marker, "")

        return friendly_msg

    async def _do_processing(self):
        manga_logger = logging.getLogger('manga_translator')
        
        # 根据 verbose 配置设置日志级别
        verbose = self.config_dict.get('cli', {}).get('verbose', False)
        log_level = logging.DEBUG if verbose else logging.INFO
        manga_logger.setLevel(log_level)
        
        # 根日志器设为 DEBUG 以允许所有日志通过
        root_logger = logging.getLogger()
        root_logger.setLevel(logging.DEBUG)
        
        # 文件处理器始终为 DEBUG，其他处理器根据 verbose 设置
        for handler in root_logger.handlers:
            if isinstance(handler, logging.FileHandler):
                handler.setLevel(logging.DEBUG)  # 文件日志始终 DEBUG
            else:
                handler.setLevel(log_level)  # 控制台根据 verbose 设置

        results = []
        try:
            from manga_translator.config import (
                ColorizerConfig,
                Config,
                DetectorConfig,
                InpainterConfig,
                OcrConfig,
                RenderConfig,
                Translator,
                TranslatorConfig,
                UpscaleConfig,
            )
            from manga_translator.manga_translator import MangaTranslator

            self._log_info("--- 번역기를 초기화하는 중...")
            translator_params = self.config_dict.get('cli', {})
            translator_params.update(self.config_dict)
            
            # 根据 verbose 设置设置日志级别
            verbose = translator_params.get('verbose', False)
            if hasattr(self, 'log_service') and self.log_service:
                self.log_service.set_console_log_level(verbose)
            
            font_family = self.config_dict.get('render', {}).get('font_family')
            if font_family:
                translator_params['font_family'] = font_family

            translator = MangaTranslator(params=translator_params)
            self._log_info("--- 번역기 초기화 완료")
            
            # 注册进度钩子，接收后端的批次进度
            progress_signal = self.progress  # 捕获信号引用
            progress_context = {
                "offset": 0,
                "overall_total": 0,
                "processing_started_at": None,
                "use_backend_hook": True,
                "batch_concurrent": False,
                "detail": self._t("Processing"),
                "failed_count": 0,
            }

            def emit_eta_progress(current: int, total: int, detail: str | None = None):
                total = max(int(total or 0), 0)
                current = max(0, min(int(current or 0), total)) if total > 0 else 0
                elapsed_seconds = 0.0
                if progress_context["processing_started_at"] is not None:
                    elapsed_seconds = max(0.0, time.perf_counter() - progress_context["processing_started_at"])
                completed_count = max(0, current - progress_context["offset"])
                remaining_count = max(0, total - current)
                message = self._build_eta_progress_message(
                    completed_count=completed_count,
                    remaining_count=remaining_count,
                    elapsed_seconds=elapsed_seconds,
                    skipped_count=progress_context["offset"],
                    failed_count=progress_context["failed_count"],
                    detail=detail if detail is not None else progress_context["detail"],
                )
                progress_signal.emit(current, total, message)
            
            async def progress_hook(state: str, finished: bool):
                try:
                    if not progress_context["use_backend_hook"]:
                        return
                    if state.startswith("batch:"):
                        # 解析批次进度: "batch:start:end:total[:failed]"
                        parts = state.split(":")
                        if len(parts) >= 4:
                            batch_end = int(parts[2])
                            total = int(parts[3])
                            failed_count = progress_context["failed_count"]
                            if len(parts) >= 5:
                                try:
                                    failed_count = max(0, int(parts[4]))
                                except (TypeError, ValueError):
                                    failed_count = progress_context["failed_count"]
                            progress_context["failed_count"] = failed_count
                            if progress_context["batch_concurrent"]:
                                batch_end += progress_context["offset"]
                                total = progress_context["overall_total"] or (total + progress_context["offset"])
                            else:
                                total = progress_context["overall_total"] or total
                            emit_eta_progress(batch_end, total)
                except Exception:
                    pass  # 忽略进度更新错误，不影响翻译流程
            
            translator.add_progress_hook(progress_hook)

            explicit_keys = {'render', 'upscale', 'translator', 'detector', 'colorizer', 'inpainter', 'ocr'}
            remaining_config = {
                k: v for k, v in self.config_dict.items() 
                if k in Config.model_fields and k not in explicit_keys
            }

            render_config_data = self.config_dict.get('render', {}).copy()

            # 转换 direction 值：'h' -> 'horizontal', 'v' -> 'vertical'
            if 'direction' in render_config_data:
                direction_value = render_config_data['direction']
                if direction_value == 'h':
                    render_config_data['direction'] = 'horizontal'
                elif direction_value == 'v':
                    render_config_data['direction'] = 'vertical'

            translator_config_data = self.config_dict.get('translator', {}).copy()
            hq_prompt_path = translator_config_data.get('high_quality_prompt_path')
            if hq_prompt_path and not os.path.isabs(hq_prompt_path):
                full_prompt_path = os.path.join(self.root_dir, hq_prompt_path)
                if os.path.exists(full_prompt_path):
                    translator_config_data['high_quality_prompt_path'] = full_prompt_path
                else:
                    self._log_warning(f"--- WARNING: High quality prompt file not found at {full_prompt_path}")
            
            # 转换超分倍数：'不使用' -> None, '2'/'4' -> int
            upscale_config_data = self.config_dict.get('upscale', {}).copy()
            if 'upscale_ratio' in upscale_config_data:
                ratio_value = upscale_config_data['upscale_ratio']
                if ratio_value == '不使用' or ratio_value is None:
                    upscale_config_data['upscale_ratio'] = None
                elif isinstance(ratio_value, str) and ratio_value in ('x2', 'x4', 'DAT2 x4'):
                    # mangajanai 的字符串选项，直接保留
                    upscale_config_data['upscale_ratio'] = ratio_value
                else:
                    try:
                        upscale_config_data['upscale_ratio'] = int(ratio_value)
                    except (ValueError, TypeError):
                        upscale_config_data['upscale_ratio'] = None

            config = Config(
                render=RenderConfig(**render_config_data),
                upscale=UpscaleConfig(**upscale_config_data),
                translator=TranslatorConfig(**translator_config_data),
                detector=DetectorConfig(**self.config_dict.get('detector', {})),
                colorizer=ColorizerConfig(**self.config_dict.get('colorizer', {})),
                inpainter=InpainterConfig(**self.config_dict.get('inpainter', {})),
                ocr=OcrConfig(**self.config_dict.get('ocr', {})),
                **remaining_config
            )
            self._log_info("--- 설정 객체 생성 완료")

            translator_type = config.translator.translator
            is_hq = translator_type in [Translator.openai_hq, Translator.gemini_hq]
            batch_size = self.config_dict.get('cli', {}).get('batch_size', 1)

            # 准备save_info（所有模式都需要）
            output_format = self.config_dict.get('cli', {}).get('format')
            if not output_format or output_format == "不指定":
                output_format = None # Set to None to preserve original extension
            if self.config_dict.get('cli', {}).get('inpaint_only', False):
                output_format = 'png'

            # 收集输入文件夹列表（从file_to_folder_map中获取）
            input_folders = set()
            for file_path in self.files:
                folder = self.file_to_folder_map.get(file_path)
                if folder:
                    input_folders.add(os.path.normpath(folder))

            save_info = {
                'output_folder': self.output_folder,
                'format': output_format,
                'overwrite': overwrite_enabled(self.config_dict.get('cli', {}).get('overwrite', False)),
                'input_folders': input_folders,
                'save_to_source_dir': self.config_dict.get('cli', {}).get('save_to_source_dir', False)
            }

            # Filter out existing files if overwrite is False
            original_files = self.files
            skipped_files = []
            files_to_process = []
            
            # 获取 cli_config（用于检查特殊模式）
            cli_config = self.config_dict.get('cli', {})
            
            if not save_info['overwrite']:
                self._log_info("--- 🔍 이미 있는 파일을 확인하는 중 (덮어쓰기 감지가 꺼져 있음)...")
                
                for file_path in self.files:
                    try:
                        should_skip = False
                        
                        # 检查导出原文/翻译的TXT文件（如果启用）
                        if cli_config.get('translate_json_only', False):
                            from manga_translator.utils.path_manager import find_script_txt_for_mode
                            txt_path = find_script_txt_for_mode(
                                file_path, bool(cli_config.get('combine_txt', True))
                            )
                            if not txt_path:
                                should_skip = True
                        elif cli_config.get('template', False) and cli_config.get('save_text', False):
                            from manga_translator.utils.path_manager import find_script_txt_for_mode
                            txt_path = find_script_txt_for_mode(
                                file_path, bool(cli_config.get('combine_txt', True))
                            )
                            if txt_path:
                                should_skip = True
                        elif cli_config.get('generate_and_export', False):
                            from manga_translator.utils.path_manager import find_script_txt_for_mode
                            txt_path = find_script_txt_for_mode(
                                file_path, bool(cli_config.get('combine_txt', True))
                            )
                            if txt_path:
                                should_skip = True
                        else:
                            # 普通翻译模式 - 检查图片文件
                            output_path = self._calculate_output_path(file_path, save_info)
                            if os.path.exists(output_path):
                                should_skip = True
                        
                        if should_skip:
                            skipped_files.append(file_path)
                            results.append({'success': True, 'original_path': file_path, 'image_data': None, 'skipped': True})
                        else:
                            files_to_process.append(file_path)
                    except Exception as e:
                        # If check fails, assume it needs processing
                        self.logger.error(f"파일 확인 중 오류 {file_path}: {e}")
                        files_to_process.append(file_path)
                
                if skipped_files:
                    skip_msg = self._t("⏭️ Skipped {count} existing files.", count=len(skipped_files))
                    self._log_info(skip_msg)
                    self._log_info("--- ℹ️ 건너뛴 파일은 처리하지 않습니다. 기존 결과 파일은 덮어쓰지 않습니다")
                    # Update files list to only include those needing processing
                    self.files = files_to_process
                else:
                    self._log_info("--- ✅ 이미 있는 파일이 없어 모든 파일을 처리합니다")
            
            # Update total count for progress bar logic
            total_original_count = len(original_files)
            skipped_count = len(skipped_files)
            
            # 确定翻译流程模式
            workflow_mode = self._t("Normal Translation")
            workflow_tip = ""
            cli_config = self.config_dict.get('cli', {})
            if cli_config.get('novelai_mode', False):
                workflow_mode = self._t("NovelAI Mode")
                workflow_tip = self._t("Tip: Convert image text into text layers. Line-break language is auto-detected per image from OCR text boxes.")
            elif cli_config.get('upscale_only', False):
                workflow_mode = self._t("Upscale Only")
                workflow_tip = self._t("Tip: Only upscale images, no detection, OCR, translation or rendering")
            elif cli_config.get('colorize_only', False):
                workflow_mode = self._t("Colorize Only")
                workflow_tip = self._t("Tip: Only colorize images, no detection, OCR, translation or rendering")
            elif cli_config.get('generate_and_export', False):
                workflow_mode = self._t("Export Translation")
                workflow_tip = self._t("Tip: After exporting, check manga_translator_work/translation/ for 0000 script.txt or combined script.txt files")
            elif cli_config.get('template', False):
                workflow_mode = self._t("Export Original Text")
                workflow_tip = self._t("Tip: After exporting, manually translate 0000 script.txt in manga_translator_work/translation/, then use 'Import Translation and Render' mode")
            elif cli_config.get('rerender_only', False):
                workflow_mode = self._t("Re-render")
                workflow_tip = self._t("Tip: Re-render image files based on JSON and inpaint data")
            elif cli_config.get('load_text', False):
                workflow_mode = self._t("Import Translation and Render")
                workflow_tip = self._t("Tip: Will read TXT files from manga_translator_work/translation/ and render (0000 script.txt / combined script.txt)\nNotice: If you already edited dialogue in the editor, it will be overwritten by the TXT content.")
            elif cli_config.get('translate_json_only', False):
                workflow_mode = self._t("Translate JSON Only")
                workflow_tip = self._t("Tip: Requires existing JSON data. The app reads original text from JSON, translates it, writes results back to JSON, and deletes 0000 script.txt after success")
                 
                # TXT导入JSON的预处理已经统一到翻译器入口（manga_translator.py），这里不再需要

            # 检查是否启用并发模式
            batch_concurrent = self.config_dict.get('cli', {}).get('batch_concurrent', False)
            
            # 检查是否有不兼容并行的特殊模式
            load_text = self.config_dict.get('cli', {}).get('load_text', False)
            rerender_only = self.config_dict.get('cli', {}).get('rerender_only', False)
            translate_json_only = self.config_dict.get('cli', {}).get('translate_json_only', False)
            template = self.config_dict.get('cli', {}).get('template', False)
            save_text = self.config_dict.get('cli', {}).get('save_text', False)
            generate_and_export = self.config_dict.get('cli', {}).get('generate_and_export', False)
            colorize_only = self.config_dict.get('cli', {}).get('colorize_only', False)
            upscale_only = self.config_dict.get('cli', {}).get('upscale_only', False)
            inpaint_only = self.config_dict.get('cli', {}).get('inpaint_only', False)
            replace_translation = self.config_dict.get('cli', {}).get('replace_translation', False)
            
            is_template_save_mode = template and save_text
            has_incompatible_mode = (
                load_text or
                rerender_only or
                translate_json_only or
                is_template_save_mode or 
                generate_and_export or 
                colorize_only or 
                upscale_only or 
                inpaint_only or
                replace_translation
            )
            
            # 如果有不兼容模式，强制禁用并行
            if batch_concurrent and has_incompatible_mode:
                incompatible_modes = []
                if load_text:
                    incompatible_modes.append("번역 가져오기")
                if rerender_only:
                    incompatible_modes.append("다시 렌더링")
                if translate_json_only:
                    incompatible_modes.append("JSON만 번역")
                if is_template_save_mode:
                    incompatible_modes.append("원문 내보내기")
                if generate_and_export:
                    incompatible_modes.append("번역 내보내기")
                if colorize_only:
                    incompatible_modes.append("색칠만")
                if upscale_only:
                    incompatible_modes.append("업스케일만")
                if inpaint_only:
                    incompatible_modes.append("인페인팅만")
                if replace_translation:
                    incompatible_modes.append("번역 교체")
                
                self._log_warning(f"⚠️  동시 처리 파이프라인이 꺼졌습니다. 현재 모드 [{', '.join(incompatible_modes)}]는 동시 처리를 지원하지 않습니다")
                batch_concurrent = False

            if load_text and not rerender_only:
                translator._txt_export_job_paths = [os.path.abspath(path) for path in self.files]
            self._prepare_txt_export_folder_hooks(
                translator,
                enabled=is_template_save_mode,
            )

            progress_context["offset"] = skipped_count
            progress_context["overall_total"] = total_original_count
            progress_context["batch_concurrent"] = batch_concurrent
            progress_context["failed_count"] = 0
            if is_hq or (len(self.files) > 0 and batch_size > 1):
                self._log_info(f"--- 일괄 처리 시작 ({'고품질 모드' if is_hq else '일괄 모드'})")

                # 输出批量处理信息
                # total_images is the number of files to process
                total_images = len(self.files)
                
                # 如果启用并发模式，不分批加载（并发流水线内部会按需加载）
                if batch_concurrent:
                    progress_context["detail"] = self._t("Concurrent processing")
                    self._log_info(self._t("📊 Concurrent pipeline mode: {total} images (Total: {orig})", total=total_images, orig=total_original_count))
                    self._log_info(self._t("🔧 Translation workflow: {mode}", mode=workflow_mode))
                    self._log_info(self._t("📁 Output directory: {dir}", dir=self.output_folder))
                    if workflow_tip:
                        self._log_info(workflow_tip)
                    self._log_info(self._t("🚀 Starting translation..."))
                    
                    # 初始化进度条 (start from skipped_count)
                    emit_eta_progress(skipped_count, total_original_count, self._t("Concurrent processing"))
                    if total_images > 0:
                        progress_context["processing_started_at"] = time.perf_counter()
                    
                    if total_images > 0:
                        # 并发模式：直接传递所有文件路径，不预加载图片
                        images_with_configs = [(file_path, config) for file_path in self.files]
                        
                        # 调用翻译（并发流水线会自动处理）
                        all_contexts = await translator.translate_batch(
                            images_with_configs,
                            save_info=save_info,
                            global_offset=skipped_count,
                            global_total=total_original_count
                        )
                    else:
                        all_contexts = []
                else:
                    progress_context["detail"] = self._t("Batch processing")
                    # 非并发模式：和并发模式一样直接把路径交给后端，由后端按 batch_size 控制加载
                    # 计算后端总批次数（用于显示统一的进度）
                    # Note: This is an estimation for logging purposes
                    backend_total_batches = (total_images + batch_size - 1) // batch_size if batch_size > 0 else total_images
                    
                    # 显示批量处理信息
                    if skipped_count > 0:
                        self._log_info(self._t("📊 Batch processing mode: {total} images in {batches} batches", total=total_images, batches=backend_total_batches))
                        self._log_info(
                            self._t(
                                "--- ℹ️ {count} additional files were skipped (original total: {orig})",
                                count=skipped_count,
                                orig=total_original_count,
                            )
                        )
                    else:
                        self._log_info(self._t("📊 Batch processing mode: {total} images in {batches} batches", total=total_images, batches=backend_total_batches))
                    
                    self._log_info(self._t("🔧 Translation workflow: {mode}", mode=workflow_mode))
                    self._log_info(self._t("📁 Output directory: {dir}", dir=self.output_folder))
                    if workflow_tip:
                        self._log_info(workflow_tip)

                    # 交给后端按 batch_size 懒加载并处理
                    self._log_info(self._t("🚀 Starting translation..."))
                    
                    # 初始化进度条
                    emit_eta_progress(skipped_count, total_original_count, self._t("Batch processing"))
                    if total_images > 0:
                        progress_context["processing_started_at"] = time.perf_counter()
                    
                    if total_images > 0:
                        images_with_configs = [(file_path, config) for file_path in self.files]
                        all_contexts = await translator.translate_batch(
                            images_with_configs,
                            save_info=save_info,
                            global_offset=skipped_count,
                            global_total=total_original_count
                        )
                    else:
                        all_contexts = []
                
                # 并发模式和非并发模式都会到这里
                contexts = all_contexts

                # The backend now handles saving for batch jobs. We just need to collect the paths/status.
                success_count = 0
                failed_count = 0
                failed_items = []
                for ctx in contexts:
                    if not self._is_running: raise asyncio.CancelledError("Task stopped by user.")
                    if ctx:
                        image_name = self._get_context_value(ctx, 'image_name', 'Unknown') or 'Unknown'
                        file_name = os.path.basename(image_name)
                        # 检查是否有翻译错误
                        error_message = self._extract_context_error_message(ctx)
                        error_summary = self._normalize_error_summary(error_message)
                        if error_message:
                            results.append({'success': False, 'original_path': image_name, 'error': error_message})
                            failed_count += 1
                            failed_items.append({'file_name': file_name, 'summary': error_summary})
                            self._log_warning(f"\n⚠️ 이미지 {file_name} 번역 실패: {error_summary}")
                            self._log_error(error_message)
                        elif self._get_context_value(ctx, 'success'):
                            # 优先检查success标志（因为result可能被清理了）
                            # 计算后端保存的文件路径
                            output_path = self._calculate_output_path(image_name, save_info)
                            results.append({'success': True, 'original_path': image_name, 'image_data': None, 'output_path': output_path})
                            success_count += 1
                        elif self._get_context_value(ctx, 'result'):
                            output_path = self._calculate_output_path(image_name, save_info)
                            results.append({'success': True, 'original_path': image_name, 'image_data': None, 'output_path': output_path})
                            success_count += 1
                        else:
                            fallback_error = "번역 결과가 비어 있습니다"
                            results.append({'success': False, 'original_path': image_name, 'error': fallback_error})
                            failed_count += 1
                            failed_items.append({'file_name': file_name, 'summary': fallback_error})
                            self._log_warning(f"\n⚠️ 이미지 {file_name} 번역 실패: {fallback_error}")
                    else:
                        fallback_error = 'Batch translation returned no context'
                        results.append({'success': False, 'original_path': 'Unknown', 'error': fallback_error})
                        failed_count += 1
                        failed_items.append({'file_name': 'Unknown', 'summary': fallback_error})
                        self._log_warning(f"\n⚠️ 이미지 Unknown 번역 실패: {fallback_error}")

                if failed_count > 0:
                    self._log_warning(
                        self._build_batch_failure_log_message(
                            failed_items=failed_items,
                            total_failed=failed_count,
                        )
                    )
                    self._log_warning(
                        self._t(
                            "\n⚠️ Batch translation completed: {success}/{total} succeeded, {failed}/{total} failed",
                            success=success_count,
                            total=total_images,
                            failed=failed_count,
                        )
                    )
                else:
                    self._log_info(self._t("✅ Batch translation completed: {success}/{total} succeeded", success=success_count, total=total_images))
                self._log_info(self._t("💾 Files saved to: {dir}", dir=self.output_folder))
                if is_template_save_mode and success_count > 0:
                    self._finalize_original_text_export(translator, write_backup=False)

            else:
                progress_context["detail"] = self._t("Sequential processing")
                progress_context["use_backend_hook"] = False
                self._log_info("--- 순차 처리 시작...")
                total_files = len(self.files)

                # 输出顺序处理信息
                self._log_info(self._t("📊 Sequential processing mode: {total} images (Total: {orig})", total=total_files, orig=total_original_count))
                self._log_info(self._t("🔧 Translation workflow: {mode}", mode=workflow_mode))
                self._log_info(self._t("📁 Output directory: {dir}", dir=self.output_folder))
                if workflow_tip:
                    self._log_info(workflow_tip)

                # 初始化进度条
                emit_eta_progress(skipped_count, total_original_count, self._t("Sequential processing"))
                if total_files > 0:
                    progress_context["processing_started_at"] = time.perf_counter()
                
                success_count = 0
                for i, file_path in enumerate(self.files):
                    if not self._is_running:
                        raise asyncio.CancelledError("Task stopped by user.")

                    current_num = skipped_count + i + 1
                    self._log_info(
                        self._t(
                            "🔄 [{current}/{total}] Processing: {name}",
                            current=current_num,
                            total=total_original_count,
                            name=os.path.basename(file_path),
                        )
                    )

                    try:
                        # 使用二进制模式读取以避免Windows路径编码问题
                        with open(file_path, 'rb') as f:
                            image = open_pil_image(f, eager=True)
                        image.name = file_path

                        ctx = await translator.translate(image, config, image_name=image.name, save_info=save_info)
                        
                        # 检查翻译是否成功（批量模式下 ctx.result 可能为 None，但文件已由后端保存）
                        if ctx and ctx.success:
                            # 计算后端保存的文件路径
                            output_path = self._calculate_output_path(file_path, save_info)
                            self.file_processed.emit({
                                'success': True, 
                                'original_path': file_path, 
                                'image_data': ctx.result,  # 可能为 None（批量模式）
                                'output_path': output_path  # 后端保存的路径
                            })
                            success_count += 1
                            self._log_info(f"✅ [{current_num}/{total_files}] 완료: {os.path.basename(file_path)}")
                            emit_eta_progress(
                                current_num,
                                total_original_count,
                                self._t("Just finished: {name}", name=os.path.basename(file_path)),
                            )
                        else:
                            error_msg = getattr(ctx, 'translation_error', 'Translation returned no result') if ctx else 'Translation failed'
                            progress_context["failed_count"] += 1
                            self.file_processed.emit({'success': False, 'original_path': file_path, 'error': error_msg})
                            self._log_warning(f"❌ [{current_num}/{total_files}] 실패: {os.path.basename(file_path)}")
                            emit_eta_progress(
                                current_num,
                                total_original_count,
                                self._t("Failed: {name}", name=os.path.basename(file_path)),
                            )

                    except Exception as e:
                        self._log_error(f"❌ [{current_num}/{total_files}] 오류: {os.path.basename(file_path)} - {e}")
                        progress_context["failed_count"] += 1
                        self.file_processed.emit({'success': False, 'original_path': file_path, 'error': str(e)})
                        emit_eta_progress(
                            current_num,
                            total_original_count,
                            self._t("Failed: {name}", name=os.path.basename(file_path)),
                        )
                        # 抛出异常，终止整个翻译流程
                        raise

                self._log_info(f"✅ 순차 번역 완료: 성공 {success_count}/{total_files}장")
                self._log_info(f"💾 파일이 저장된 위치: {self.output_folder}")
                if is_template_save_mode and success_count > 0:
                    self._finalize_original_text_export(translator, write_backup=True)
            
            self.finished.emit(results)

        except asyncio.CancelledError as e:
            self._log_warning(f"Task cancelled: {e}")
            self.logger.warning(f"Task cancelled: {e}")
            self.error.emit(str(e))
        except Exception as e:
            import traceback
            error_message = str(e)
            error_traceback = traceback.format_exc()
            
            # 记录到logger，确保命令行能看到
            self.logger.error(f"Translation error: {error_message}")
            self.logger.error(error_traceback)
            
            # 构建友好的中文错误提示
            friendly_error = self._build_friendly_error_message(error_message, error_traceback)
            
            self.error.emit(friendly_error)
        finally:
            # 翻译结束后进行完整的内存清理（特别是CPU模式）
            try:
                # 显式清理大对象引用，帮助GC回收
                if 'translator' in locals():
                    # 确保卸载所有模型
                    if hasattr(translator, '_detector_cleanup_task') and translator._detector_cleanup_task:
                        translator._detector_cleanup_task.cancel()
                        try:
                            await translator._detector_cleanup_task
                        except asyncio.CancelledError:
                            pass
                    del translator
                if 'results' in locals():
                    del results
                if 'all_contexts' in locals():
                    del all_contexts
                if 'images_with_configs' in locals():
                    del images_with_configs
                
                from desktop_qt_ui.utils.memory_cleanup import full_memory_cleanup
                # 使用配置中的卸载模型开关
                unload_models = self.config_dict.get('app', {}).get('unload_models_after_translation', False)
                full_memory_cleanup(log_callback=self._log_info, unload_models=unload_models)
            except Exception as e:
                self._log_warning(f"--- [CLEANUP] Warning: 메모리 정리 중 오류: {e}")

    @pyqtSlot()
    def process(self):
        loop = None
        try:
            import asyncio
            import sys
            self._log_info("--- 작업 처리를 시작합니다...")

            # 在Windows上的工作线程中，需要手动初始化Windows Socket
            if sys.platform == 'win32':
                # 使用ctypes直接调用WSAStartup
                import ctypes
                
                try:
                    # WSADATA结构体大小
                    WSADATA_SIZE = 400
                    wsa_data = ctypes.create_string_buffer(WSADATA_SIZE)
                    # 调用WSAStartup，版本2.2
                    ws2_32 = ctypes.WinDLL('ws2_32')
                    result = ws2_32.WSAStartup(0x0202, wsa_data)
                    if result != 0:
                        self._log_error(f"--- [ERROR] WSAStartup failed with code {result}")
                except Exception as e:
                    self._log_error(f"--- [ERROR] Failed to initialize WSA: {e}")
                
                # 使用ProactorEventLoop（Windows默认）
                asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

            # 创建事件循环并保存任务引用
            try:
                loop = asyncio.new_event_loop()
            except Exception as e:
                self._log_error(f"--- [ERROR] Failed to create event loop: {e}")
                import traceback
                self._log_error(f"--- [ERROR] Traceback: {traceback.format_exc()}")
                raise
            
            asyncio.set_event_loop(loop)
            
            self._current_task = loop.create_task(self._do_processing())
            loop.run_until_complete(self._current_task)
            # 任务处理完成，不输出日志

        except asyncio.CancelledError:
            pass
        except Exception as e:
            import traceback
            error_msg = f"An error occurred in the asyncio runner: {str(e)}\n{traceback.format_exc()}"
            # 同时记录到logger，确保命令行能看到
            self.logger.error(error_msg)
            self.error.emit(error_msg)
        finally:
            if loop:
                shutdown_event_loop(loop, logger=self.logger, label="worker loop")
                # 清理完成，不输出日志



# ============================================================================
# 线程池版本的Worker类（使用QRunnable替代QThread，避免线程管理问题）
# ============================================================================

class WorkerSignals(QObject):
    """信号包装器，因为QRunnable不能直接发送信号"""
    finished = pyqtSignal(object)
    error = pyqtSignal(str)
    progress = pyqtSignal(str)
    translation_progress = pyqtSignal(int, int, str)
    file_processed = pyqtSignal(dict)


class FileScannerRunnable(QRunnable):
    """文件扫描任务（线程池版本）"""
    
    def __init__(self, source_files, excluded_subfolders, file_service, 
                 finished_callback, error_callback, progress_callback):
        super().__init__()
        self.source_files = source_files
        self.excluded_subfolders = excluded_subfolders.copy()
        self.file_service = file_service
        self.finished_callback = finished_callback
        self.error_callback = error_callback
        self.progress_callback = progress_callback
        self.file_to_folder_map = {}
        self.archive_to_temp_map = {}
        self.setAutoDelete(True)
        
        # ✅ 创建信号对象用于线程安全通信
        self.signals = WorkerSignals()
        if finished_callback:
            self.signals.finished.connect(lambda args: finished_callback(*args), type=Qt.ConnectionType.QueuedConnection)
        if error_callback:
            self.signals.error.connect(error_callback, type=Qt.ConnectionType.QueuedConnection)
        if progress_callback:
            self.signals.progress.connect(progress_callback, type=Qt.ConnectionType.QueuedConnection)
    
    def _t(self, key: str, **kwargs) -> str:
        i18n = get_i18n_manager()
        if i18n:
            return i18n.translate(key, **kwargs)
        return key

    def run(self):
        """在线程池中执行"""
        try:
            self._emit_progress(self._t("Scanning files..."))
            resolved_files = []
            processed_archives = set()
             
            # 分离文件和文件夹
            folders = []
            individual_files = []
            archive_files = []
            
            for path in self.source_files:
                if os.path.isdir(path):
                    folders.append(path)
                elif os.path.isfile(path):
                    if self.file_service.is_archive_file(path):
                        archive_files.append(path)
                    elif self.file_service.validate_image_file(path):
                        individual_files.append(path)

            from desktop_qt_ui.utils.archive_extractor import (
                check_output_extract_conflict,
                clear_output_extract_root,
                extract_images_from_archive,
                get_output_extract_dir,
                write_output_extract_marker,
            )

            output_base_dir = ''
            overwrite_extract = False
            try:
                cfg = self.file_service.config_service.get_config()
                output_base_dir = cfg.app.last_output_path
                overwrite_extract = overwrite_enabled(getattr(cfg.cli, 'overwrite', OVERWRITE_SKIP))
            except Exception:
                output_base_dir = ''
                overwrite_extract = False

            def _is_excluded(file_path: str) -> bool:
                if not self.excluded_subfolders:
                    return False
                for excluded_folder in self.excluded_subfolders:
                    try:
                        common = os.path.commonpath([excluded_folder, file_path])
                        if common == excluded_folder:
                            return True
                    except ValueError:
                        continue
                return False

            def _get_archive_output_base_dir(archive_path: str, scan_root: str = None) -> str:
                if not (output_base_dir and os.path.isdir(output_base_dir)):
                    return ''
                if not scan_root:
                    return output_base_dir

                archive_parent = os.path.normpath(os.path.dirname(archive_path))
                scan_root_norm = os.path.normpath(scan_root)
                try:
                    relative_parent = os.path.relpath(archive_parent, scan_root_norm)
                except ValueError:
                    return output_base_dir

                nested_base = os.path.join(output_base_dir, os.path.basename(scan_root_norm))
                if relative_parent != '.':
                    nested_base = os.path.join(nested_base, relative_parent)
                return os.path.normpath(nested_base)

            def _extract_archive(archive_path: str, scan_root: str = None) -> None:
                norm_archive = os.path.normcase(os.path.abspath(archive_path))
                if norm_archive in processed_archives:
                    return
                processed_archives.add(norm_archive)

                try:
                    self._emit_progress(
                        self._t("Extracting: {name}", name=os.path.basename(archive_path))
                    )
                    archive_output_base_dir = _get_archive_output_base_dir(archive_path, scan_root)
                    if archive_output_base_dir:
                        if check_output_extract_conflict(archive_output_base_dir, archive_path):
                            if not overwrite_extract:
                                self._emit_progress(
                                    self._t(
                                        "Skipping extract (name conflict, overwrite disabled): {name}",
                                        name=os.path.basename(archive_path),
                                    )
                                )
                                return
                            clear_output_extract_root(archive_output_base_dir, archive_path)
                        extract_dir = get_output_extract_dir(archive_output_base_dir, archive_path)
                        images, extracted_dir = extract_images_from_archive(archive_path, extract_dir)
                        if images:
                            write_output_extract_marker(archive_output_base_dir, archive_path)
                    else:
                        images, extracted_dir = extract_images_from_archive(archive_path)

                    if images:
                        self.archive_to_temp_map[archive_path] = extracted_dir
                        for img_path in images:
                            resolved_files.append(img_path)
                            self.file_to_folder_map[img_path] = archive_path
                        self._emit_progress(
                            self._t(
                                "Extracted {count} images from {name}",
                                count=len(images),
                                name=os.path.basename(archive_path),
                            )
                        )
                    else:
                        self._emit_progress(
                            self._t(
                                "Warning: no images found in {name}",
                                name=os.path.basename(archive_path),
                            )
                        )
                except Exception as e:
                    self._emit_progress(
                        self._t(
                            "Failed to extract {name}: {error}",
                            name=os.path.basename(archive_path),
                            error=e,
                        )
                    )

            # 处理顶层压缩包文件
            for archive_path in archive_files:
                _extract_archive(archive_path)
            
            # 清理排除列表
            if self.excluded_subfolders:
                excluded_to_remove = set()
                for excluded_folder in self.excluded_subfolders:
                    is_valid = False
                    for folder in folders:
                        try:
                            common = os.path.commonpath([folder, excluded_folder])
                            if common == os.path.normpath(folder):
                                is_valid = True
                                break
                        except ValueError:
                            continue
                    if not is_valid:
                        excluded_to_remove.add(excluded_folder)
                self.excluded_subfolders -= excluded_to_remove
            
            # 对文件夹进行自然排序
            folders.sort(key=self.file_service._natural_sort_key)
            
            # 按文件夹分组处理
            for folder in folders:
                self._emit_progress(
                    self._t("Scanning folder: {name}", name=os.path.basename(folder))
                )
                folder_files = self.file_service.get_image_files_from_folder(folder, recursive=True)
                folder_archives = self.file_service.get_archive_files_from_folder(folder, recursive=True)
                 
                # 过滤掉被排除的子文件夹中的文件
                if self.excluded_subfolders:
                    folder_files = [f for f in folder_files if not _is_excluded(f)]
                    folder_archives = [f for f in folder_archives if not _is_excluded(f)]

                # 处理文件夹内的压缩包文件
                for archive_path in folder_archives:
                    _extract_archive(archive_path, folder)
                 
                resolved_files.extend(folder_files)
                for file_path in folder_files:
                    self.file_to_folder_map[file_path] = folder
            
            # 处理单独添加的文件
            individual_files.sort(key=self.file_service._natural_sort_key)
            for file_path in individual_files:
                resolved_files.append(file_path)
                self.file_to_folder_map[file_path] = None

            unique_files = list(dict.fromkeys(resolved_files))
            self._emit_finished(unique_files, self.file_to_folder_map, self.archive_to_temp_map, self.excluded_subfolders)
            
        except Exception as e:
            self._emit_error(str(e))
    
    def _emit_finished(self, *args):
        """线程安全地发送完成信号"""
        self.signals.finished.emit(args)
    
    def _emit_error(self, msg):
        """线程安全地发送错误信号"""
        self.signals.error.emit(msg)
    
    def _emit_progress(self, msg):
        """线程安全地发送进度信号"""
        self.signals.progress.emit(msg)


class TranslationRunnable(QRunnable):
    """翻译任务（线程池版本）"""
    
    def __init__(self, files, config_dict, output_folder, root_dir, file_to_folder_map,
                 finished_callback, error_callback, progress_callback, file_processed_callback):
        super().__init__()
        self.files = files
        self.config_dict = config_dict
        self.output_folder = output_folder
        self.root_dir = root_dir
        self.file_to_folder_map = file_to_folder_map or {}
        self.finished_callback = finished_callback
        self.error_callback = error_callback
        
        self.progress_callback = progress_callback # Keep reference just in case
        self._is_running = True
        self._current_task = None
        self.logger = get_logger(__name__)
        self.file_service = get_file_service()
        self.setAutoDelete(True)
        
        # ✅ 创建信号对象用于线程安全通信
        self.signals = WorkerSignals()
        if finished_callback:
            self.signals.finished.connect(lambda args: finished_callback(*args), type=Qt.ConnectionType.QueuedConnection)
        if error_callback:
            self.signals.error.connect(error_callback, type=Qt.ConnectionType.QueuedConnection)
            
        if progress_callback:
            self.signals.translation_progress.connect(progress_callback, type=Qt.ConnectionType.QueuedConnection)
        if file_processed_callback:
            self.signals.file_processed.connect(file_processed_callback, type=Qt.ConnectionType.QueuedConnection)
    
    def stop(self):
        """停止任务"""
        self.logger.info("--- 중지 요청을 받았습니다")
        self._is_running = False
        if self._current_task and not self._current_task.done():
            self._current_task.cancel()
        
        try:
            from desktop_qt_ui.utils.memory_cleanup import full_memory_cleanup
            # 使用配置中的卸载模型开关（这里没有config_dict，默认使用False）
            full_memory_cleanup(log_callback=lambda msg: self.logger.info(str(msg).rstrip()), unload_models=False)
        except Exception as e:
            self.logger.warning(f"--- [CLEANUP] 정리 실패: {e}")
    
    def run(self):
        """在线程池中执行"""
        loop = None
        try:
            import asyncio
            import sys
            self.logger.info("--- 작업 처리를 시작합니다...")

            # Windows平台初始化
            if sys.platform == 'win32':
                import ctypes
                try:
                    WSADATA_SIZE = 400
                    wsa_data = ctypes.create_string_buffer(WSADATA_SIZE)
                    ws2_32 = ctypes.WinDLL('ws2_32')
                    result = ws2_32.WSAStartup(0x0202, wsa_data)
                    if result != 0:
                        self.logger.error(f"--- [ERROR] WSAStartup failed with code {result}")
                except Exception as e:
                    self.logger.error(f"--- [ERROR] Failed to initialize WSA: {e}")
                
                asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

            # 创建事件循环
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            # 创建并运行任务（复用TranslationWorker的_do_processing逻辑）
            worker = TranslationWorker(
                self.files, self.config_dict, self.output_folder, 
                self.root_dir, self.file_to_folder_map
            )
            worker._is_running = self._is_running
            
            # 用于接收 worker 的 finished 信号
            results = []
            worker_had_error = False

            def on_worker_finished(worker_results):
                results.extend(worker_results)

            def on_worker_error(msg):
                nonlocal worker_had_error
                worker_had_error = True
                self._emit_error(msg)
            
            # 连接信号到回调
            worker.progress.connect(lambda c, t, m: self._emit_progress(c, t, m))
            worker.file_processed.connect(lambda d: self._emit_file_processed(d))
            worker.error.connect(on_worker_error)
            worker.finished.connect(on_worker_finished)
            
            self._current_task = loop.create_task(worker._do_processing())
            loop.run_until_complete(self._current_task)
            
            # 任务完成，发送结果
            if not worker_had_error:
                self._emit_finished(results)

        except asyncio.CancelledError:
            pass
        except Exception as e:
            import traceback
            error_msg = f"번역 작업 오류: {str(e)}\n{traceback.format_exc()}"
            self.logger.error(error_msg)
            self._emit_error(error_msg)
        finally:
            if loop:
                shutdown_event_loop(loop, logger=self.logger, label="threadpool worker loop")
    
    def _emit_finished(self, results):
        """线程安全地发送完成信号"""
        self.signals.finished.emit((results,))
    
    def _emit_error(self, msg):
        """线程安全地发送错误信号"""
        self.signals.error.emit(msg)
    
    def _emit_progress(self, current, total, message):
        """线程安全地发送进度信号"""
        self.signals.translation_progress.emit(current, total, message)
    
    def _emit_file_processed(self, data):
        """线程安全地发送文件处理完成信号"""
        self.signals.file_processed.emit(data)

