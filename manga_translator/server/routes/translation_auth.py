"""
Translation endpoint authentication and authorization helpers.

This module provides helper functions for integrating authentication and
permission checks into translation endpoints.
"""

import logging
from enum import Enum
from typing import Optional

from fastapi import HTTPException, Request

from manga_translator import Config
from manga_translator.server.core.audit_service import AuditService
from manga_translator.server.core.group_management_service import (
    get_group_management_service,
)
from manga_translator.server.core.middleware import (
    check_concurrent_limit,
    check_daily_quota,
    decrement_task_count,
    get_services,
    increment_daily_usage,
    increment_task_count,
)

logger = logging.getLogger(__name__)


def filter_disabled_parameters(config: Config, username: str, permission_service) -> None:
    """
    过滤掉用户无权修改的参数，使用管理员设置的默认值
    
    执行层面合并用户组和用户的配置:
    - 用户组白名单/黑名单
    - 用户白名单/黑名单
    
    优先级（从高到低）:
    1. 用户黑名单（最高优先级，即使用户组白名单允许也禁用）
    2. 用户白名单（可以解锁用户组黑名单）
    3. 用户组黑名单
    4. 用户组白名单
    
    最终禁用 = 用户黑名单 + (用户组黑名单 - 用户白名单)
    
    Args:
        config: 翻译配置对象
        username: 用户名
        permission_service: 权限服务
    """
    try:
        # 获取服务
        account_service, _, _ = get_services()
        group_service = get_group_management_service()
        
        # 获取用户信息
        user_account = account_service.get_user(username)
        if not user_account:
            return
        
        group_id = user_account.group if hasattr(user_account, 'group') else 'default'
        
        # 获取用户组的参数配置
        group = group_service.get_group(group_id)
        group_param_config = group.get('parameter_config', {}) if group else {}
        
        # 获取用户的权限配置
        user_permissions = user_account.permissions if hasattr(user_account, 'permissions') else None
        
        # 用户的白名单和黑名单
        user_allowed_params = set()  # 用户白名单
        user_denied_params = set()   # 用户黑名单
        if user_permissions:
            allowed = getattr(user_permissions, 'allowed_parameters', ['*'])
            denied = getattr(user_permissions, 'denied_parameters', [])
            # 只有非通配符才是有效白名单
            if '*' not in allowed:
                user_allowed_params = set(allowed)
            user_denied_params = set(denied)
        
        # 用户组黑名单（disabled=True的参数）
        # 注意：禁用配置可能嵌套在 parameter_config.parameter_config 中
        group_disabled = {}
        
        # 检查是否有嵌套的 parameter_config（新格式）
        nested_param_config = group_param_config.get('parameter_config', {})
        if nested_param_config:
            logger.debug(f"Found nested parameter_config for user {username}: {list(nested_param_config.keys())}")
            for full_key, settings in nested_param_config.items():
                if isinstance(settings, dict) and settings.get('disabled', False):
                    group_disabled[full_key] = settings
                    logger.debug(f"Parameter {full_key} is disabled for group {group_id}, default: {settings.get('default_value')}")
        
        # 也检查旧格式（直接在 parameter_config 中的禁用配置）
        for full_key, settings in group_param_config.items():
            if full_key == 'parameter_config':
                continue  # 跳过嵌套的配置
            if isinstance(settings, dict) and settings.get('disabled', False):
                group_disabled[full_key] = settings
        
        logger.debug(f"Total disabled parameters for user {username}: {list(group_disabled.keys())}")
        
        # 获取用户级别的参数配置（用于默认值）
        user_param_config = {}
        user_disabled = {}  # 用户的禁用配置
        if hasattr(user_account, 'parameter_config') and user_account.parameter_config:
            user_param_config = user_account.parameter_config
            # 检查用户配置中是否有嵌套的 parameter_config（禁用配置）
            nested_user_param = user_param_config.get('parameter_config', {})
            if nested_user_param:
                for full_key, settings in nested_user_param.items():
                    if isinstance(settings, dict) and settings.get('disabled', False):
                        user_disabled[full_key] = settings
        
        # 计算最终禁用的参数
        # 最终禁用 = 用户黑名单 + (用户组黑名单 - 用户白名单)
        final_disabled = {}
        
        # 1. 用户黑名单（最高优先级）
        for param in user_denied_params:
            final_disabled[param] = {'disabled': True, 'source': 'user'}
        
        # 2. 用户组黑名单，但用户白名单可以解锁
        for full_key, settings in group_disabled.items():
            # 如果用户白名单包含此参数，则解锁（不禁用）
            if full_key in user_allowed_params:
                continue
            # 如果已经在用户黑名单中，保持用户黑名单的设置
            if full_key not in final_disabled:
                final_disabled[full_key] = {**settings, 'source': 'group'}
        
        if not final_disabled:
            return
        
        # 遍历禁用的参数，用默认值覆盖用户提交的值
        # 默认值优先级：用户配置 > 用户组配置 > 服务器默认
        for full_key, settings in final_disabled.items():
            # 解析参数路径，如 "translator.translator" -> section="translator", key="translator"
            parts = full_key.split('.')
            if len(parts) != 2:
                continue
            
            section, key = parts
            
            # 获取默认值（按优先级）
            default_value = None
            
            # 1. 优先使用用户禁用配置中的默认值
            if full_key in user_disabled:
                user_setting = user_disabled[full_key]
                if isinstance(user_setting, dict) and 'default_value' in user_setting:
                    default_value = user_setting['default_value']
            
            # 2. 其次使用用户配置的值（用户配置格式: {"section": {"key": value}}）
            if default_value is None and section in user_param_config:
                user_section = user_param_config[section]
                if isinstance(user_section, dict) and key in user_section:
                    default_value = user_section[key]
            
            # 3. 再次使用用户组禁用配置中的默认值
            if default_value is None and isinstance(settings, dict):
                default_value = settings.get('default_value')
            
            # 4. 最后尝试从用户组的参数配置中获取默认值（非禁用配置部分）
            if default_value is None:
                # 从 group_param_config 中获取对应 section.key 的值
                section_config = group_param_config.get(section, {})
                if isinstance(section_config, dict) and key in section_config:
                    section_value = section_config[key]
                    # 如果是简单值（非禁用配置对象），直接使用
                    if not isinstance(section_value, dict) or 'disabled' not in section_value:
                        default_value = section_value
            
            # AppSettings 有 cli 属性，可以直接设置 cli.attempts
            # 根据section找到config中对应的子对象
            if hasattr(config, section):
                section_obj = getattr(config, section)
                if hasattr(section_obj, key) and default_value is not None:
                    # 获取目标属性的类型注解
                    field_type = None
                    if hasattr(section_obj.__class__, '__annotations__'):
                        field_type = section_obj.__class__.__annotations__.get(key)
                    
                    # 如果目标类型是枚举，且当前值是字符串，则转换为枚举
                    if field_type and isinstance(field_type, type) and issubclass(field_type, Enum):
                        if isinstance(default_value, str):
                            # 尝试通过字符串值找到对应的枚举成员
                            try:
                                default_value = field_type(default_value)
                            except (ValueError, KeyError):
                                logger.warning(f"Failed to convert '{default_value}' to {field_type.__name__}, using as-is")
                    
                    setattr(section_obj, key, default_value)
    
    except Exception as e:
        logger.warning(f"Failed to filter disabled parameters for user {username}: {e}")

# Global audit service instance (initialized on server startup)
_audit_service: Optional[AuditService] = None


def init_translation_auth(audit_service: AuditService) -> None:
    """
    Initialize translation authentication module
    
    Args:
        audit_service: Audit service instance
    """
    global _audit_service
    _audit_service = audit_service
    logger.info("Translation authentication module initialized")


def get_audit_service() -> AuditService:
    """Get audit service instance"""
    if not _audit_service:
        raise RuntimeError("Translation authentication module not initialized")
    return _audit_service


async def verify_translation_auth(
    request: Request,
    config: Config,
    translator: Optional[str] = None
) -> tuple[str, str]:
    """
    Verify authentication and permissions for translation request
    
    This function:
    1. Extracts and validates session token from request headers
    2. Checks translator permission
    3. Filters config parameters based on user permissions
    4. Checks concurrent task limit
    5. Checks daily quota
    
    Args:
        request: FastAPI request object
        config: Translation configuration
        translator: Translator name (if None, extracted from config)
    
    Returns:
        tuple[str, str]: (username, ip_address)
    
    Raises:
        HTTPException: If authentication or authorization fails
    """
    # Extract session token from headers
    session_token = request.headers.get("X-Session-Token")
    
    if not session_token:
        logger.warning("Translation request without session token")
        raise HTTPException(
            status_code=401,
            detail={
                "error": {
                    "code": "NO_TOKEN",
                    "message": "未提供会话令牌，请先登录"
                }
            }
        )
    
    # Verify session token
    _, session_service, permission_service = get_services()
    session = session_service.verify_token(session_token)
    
    if not session:
        logger.warning("Translation request with invalid token")
        raise HTTPException(
            status_code=401,
            detail={
                "error": {
                    "code": "INVALID_TOKEN",
                    "message": "会话令牌无效或已过期，请重新登录"
                }
            }
        )

    if not session_service.update_activity(session_token):
        logger.warning("Translation request with expired token during activity refresh")
        raise HTTPException(
            status_code=401,
            detail={
                "error": {
                    "code": "INVALID_TOKEN",
                    "message": "会话令牌无效或已过期，请重新登录"
                }
            }
        )
    
    username = session.username
    ip_address = request.client.host if request.client else "unknown"
    
    # 将会话ID存储到配置中，用于日志追踪
    config._session_id = session_token
    
    # 【重要】先应用禁用参数的默认值，再检查权限
    # 这样如果翻译器参数被禁用，会使用管理员设置的默认翻译器
    filter_disabled_parameters(config, username, permission_service)
    
    # Extract translator from config (after filter_disabled_parameters applied defaults)
    if translator is None:
        if hasattr(config, 'translator') and hasattr(config.translator, 'translator'):
            translator = config.translator.translator
        else:
            translator = "unknown"
    
    permissions = permission_service.get_user_permissions(username)

    def _feature_value(value) -> str:
        if value is None:
            return ''
        return str(getattr(value, 'value', value) or '')

    def _assert_feature_permission(
        feature_type: str,
        feature_name: str,
        checker,
        allowed_attr: str,
        allowed_details_key: str,
        code: str,
        label: str,
    ) -> None:
        if not checker(username, feature_name):
            allowed_values = getattr(permissions, allowed_attr, []) if permissions else []

            logger.warning(
                f"Permission denied: User '{username}' attempted to use "
                f"unauthorized {feature_type} '{feature_name}'"
            )

            audit_service = get_audit_service()
            audit_service.log_event(
                event_type="permission_denied",
                username=username,
                ip_address=ip_address,
                details={
                    feature_type: feature_name,
                    "reason": f"{feature_type}_not_allowed",
                    allowed_details_key: allowed_values,
                },
                result="failure",
            )

            raise HTTPException(
                status_code=403,
                detail={
                    "error": {
                        "code": code,
                        "message": f"您没有权限使用{label} '{feature_name}'",
                        "details": {
                            feature_type: feature_name,
                            allowed_details_key: allowed_values,
                        },
                    }
                },
            )

    _assert_feature_permission(
        'translator',
        translator,
        permission_service.check_translator_permission,
        'allowed_translators',
        'allowed_translators',
        'TRANSLATOR_PERMISSION_DENIED',
        '翻译器',
    )

    if hasattr(config, 'ocr'):
        primary_ocr = _feature_value(getattr(config.ocr, 'ocr', ''))
        if primary_ocr:
            _assert_feature_permission(
                'ocr',
                primary_ocr,
                permission_service.check_ocr_permission,
                'allowed_ocr',
                'allowed_ocr',
                'OCR_PERMISSION_DENIED',
                'OCR',
            )

        secondary_ocr = _feature_value(getattr(config.ocr, 'secondary_ocr', ''))
        if secondary_ocr and secondary_ocr != primary_ocr:
            _assert_feature_permission(
                'ocr',
                secondary_ocr,
                permission_service.check_ocr_permission,
                'allowed_ocr',
                'allowed_ocr',
                'OCR_PERMISSION_DENIED',
                'OCR',
            )

    if hasattr(config, 'colorizer'):
        colorizer = _feature_value(getattr(config.colorizer, 'colorizer', ''))
        if colorizer:
            _assert_feature_permission(
                'colorizer',
                colorizer,
                permission_service.check_colorizer_permission,
                'allowed_colorizers',
                'allowed_colorizers',
                'COLORIZER_PERMISSION_DENIED',
                '上色器',
            )

    if hasattr(config, 'render'):
        renderer = _feature_value(getattr(config.render, 'renderer', ''))
        if renderer:
            _assert_feature_permission(
                'renderer',
                renderer,
                permission_service.check_renderer_permission,
                'allowed_renderers',
                'allowed_renderers',
                'RENDERER_PERMISSION_DENIED',
                '渲染器',
            )
    
    # 注意：并发限制检查和计数增加由路由层的 track_task_start/track_task_end 负责
    # 这里只做认证和权限检查，不修改计数器
    
    logger.info(
        f"Translation auth verified: user='{username}', translator='{translator}'"
    )
    
    return username, ip_address


def log_translation_task_created(
    username: str,
    ip_address: str,
    translator: str,
    config: Config,
    task_id: Optional[str] = None
) -> None:
    """
    Log translation task creation audit event
    
    Args:
        username: Username
        ip_address: IP address
        translator: Translator name
        config: Translation configuration
        task_id: Task ID (optional)
    """
    audit_service = get_audit_service()
    
    # Extract relevant config details
    details = {
        "translator": translator,
        "task_id": task_id or "unknown"
    }
    
    # Add target language if available
    if hasattr(config, 'translator') and hasattr(config.translator, 'target_lang'):
        details["target_lang"] = config.translator.target_lang
    
    # Log audit event
    audit_service.log_event(
        event_type="create_task",
        username=username,
        ip_address=ip_address,
        details=details,
        result="success"
    )
    
    logger.debug(f"Logged translation task creation: user='{username}', translator='{translator}'")


def track_task_start(username: str) -> None:
    """
    Track task start (increment counters and check limits)
    
    This function:
    1. Increments concurrent task count
    2. Checks concurrent limit (raises HTTPException if exceeded)
    3. Checks daily quota (raises HTTPException if exceeded)
    4. Increments daily usage
    
    If any check fails, the concurrent count is rolled back.
    
    Args:
        username: Username
    
    Raises:
        HTTPException: If concurrent limit or daily quota exceeded
    """
    # 先增加并发计数
    increment_task_count(username)
    
    # 获取当前计数用于日志
    _, _, permission_service = get_services()
    current_count = permission_service.get_active_task_count(username)
    # 使用有效的并发限制（优先从用户组获取）
    max_tasks = permission_service.get_effective_max_concurrent(username)
    print(f"[并发检查] 用户 '{username}': 当前任务数={current_count}, 最大允许={max_tasks}")
    
    try:
        # 检查并发限制
        check_concurrent_limit(username)
        # 检查每日配额
        check_daily_quota(username)
        # 增加每日使用量
        increment_daily_usage(username)
        print(f"[并发检查] 用户 '{username}': 检查通过，任务开始")
    except Exception as e:
        # 检查失败，回滚并发计数
        print(f"[并发检查] 用户 '{username}': 检查失败，回滚计数 - {e}")
        decrement_task_count(username)
        raise


def track_task_end(username: str) -> None:
    """
    Track task end (decrement counters)
    
    Args:
        username: Username
    """
    decrement_task_count(username)
