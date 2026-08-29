"""
User management routes module.

This module contains all /users/* endpoints for user account management.
"""

import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from manga_translator.server.core.audit_service import AuditService
from manga_translator.server.core.middleware import get_services, require_admin
from manga_translator.server.core.models import Session, UserPermissions

logger = logging.getLogger('manga_translator.server')

router = APIRouter(prefix="/api/admin/users", tags=["users"])


# ============================================================================
# Request/Response Models
# ============================================================================

class CreateUserRequest(BaseModel):
    """创建用户请求"""
    username: str = Field(..., min_length=1, max_length=50, description="用户名")
    password: str = Field(..., min_length=6, description="密码（至少6个字符）")
    role: str = Field(..., pattern="^(admin|user)$", description="角色（admin 或 user）")
    group: str = Field(default="default", description="用户组名称")
    permissions: Optional[dict] = Field(None, description="用户权限（可选）")


class UpdateUserRequest(BaseModel):
    """更新用户请求"""
    role: Optional[str] = Field(None, pattern="^(admin|user)$", description="角色")
    group: Optional[str] = Field(None, description="用户组名称")
    is_active: Optional[bool] = Field(None, description="是否激活")
    must_change_password: Optional[bool] = Field(None, description="是否必须修改密码")


class UpdatePermissionsRequest(BaseModel):
    """更新权限请求"""
    allowed_translators: Optional[List[str]] = Field(None, description="允许使用的翻译器列表（白名单）")
    denied_translators: Optional[List[str]] = Field(None, description="禁止使用的翻译器列表（黑名单）")
    allowed_ocr: Optional[List[str]] = Field(None, description="允许使用的 OCR 列表（白名单）")
    denied_ocr: Optional[List[str]] = Field(None, description="禁止使用的 OCR 列表（黑名单）")
    allowed_colorizers: Optional[List[str]] = Field(None, description="允许使用的上色器列表（白名单）")
    denied_colorizers: Optional[List[str]] = Field(None, description="禁止使用的上色器列表（黑名单）")
    allowed_renderers: Optional[List[str]] = Field(None, description="允许使用的渲染器列表（白名单）")
    denied_renderers: Optional[List[str]] = Field(None, description="禁止使用的渲染器列表（黑名单）")
    allowed_workflows: Optional[List[str]] = Field(None, description="允许使用的工作流列表（白名单）")
    denied_workflows: Optional[List[str]] = Field(None, description="禁止使用的工作流列表（黑名单）")
    allowed_parameters: Optional[List[str]] = Field(None, description="允许调整的参数列表（白名单）")
    denied_parameters: Optional[List[str]] = Field(None, description="禁止调整的参数列表（黑名单）")
    max_concurrent_tasks: Optional[int] = Field(None, ge=0, description="最大并发任务数")
    daily_quota: Optional[int] = Field(None, ge=-1, description="每日翻译配额（-1表示无限制）")
    can_upload_files: Optional[bool] = Field(None, description="是否可以上传文件")
    can_delete_files: Optional[bool] = Field(None, description="是否可以删除文件")


class UserResponse(BaseModel):
    """用户响应"""
    username: str
    role: str
    group: str
    permissions: dict
    created_at: str
    last_login: Optional[str]
    is_active: bool
    must_change_password: bool


# ============================================================================
# User Management Endpoints
# ============================================================================

@router.post("", response_model=UserResponse, status_code=201)
async def create_user(
    request: CreateUserRequest,
    session: Session = Depends(require_admin)
):
    """
    创建新用户（管理员）
    
    需要管理员权限。创建新用户账号并设置初始权限。
    
    - **username**: 用户名（唯一）
    - **password**: 密码（至少6个字符）
    - **role**: 角色（admin 或 user）
    - **permissions**: 用户权限（可选，如果不提供则使用默认权限）
    """
    account_service, _, _ = get_services()
    
    try:
        # 解析权限
        permissions = None
        if request.permissions:
            permissions = UserPermissions.from_dict(request.permissions)
        
        # 创建用户
        account = account_service.create_user(
            username=request.username,
            password=request.password,
            role=request.role,
            group=request.group,
            permissions=permissions
        )
        
        # 记录审计日志
        try:
            audit_service = AuditService()
            audit_service.log_event(
                event_type='create_user',
                username=session.username,
                ip_address='',  # TODO: 从请求中获取
                details={
                    'target_user': request.username,
                    'role': request.role
                },
                result='success'
            )
        except Exception as e:
            logger.warning(f"Failed to log audit event: {e}")
        
        logger.info(f"User created by admin '{session.username}': {request.username}")
        
        return UserResponse(
            username=account.username,
            role=account.role,
            group=account.group,
            permissions=account.permissions.to_dict(),
            created_at=account.created_at.isoformat(),
            last_login=account.last_login.isoformat() if account.last_login else None,
            is_active=account.is_active,
            must_change_password=account.must_change_password
        )
    
    except ValueError as e:
        logger.warning(f"Failed to create user: {e}")
        raise HTTPException(
            status_code=400,
            detail={
                "error": {
                    "code": "INVALID_REQUEST",
                    "message": str(e)
                }
            }
        )
    except Exception as e:
        logger.error(f"Error creating user: {e}")
        raise HTTPException(
            status_code=500,
            detail={
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": "创建用户时发生错误"
                }
            }
        )


@router.get("")
async def list_users(
    session: Session = Depends(require_admin)
):
    """
    列出所有用户（管理员）
    
    需要管理员权限。返回所有用户账号的列表，包含配额使用情况。
    """
    account_service, _, permission_service = get_services()
    
    try:
        accounts = account_service.list_users()
        
        result = []
        for account in accounts:
            # 获取用户的配额使用情况
            daily_used = permission_service.get_daily_usage(account.username)
            daily_limit = permission_service.get_effective_daily_quota(account.username)
            
            user_data = {
                "username": account.username,
                "role": account.role,
                "group": account.group,
                "permissions": account.permissions.to_dict(),
                "created_at": account.created_at.isoformat(),
                "last_login": account.last_login.isoformat() if account.last_login else None,
                "is_active": account.is_active,
                "must_change_password": account.must_change_password,
                "quota": {
                    "daily_used": daily_used,
                    "daily_limit": daily_limit if daily_limit > 0 else 999999,
                    "monthly_used": 0,  # TODO: 实现月度统计
                    "monthly_limit": 999999
                }
            }
            result.append(user_data)
        
        return result
    
    except Exception as e:
        logger.error(f"Error listing users: {e}")
        raise HTTPException(
            status_code=500,
            detail={
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": "获取用户列表时发生错误"
                }
            }
        )


@router.get("/{username}", response_model=UserResponse)
async def get_user(
    username: str,
    session: Session = Depends(require_admin)
):
    """
    获取用户信息（管理员）
    
    需要管理员权限。返回指定用户的详细信息。
    
    - **username**: 用户名
    """
    account_service, _, _ = get_services()
    
    try:
        account = account_service.get_user(username)
        
        if not account:
            raise HTTPException(
                status_code=404,
                detail={
                    "error": {
                        "code": "USER_NOT_FOUND",
                        "message": f"用户 '{username}' 不存在"
                    }
                }
            )
        
        return UserResponse(
            username=account.username,
            role=account.role,
            group=account.group,
            permissions=account.permissions.to_dict(),
            created_at=account.created_at.isoformat(),
            last_login=account.last_login.isoformat() if account.last_login else None,
            is_active=account.is_active,
            must_change_password=account.must_change_password
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting user: {e}")
        raise HTTPException(
            status_code=500,
            detail={
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": "获取用户信息时发生错误"
                }
            }
        )


@router.put("/{username}", response_model=UserResponse)
async def update_user(
    username: str,
    request: UpdateUserRequest,
    session: Session = Depends(require_admin)
):
    """
    更新用户信息（管理员）
    
    需要管理员权限。更新用户的角色、激活状态等信息。
    
    - **username**: 用户名
    - **role**: 角色（可选）
    - **is_active**: 是否激活（可选）
    - **must_change_password**: 是否必须修改密码（可选）
    """
    account_service, session_service, _ = get_services()
    
    try:
        # 构建更新字典
        updates = {}
        if request.role is not None:
            updates['role'] = request.role
        if request.group is not None:
            updates['group'] = request.group
        if request.is_active is not None:
            updates['is_active'] = request.is_active
        if request.must_change_password is not None:
            updates['must_change_password'] = request.must_change_password
        
        if not updates:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": {
                        "code": "NO_UPDATES",
                        "message": "没有提供要更新的字段"
                    }
                }
            )
        
        # 更新用户
        account_service.update_user(username, updates)
        
        # 如果停用用户，终止其所有会话
        if request.is_active is False:
            terminated_count = session_service.terminate_user_sessions(username)
            logger.info(f"Terminated {terminated_count} session(s) for deactivated user: {username}")
        
        # 记录审计日志
        try:
            audit_service = AuditService()
            audit_service.log_event(
                event_type='update_user',
                username=session.username,
                ip_address='',  # TODO: 从请求中获取
                details={
                    'target_user': username,
                    'updates': updates
                },
                result='success'
            )
        except Exception as e:
            logger.warning(f"Failed to log audit event: {e}")
        
        # 获取更新后的用户信息
        account = account_service.get_user(username)
        
        logger.info(f"User updated by admin '{session.username}': {username}")
        
        return UserResponse(
            username=account.username,
            role=account.role,
            group=account.group,
            permissions=account.permissions.to_dict(),
            created_at=account.created_at.isoformat(),
            last_login=account.last_login.isoformat() if account.last_login else None,
            is_active=account.is_active,
            must_change_password=account.must_change_password
        )
    
    except ValueError as e:
        logger.warning(f"Failed to update user: {e}")
        raise HTTPException(
            status_code=400,
            detail={
                "error": {
                    "code": "INVALID_REQUEST",
                    "message": str(e)
                }
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating user: {e}")
        raise HTTPException(
            status_code=500,
            detail={
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": "更新用户信息时发生错误"
                }
            }
        )


@router.delete("/{username}", status_code=204)
async def delete_user(
    username: str,
    session: Session = Depends(require_admin)
):
    """
    删除用户（管理员）
    
    需要管理员权限。删除指定用户账号并终止其所有会话。
    
    - **username**: 用户名
    """
    account_service, session_service, _ = get_services()
    
    try:
        # 防止删除自己
        if username == session.username:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": {
                        "code": "CANNOT_DELETE_SELF",
                        "message": "不能删除自己的账号"
                    }
                }
            )
        
        # 终止用户的所有会话
        terminated_count = session_service.terminate_user_sessions(username)
        logger.info(f"Terminated {terminated_count} session(s) for deleted user: {username}")
        
        # 删除用户
        account_service.delete_user(username)
        
        # 记录审计日志
        try:
            audit_service = AuditService()
            audit_service.log_event(
                event_type='delete_user',
                username=session.username,
                ip_address='',  # TODO: 从请求中获取
                details={
                    'target_user': username
                },
                result='success'
            )
        except Exception as e:
            logger.warning(f"Failed to log audit event: {e}")
        
        logger.info(f"User deleted by admin '{session.username}': {username}")
        
        return None  # 204 No Content
    
    except ValueError as e:
        logger.warning(f"Failed to delete user: {e}")
        raise HTTPException(
            status_code=404,
            detail={
                "error": {
                    "code": "USER_NOT_FOUND",
                    "message": str(e)
                }
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting user: {e}")
        raise HTTPException(
            status_code=500,
            detail={
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": "删除用户时发生错误"
                }
            }
        )


@router.put("/{username}/permissions", response_model=UserResponse)
async def update_user_permissions(
    username: str,
    request: UpdatePermissionsRequest,
    session: Session = Depends(require_admin)
):
    """
    更新用户权限（管理员）
    
    需要管理员权限。更新用户的权限配置。
    
    - **username**: 用户名
    - **allowed_translators**: 允许使用的翻译器列表（可选）
    - **allowed_parameters**: 允许调整的参数列表（可选）
    - **max_concurrent_tasks**: 最大并发任务数（可选）
    - **daily_quota**: 每日翻译配额（可选，-1表示无限制）
    - **can_upload_files**: 是否可以上传文件（可选）
    - **can_delete_files**: 是否可以删除文件（可选）
    """
    account_service, _, permission_service = get_services()
    
    try:
        # 获取当前用户
        account = account_service.get_user(username)
        if not account:
            raise HTTPException(
                status_code=404,
                detail={
                    "error": {
                        "code": "USER_NOT_FOUND",
                        "message": f"用户 '{username}' 不存在"
                    }
                }
            )
        
        # 构建权限更新字典
        permissions_dict = account.permissions.to_dict()
        updated_fields = []
        
        if request.allowed_translators is not None:
            permissions_dict['allowed_translators'] = request.allowed_translators
            updated_fields.append('allowed_translators')
        if request.denied_translators is not None:
            permissions_dict['denied_translators'] = request.denied_translators
            updated_fields.append('denied_translators')
        if request.allowed_ocr is not None:
            permissions_dict['allowed_ocr'] = request.allowed_ocr
            updated_fields.append('allowed_ocr')
        if request.denied_ocr is not None:
            permissions_dict['denied_ocr'] = request.denied_ocr
            updated_fields.append('denied_ocr')
        if request.allowed_colorizers is not None:
            permissions_dict['allowed_colorizers'] = request.allowed_colorizers
            updated_fields.append('allowed_colorizers')
        if request.denied_colorizers is not None:
            permissions_dict['denied_colorizers'] = request.denied_colorizers
            updated_fields.append('denied_colorizers')
        if request.allowed_renderers is not None:
            permissions_dict['allowed_renderers'] = request.allowed_renderers
            updated_fields.append('allowed_renderers')
        if request.denied_renderers is not None:
            permissions_dict['denied_renderers'] = request.denied_renderers
            updated_fields.append('denied_renderers')
        if request.allowed_workflows is not None:
            permissions_dict['allowed_workflows'] = request.allowed_workflows
            updated_fields.append('allowed_workflows')
        if request.denied_workflows is not None:
            permissions_dict['denied_workflows'] = request.denied_workflows
            updated_fields.append('denied_workflows')
        if request.allowed_parameters is not None:
            permissions_dict['allowed_parameters'] = request.allowed_parameters
            updated_fields.append('allowed_parameters')
        if request.denied_parameters is not None:
            permissions_dict['denied_parameters'] = request.denied_parameters
            updated_fields.append('denied_parameters')
        if request.max_concurrent_tasks is not None:
            permissions_dict['max_concurrent_tasks'] = request.max_concurrent_tasks
            updated_fields.append('max_concurrent_tasks')
        if request.daily_quota is not None:
            permissions_dict['daily_quota'] = request.daily_quota
            updated_fields.append('daily_quota')
        if request.can_upload_files is not None:
            permissions_dict['can_upload_files'] = request.can_upload_files
            updated_fields.append('can_upload_files')
        if request.can_delete_files is not None:
            permissions_dict['can_delete_files'] = request.can_delete_files
            updated_fields.append('can_delete_files')
        
        if not updated_fields:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": {
                        "code": "NO_UPDATES",
                        "message": "没有提供要更新的权限字段"
                    }
                }
            )
        
        # 更新权限
        account_service.update_user(username, {'permissions': permissions_dict})
        
        # 记录审计日志
        try:
            audit_service = AuditService()
            audit_service.log_event(
                event_type='update_permissions',
                username=session.username,
                ip_address='',  # TODO: 从请求中获取
                details={
                    'target_user': username,
                    'updated_fields': updated_fields,
                    'new_permissions': permissions_dict
                },
                result='success'
            )
        except Exception as e:
            logger.warning(f"Failed to log audit event: {e}")
        
        # 获取更新后的用户信息
        account = account_service.get_user(username)
        
        logger.info(f"Permissions updated by admin '{session.username}' for user: {username}")
        
        return UserResponse(
            username=account.username,
            role=account.role,
            group=account.group,
            permissions=account.permissions.to_dict(),
            created_at=account.created_at.isoformat(),
            last_login=account.last_login.isoformat() if account.last_login else None,
            is_active=account.is_active,
            must_change_password=account.must_change_password
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating user permissions: {e}")
        raise HTTPException(
            status_code=500,
            detail={
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": "更新用户权限时发生错误"
                }
            }
        )
