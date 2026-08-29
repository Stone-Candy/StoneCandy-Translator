"""
用户组配置管理服务

负责管理用户组的参数配置，包括参数的可见性、只读状态和默认值。
"""

import json
import logging
import os
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class GroupService:
    """用户组配置管理服务"""
    
    def __init__(self, config_file: str = "manga_translator/server/data/group_config.json"):
        """
        初始化用户组服务
        
        Args:
            config_file: 用户组配置文件路径
        """
        self.config_file = config_file
        self.groups: Dict[str, Dict[str, Any]] = {}
        self._load_groups()
    
    def _load_groups(self) -> None:
        """从文件加载用户组配置"""
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.groups = data.get('groups', {})
                logger.info(f"Loaded {len(self.groups)} group(s) from {self.config_file}")
            else:
                logger.warning(f"Group config file not found: {self.config_file}")
                self._create_default_groups()
        except Exception as e:
            logger.error(f"Failed to load group config: {e}")
            self._create_default_groups()
    
    def _create_default_groups(self) -> None:
        """创建默认用户组配置"""
        self.groups = {
            "admin": {
                "name": "管理员组",
                "description": "拥有所有权限的管理员用户组",
                "parameter_config": {}
            },
            "default": {
                "name": "默认用户组",
                "description": "新用户的默认用户组",
                "parameter_config": {
                    "target_lang": {
                        "visible": True,
                        "readonly": False,
                        "default_value": "CHS"
                    }
                }
            }
        }
        self._save_groups()
    
    def _save_groups(self) -> None:
        """保存用户组配置到文件"""
        try:
            data = {
                "version": "1.0",
                "groups": self.groups
            }
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            logger.info(f"Saved group config to {self.config_file}")
        except Exception as e:
            logger.error(f"Failed to save group config: {e}")
    
    def get_group(self, group_name: str) -> Optional[Dict[str, Any]]:
        """
        获取用户组配置
        
        Args:
            group_name: 用户组名称
        
        Returns:
            用户组配置字典，如果不存在返回 None
        """
        return self.groups.get(group_name)
    
    def get_parameter_config(self, group_name: str, parameter: str) -> Optional[Dict[str, Any]]:
        """
        获取用户组中特定参数的配置
        
        Args:
            group_name: 用户组名称
            parameter: 参数名称
        
        Returns:
            参数配置字典，如果不存在返回 None
        """
        group = self.get_group(group_name)
        if not group:
            return None
        
        param_config = group.get('parameter_config', {})
        return param_config.get(parameter)
    
    def get_all_groups(self) -> Dict[str, Dict[str, Any]]:
        """获取所有用户组配置"""
        return self.groups
    
    def update_group(self, group_name: str, group_data: Dict[str, Any]) -> bool:
        """
        更新用户组配置
        
        Args:
            group_name: 用户组名称
            group_data: 用户组数据
        
        Returns:
            是否成功
        """
        try:
            self.groups[group_name] = group_data
            self._save_groups()
            return True
        except Exception as e:
            logger.error(f"Failed to update group {group_name}: {e}")
            return False
    
    def delete_group(self, group_name: str) -> bool:
        """
        删除用户组
        
        Args:
            group_name: 用户组名称
        
        Returns:
            是否成功
        """
        if group_name in ['admin', 'default']:
            logger.warning(f"Cannot delete system group: {group_name}")
            return False
        
        try:
            if group_name in self.groups:
                del self.groups[group_name]
                self._save_groups()
                return True
            return False
        except Exception as e:
            logger.error(f"Failed to delete group {group_name}: {e}")
            return False


# 全局用户组服务实例
_group_service: Optional[GroupService] = None


def get_group_service() -> GroupService:
    """获取用户组服务实例"""
    global _group_service
    if _group_service is None:
        _group_service = GroupService()
    return _group_service
