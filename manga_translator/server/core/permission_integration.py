"""
权限系统集成模块

将新的权限系统与现有的账户系统集成。
"""

import logging
from typing import Any, Dict, Optional

from manga_translator.server.core.account_service import AccountService
from manga_translator.server.core.permission_service_v2 import (
    EnhancedPermissionService,
    get_enhanced_permission_service,
)

logger = logging.getLogger(__name__)


class IntegratedPermissionService:
    """集成的权限服务"""
    
    def __init__(
        self,
        account_service: AccountService,
        permission_service: Optional[EnhancedPermissionService] = None
    ):
        """
        初始化集成权限服务
        
        Args:
            account_service: 账户服务实例
            permission_service: 增强权限服务实例（可选）
        """
        self.account_service = account_service
        
        if permission_service is None:
            permission_service = get_enhanced_permission_service()
        
        self.permission_service = permission_service
    
    def _get_user_group(self, username: str) -> Optional[str]:
        """
        获取用户所属的用户组
        
        Args:
            username: 用户名
        
        Returns:
            用户组ID，如果用户不存在返回 None
        """
        account = self.account_service.get_user(username)
        if account:
            return account.group
        return None
    
    def check_upload_prompt_permission(self, username: str) -> bool:
        """
        检查用户是否有上传提示词的权限
        
        Args:
            username: 用户名
        
        Returns:
            bool: 是否有权限
        """
        group_id = self._get_user_group(username)
        return self.permission_service.check_upload_prompt_permission(username, group_id)
    
    def check_upload_font_permission(self, username: str) -> bool:
        """
        检查用户是否有上传字体的权限
        
        Args:
            username: 用户名
        
        Returns:
            bool: 是否有权限
        """
        group_id = self._get_user_group(username)
        result = self.permission_service.check_upload_font_permission(username, group_id)
        logger.info(f"[DEBUG] check_upload_font_permission: user={username}, group={group_id}, result={result}")
        return result
    
    def check_delete_own_files_permission(self, username: str) -> bool:
        """
        检查用户是否有删除自己文件的权限
        
        Args:
            username: 用户名
        
        Returns:
            bool: 是否有权限
        """
        group_id = self._get_user_group(username)
        return self.permission_service.check_delete_own_files_permission(username, group_id)
    
    def check_delete_all_files_permission(self, username: str) -> bool:
        """
        检查用户是否有删除所有文件的权限
        
        Args:
            username: 用户名
        
        Returns:
            bool: 是否有权限
        """
        group_id = self._get_user_group(username)
        return self.permission_service.check_delete_all_files_permission(username, group_id)
    
    def check_delete_file_permission(self, username: str, file_owner: str) -> bool:
        """
        检查用户是否有删除指定文件的权限
        
        Args:
            username: 用户名
            file_owner: 文件所有者用户名
        
        Returns:
            bool: 是否有权限
        """
        # 如果是自己的文件，检查 can_delete_own_files
        if username == file_owner:
            return self.check_delete_own_files_permission(username)
        
        # 如果是其他人的文件，检查 can_delete_all_files
        return self.check_delete_all_files_permission(username)
    
    def check_view_permission(self, username: str) -> str:
        """
        获取用户的查看权限级别
        
        Args:
            username: 用户名
        
        Returns:
            str: 权限级别 ("own", "none", "all")
        """
        group_id = self._get_user_group(username)
        return self.permission_service.check_view_permission(username, group_id)
    
    def get_view_history_permission(self, username: str) -> str:
        """
        获取用户的历史查看权限级别
        
        Args:
            username: 用户名
        
        Returns:
            str: 权限级别 ("own", "none", "all")
        """
        group_id = self._get_user_group(username)
        return self.permission_service.get_view_history_permission(username, group_id)
    
    def check_save_enabled(self, username: str) -> bool:
        """
        检查用户是否启用保存翻译结果
        
        Args:
            username: 用户名
        
        Returns:
            bool: 是否启用保存
        """
        group_id = self._get_user_group(username)
        return self.permission_service.check_save_enabled(username, group_id)
    
    def check_edit_own_env_permission(self, username: str) -> bool:
        """
        检查用户是否有编辑自己.env配置的权限
        
        Args:
            username: 用户名
        
        Returns:
            bool: 是否有权限
        """
        group_id = self._get_user_group(username)
        return self.permission_service.check_edit_own_env_permission(username, group_id)
    
    def check_edit_server_env_permission(self, username: str) -> bool:
        """
        检查用户是否有编辑服务器.env配置的权限
        
        Args:
            username: 用户名
        
        Returns:
            bool: 是否有权限
        """
        group_id = self._get_user_group(username)
        return self.permission_service.check_edit_server_env_permission(username, group_id)
    
    def check_view_own_logs_permission(self, username: str) -> bool:
        """
        检查用户是否有查看自己日志的权限
        
        Args:
            username: 用户名
        
        Returns:
            bool: 是否有权限
        """
        group_id = self._get_user_group(username)
        return self.permission_service.check_view_own_logs_permission(username, group_id)
    
    def check_view_all_logs_permission(self, username: str) -> bool:
        """
        检查用户是否有查看所有用户日志的权限
        
        Args:
            username: 用户名
        
        Returns:
            bool: 是否有权限
        """
        group_id = self._get_user_group(username)
        return self.permission_service.check_view_all_logs_permission(username, group_id)
    
    def check_view_system_logs_permission(self, username: str) -> bool:
        """
        检查用户是否有查看系统日志的权限
        
        Args:
            username: 用户名
        
        Returns:
            bool: 是否有权限
        """
        group_id = self._get_user_group(username)
        return self.permission_service.check_view_system_logs_permission(username, group_id)
    
    def check_view_logs_permission(self, username: str, log_owner: Optional[str] = None) -> bool:
        """
        检查用户是否有查看指定日志的权限
        
        Args:
            username: 用户名
            log_owner: 日志所有者用户名（None 表示系统日志）
        
        Returns:
            bool: 是否有权限
        """
        # 系统日志
        if log_owner is None:
            return self.check_view_system_logs_permission(username)
        
        # 自己的日志
        if username == log_owner:
            return self.check_view_own_logs_permission(username)
        
        # 其他人的日志
        return self.check_view_all_logs_permission(username)
    
    def get_effective_permissions(self, username: str) -> Dict[str, Any]:
        """
        获取用户的有效权限（应用继承规则）
        
        Args:
            username: 用户名
        
        Returns:
            Dict[str, Any]: 有效权限字典
        """
        group_id = self._get_user_group(username)
        return self.permission_service.get_effective_permissions(username, group_id)
    
    def get_permission_summary(self, username: str) -> Dict[str, Any]:
        """
        获取用户权限摘要（用于显示）
        
        Args:
            username: 用户名
        
        Returns:
            Dict[str, Any]: 权限摘要
        """
        group_id = self._get_user_group(username)
        return self.permission_service.get_permission_summary(username, group_id)
    
    def set_user_permissions(
        self,
        username: str,
        permissions: Dict[str, Any],
        updated_by: str
    ) -> bool:
        """
        设置用户权限
        
        Args:
            username: 用户名
            permissions: 权限字典
            updated_by: 更新者用户名
        
        Returns:
            bool: 是否成功
        """
        return self.permission_service.set_user_permissions(username, permissions, updated_by)
    
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
        return self.permission_service.set_group_permissions(group_id, permissions)
    
    def set_global_permissions(self, permissions: Dict[str, Any]) -> bool:
        """
        设置全局默认权限
        
        Args:
            permissions: 权限字典
        
        Returns:
            bool: 是否成功
        """
        return self.permission_service.set_global_permissions(permissions)
    
    def delete_user_permissions(self, username: str) -> bool:
        """
        删除用户权限（回退到用户组/全局权限）
        
        Args:
            username: 用户名
        
        Returns:
            bool: 是否成功
        """
        return self.permission_service.delete_user_permissions(username)
    
    def delete_group_permissions(self, group_id: str) -> bool:
        """
        删除用户组权限（回退到全局权限）
        
        Args:
            group_id: 用户组ID
        
        Returns:
            bool: 是否成功
        """
        return self.permission_service.delete_group_permissions(group_id)


# 全局服务实例
_integrated_permission_service: Optional[IntegratedPermissionService] = None


def get_integrated_permission_service(
    account_service: Optional[AccountService] = None
) -> IntegratedPermissionService:
    """
    获取集成权限服务实例
    
    Args:
        account_service: 账户服务实例（可选）
    
    Returns:
        IntegratedPermissionService: 服务实例
    """
    global _integrated_permission_service
    
    if _integrated_permission_service is None:
        if account_service is None:
            # 导入并获取默认账户服务
            from .account_service import get_account_service
            account_service = get_account_service()
        
        _integrated_permission_service = IntegratedPermissionService(account_service)
    
    return _integrated_permission_service
