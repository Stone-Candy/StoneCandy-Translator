"""
权限计算服务

实现基于用户组和用户个人设置的权限计算逻辑。

计算规则：
最终权限 = (用户组可见参数 + 用户allowed列表) - 用户denied列表
优先级：用户个人设置 > 用户组设置
"""

import logging
from typing import Any, Dict, List, Optional, Set

from manga_translator.server.core.group_service import get_group_service
from manga_translator.server.core.models import UserAccount

logger = logging.getLogger(__name__)


class PermissionCalculator:
    """权限计算器"""
    
    def __init__(self):
        self.group_service = get_group_service()
    
    def calculate_allowed_translators(self, user: UserAccount) -> List[str]:
        """
        计算用户最终可以使用的翻译器列表
        
        Args:
            user: 用户账号对象
        
        Returns:
            允许使用的翻译器列表
        """
        # 如果用户是管理员，允许所有
        if user.role == 'admin':
            return ['*']
        
        # 获取用户组配置
        self.group_service.get_group(user.group)
        
        # 基础集合：从用户组获取（目前用户组不限制翻译器，所以默认全部）
        base_translators: Set[str] = {'*'}
        
        # 用户个人允许列表
        user_allowed = set(user.permissions.allowed_translators)
        
        # 如果用户allowed包含'*'，表示允许所有
        if '*' in user_allowed:
            allowed = base_translators
        else:
            # 否则，基础集合 + 用户allowed
            allowed = base_translators.union(user_allowed)
        
        # 减去用户denied列表
        denied = set(user.permissions.denied_translators)
        final = allowed - denied
        
        # 如果结果包含'*'且还有其他项，只保留'*'
        if '*' in final and len(final) > 1:
            return ['*']
        
        return list(final)
    
    def calculate_allowed_parameters(self, user: UserAccount) -> List[str]:
        """
        计算用户最终可以调整的参数列表
        
        Args:
            user: 用户账号对象
        
        Returns:
            允许调整的参数列表
        """
        # 如果用户是管理员，允许所有
        if user.role == 'admin':
            return ['*']
        
        # 获取用户组配置
        group_config = self.group_service.get_group(user.group)
        
        # 基础集合：从用户组获取可见的参数
        base_parameters: Set[str] = set()
        if group_config:
            param_config = group_config.get('parameter_config', {})
            for param_name, param_settings in param_config.items():
                if param_settings.get('visible', False):
                    base_parameters.add(param_name)
        
        # 如果用户组没有配置，默认允许所有
        if not base_parameters:
            base_parameters = {'*'}
        
        # 用户个人允许列表
        user_allowed = set(user.permissions.allowed_parameters)
        
        # 如果用户allowed包含'*'，表示允许所有
        if '*' in user_allowed:
            allowed = base_parameters if '*' not in base_parameters else {'*'}
        else:
            # 否则，基础集合 + 用户allowed
            allowed = base_parameters.union(user_allowed)
        
        # 减去用户denied列表
        denied = set(user.permissions.denied_parameters)
        final = allowed - denied
        
        # 如果结果包含'*'且还有其他项，只保留'*'
        if '*' in final and len(final) > 1:
            return ['*']
        
        return list(final)
    
    def get_parameter_config(self, user: UserAccount, parameter: str) -> Optional[Dict[str, Any]]:
        """
        获取用户对特定参数的配置（可见性、只读、默认值）
        
        Args:
            user: 用户账号对象
            parameter: 参数名称
        
        Returns:
            参数配置字典，如果不可访问返回 None
        """
        # 检查用户是否有权限访问此参数
        allowed_params = self.calculate_allowed_parameters(user)
        
        if '*' not in allowed_params and parameter not in allowed_params:
            return None
        
        # 从用户组获取参数配置
        param_config = self.group_service.get_parameter_config(user.group, parameter)
        
        if not param_config:
            # 如果用户组没有配置，返回默认配置
            return {
                'visible': True,
                'readonly': False,
                'default_value': None
            }
        
        return param_config
    
    def check_translator_permission(self, user: UserAccount, translator: str) -> bool:
        """
        检查用户是否有权限使用指定的翻译器
        
        Args:
            user: 用户账号对象
            translator: 翻译器名称
        
        Returns:
            是否有权限
        """
        allowed = self.calculate_allowed_translators(user)
        return '*' in allowed or translator in allowed
    
    def check_parameter_permission(self, user: UserAccount, parameter: str) -> bool:
        """
        检查用户是否有权限调整指定的参数
        
        Args:
            user: 用户账号对象
            parameter: 参数名称
        
        Returns:
            是否有权限
        """
        allowed = self.calculate_allowed_parameters(user)
        return '*' in allowed or parameter in allowed


# 全局权限计算器实例
_permission_calculator: Optional[PermissionCalculator] = None


def get_permission_calculator() -> PermissionCalculator:
    """获取权限计算器实例"""
    global _permission_calculator
    if _permission_calculator is None:
        _permission_calculator = PermissionCalculator()
    return _permission_calculator
