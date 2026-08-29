"""
文件服务层
处理文件和文件夹的选择、验证、拖拽等操作
"""
import base64
import json
import logging
import mimetypes
import os
import shutil
import sys
from typing import List, Optional, Set, Tuple

import cv2
import numpy as np
from PIL import Image

# 添加项目根目录到路径以便导入path_manager
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
from manga_translator.utils import open_pil_image
from manga_translator.utils.path_manager import find_json_path


def natural_sort_key(path: str):
    """
    생성 자연 정렬 키. 숫자 구간은 정수로 비교한다.
    예: file1.jpg, file2.jpg, file10.jpg → 1, 2, 10

    전체 경로를 기준으로 비교해서 하위 폴더 이름도 같은 규칙으로 정렬한다.
    예: 제1화/001.jpg, 제2화/001.jpg, 제10화/001.jpg → 1, 2, 10
    """
    import re

    normalized_path = path.replace('\\', '/')
    parts = []
    for part in re.split(r'(\d+)', normalized_path):
        if part.isdigit():
            parts.append((False, int(part)))
        elif part:
            parts.append((True, part.lower()))
    return parts


class FileService:
    """文件操作服务"""
    
    def __init__(self):
        from services import get_config_service
        self.logger = logging.getLogger(__name__)
        self.config_service = get_config_service()
        # 支持的图片格式
        self.supported_image_extensions = {
            '.png', '.jpg', '.jpeg', '.bmp', '.gif', '.webp', '.avif', '.tiff', '.tif', '.heic', '.heif'
        }
        # 支持的压缩包/文档格式
        self.supported_archive_extensions = {
            '.pdf', '.epub', '.cbz', '.cbr', '.zip'
        }
        # 支持的配置文件格式
        self.supported_config_extensions = {
            '.json', '.yaml', '.yml', '.toml'
        }

    def load_translation_json(self, image_path: str, image: Image.Image = None) -> Tuple[List[dict], Optional[np.ndarray], Optional[Tuple[int, int]]]:
        """
        根据给定的图片路径，加载关联的 _translations.json 文件。
        优先从新目录结构加载，支持向后兼容。
        返回 regions, raw_mask, original_size。
        """
        # 使用path_manager查找JSON文件（新位置优先）
        json_path = find_json_path(image_path)
        regions = []
        raw_mask = None
        original_size = None

        if not json_path:
            self.logger.warning(f"JSON file not found for {os.path.basename(image_path)}")
            return regions, raw_mask, original_size

        self.logger.debug(f"Loading JSON from: {json_path}")

        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            image_key = os.path.abspath(image_path)
            
            if image_key not in data:
                if data:
                    first_key = next(iter(data))
                    self.logger.warning(f"Exact image path '{image_key}' not found in JSON. Using first available key '{first_key}'.")
                    image_data = data[first_key]
                else:
                    image_data = {}
            else:
                image_data = data[image_key]

            regions = image_data.get('regions', [])

            config = self.config_service.get_config()
            default_target_lang = config.translator.target_lang if config else None

            if default_target_lang:
                for region in regions:
                    if not region.get('target_lang'):
                        region['target_lang'] = default_target_lang

            # 旧 JSON 兼容:缺 translation_raw 时用 translation 回填,
            # 保证编辑器"替换前译文"框始终有值显示
            for region in regions:
                if 'translation_raw' not in region:
                    region['translation_raw'] = region.get('translation', '')

            # 끝 [BR] 빈 줄 제거. 저장된 font_size는 그대로 둔다.
            try:
                from editor.geometry_commit_pipeline import repair_region_font_box_consistency

                for region in regions:
                    if isinstance(region, dict):
                        repair_region_font_box_consistency(region)
            except Exception as e:
                self.logger.debug("Skipped region font/box repair on load: %s", e)

            mask_data = image_data.get('mask_raw')
            if isinstance(mask_data, str):
                try:
                    img_bytes = base64.b64decode(mask_data)
                    img_array = np.frombuffer(img_bytes, dtype=np.uint8)
                    raw_mask = cv2.imdecode(img_array, cv2.IMREAD_UNCHANGED)
                except Exception as e:
                    self.logger.error(f"Failed to decode base64 mask in {os.path.basename(json_path)}: {e}")
                    raw_mask = None
            elif isinstance(mask_data, list):
                raw_mask = np.array(mask_data, dtype=np.uint8)
            
            original_size = (image_data.get('original_width'), image_data.get('original_height'))

            self.logger.debug(f"Loaded {len(regions)} regions from {os.path.basename(json_path)}")

        except Exception as e:
            import traceback
            self.logger.error(f"Failed to load or parse JSON file {json_path}: {e}")
            self.logger.error(f"Traceback: {traceback.format_exc()}")
            return [], None, None

        return regions, raw_mask, original_size
        
    def validate_image_file(self, file_path: str) -> bool:
        """验证是否为有效的图片文件或压缩包文件"""
        try:
            if not os.path.exists(file_path):
                return False
                
            # 检查文件扩展名
            _, ext = os.path.splitext(file_path)
            ext_lower = ext.lower()
            
            # 支持压缩包格式
            if ext_lower in self.supported_archive_extensions:
                return os.access(file_path, os.R_OK)
            
            if ext_lower not in self.supported_image_extensions:
                return False
                
            # 检查MIME类型
            mime_type, _ = mimetypes.guess_type(file_path)
            if mime_type and not mime_type.startswith('image/'):
                return False
                
            # 检查文件是否可读
            if not os.access(file_path, os.R_OK):
                return False
                
            return True
            
        except Exception as e:
            self.logger.error(f"이미지 파일 검증 실패 {file_path}: {e}")
            return False
    
    def is_archive_file(self, file_path: str) -> bool:
        """检查文件是否是压缩包/文档格式"""
        _, ext = os.path.splitext(file_path)
        return ext.lower() in self.supported_archive_extensions
    
    def validate_config_file(self, file_path: str) -> bool:
        """验证是否为有效的配置文件"""
        try:
            if not os.path.exists(file_path):
                return False
                
            _, ext = os.path.splitext(file_path)
            return ext.lower() in self.supported_config_extensions
            
        except Exception as e:
            self.logger.error(f"설정 파일 검증 실패 {file_path}: {e}")
            return False
    
    def _natural_sort_key(self, path: str):
        return natural_sort_key(path)
    
    def get_image_files_from_folder(self, folder_path: str, recursive: bool = True) -> List[str]:
        """从文件夹获取所有图片文件（默认递归查找所有子文件夹），忽略manga_translator_work目录"""
        image_files = []

        try:
            if not os.path.exists(folder_path) or not os.path.isdir(folder_path):
                return image_files

            if recursive:
                # 递归搜索，按子文件夹分组排序
                for root, dirs, files in os.walk(folder_path):
                    # 移除manga_translator_work目录，避免遍历
                    if 'manga_translator_work' in dirs:
                        dirs.remove('manga_translator_work')
                    
                    # 对dirs进行自然排序，确保os.walk按正确顺序遍历
                    dirs.sort(key=self._natural_sort_key)
                    
                    # 收集当前目录的图片文件
                    current_files = []
                    for file in files:
                        file_path = os.path.join(root, file)
                        ext = os.path.splitext(file)[1].lower()
                        if ext in self.supported_image_extensions and os.path.isfile(file_path):
                            current_files.append(file_path)
                    
                    # 对当前目录的文件进行自然排序
                    current_files.sort(key=self._natural_sort_key)
                    image_files.extend(current_files)
            else:
                # 只搜索当前目录，忽略manga_translator_work目录
                for file in os.listdir(folder_path):
                    file_path = os.path.join(folder_path, file)
                    ext = os.path.splitext(file)[1].lower()
                    if os.path.isfile(file_path) and ext in self.supported_image_extensions:
                        image_files.append(file_path)
                
                # 使用自然排序（支持数字排序）
                image_files.sort(key=self._natural_sort_key)

        except Exception as e:
            self.logger.error(f"폴더 이미지 가져오기 실패 {folder_path}: {e}")
            
        return image_files

    def get_archive_files_from_folder(self, folder_path: str, recursive: bool = True) -> List[str]:
        """从文件夹获取所有压缩包/文档文件（默认递归查找所有子文件夹），忽略manga_translator_work目录"""
        archive_files = []

        try:
            if not os.path.exists(folder_path) or not os.path.isdir(folder_path):
                return archive_files

            if recursive:
                for root, dirs, files in os.walk(folder_path):
                    if 'manga_translator_work' in dirs:
                        dirs.remove('manga_translator_work')
                    dirs.sort(key=self._natural_sort_key)

                    current_files = []
                    for file in files:
                        file_path = os.path.join(root, file)
                        ext = os.path.splitext(file)[1].lower()
                        if ext in self.supported_archive_extensions and os.path.isfile(file_path):
                            current_files.append(file_path)

                    current_files.sort(key=self._natural_sort_key)
                    archive_files.extend(current_files)
            else:
                for file in os.listdir(folder_path):
                    file_path = os.path.join(folder_path, file)
                    ext = os.path.splitext(file)[1].lower()
                    if os.path.isfile(file_path) and ext in self.supported_archive_extensions:
                        archive_files.append(file_path)

                archive_files.sort(key=self._natural_sort_key)

        except Exception as e:
            self.logger.error(f"폴더 압축 파일 가져오기 실패 {folder_path}: {e}")

        return archive_files
    
    def filter_valid_image_files(self, file_paths: List[str]) -> List[str]:
        """过滤出有效的图片文件"""
        valid_files = []
        
        for file_path in file_paths:
            if self.validate_image_file(file_path):
                valid_files.append(file_path)
            else:
                self.logger.warning(f"잘못된 파일을 건너뜁니다: {file_path}")
                
        return valid_files
    
    def process_dropped_files(self, dropped_data: str) -> Tuple[List[str], List[str]]:
        """处理拖拽的文件数据
        
        Returns:
            Tuple[List[str], List[str]]: (有效的图片文件列表, 错误信息列表)
        """
        image_files = []
        errors = []
        
        try:
            # 解析拖拽数据
            file_paths = self._parse_drop_data(dropped_data)
            
            for file_path in file_paths:
                if os.path.isfile(file_path):
                    if self.validate_image_file(file_path):
                        image_files.append(file_path)
                    else:
                        errors.append(f"지원하지 않는 이미지 형식: {os.path.basename(file_path)}")
                        
                elif os.path.isdir(file_path):
                    # 处理文件夹
                    folder_images = self.get_image_files_from_folder(file_path)
                    if folder_images:
                        image_files.extend(folder_images)
                    else:
                        errors.append(f"文件夹中没有找到图片: {os.path.basename(file_path)}")
                else:
                    errors.append(f"파일이 존재하지 않습니다: {os.path.basename(file_path)}")
                    
        except Exception as e:
            self.logger.error(f"드래그 파일 처리 실패: {e}")
            errors.append(f"드래그한 파일을 처리하는 중 오류: {str(e)}")
            
        return image_files, errors
    
    def _parse_drop_data(self, dropped_data: str) -> List[str]:
        """解析拖拽数据，提取文件路径"""
        file_paths = []
        
        # 处理不同操作系统的换行符
        lines = dropped_data.replace('\r\n', '\n').replace('\r', '\n').split('\n')
        
        for line in lines:
            line = line.strip()
            if line:
                # 移除可能的URI前缀
                if line.startswith('file:///'):
                    line = line[8:]  # 移除 'file:///'
                elif line.startswith('file://'):
                    line = line[7:]  # 移除 'file://'
                
                # URL解码
                try:
                    import urllib.parse
                    line = urllib.parse.unquote(line)
                except Exception:
                    pass
                
                if os.path.exists(line):
                    file_paths.append(os.path.abspath(line))
                    
        return file_paths
    
    def get_file_info(self, file_path: str) -> dict:
        """获取文件信息"""
        try:
            if not os.path.exists(file_path):
                return {'error': '파일이 존재하지 않습니다'}
                
            stat = os.stat(file_path)
            file_info = {
                'name': os.path.basename(file_path),
                'path': os.path.abspath(file_path),
                'size': stat.st_size,
                'size_human': self._format_file_size(stat.st_size),
                'modified': stat.st_mtime,
                'is_readable': os.access(file_path, os.R_OK),
                'is_writable': os.access(file_path, os.W_OK)
            }
            
            if self.validate_image_file(file_path):
                file_info['type'] = 'image'
                # 获取图片尺寸
                try:
                    with open_pil_image(file_path, eager=False) as img:
                        file_info['width'] = img.width
                        file_info['height'] = img.height
                        file_info['format'] = img.format
                except Exception as e:
                    self.logger.warning(f"이미지 정보 가져오기 실패 {file_path}: {e}")
                    
            return file_info
            
        except Exception as e:
            self.logger.error(f"파일 정보 가져오기 실패 {file_path}: {e}")
            return {'error': str(e)}
    
    def _format_file_size(self, size_bytes: int) -> str:
        """格式化文件大小"""
        if size_bytes < 1024:
            return f"{size_bytes} B"
        elif size_bytes < 1024**2:
            return f"{size_bytes/1024:.1f} KB"
        elif size_bytes < 1024**3:
            return f"{size_bytes/(1024**2):.1f} MB"
        else:
            return f"{size_bytes/(1024**3):.1f} GB"
    
    def create_backup(self, file_path: str, backup_dir: Optional[str] = None) -> str:
        """创建文件备份"""
        try:
            if backup_dir is None:
                backup_dir = os.path.join(os.path.dirname(file_path), 'backups')
                
            os.makedirs(backup_dir, exist_ok=True)
            
            # 生成备份文件名
            import time
            timestamp = time.strftime('%Y%m%d_%H%M%S')
            name, ext = os.path.splitext(os.path.basename(file_path))
            backup_name = f"{name}_{timestamp}{ext}"
            backup_path = os.path.join(backup_dir, backup_name)
            
            # 复制文件
            shutil.copy2(file_path, backup_path)
            self.logger.info(f"백업 생성: {backup_path}")
            
            return backup_path
            
        except Exception as e:
            self.logger.error(f"백업 생성 실패 {file_path}: {e}")
            raise
    
    def cleanup_temp_files(self, temp_dir: str, max_age_hours: int = 24) -> None:
        """清理临时文件"""
        try:
            if not os.path.exists(temp_dir):
                return
                
            import time
            current_time = time.time()
            max_age_seconds = max_age_hours * 3600
            
            for root, dirs, files in os.walk(temp_dir):
                for file in files:
                    file_path = os.path.join(root, file)
                    try:
                        if current_time - os.path.getmtime(file_path) > max_age_seconds:
                            os.remove(file_path)
                            self.logger.info(f"만료된 임시 파일 삭제: {file_path}")
                    except Exception as e:
                        self.logger.warning(f"임시 파일 삭제 실패 {file_path}: {e}")
                        
        except Exception as e:
            self.logger.error(f"임시 파일 정리 실패: {e}")
    
    def get_supported_image_extensions(self) -> Set[str]:
        """获取支持的图片文件扩展名"""
        return self.supported_image_extensions.copy()
    
    def get_supported_config_extensions(self) -> Set[str]:
        """获取支持的配置文件扩展名"""
        return self.supported_config_extensions.copy()
    
    def normalize_path(self, path: str) -> str:
        """标准化路径"""
        return os.path.normpath(os.path.abspath(path))
