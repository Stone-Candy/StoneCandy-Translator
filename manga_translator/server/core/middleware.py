"""
认证和授权中间件

提供 FastAPI 依赖函数用于验证用户身份和权限。
"""

import logging
from typing import Any, Dict, Optional

from fastapi import Depends, Header, HTTPException
from fastapi.responses import JSONResponse

from manga_translator.server.core.account_service import AccountService
from manga_translator.server.core.models import Session
from manga_translator.server.core.permission_service import PermissionService
from manga_translator.server.core.session_service import SessionService

logger = logging.getLogger(__name__)


# 全局服务实例（将在服务器启动时初始化）
_account_service: Optional[AccountService] = None
_session_service: Optional[SessionService] = None
_permission_service: Optional[PermissionService] = None


def init_middleware_services(
    account_service: AccountService,
    session_service: SessionService,
    permission_service: PermissionService
) -> None:
    """
    初始化中间件使用的服务实例
    
    Args:
        account_service: 账号管理服务
        session_service: 会话管理服务
        permission_service: 权限管理服务
    """
    global _account_service, _session_service, _permission_service
    _account_service = account_service
    _session_service = session_service
    _permission_service = permission_service
    logger.info("Middleware services initialized")


def get_services() -> tuple[AccountService, SessionService, PermissionService]:
    """获取服务实例（用于依赖注入）
    
    Returns:
        tuple: (account_service, session_service, permission_service)
    """
    if not _account_service or not _session_service or not _permission_service:
        raise RuntimeError("Middleware services not initialized")
    return _account_service, _session_service, _permission_service


# 错误响应格式化函数
def create_error_response(
    code: str,
    message: str,
    details: Optional[Dict[str, Any]] = None,
    status_code: int = 400
) -> JSONResponse:
    """
    创建统一的错误响应
    
    Args:
        code: 错误代码
        message: 错误消息
        details: 错误详情（可选）
        status_code: HTTP 状态码
    
    Returns:
        JSONResponse: 格式化的错误响应
    """
    error_data = {
        "error": {
            "code": code,
            "message": message
        }
    }
    
    if details:
        error_data["error"]["details"] = details
    
    return JSONResponse(
        status_code=status_code,
        content=error_data
    )


# 认证依赖函数
async def require_auth(
    x_session_token: Optional[str] = Header(None, alias="X-Session-Token"),
) -> Session:
    """
    FastAPI 依赖函数：要求用户认证（管理员或普通用户）
    
    验证会话令牌并返回会话对象。如果令牌无效或缺失，抛出 401 错误。
    
    Args:
        x_session_token: 从请求头获取的会话令牌
    
    Returns:
        Session: 验证通过的会话对象
    
    Raises:
        HTTPException: 如果令牌无效或缺失（401）
    """
    _, session_service, _ = get_services()
    
    session_token = x_session_token
    
    # 检查令牌是否存在
    if not session_token:
        logger.warning("Authentication failed: No session token provided")
        raise HTTPException(
            status_code=401,
            detail={
                "error": {
                    "code": "NO_TOKEN",
                    "message": "未提供会话令牌，请先登录"
                }
            }
        )
    
    # 验证令牌
    session = session_service.verify_token(session_token)
    
    if not session:
        logger.warning("Authentication failed: Invalid or expired token")
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
        logger.warning("Authentication failed: Failed to refresh session activity")
        raise HTTPException(
            status_code=401,
            detail={
                "error": {
                    "code": "INVALID_TOKEN",
                    "message": "会话令牌无效或已过期，请重新登录"
                }
            }
        )
    
    # 检查用户是否活跃
    account_service, _, _ = get_services()
    account = account_service.get_user(session.username)
    
    if not account or not account.is_active:
        logger.warning(f"Authentication failed: User '{session.username}' is inactive")
        raise HTTPException(
            status_code=401,
            detail={
                "error": {
                    "code": "USER_INACTIVE",
                    "message": "用户账号已被停用"
                }
            }
        )
    
    logger.debug(f"Authentication successful: {session.username} (role: {session.role})")
    return session


async def require_admin(
    session: Session = Depends(require_auth)
) -> Session:
    """
    FastAPI 依赖函数：要求管理员认证
    
    验证用户是否为管理员。如果不是管理员，抛出 403 错误。
    
    Args:
        session: 从 require_auth 获取的会话对象
    
    Returns:
        Session: 验证通过的管理员会话对象
    
    Raises:
        HTTPException: 如果用户不是管理员（403）
    """
    if session.role != 'admin':
        logger.warning(
            f"Authorization failed: User '{session.username}' "
            f"(role: {session.role}) attempted to access admin endpoint"
        )
        raise HTTPException(
            status_code=403,
            detail={
                "error": {
                    "code": "ADMIN_REQUIRED",
                    "message": "此操作需要管理员权限"
                }
            }
        )
    
    logger.debug(f"Admin authorization successful: {session.username}")
    return session


async def check_translator_permission(
    translator: str,
    session: Session = Depends(require_auth)
) -> None:
    """
    FastAPI 依赖函数：检查翻译器权限
    
    验证用户是否有权限使用指定的翻译器。如果没有权限，抛出 403 错误。
    
    Args:
        translator: 翻译器名称
        session: 从 require_auth 获取的会话对象
    
    Raises:
        HTTPException: 如果用户没有权限使用该翻译器（403）
    """
    _, _, permission_service = get_services()
    
    # 检查权限
    has_permission = permission_service.check_translator_permission(
        session.username,
        translator
    )
    
    if not has_permission:
        # 获取用户的允许翻译器列表
        permissions = permission_service.get_user_permissions(session.username)
        allowed_translators = permissions.allowed_translators if permissions else []
        
        logger.warning(
            f"Permission denied: User '{session.username}' "
            f"attempted to use unauthorized translator '{translator}'"
        )
        
        raise HTTPException(
            status_code=403,
            detail={
                "error": {
                    "code": "TRANSLATOR_PERMISSION_DENIED",
                    "message": f"您没有权限使用翻译器 '{translator}'",
                    "details": {
                        "translator": translator,
                        "allowed_translators": allowed_translators
                    }
                }
            }
        )
    
    logger.debug(
        f"Translator permission check passed: "
        f"user='{session.username}', translator='{translator}'"
    )


async def check_parameter_permission(
    parameters: Dict[str, Any],
    session: Session = Depends(require_auth)
) -> Dict[str, Any]:
    """
    FastAPI 依赖函数：检查并过滤参数权限
    
    过滤用户提交的参数，只保留用户有权限调整的参数。
    不会抛出错误，而是静默过滤掉未授权的参数。
    
    Args:
        parameters: 用户提交的参数字典
        session: 从 require_auth 获取的会话对象
    
    Returns:
        Dict[str, Any]: 过滤后的参数字典
    """
    _, _, permission_service = get_services()
    
    # 过滤参数
    filtered_parameters = permission_service.filter_parameters(
        session.username,
        parameters
    )
    
    # 记录被过滤的参数
    filtered_keys = set(parameters.keys()) - set(filtered_parameters.keys())
    if filtered_keys:
        logger.info(
            f"Filtered parameters for user '{session.username}': "
            f"{', '.join(filtered_keys)}"
        )
    
    return filtered_parameters


# 并发和配额检查函数（不是依赖函数，而是在业务逻辑中调用）
def check_concurrent_limit(username: str) -> None:
    """
    检查用户的并发任务限制
    
    Args:
        username: 用户名
    
    Raises:
        HTTPException: 如果用户超过并发限制（429）
    """
    _, _, permission_service = get_services()
    
    can_create = permission_service.check_concurrent_limit(username)
    
    if not can_create:
        current_tasks = permission_service.get_active_task_count(username)
        # 使用有效的并发限制（优先从用户组获取）
        max_tasks = permission_service.get_effective_max_concurrent(username)
        
        logger.warning(
            f"Concurrent limit exceeded: User '{username}' "
            f"has {current_tasks}/{max_tasks} active tasks"
        )
        
        raise HTTPException(
            status_code=429,
            detail={
                "error": {
                    "code": "CONCURRENT_LIMIT_EXCEEDED",
                    "message": "您已达到最大并发任务数限制",
                    "details": {
                        "current_tasks": current_tasks,
                        "max_concurrent_tasks": max_tasks
                    }
                }
            }
        )


def check_daily_quota(username: str) -> None:
    """
    检查用户的每日配额
    
    Args:
        username: 用户名
    
    Raises:
        HTTPException: 如果用户超过每日配额（429）
    """
    _, _, permission_service = get_services()
    
    can_create = permission_service.check_daily_quota(username)
    
    if not can_create:
        current_usage = permission_service.get_daily_usage(username)
        # 使用有效配额（优先从用户组获取）
        daily_quota = permission_service.get_effective_daily_quota(username)
        
        logger.warning(
            f"Daily quota exceeded: User '{username}' "
            f"has used {current_usage}/{daily_quota} today"
        )
        
        raise HTTPException(
            status_code=429,
            detail={
                "error": {
                    "code": "DAILY_QUOTA_EXCEEDED",
                    "message": "您已达到今日翻译配额限制",
                    "details": {
                        "current_usage": current_usage,
                        "daily_quota": daily_quota
                    }
                }
            }
        )


# 任务计数管理函数（在任务开始和结束时调用）
def increment_task_count(username: str) -> None:
    """
    增加用户的活动任务计数
    
    Args:
        username: 用户名
    """
    _, _, permission_service = get_services()
    permission_service.increment_task_count(username)


def decrement_task_count(username: str) -> None:
    """
    减少用户的活动任务计数
    
    Args:
        username: 用户名
    """
    _, _, permission_service = get_services()
    permission_service.decrement_task_count(username)


def increment_daily_usage(username: str) -> None:
    """
    增加用户的每日使用量
    
    Args:
        username: 用户名
    """
    _, _, permission_service = get_services()
    permission_service.increment_daily_usage(username)
