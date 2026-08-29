"""
Group management routes module.

This module contains all /groups/* endpoints for user group management.
"""

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from manga_translator.server.core.group_management_service import (
    get_group_management_service,
)
from manga_translator.server.core.middleware import require_admin
from manga_translator.server.core.models import Session

logger = logging.getLogger('manga_translator.server')

router = APIRouter(prefix="/api/admin/groups", tags=["groups"])


# ============================================================================
# Request/Response Models
# ============================================================================

class GroupResponse(BaseModel):
    """用户组响应"""
    name: str
    display_name: str
    description: str
    parameter_config: Dict[str, Any]


class CreateGroupRequest(BaseModel):
    """创建用户组请求"""
    group_id: str = Field(..., description="用户组ID")
    name: str = Field(..., description="用户组名称")
    description: str = Field(..., description="描述")
    parameter_config: Optional[Dict[str, Any]] = Field(default=None, description="参数配置")
    permissions: Optional[Dict[str, Any]] = Field(default=None, description="权限配置")
    quota_limits: Optional[Dict[str, Any]] = Field(default=None, description="配额限制")
    visible_presets: Optional[List[str]] = Field(default=None, description="可见预设列表")
    default_preset_id: Optional[str] = Field(default=None, description="默认API密钥预设ID")


class RenameGroupRequest(BaseModel):
    """重命名用户组请求"""
    new_group_id: str = Field(..., description="新用户组ID")
    new_name: str = Field(..., description="新用户组名称")


class UpdateGroupRequest(BaseModel):
    """更新用户组请求"""
    display_name: str = Field(..., description="显示名称")
    description: str = Field(..., description="描述")
    parameter_config: Dict[str, Any] = Field(..., description="参数配置")


class UpdateGroupConfigRequest(BaseModel):
    """更新用户组配置请求"""
    parameter_config: Dict[str, Any] = Field(default={}, description="参数配置")
    allowed_translators: Optional[List[str]] = Field(default=None, description="翻译器白名单")
    denied_translators: Optional[List[str]] = Field(default=None, description="翻译器黑名单")
    allowed_ocr: Optional[List[str]] = Field(default=None, description="OCR 白名单")
    denied_ocr: Optional[List[str]] = Field(default=None, description="OCR 黑名单")
    allowed_colorizers: Optional[List[str]] = Field(default=None, description="上色器白名单")
    denied_colorizers: Optional[List[str]] = Field(default=None, description="上色器黑名单")
    allowed_renderers: Optional[List[str]] = Field(default=None, description="渲染器白名单")
    denied_renderers: Optional[List[str]] = Field(default=None, description="渲染器黑名单")
    allowed_workflows: Optional[List[str]] = Field(default=None, description="工作流白名单")
    denied_workflows: Optional[List[str]] = Field(default=None, description="工作流黑名单")
    default_preset_id: Optional[str] = Field(default=None, description="默认API密钥预设ID")
    visible_presets: Optional[List[str]] = Field(default=None, description="可见的API预设列表")


# ============================================================================
# Group Management Endpoints
# ============================================================================


# ============================================================================
# New Group Management Endpoints (Task 8.2)
# ============================================================================

@router.post("", status_code=201)
async def create_group(
    request: CreateGroupRequest,
    session: Session = Depends(require_admin)
):
    """
    创建新用户组（管理员）
    
    需要管理员权限。创建一个新的用户组。
    """
    group_mgmt_service = get_group_management_service()
    
    try:
        # 创建用户组
        group = group_mgmt_service.create_group(
            group_id=request.group_id,
            name=request.name,
            description=request.description,
            admin_id=session.username,
            permissions=request.permissions,
            quota_limits=request.quota_limits,
            visible_presets=request.visible_presets,
            parameter_config=request.parameter_config
        )
        
        if not group:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": {
                        "code": "CREATE_FAILED",
                        "message": f"创建用户组失败，可能用户组ID '{request.group_id}' 已存在"
                    }
                }
            )
        
        logger.info(f"Group created by admin '{session.username}': {request.group_id}")
        
        return {
            "success": True,
            "message": "用户组创建成功",
            "group": {
                "id": group.id,
                "name": group.name,
                "description": group.description,
                "is_system": group.is_system
            }
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating group: {e}")
        raise HTTPException(
            status_code=500,
            detail={
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": "创建用户组失败"
                }
            }
        )


@router.put("/{group_id}/rename")
async def rename_group(
    group_id: str,
    request: RenameGroupRequest,
    session: Session = Depends(require_admin)
):
    """
    重命名用户组（管理员）
    
    需要管理员权限。重命名一个用户组，并自动更新所有用户的组关联。
    """
    group_mgmt_service = get_group_management_service()
    
    try:
        # 重命名用户组
        success = group_mgmt_service.rename_group(
            old_group_id=group_id,
            new_group_id=request.new_group_id,
            new_name=request.new_name,
            admin_id=session.username
        )
        
        if not success:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": {
                        "code": "RENAME_FAILED",
                        "message": "重命名用户组失败，可能是系统组或新ID已存在"
                    }
                }
            )
        
        logger.info(f"Group renamed by admin '{session.username}': {group_id} -> {request.new_group_id}")
        
        return {
            "success": True,
            "message": "用户组重命名成功",
            "old_group_id": group_id,
            "new_group_id": request.new_group_id,
            "new_name": request.new_name
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error renaming group: {e}")
        raise HTTPException(
            status_code=500,
            detail={
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": "重命名用户组失败"
                }
            }
        )


@router.delete("/{group_id}")
async def delete_group(
    group_id: str,
    session: Session = Depends(require_admin)
):
    """
    删除用户组（管理员）
    
    需要管理员权限。删除一个用户组，并将该组的所有用户移动到default组。
    系统预定义的用户组（admin, default, guest）不能被删除。
    """
    group_mgmt_service = get_group_management_service()
    
    try:
        # 删除用户组
        success = group_mgmt_service.delete_group(
            group_id=group_id,
            admin_id=session.username
        )
        
        if not success:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": {
                        "code": "DELETE_FAILED",
                        "message": "删除用户组失败，可能是系统组或不存在"
                    }
                }
            )
        
        logger.info(f"Group deleted by admin '{session.username}': {group_id}")
        
        return {
            "success": True,
            "message": "用户组删除成功，该组用户已移动到default组",
            "group_id": group_id
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting group: {e}")
        raise HTTPException(
            status_code=500,
            detail={
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": "删除用户组失败"
                }
            }
        )


@router.get("")
async def get_all_groups(
    session: Session = Depends(require_admin)
):
    """
    获取所有用户组（管理员）
    
    需要管理员权限。返回所有用户组的列表。
    """
    group_mgmt_service = get_group_management_service()
    
    try:
        groups = group_mgmt_service.get_all_groups()
        
        logger.info(f"Groups listed by admin '{session.username}'")
        
        return {
            "success": True,
            "groups": groups
        }
    
    except Exception as e:
        logger.error(f"Error getting all groups: {e}")
        raise HTTPException(
            status_code=500,
            detail={
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": "获取用户组列表失败"
                }
            }
        )


@router.get("/{group_id}")
async def get_group(
    group_id: str,
    session: Session = Depends(require_admin)
):
    """
    获取指定用户组（管理员）
    
    需要管理员权限。返回指定用户组的信息。
    """
    group_mgmt_service = get_group_management_service()
    
    try:
        group = group_mgmt_service.get_group(group_id)
        
        if not group:
            raise HTTPException(
                status_code=404,
                detail={
                    "error": {
                        "code": "GROUP_NOT_FOUND",
                        "message": f"用户组 '{group_id}' 不存在"
                    }
                }
            )
        
        logger.info(f"Group retrieved by admin '{session.username}': {group_id}")
        
        return {
            "success": True,
            "group": group
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting group: {e}")
        raise HTTPException(
            status_code=500,
            detail={
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": "获取用户组失败"
                }
            }
        )


@router.put("/{group_id}/config")
async def update_group_config(
    group_id: str,
    request: UpdateGroupConfigRequest,
    session: Session = Depends(require_admin)
):
    """
    更新用户组配置（管理员）
    
    需要管理员权限。更新指定用户组的参数配置、翻译器白名单/黑名单等。
    """
    group_mgmt_service = get_group_management_service()
    
    try:
        # 构建完整配置
        config = {
            'parameter_config': request.parameter_config
        }
        
        # 添加翻译器白名单/黑名单
        if request.allowed_translators is not None:
            config['allowed_translators'] = request.allowed_translators
        if request.denied_translators is not None:
            config['denied_translators'] = request.denied_translators
        if request.allowed_ocr is not None:
            config['allowed_ocr'] = request.allowed_ocr
        if request.denied_ocr is not None:
            config['denied_ocr'] = request.denied_ocr
        if request.allowed_colorizers is not None:
            config['allowed_colorizers'] = request.allowed_colorizers
        if request.denied_colorizers is not None:
            config['denied_colorizers'] = request.denied_colorizers
        if request.allowed_renderers is not None:
            config['allowed_renderers'] = request.allowed_renderers
        if request.denied_renderers is not None:
            config['denied_renderers'] = request.denied_renderers
        # 添加工作流白名单/黑名单
        if request.allowed_workflows is not None:
            config['allowed_workflows'] = request.allowed_workflows
        if request.denied_workflows is not None:
            config['denied_workflows'] = request.denied_workflows
        if request.default_preset_id is not None:
            config['default_preset_id'] = request.default_preset_id
        if request.visible_presets is not None:
            config['visible_presets'] = request.visible_presets
        
        # 更新配置
        success = group_mgmt_service.update_group_config(
            group_id=group_id,
            config=config,
            admin_id=session.username
        )
        
        if not success:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": {
                        "code": "UPDATE_FAILED",
                        "message": "更新用户组配置失败，用户组可能不存在"
                    }
                }
            )
        
        logger.info(f"Group config updated by admin '{session.username}': {group_id}")
        
        return {
            "success": True,
            "message": "用户组配置更新成功",
            "group_id": group_id
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating group config: {e}")
        raise HTTPException(
            status_code=500,
            detail={
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": "更新用户组配置失败"
                }
            }
        )
