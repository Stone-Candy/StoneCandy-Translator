"""
权限管理服务（PermissionService）

检查用户权限、过滤配置数据、管理并发限制和配额。
"""

import logging
from collections import defaultdict
from datetime import date
from typing import Any, Dict, Optional

from manga_translator.server.core.account_service import AccountService
from manga_translator.server.core.models import UserPermissions

logger = logging.getLogger(__name__)


class PermissionService:
    """权限管理服务"""

    FEATURE_PERMISSION_FIELDS = {
        'translator': ('allowed_translators', 'denied_translators'),
        'ocr': ('allowed_ocr', 'denied_ocr'),
        'colorizer': ('allowed_colorizers', 'denied_colorizers'),
        'renderer': ('allowed_renderers', 'denied_renderers'),
        'workflow': ('allowed_workflows', 'denied_workflows'),
    }
    
    def __init__(self, account_service: AccountService):
        """
        初始化权限管理服务
        
        Args:
            account_service: 账号管理服务实例
        """
        self.account_service = account_service
        
        # 跟踪用户的活动任务数: username -> count
        self.active_tasks: Dict[str, int] = defaultdict(int)
        
        # 跟踪用户的每日使用配额: (username, date) -> count
        self.daily_usage: Dict[tuple, int] = defaultdict(int)
    
    def _resolve_feature_permission_fields(self, feature_type: str) -> tuple[str, str]:
        fields = self.FEATURE_PERMISSION_FIELDS.get(feature_type)
        if not fields:
            raise ValueError(f"Unsupported feature type: {feature_type}")
        return fields

    def _get_group_feature_permissions(self, account, allowed_field: str, denied_field: str) -> tuple[set, set]:
        group_allowed = set()
        group_denied = set()

        try:
            from manga_translator.server.core.group_management_service import (
                get_group_management_service,
            )
            group_service = get_group_management_service()
            group = group_service.get_group(account.group)

            if group:
                group_allowed = set(group.get(allowed_field, []))
                group_denied = set(group.get(denied_field, []))
        except Exception as e:
            logger.warning(f"Failed to get group permissions for {allowed_field}: {e}")

        return group_allowed, group_denied

    def check_feature_permission(self, username: str, feature_type: str, feature_name: str) -> bool:
        """
        检查指定能力的权限。

        优先级（从高到低）：
        1. 用户黑名单
        2. 用户白名单（可解锁用户组黑名单）
        3. 用户组黑名单
        4. 用户组白名单
        """
        account = self.account_service.get_user(username)
        if not account:
            logger.warning(f"User not found: {username}")
            return False

        allowed_field, denied_field = self._resolve_feature_permission_fields(feature_type)
        permissions = account.permissions

        user_allowed = set(getattr(permissions, allowed_field, []) or [])
        user_denied = set(getattr(permissions, denied_field, []) or [])

        if feature_name in user_denied:
            return False

        if "*" in user_allowed or feature_name in user_allowed:
            return True

        group_allowed, group_denied = self._get_group_feature_permissions(
            account,
            allowed_field,
            denied_field,
        )

        if feature_name in group_denied:
            return False

        if not group_allowed or "*" in group_allowed or feature_name in group_allowed:
            return True

        return False

    def filter_allowed_options(self, username: str, feature_type: str, options: list[str]) -> list[str]:
        """根据用户权限过滤选项列表。"""
        return [
            option for option in options
            if self.check_feature_permission(username, feature_type, option)
        ]

    def check_translator_permission(self, username: str, translator: str) -> bool:
        """检查翻译器权限。"""
        return self.check_feature_permission(username, 'translator', translator)

    def check_ocr_permission(self, username: str, ocr: str) -> bool:
        """检查 OCR 权限。"""
        return self.check_feature_permission(username, 'ocr', ocr)

    def check_colorizer_permission(self, username: str, colorizer: str) -> bool:
        """检查上色器权限。"""
        return self.check_feature_permission(username, 'colorizer', colorizer)

    def check_renderer_permission(self, username: str, renderer: str) -> bool:
        """检查渲染器权限。"""
        return self.check_feature_permission(username, 'renderer', renderer)

    def check_workflow_permission(self, username: str, workflow: str) -> bool:
        """检查工作流权限。"""
        return self.check_feature_permission(username, 'workflow', workflow)
    
    def check_parameter_permission(self, username: str, parameter: str) -> bool:
        """
        检查参数权限
        
        Args:
            username: 用户名
            parameter: 参数名称（如 "translator.target_lang"）
        
        Returns:
            bool: 用户是否有权限调整该参数
        """
        account = self.account_service.get_user(username)
        if not account:
            logger.warning(f"User not found: {username}")
            return False
        
        permissions = account.permissions
        
        # 检查是否有通配符权限
        if "*" in permissions.allowed_parameters:
            return True
        
        # 检查是否在允许列表中
        return parameter in permissions.allowed_parameters
    
    def filter_parameters(self, username: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """
        过滤参数，只保留用户有权限的参数
        
        Args:
            username: 用户名
            parameters: 原始参数字典
        
        Returns:
            Dict[str, Any]: 过滤后的参数字典
        """
        account = self.account_service.get_user(username)
        if not account:
            logger.warning(f"User not found: {username}")
            return {}
        
        permissions = account.permissions
        
        # 如果有通配符权限，返回所有参数
        if "*" in permissions.allowed_parameters:
            return parameters
        
        # 过滤参数
        filtered = {}
        for key, value in parameters.items():
            if self.check_parameter_permission(username, key):
                filtered[key] = value
            else:
                logger.debug(f"Filtered parameter '{key}' for user '{username}'")
        
        return filtered
    
    def check_offline_translation_permission(self, username: str) -> bool:
        """
        检查用户是否有离线翻译权限（用户离线后任务继续执行）
        
        Args:
            username: 用户名
        
        Returns:
            bool: 是否允许离线翻译
        """
        account = self.account_service.get_user(username)
        if not account:
            logger.warning(f"User not found: {username}")
            return False
        
        # 检查用户权限
        if account.permissions.allow_offline_translation:
            return True
        
        # 检查用户组权限
        try:
            from manga_translator.server.core.group_management_service import (
                get_group_management_service,
            )
            group_service = get_group_management_service()
            group = group_service.get_group(account.group)
            
            if group:
                return group.get('allow_offline_translation', False)
        except Exception as e:
            logger.warning(f"Failed to get group offline translation permission: {e}")
        
        return False
    
    def check_concurrent_limit(self, username: str) -> bool:
        """
        检查并发限制
        
        注意：此函数应在 increment_task_count 之后调用，
        所以检查条件是 current_tasks <= max（而不是 <）
        
        优先级：用户组配置 > 用户配置
        
        Args:
            username: 用户名
        
        Returns:
            bool: 用户是否可以创建新任务（未超过并发限制）
        """
        account = self.account_service.get_user(username)
        if not account:
            logger.warning(f"User not found: {username}")
            return False
        
        # 获取有效的并发限制（优先从用户组获取）
        max_concurrent = self.get_effective_max_concurrent(username)
        current_tasks = self.active_tasks.get(username, 0)
        
        # 检查是否超过限制（因为已经先增加了计数，所以用 <=）
        can_create = current_tasks <= max_concurrent
        
        if not can_create:
            logger.info(
                f"User '{username}' reached concurrent task limit "
                f"({current_tasks}/{max_concurrent})"
            )
        
        return can_create
    
    def get_effective_max_concurrent(self, username: str) -> int:
        """
        获取用户的有效最大并发数（优先从用户组获取）
        
        Args:
            username: 用户名
        
        Returns:
            int: 最大并发任务数
        """
        account = self.account_service.get_user(username)
        if not account:
            return 1  # 默认限制为 1
        
        # 优先从用户组获取并发限制
        try:
            from manga_translator.server.core.group_management_service import (
                get_group_management_service,
            )
            group_service = get_group_management_service()
            group = group_service.get_group(account.group)
            if group:
                param_config = group.get('parameter_config', {})
                quota_config = param_config.get('quota', {})
                group_max = quota_config.get('max_concurrent_tasks')
                if group_max is not None and group_max > 0:
                    return group_max
        except Exception as e:
            logger.warning(f"Failed to get group concurrent limit: {e}")
        
        # 如果用户组没有设置，使用用户级别的配置
        return account.permissions.max_concurrent_tasks
    
    def check_daily_quota(self, username: str) -> bool:
        """
        检查每日配额
        
        Args:
            username: 用户名
        
        Returns:
            bool: 用户是否还有剩余配额
        """
        account = self.account_service.get_user(username)
        if not account:
            logger.warning(f"User not found: {username}")
            return False
        
        # 获取用户组的配额设置
        daily_quota = -1  # 默认无限制
        try:
            from manga_translator.server.core.group_management_service import (
                get_group_management_service,
            )
            group_service = get_group_management_service()
            group = group_service.get_group(account.group)
            if group:
                param_config = group.get('parameter_config', {})
                quota_config = param_config.get('quota', {})
                # 使用用户组的 daily_image_limit
                group_quota = quota_config.get('daily_image_limit', -1)
                if group_quota is not None and group_quota > 0:
                    daily_quota = group_quota
        except Exception as e:
            logger.warning(f"Failed to get group quota: {e}")
        
        # 如果用户组没有设置，使用用户级别的配额
        if daily_quota == -1:
            daily_quota = account.permissions.daily_quota
        
        # -1 表示无限制
        if daily_quota == -1:
            return True
        
        # 获取今天的使用量
        today = date.today()
        usage_key = (username, today)
        current_usage = self.daily_usage.get(usage_key, 0)
        
        # 检查是否超过配额
        can_create = current_usage < daily_quota
        
        if not can_create:
            logger.info(
                f"User '{username}' reached daily quota "
                f"({current_usage}/{daily_quota})"
            )
        
        return can_create
    
    def increment_task_count(self, username: str) -> None:
        """
        增加用户的活动任务计数
        
        Args:
            username: 用户名
        """
        self.active_tasks[username] = self.active_tasks.get(username, 0) + 1
        logger.debug(f"User '{username}' active tasks: {self.active_tasks[username]}")
    
    def decrement_task_count(self, username: str) -> None:
        """
        减少用户的活动任务计数
        
        Args:
            username: 用户名
        """
        if username in self.active_tasks:
            self.active_tasks[username] = max(0, self.active_tasks[username] - 1)
            logger.debug(f"User '{username}' active tasks: {self.active_tasks[username]}")
    
    def increment_daily_usage(self, username: str) -> None:
        """
        增加用户的每日使用量
        
        Args:
            username: 用户名
        """
        today = date.today()
        usage_key = (username, today)
        self.daily_usage[usage_key] = self.daily_usage.get(usage_key, 0) + 1
        logger.debug(f"User '{username}' daily usage: {self.daily_usage[usage_key]}")
    
    def get_user_permissions(self, username: str) -> Optional[UserPermissions]:
        """
        获取用户权限
        
        Args:
            username: 用户名
        
        Returns:
            Optional[UserPermissions]: 用户权限对象，如果用户不存在返回 None
        """
        account = self.account_service.get_user(username)
        if not account:
            return None
        
        return account.permissions
    
    def update_user_permissions(
        self,
        username: str,
        permissions: UserPermissions
    ) -> bool:
        """
        更新用户权限（立即生效）
        
        Args:
            username: 用户名
            permissions: 新的权限对象
        
        Returns:
            bool: 更新是否成功
        """
        try:
            success = self.account_service.update_user(
                username,
                {'permissions': permissions}
            )
            
            if success:
                logger.info(f"Updated permissions for user: {username}")
            
            return success
        except Exception as e:
            logger.error(f"Failed to update permissions for user '{username}': {e}")
            return False
    
    def filter_config_for_user(
        self,
        username: str,
        config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        为用户过滤配置数据
        
        Args:
            username: 用户名
            config: 原始配置字典
        
        Returns:
            Dict[str, Any]: 过滤后的配置字典
        """
        account = self.account_service.get_user(username)
        if not account:
            logger.warning(f"User not found: {username}")
            return {}
        
        permissions = account.permissions
        filtered_config = config.copy()
        
        # 过滤翻译器列表
        if 'translators' in filtered_config:
            filtered_config['translators'] = self.filter_allowed_options(
                username,
                'translator',
                filtered_config['translators'],
            )
        
        # 过滤参数
        if 'parameters' in filtered_config:
            filtered_config['parameters'] = self.filter_parameters(
                username,
                filtered_config['parameters']
            )
        
        # 添加用户权限信息
        filtered_config['user_permissions'] = {
            'allowed_translators': permissions.allowed_translators,
            'allowed_ocr': permissions.allowed_ocr,
            'allowed_colorizers': permissions.allowed_colorizers,
            'allowed_renderers': permissions.allowed_renderers,
            'allowed_workflows': permissions.allowed_workflows,
            'allowed_parameters': permissions.allowed_parameters,
            'max_concurrent_tasks': permissions.max_concurrent_tasks,
            'daily_quota': permissions.daily_quota,
            'can_upload_files': permissions.can_upload_files,
            'can_delete_files': permissions.can_delete_files
        }
        
        return filtered_config
    
    def get_active_task_count(self, username: str) -> int:
        """
        获取用户的活动任务数
        
        Args:
            username: 用户名
        
        Returns:
            int: 活动任务数
        """
        return self.active_tasks.get(username, 0)
    
    def get_daily_usage(self, username: str) -> int:
        """
        获取用户今天的使用量
        
        Args:
            username: 用户名
        
        Returns:
            int: 今天的使用量
        """
        today = date.today()
        usage_key = (username, today)
        return self.daily_usage.get(usage_key, 0)
    
    def get_effective_daily_quota(self, username: str) -> int:
        """
        获取用户的有效每日配额（优先从用户组获取）
        
        Args:
            username: 用户名
        
        Returns:
            int: 每日配额，-1 表示无限制
        """
        account = self.account_service.get_user(username)
        if not account:
            return -1
        
        # 优先从用户组获取配额
        try:
            from manga_translator.server.core.group_management_service import (
                get_group_management_service,
            )
            group_service = get_group_management_service()
            group = group_service.get_group(account.group)
            if group:
                param_config = group.get('parameter_config', {})
                quota_config = param_config.get('quota', {})
                group_quota = quota_config.get('daily_image_limit', -1)
                if group_quota is not None and group_quota > 0:
                    return group_quota
        except Exception as e:
            logger.warning(f"Failed to get group quota: {e}")
        
        # 如果用户组没有设置，使用用户级别的配额
        return account.permissions.daily_quota
    
    def cleanup_old_usage_data(self) -> None:
        """
        清理旧的使用数据（保留最近7天）
        """
        today = date.today()
        keys_to_remove = []
        
        for (username, usage_date) in self.daily_usage.keys():
            days_old = (today - usage_date).days
            if days_old > 7:
                keys_to_remove.append((username, usage_date))
        
        for key in keys_to_remove:
            del self.daily_usage[key]
        
        if keys_to_remove:
            logger.info(f"Cleaned up {len(keys_to_remove)} old usage records")
    
    def get_effective_file_permissions(self, username: str) -> dict:
        """
        获取用户的有效文件操作权限（优先从用户组获取）
        
        Args:
            username: 用户名
        
        Returns:
            dict: 文件操作权限字典
        """
        account = self.account_service.get_user(username)
        if not account:
            return {
                'can_upload_fonts': False,
                'can_delete_fonts': False,
                'can_upload_prompts': False,
                'can_delete_prompts': False,
            }
        
        # 默认使用用户级别的权限
        result = {
            'can_upload_fonts': account.permissions.can_upload_files,
            'can_delete_fonts': account.permissions.can_delete_files,
            'can_upload_prompts': account.permissions.can_upload_files,
            'can_delete_prompts': account.permissions.can_delete_files,
        }
        
        # 优先从用户组获取权限
        try:
            from manga_translator.server.core.group_management_service import (
                get_group_management_service,
            )
            group_service = get_group_management_service()
            group = group_service.get_group(account.group)
            if group:
                param_config = group.get('parameter_config', {})
                perm_config = param_config.get('permissions', {})
                
                # 如果用户组有配置，使用用户组的配置
                if 'can_upload_fonts' in perm_config:
                    result['can_upload_fonts'] = perm_config['can_upload_fonts']
                if 'can_delete_fonts' in perm_config:
                    result['can_delete_fonts'] = perm_config['can_delete_fonts']
                if 'can_upload_prompts' in perm_config:
                    result['can_upload_prompts'] = perm_config['can_upload_prompts']
                if 'can_delete_prompts' in perm_config:
                    result['can_delete_prompts'] = perm_config['can_delete_prompts']
        except Exception as e:
            logger.warning(f"Failed to get group file permissions: {e}")
        
        return result
    
    def can_upload_fonts(self, username: str) -> bool:
        """检查用户是否可以上传字体"""
        return self.get_effective_file_permissions(username).get('can_upload_fonts', False)
    
    def can_delete_fonts(self, username: str) -> bool:
        """检查用户是否可以删除字体"""
        return self.get_effective_file_permissions(username).get('can_delete_fonts', False)
    
    def can_upload_prompts(self, username: str) -> bool:
        """检查用户是否可以上传提示词"""
        return self.get_effective_file_permissions(username).get('can_upload_prompts', False)
    
    def can_delete_prompts(self, username: str) -> bool:
        """检查用户是否可以删除提示词"""
        return self.get_effective_file_permissions(username).get('can_delete_prompts', False)
