"""
持久化存储工具

提供原子性写入、备份和数据加载功能。
"""

import json
import logging
import os
import shutil
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


def atomic_write_json(file_path: str, data: Dict[str, Any], create_backup: bool = True) -> bool:
    """
    原子性地写入 JSON 文件
    
    使用临时文件和重命名操作确保写入的原子性，避免因中断导致数据损坏。
    
    Args:
        file_path: 目标文件路径
        data: 要写入的数据
        create_backup: 是否在写入前创建备份
    
    Returns:
        bool: 写入是否成功
    """
    try:
        file_path = Path(file_path)
        
        # 确保目录存在
        file_path.parent.mkdir(parents=True, exist_ok=True)
        
        # 如果文件存在且需要备份，创建备份
        if create_backup and file_path.exists():
            backup_path = file_path.with_suffix(file_path.suffix + '.backup')
            try:
                shutil.copy2(file_path, backup_path)
                logger.debug(f"Created backup: {backup_path}")
            except Exception as e:
                logger.warning(f"Failed to create backup: {e}")
        
        # 写入临时文件
        temp_fd, temp_path = tempfile.mkstemp(
            dir=file_path.parent,
            prefix=f".{file_path.name}.",
            suffix=".tmp"
        )
        
        try:
            with os.fdopen(temp_fd, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())  # 确保数据写入磁盘
            
            # 原子性地重命名临时文件为目标文件
            # 在 Windows 上，如果目标文件存在，需要先删除
            if os.name == 'nt' and file_path.exists():
                file_path.unlink()
            
            os.rename(temp_path, file_path)
            logger.debug(f"Successfully wrote to {file_path}")
            return True
            
        except Exception as e:
            # 清理临时文件
            try:
                os.unlink(temp_path)
            except Exception:
                pass
            raise e
            
    except Exception as e:
        logger.error(f"Failed to write {file_path}: {e}")
        return False


def load_json(file_path: str, default: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    加载 JSON 文件
    
    如果文件不存在或损坏，尝试从备份恢复。
    
    Args:
        file_path: 文件路径
        default: 如果文件不存在时返回的默认值
    
    Returns:
        Dict[str, Any]: 加载的数据
    """
    file_path = Path(file_path)
    
    # 尝试加载主文件
    if file_path.exists():
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                logger.debug(f"Successfully loaded {file_path}")
                return data
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse {file_path}: {e}")
            
            # 尝试从备份恢复
            backup_path = file_path.with_suffix(file_path.suffix + '.backup')
            if backup_path.exists():
                logger.info(f"Attempting to restore from backup: {backup_path}")
                try:
                    with open(backup_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        logger.info("Successfully restored from backup")
                        # 恢复主文件
                        atomic_write_json(str(file_path), data, create_backup=False)
                        return data
                except Exception as backup_error:
                    logger.error(f"Failed to restore from backup: {backup_error}")
        except Exception as e:
            logger.error(f"Failed to load {file_path}: {e}")
    
    # 返回默认值
    if default is not None:
        logger.info(f"Using default value for {file_path}")
        return default
    
    logger.warning(f"File {file_path} not found and no default provided")
    return {}


def create_backup(file_path: str, backup_dir: Optional[str] = None) -> Optional[str]:
    """
    创建文件的时间戳备份
    
    Args:
        file_path: 要备份的文件路径
        backup_dir: 备份目录（如果为 None，使用文件所在目录）
    
    Returns:
        Optional[str]: 备份文件路径，如果失败返回 None
    """
    try:
        file_path = Path(file_path)
        
        if not file_path.exists():
            logger.warning(f"File {file_path} does not exist, cannot create backup")
            return None
        
        # 确定备份目录
        if backup_dir:
            backup_dir_path = Path(backup_dir)
            backup_dir_path.mkdir(parents=True, exist_ok=True)
        else:
            backup_dir_path = file_path.parent
        
        # 创建带时间戳的备份文件名
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_name = f"{file_path.stem}_{timestamp}{file_path.suffix}"
        backup_path = backup_dir_path / backup_name
        
        # 复制文件
        shutil.copy2(file_path, backup_path)
        logger.info(f"Created backup: {backup_path}")
        return str(backup_path)
        
    except Exception as e:
        logger.error(f"Failed to create backup of {file_path}: {e}")
        return None


def cleanup_old_backups(backup_dir: str, pattern: str, keep_count: int = 5) -> int:
    """
    清理旧的备份文件，只保留最新的几个
    
    Args:
        backup_dir: 备份目录
        pattern: 文件名模式（glob 格式）
        keep_count: 保留的备份数量
    
    Returns:
        int: 删除的文件数量
    """
    try:
        backup_dir_path = Path(backup_dir)
        
        if not backup_dir_path.exists():
            return 0
        
        # 获取所有匹配的备份文件
        backup_files = sorted(
            backup_dir_path.glob(pattern),
            key=lambda p: p.stat().st_mtime,
            reverse=True
        )
        
        # 删除多余的备份
        deleted_count = 0
        for backup_file in backup_files[keep_count:]:
            try:
                backup_file.unlink()
                deleted_count += 1
                logger.debug(f"Deleted old backup: {backup_file}")
            except Exception as e:
                logger.warning(f"Failed to delete {backup_file}: {e}")
        
        if deleted_count > 0:
            logger.info(f"Cleaned up {deleted_count} old backup(s)")
        
        return deleted_count
        
    except Exception as e:
        logger.error(f"Failed to cleanup backups: {e}")
        return 0


def ensure_directory(dir_path: str) -> bool:
    """
    确保目录存在
    
    Args:
        dir_path: 目录路径
    
    Returns:
        bool: 是否成功
    """
    try:
        Path(dir_path).mkdir(parents=True, exist_ok=True)
        return True
    except Exception as e:
        logger.error(f"Failed to create directory {dir_path}: {e}")
        return False
