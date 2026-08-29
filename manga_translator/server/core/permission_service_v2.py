"""
增强的权限管理服务 (Enhanced Permission Service)

实现基于继承的权限系统：全局 → 用户组 → 用户
支持细分权限（can_upload_prompt, can_upload_font等）
"""

import logging
from typing import Any, Dict, Optional

from manga_translator.server.models.permission_models import UserPermission
from manga_translator.server.repositories.permission_repository import (
    PermissionRepository,
)

logger = logging.getLogger(__name__)


class EnhancedPermissionService:
    """增强的权限管理服务"""
    
    def __init__(self, permission_repo: PermissionRepository):
        """
        初始化权限服务
        
        Args:
            permission_repo: 权限仓库实例
        """
        self.permission_repo = permission_repo
    
    def check_upload_prompt_permission(self, user_id: str, group_id: Optional[str] = None) -> bool:
        """
        检查用户是否有上传提示词的权限
        
        Args:
            user_id: 用户ID
            group_id: 用户组ID（可选）
        
        Returns:
            bool: 是否有权限
        """
        perms = self.permission_repo.get_effective_permissions(user_id, group_id)
        return perms.get("can_upload_prompt", False)
    
    def check_upload_font_permission(self, user_id: str, group_id: Optional[str] = None) -> bool:
        """
        检查用户是否有上传字体的权限
        
        Args:
            user_id: 用户ID
            group_id: 用户组ID（可选）
        
        Returns:
            bool: 是否有权限
        """
        perms = self.permission_repo.get_effective_permissions(user_id, group_id)
        result = perms.get("can_upload_font", False)
        logger.info(f"[DEBUG] EnhancedPermissionService.check_upload_font_permission: user={user_id}, group={group_id}, perms={perms}, result={result}")
        return result
    
    def check_delete_own_files_permission(self, user_id: str, group_id: Optional[str] = None) -> bool:
        """
        检查用户是否有删除自己文件的权限
        
        Args:
            user_id: 用户ID
            group_id: 用户组ID（可选）
        
        Returns:
            bool: 是否有权限
        """
        perms = self.permission_repo.get_effective_permissions(user_id, group_id)
        return perms.get("can_delete_own_files", True)  # 默认允许
    
    def check_delete_all_files_permission(self, user_id: str, group_id: Optional[str] = None) -> bool:
        """
        检查用户是否有删除所有文件的权限
        
        Args:
            user_id: 用户ID
            group_id: 用户组ID（可选）
        
        Returns:
            bool: 是否有权限
        """
        perms = self.permission_repo.get_effective_permissions(user_id, group_id)
        return perms.get("can_delete_all_files", False)
    
    def check_view_permission(self, user_id: str, group_id: Optional[str] = None) -> str:
        """
        获取用户的查看权限级别
        
        Args:
            user_id: 用户ID
            group_id: 用户组ID（可选）
        
        Returns:
            str: 权限级别 ("own", "none", "all")
        """
        perms = self.permission_repo.get_effective_permissions(user_id, group_id)
        return perms.get("view_permission", "own")
    
    def check_save_enabled(self, user_id: str, group_id: Optional[str] = None) -> bool:
        """
        检查用户是否启用保存翻译结果
        
        Args:
            user_id: 用户ID
            group_id: 用户组ID（可选）
        
        Returns:
            bool: 是否启用保存
        """
        perms = self.permission_repo.get_effective_permissions(user_id, group_id)
        return perms.get("save_enabled", True)
    
    def check_edit_own_env_permission(self, user_id: str, group_id: Optional[str] = None) -> bool:
        """
        检查用户是否有编辑自己.env配置的权限
        
        Args:
            user_id: 用户ID
            group_id: 用户组ID（可选）
        
        Returns:
            bool: 是否有权限
        """
        perms = self.permission_repo.get_effective_permissions(user_id, group_id)
        return perms.get("can_edit_own_env", False)
    
    def check_edit_server_env_permission(self, user_id: str, group_id: Optional[str] = None) -> bool:
        """
        检查用户是否有编辑服务器.env配置的权限
        
        Args:
            user_id: 用户ID
            group_id: 用户组ID（可选）
        
        Returns:
            bool: 是否有权限
        """
        perms = self.permission_repo.get_effective_permissions(user_id, group_id)
        return perms.get("can_edit_server_env", False)
    
    def check_view_own_logs_permission(self, user_id: str, group_id: Optional[str] = None) -> bool:
        """
        检查用户是否有查看自己日志的权限
        
        Args:
            user_id: 用户ID
            group_id: 用户组ID（可选）
        
        Returns:
            bool: 是否有权限
        """
        perms = self.permission_repo.get_effective_permissions(user_id, group_id)
        return perms.get("can_view_own_logs", True)
    
    def check_view_all_logs_permission(self, user_id: str, group_id: Optional[str] = None) -> bool:
        """
        检查用户是否有查看所有用户日志的权限
        
        Args:
            user_id: 用户ID
            group_id: 用户组ID（可选）
        
        Returns:
            bool: 是否有权限
        """
        perms = self.permission_repo.get_effective_permissions(user_id, group_id)
        return perms.get("can_view_all_logs", False)
    
    def check_view_system_logs_permission(self, user_id: str, group_id: Optional[str] = None) -> bool:
        """
        检查用户是否有查看系统日志的权限
        
        Args:
            user_id: 用户ID
            group_id: 用户组ID（可选）
        
        Returns:
            bool: 是否有权限
        """
        perms = self.permission_repo.get_effective_permissions(user_id, group_id)
        return perms.get("can_view_system_logs", False)
    
    def get_view_history_permission(self, user_id: str, group_id: Optional[str] = None) -> str:
        """
        获取用户的历史查看权限级别
        
        Args:
            user_id: 用户ID
            group_id: 用户组ID（可选）
        
        Returns:
            str: 权限级别 ("own", "none", "all")
        """
        # 使用 view_permission 字段
        return self.check_view_permission(user_id, group_id)
    
    def is_admin(self, user_id: str) -> bool:
        """
        检查用户是否是管理员
        
        Args:
            user_id: 用户ID
        
        Returns:
            bool: 是否是管理员
        """
        perms = self.permission_repo.get_effective_permissions(user_id, None)
        # 管理员通常有 can_delete_all_files 和 can_view_all_logs 权限
        return (perms.get("can_delete_all_files", False) and 
                perms.get("can_view_all_logs", False))
    
    def get_effective_permissions(self, user_id: str, group_id: Optional[str] = None) -> Dict[str, Any]:
        """
        获取用户的有效权限（应用继承规则）
        
        Args:
            user_id: 用户ID
            group_id: 用户组ID（可选）
        
        Returns:
            Dict[str, Any]: 有效权限字典
        """
        return self.permission_repo.get_effective_permissions(user_id, group_id)
    
    def set_user_permissions(
        self,
        user_id: str,
        permissions: Dict[str, Any],
        updated_by: str
    ) -> bool:
        """
        设置用户权限
        
        Args:
            user_id: 用户ID
            permissions: 权限字典
            updated_by: 更新者ID
        
        Returns:
            bool: 是否成功
        """
        try:
            # 创建 UserPermission 对象
            user_perm = UserPermission.create(
                user_id=user_id,
                updated_by=updated_by,
                **permissions
            )
            
            # 保存到仓库
            self.permission_repo.set_user_permissions(user_id, user_perm)
            self.permission_repo.update_last_modified()
            
            logger.info(f"Set permissions for user '{user_id}' by '{updated_by}'")
            return True
            
        except Exception as e:
            logger.error(f"Failed to set permissions for user '{user_id}': {e}")
            return False
    
    def set_group_permissions(
        self,
        group_id: str,
        permissions: Dict[str, Any]
    ) -> bool:
        """
        设置用户组权限
        
        Args:
            group_id: 用户组ID
            permissions: 权限字典
        
        Returns:
            bool: 是否成功
        """
        try:
            self.permission_repo.set_group_permissions(group_id, permissions)
            self.permission_repo.update_last_modified()
            
            logger.info(f"Set permissions for group '{group_id}'")
            return True
            
        except Exception as e:
            logger.error(f"Failed to set permissions for group '{group_id}': {e}")
            return False
    
    def set_global_permissions(self, permissions: Dict[str, Any]) -> bool:
        """
        设置全局默认权限
        
        Args:
            permissions: 权限字典
        
        Returns:
            bool: 是否成功
        """
        try:
            self.permission_repo.set_global_permissions(permissions)
            self.permission_repo.update_last_modified()
            
            logger.info("Set global permissions")
            return True
            
        except Exception as e:
            logger.error(f"Failed to set global permissions: {e}")
            return False
    
    def delete_user_permissions(self, user_id: str) -> bool:
        """
        删除用户权限（回退到用户组/全局权限）
        
        Args:
            user_id: 用户ID
        
        Returns:
            bool: 是否成功
        """
        try:
            success = self.permission_repo.delete_user_permissions(user_id)
            if success:
                self.permission_repo.update_last_modified()
                logger.info(f"Deleted permissions for user '{user_id}'")
            return success
            
        except Exception as e:
            logger.error(f"Failed to delete permissions for user '{user_id}': {e}")
            return False
    
    def delete_group_permissions(self, group_id: str) -> bool:
        """
        删除用户组权限（回退到全局权限）
        
        Args:
            group_id: 用户组ID
        
        Returns:
            bool: 是否成功
        """
        try:
            success = self.permission_repo.delete_group_permissions(group_id)
            if success:
                self.permission_repo.update_last_modified()
                logger.info(f"Deleted permissions for group '{group_id}'")
            return success
            
        except Exception as e:
            logger.error(f"Failed to delete permissions for group '{group_id}': {e}")
            return False
    
    def get_permission_summary(self, user_id: str, group_id: Optional[str] = None) -> Dict[str, Any]:
        """
        获取用户权限摘要（用于显示）
        
        Args:
            user_id: 用户ID
            group_id: 用户组ID（可选）
        
        Returns:
            Dict[str, Any]: 权限摘要
        """
        effective_perms = self.get_effective_permissions(user_id, group_id)
        
        return {
            "user_id": user_id,
            "group_id": group_id,
            "upload": {
                "can_upload_prompt": effective_perms.get("can_upload_prompt", False),
                "can_upload_font": effective_perms.get("can_upload_font", False)
            },
            "delete": {
                "can_delete_own_files": effective_perms.get("can_delete_own_files", True),
                "can_delete_all_files": effective_perms.get("can_delete_all_files", False)
            },
            "view": {
                "view_permission": effective_perms.get("view_permission", "own"),
                "can_view_own_logs": effective_perms.get("can_view_own_logs", True),
                "can_view_all_logs": effective_perms.get("can_view_all_logs", False),
                "can_view_system_logs": effective_perms.get("can_view_system_logs", False)
            },
            "config": {
                "can_edit_own_env": effective_perms.get("can_edit_own_env", False),
                "can_edit_server_env": effective_perms.get("can_edit_server_env", False)
            },
            "save_enabled": effective_perms.get("save_enabled", True)
        }


# 全局服务实例
_enhanced_permission_service: Optional[EnhancedPermissionService] = None


def get_enhanced_permission_service(
    permission_repo: Optional[PermissionRepository] = None
) -> EnhancedPermissionService:
    """
    获取增强权限服务实例
    
    Args:
        permission_repo: 权限仓库实例（可选）
    
    Returns:
        EnhancedPermissionService: 服务实例
    """
    global _enhanced_permission_service
    
    if _enhanced_permission_service is None:
        if permission_repo is None:
            # 创建默认仓库
            permission_repo = PermissionRepository("manga_translator/server/data/permissions.json")
        
        _enhanced_permission_service = EnhancedPermissionService(permission_repo)
    
    return _enhanced_permission_service
