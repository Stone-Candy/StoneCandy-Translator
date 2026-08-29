"""
配额管理路由模块

提供配额查询、统计和管理API。
"""

import logging
from typing import Dict, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from manga_translator.server.core.middleware import require_admin, require_auth
from manga_translator.server.core.models import Session
from manga_translator.server.core.quota_service import QuotaManagementService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["quota"])

# 全局服务实例（将在服务器启动时初始化）
_quota_service: QuotaManagementService = None


def init_quota_routes(quota_service: QuotaManagementService) -> None:
    """
    初始化配额路由使用的服务实例
    
    Args:
        quota_service: 配额管理服务
    """
    global _quota_service
    _quota_service = quota_service
    logger.info("Quota routes initialized")


def get_quota_service() -> QuotaManagementService:
    """获取配额管理服务实例"""
    if not _quota_service:
        raise RuntimeError("Quota service not initialized")
    return _quota_service


# ============================================================================
# 请求/响应模型
# ============================================================================

class QuotaStatsResponse(BaseModel):
    """配额统计响应"""
    user_id: str
    daily_limit: int
    used_today: int
    remaining: int
    active_sessions: int
    total_uploaded: int


class AllQuotaStatsResponse(BaseModel):
    """所有用户配额统计响应"""
    quotas: Dict[str, QuotaStatsResponse]
    total_users: int


class QuotaResetRequest(BaseModel):
    """配额重置请求"""
    user_id: Optional[str] = None  # None表示重置所有用户


class QuotaResetResponse(BaseModel):
    """配额重置响应"""
    success: bool
    message: str
    users_reset: Optional[int] = None


class SetQuotaLimitsRequest(BaseModel):
    """设置配额限制请求"""
    user_id: str
    max_file_size: Optional[int] = None
    max_files_per_upload: Optional[int] = None
    max_sessions: Optional[int] = None
    daily_quota: Optional[int] = None


# ============================================================================
# 用户配额端点
# ============================================================================

@router.get("/quota/stats", response_model=QuotaStatsResponse)
async def get_user_quota_stats(
    session: Session = Depends(require_auth),
    quota_service: QuotaManagementService = Depends(get_quota_service)
):
    """
    获取当前用户的配额统计
    
    Returns:
        QuotaStatsResponse: 配额统计信息
    """
    try:
        stats = quota_service.get_quota_stats(session.username)
        
        if not stats:
            raise HTTPException(status_code=404, detail="配额信息未找到")
        
        return QuotaStatsResponse(
            user_id=stats.user_id,
            daily_limit=stats.daily_limit,
            used_today=stats.used_today,
            remaining=stats.remaining,
            active_sessions=stats.active_sessions,
            total_uploaded=stats.total_uploaded
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting quota stats for user {session.username}: {e}")
        raise HTTPException(status_code=500, detail=f"获取配额统计失败: {str(e)}")


# ============================================================================
# 管理员配额端点
# ============================================================================

@router.get("/admin/quota/stats", response_model=AllQuotaStatsResponse)
async def get_all_quota_stats(
    session: Session = Depends(require_admin),
    quota_service: QuotaManagementService = Depends(get_quota_service)
):
    """
    获取所有用户的配额统计（管理员）
    
    Returns:
        AllQuotaStatsResponse: 所有用户的配额统计
    """
    try:
        all_stats = quota_service.get_all_quota_stats()
        
        # 转换为响应格式
        quotas_dict = {}
        for user_id, stats in all_stats.items():
            quotas_dict[user_id] = QuotaStatsResponse(
                user_id=stats.user_id,
                daily_limit=stats.daily_limit,
                used_today=stats.used_today,
                remaining=stats.remaining,
                active_sessions=stats.active_sessions,
                total_uploaded=stats.total_uploaded
            )
        
        return AllQuotaStatsResponse(
            quotas=quotas_dict,
            total_users=len(quotas_dict)
        )
        
    except Exception as e:
        logger.error(f"Error getting all quota stats: {e}")
        raise HTTPException(status_code=500, detail=f"获取配额统计失败: {str(e)}")


@router.post("/admin/quota/reset", response_model=QuotaResetResponse)
async def reset_quota(
    request: QuotaResetRequest,
    session: Session = Depends(require_admin),
    quota_service: QuotaManagementService = Depends(get_quota_service)
):
    """
    手动重置配额（管理员）
    
    Args:
        request: 重置请求，包含可选的user_id
        
    Returns:
        QuotaResetResponse: 重置结果
    """
    try:
        if request.user_id:
            # 重置单个用户
            success = quota_service.reset_daily_quota(request.user_id)
            
            if success:
                logger.info(f"Admin {session.username} reset quota for user {request.user_id}")
                return QuotaResetResponse(
                    success=True,
                    message=f"成功重置用户 {request.user_id} 的配额",
                    users_reset=1
                )
            else:
                return QuotaResetResponse(
                    success=False,
                    message=f"重置用户 {request.user_id} 的配额失败"
                )
        else:
            # 重置所有用户
            success = quota_service.reset_daily_quota(user_id=None)
            
            if success:
                all_quotas = quota_service.get_all_quota_stats()
                users_count = len(all_quotas)
                logger.info(f"Admin {session.username} reset quota for all users ({users_count} users)")
                return QuotaResetResponse(
                    success=True,
                    message="成功重置所有用户的配额",
                    users_reset=users_count
                )
            else:
                return QuotaResetResponse(
                    success=False,
                    message="重置所有用户配额失败"
                )
                
    except Exception as e:
        logger.error(f"Error resetting quota: {e}")
        raise HTTPException(status_code=500, detail=f"重置配额失败: {str(e)}")


@router.post("/admin/quota/set-limits")
async def set_quota_limits(
    request: SetQuotaLimitsRequest,
    session: Session = Depends(require_admin),
    quota_service: QuotaManagementService = Depends(get_quota_service)
):
    """
    设置用户的配额限制（管理员）
    
    Args:
        request: 配额限制设置请求
        
    Returns:
        dict: 操作结果
    """
    try:
        success = quota_service.set_user_quota_limits(
            user_id=request.user_id,
            max_file_size=request.max_file_size,
            max_files_per_upload=request.max_files_per_upload,
            max_sessions=request.max_sessions,
            daily_quota=request.daily_quota
        )
        
        if success:
            logger.info(f"Admin {session.username} updated quota limits for user {request.user_id}")
            return {
                "success": True,
                "message": f"成功更新用户 {request.user_id} 的配额限制"
            }
        else:
            return {
                "success": False,
                "message": f"更新用户 {request.user_id} 的配额限制失败"
            }
            
    except Exception as e:
        logger.error(f"Error setting quota limits: {e}")
        raise HTTPException(status_code=500, detail=f"设置配额限制失败: {str(e)}")


@router.get("/admin/quota/user/{user_id}", response_model=QuotaStatsResponse)
async def get_user_quota_stats_admin(
    user_id: str,
    session: Session = Depends(require_admin),
    quota_service: QuotaManagementService = Depends(get_quota_service)
):
    """
    获取指定用户的配额统计（管理员）
    
    Args:
        user_id: 用户ID
        
    Returns:
        QuotaStatsResponse: 配额统计信息
    """
    try:
        stats = quota_service.get_quota_stats(user_id)
        
        if not stats:
            raise HTTPException(status_code=404, detail=f"用户 {user_id} 的配额信息未找到")
        
        return QuotaStatsResponse(
            user_id=stats.user_id,
            daily_limit=stats.daily_limit,
            used_today=stats.used_today,
            remaining=stats.remaining,
            active_sessions=stats.active_sessions,
            total_uploaded=stats.total_uploaded
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting quota stats for user {user_id}: {e}")
        raise HTTPException(status_code=500, detail=f"获取配额统计失败: {str(e)}")
