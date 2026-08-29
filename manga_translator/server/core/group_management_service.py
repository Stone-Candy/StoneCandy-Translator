"""
User Group Management Service

实现用户组的创建、重命名、删除和配置管理功能。
"""

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from manga_translator.server.models.group_models import UserGroup
from manga_translator.server.repositories.group_repository import GroupRepository

logger = logging.getLogger(__name__)


class GroupManagementService:
    """用户组管理服务"""
    
    def __init__(self, group_repo: GroupRepository, accounts_file: str):
        """
        初始化用户组管理服务
        
        Args:
            group_repo: 用户组仓库实例
            accounts_file: 账户文件路径
        """
        self.group_repo = group_repo
        self.accounts_file = accounts_file
    
    def create_group(
        self,
        group_id: str,
        name: str,
        description: str,
        admin_id: str,
        permissions: Optional[Dict[str, Any]] = None,
        quota_limits: Optional[Dict[str, Any]] = None,
        visible_presets: Optional[List[str]] = None,
        parameter_config: Optional[Dict[str, Any]] = None
    ) -> Optional[UserGroup]:
        """
        创建新的用户组
        
        Args:
            group_id: 用户组ID
            name: 用户组名称
            description: 描述
            admin_id: 创建者管理员ID
            permissions: 权限配置
            quota_limits: 配额限制
            visible_presets: 可见预设列表
            parameter_config: 参数配置
        
        Returns:
            UserGroup: 创建的用户组对象，如果失败则返回None
        """
        try:
            # 检查用户组是否已存在
            if self.group_repo.group_exists(group_id):
                logger.error(f"Group '{group_id}' already exists")
                return None
            
            # 创建用户组数据
            group_data = {
                "name": name,
                "description": description,
                "parameter_config": parameter_config or {}
            }
            
            # 创建用户组
            success = self.group_repo.create_group(group_id, group_data)
            
            if not success:
                logger.error(f"Failed to create group '{group_id}'")
                return None
            
            # 记录审计日志
            self._log_audit(admin_id, "create_group", {
                "group_id": group_id,
                "name": name
            })
            
            logger.info(f"Created group '{group_id}' by admin '{admin_id}'")
            
            # 返回用户组对象
            return UserGroup(
                id=group_id,
                name=name,
                description=description,
                permissions=permissions or {},
                quota_limits=quota_limits or {},
                visible_presets=visible_presets or [],
                created_at=datetime.now(timezone.utc).isoformat(),
                created_by=admin_id,
                is_system=False
            )
            
        except Exception as e:
            logger.error(f"Error creating group '{group_id}': {e}")
            return None
    
    def rename_group(
        self,
        old_group_id: str,
        new_group_id: str,
        new_name: str,
        admin_id: str
    ) -> bool:
        """
        重命名用户组
        
        Args:
            old_group_id: 当前用户组ID
            new_group_id: 新用户组ID
            new_name: 新用户组名称
            admin_id: 管理员ID
        
        Returns:
            bool: 是否成功
        """
        try:
            # 检查是否是系统组
            if self.group_repo.is_system_group(old_group_id):
                logger.error(f"Cannot rename system group '{old_group_id}'")
                return False
            
            # 检查旧组是否存在
            if not self.group_repo.group_exists(old_group_id):
                logger.error(f"Group '{old_group_id}' does not exist")
                return False
            
            # 检查新组ID是否已存在
            if self.group_repo.group_exists(new_group_id):
                logger.error(f"Group '{new_group_id}' already exists")
                return False
            
            # 重命名用户组
            success = self.group_repo.rename_group(old_group_id, new_group_id, new_name)
            
            if not success:
                logger.error(f"Failed to rename group '{old_group_id}' to '{new_group_id}'")
                return False
            
            # 更新所有属于该组的用户的组关联
            self._update_user_group_associations(old_group_id, new_group_id)
            
            # 记录审计日志
            self._log_audit(admin_id, "rename_group", {
                "old_group_id": old_group_id,
                "new_group_id": new_group_id,
                "new_name": new_name
            })
            
            logger.info(f"Renamed group '{old_group_id}' to '{new_group_id}' by admin '{admin_id}'")
            return True
            
        except Exception as e:
            logger.error(f"Error renaming group '{old_group_id}': {e}")
            return False
    
    def delete_group(self, group_id: str, admin_id: str) -> bool:
        """
        删除用户组
        
        Args:
            group_id: 用户组ID
            admin_id: 管理员ID
        
        Returns:
            bool: 是否成功
        """
        try:
            # 检查是否是系统组
            if self.group_repo.is_system_group(group_id):
                logger.error(f"Cannot delete system group '{group_id}'")
                return False
            
            # 检查组是否存在
            if not self.group_repo.group_exists(group_id):
                logger.error(f"Group '{group_id}' does not exist")
                return False
            
            # 将该组的所有用户移动到default组
            moved_count = self._move_users_to_default_group(group_id)
            
            # 删除用户组
            success = self.group_repo.delete_group(group_id)
            
            if not success:
                logger.error(f"Failed to delete group '{group_id}'")
                return False
            
            # 记录审计日志
            self._log_audit(admin_id, "delete_group", {
                "group_id": group_id,
                "moved_users": moved_count
            })
            
            logger.info(f"Deleted group '{group_id}' by admin '{admin_id}', moved {moved_count} users to default")
            return True
            
        except Exception as e:
            logger.error(f"Error deleting group '{group_id}': {e}")
            return False
    
    def get_all_groups(self) -> List[Dict[str, Any]]:
        """
        获取所有用户组
        
        Returns:
            List[Dict]: 用户组列表
        """
        try:
            groups = self.group_repo.get_all_groups()
            
            # 转换为列表格式
            result = []
            for group_id, group_data in groups.items():
                result.append({
                    "id": group_id,
                    "name": group_data.get("name", group_id),
                    "description": group_data.get("description", ""),
                    "parameter_config": group_data.get("parameter_config", {}),
                    "allowed_translators": group_data.get("allowed_translators", ["*"]),
                    "denied_translators": group_data.get("denied_translators", []),
                    "allowed_ocr": group_data.get("allowed_ocr", ["*"]),
                    "denied_ocr": group_data.get("denied_ocr", []),
                    "allowed_colorizers": group_data.get("allowed_colorizers", ["*"]),
                    "denied_colorizers": group_data.get("denied_colorizers", []),
                    "allowed_renderers": group_data.get("allowed_renderers", ["*"]),
                    "denied_renderers": group_data.get("denied_renderers", []),
                    "allowed_workflows": group_data.get("allowed_workflows", ["*"]),
                    "denied_workflows": group_data.get("denied_workflows", []),
                    "default_preset_id": group_data.get("default_preset_id"),
                    "visible_presets": group_data.get("visible_presets", []),
                    "is_system": self.group_repo.is_system_group(group_id)
                })
            
            return result
            
        except Exception as e:
            logger.error(f"Error getting all groups: {e}")
            return []
    
    def get_group(self, group_id: str) -> Optional[Dict[str, Any]]:
        """
        获取单个用户组
        
        Args:
            group_id: 用户组ID
        
        Returns:
            Dict: 用户组信息，如果不存在则返回None
        """
        try:
            group_data = self.group_repo.get_group(group_id)
            
            if not group_data:
                return None
            
            return {
                "id": group_id,
                "name": group_data.get("name", group_id),
                "description": group_data.get("description", ""),
                "parameter_config": group_data.get("parameter_config", {}),
                "allowed_translators": group_data.get("allowed_translators", ["*"]),
                "denied_translators": group_data.get("denied_translators", []),
                "allowed_ocr": group_data.get("allowed_ocr", ["*"]),
                "denied_ocr": group_data.get("denied_ocr", []),
                "allowed_colorizers": group_data.get("allowed_colorizers", ["*"]),
                "denied_colorizers": group_data.get("denied_colorizers", []),
                "allowed_renderers": group_data.get("allowed_renderers", ["*"]),
                "denied_renderers": group_data.get("denied_renderers", []),
                "allowed_workflows": group_data.get("allowed_workflows", ["*"]),
                "denied_workflows": group_data.get("denied_workflows", []),
                "allowed_languages": group_data.get("allowed_languages", ["*"]),
                "denied_languages": group_data.get("denied_languages", []),
                "default_preset_id": group_data.get("default_preset_id"),
                "visible_presets": group_data.get("visible_presets", []),
                "allow_offline_translation": group_data.get("allow_offline_translation", False),
                "is_system": self.group_repo.is_system_group(group_id)
            }
            
        except Exception as e:
            logger.error(f"Error getting group '{group_id}': {e}")
            return None
    
    def update_group_config(
        self,
        group_id: str,
        config: Dict[str, Any],
        admin_id: str
    ) -> bool:
        """
        更新用户组配置
        
        Args:
            group_id: 用户组ID
            config: 新配置
            admin_id: 管理员ID
        
        Returns:
            bool: 是否成功
        """
        try:
            # 检查组是否存在
            if not self.group_repo.group_exists(group_id):
                logger.error(f"Group '{group_id}' does not exist")
                return False
            
            # 更新配置
            success = self.group_repo.update_group_config(group_id, config)
            
            if not success:
                logger.error(f"Failed to update config for group '{group_id}'")
                return False
            
            # 记录审计日志
            self._log_audit(admin_id, "update_group_config", {
                "group_id": group_id
            })
            
            logger.info(f"Updated config for group '{group_id}' by admin '{admin_id}'")
            return True
            
        except Exception as e:
            logger.error(f"Error updating config for group '{group_id}': {e}")
            return False
    
    def _update_user_group_associations(self, old_group_id: str, new_group_id: str) -> int:
        """
        更新所有用户的组关联
        
        Args:
            old_group_id: 旧用户组ID
            new_group_id: 新用户组ID
        
        Returns:
            int: 更新的用户数量
        """
        try:
            # 读取账户文件
            with open(self.accounts_file, 'r', encoding='utf-8') as f:
                accounts_data = json.load(f)
            
            updated_count = 0
            
            # 更新所有属于旧组的用户
            for account in accounts_data.get("accounts", []):
                if account.get("group") == old_group_id:
                    account["group"] = new_group_id
                    updated_count += 1
            
            # 写回文件
            if updated_count > 0:
                with open(self.accounts_file, 'w', encoding='utf-8') as f:
                    json.dump(accounts_data, f, indent=2, ensure_ascii=False)
            
            return updated_count
            
        except Exception as e:
            logger.error(f"Error updating user group associations: {e}")
            return 0
    
    def _move_users_to_default_group(self, group_id: str) -> int:
        """
        将用户组的所有用户移动到default组
        
        Args:
            group_id: 要删除的用户组ID
        
        Returns:
            int: 移动的用户数量
        """
        return self._update_user_group_associations(group_id, "default")
    
    def _log_audit(self, admin_id: str, action: str, details: Dict[str, Any]) -> None:
        """
        记录审计日志
        
        Args:
            admin_id: 管理员ID
            action: 操作类型
            details: 操作详情
        """
        try:
            audit_file = "manga_translator/server/data/audit.log"
            
            log_entry = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "admin_id": admin_id,
                "action": action,
                "details": details
            }
            
            with open(audit_file, 'a', encoding='utf-8') as f:
                f.write(json.dumps(log_entry, ensure_ascii=False) + '\n')
                
        except Exception as e:
            logger.error(f"Error writing audit log: {e}")


# 全局服务实例
_group_management_service: Optional[GroupManagementService] = None


def get_group_management_service(
    group_repo: Optional[GroupRepository] = None,
    accounts_file: Optional[str] = None
) -> GroupManagementService:
    """
    获取用户组管理服务实例
    
    Args:
        group_repo: 用户组仓库实例（可选）
        accounts_file: 账户文件路径（可选）
    
    Returns:
        GroupManagementService: 服务实例
    """
    global _group_management_service
    
    if _group_management_service is None:
        if group_repo is None:
            group_repo = GroupRepository("manga_translator/server/data/group_config.json")
        
        if accounts_file is None:
            accounts_file = "manga_translator/server/data/accounts.json"
        
        _group_management_service = GroupManagementService(group_repo, accounts_file)
    
    return _group_management_service
