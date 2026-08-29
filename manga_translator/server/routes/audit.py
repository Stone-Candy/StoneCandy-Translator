"""
Audit log routes module.

This module contains all /audit/* endpoints for audit log management.
"""

import logging
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel

from manga_translator.server.core.audit_service import AuditService
from manga_translator.server.core.middleware import require_admin
from manga_translator.server.core.models import Session

logger = logging.getLogger('manga_translator.server')

router = APIRouter(prefix="/audit", tags=["audit"])


# ============================================================================
# Request/Response Models
# ============================================================================

class AuditEventResponse(BaseModel):
    """审计事件响应"""
    event_id: str
    timestamp: str
    event_type: str
    username: str
    ip_address: str
    details: dict
    result: str


# ============================================================================
# Audit Log Endpoints
# ============================================================================

@router.get("/events", response_model=List[AuditEventResponse])
async def query_audit_events(
    username: Optional[str] = Query(None, description="按用户名筛选"),
    event_type: Optional[str] = Query(None, description="按事件类型筛选"),
    result: Optional[str] = Query(None, pattern="^(success|failure)$", description="按结果筛选"),
    start_time: Optional[str] = Query(None, description="开始时间（ISO格式）"),
    end_time: Optional[str] = Query(None, description="结束时间（ISO格式）"),
    limit: int = Query(100, ge=1, le=1000, description="返回的最大事件数"),
    offset: int = Query(0, ge=0, description="跳过的事件数（用于分页）"),
    session: Session = Depends(require_admin)
):
    """
    查询审计事件（管理员）
    
    需要管理员权限。查询审计日志，支持多种筛选条件。
    
    - **username**: 按用户名筛选（可选）
    - **event_type**: 按事件类型筛选（可选）
    - **result**: 按结果筛选（success 或 failure，可选）
    - **start_time**: 开始时间，ISO格式（可选）
    - **end_time**: 结束时间，ISO格式（可选）
    - **limit**: 返回的最大事件数（默认100，最大1000）
    - **offset**: 跳过的事件数，用于分页（默认0）
    """
    try:
        # 构建筛选条件
        filters = {}
        
        if username:
            filters['username'] = username
        if event_type:
            filters['event_type'] = event_type
        if result:
            filters['result'] = result
        if start_time:
            try:
                filters['start_time'] = datetime.fromisoformat(start_time)
            except ValueError:
                raise HTTPException(
                    status_code=400,
                    detail={
                        "error": {
                            "code": "INVALID_TIME_FORMAT",
                            "message": "start_time 格式无效，请使用 ISO 格式"
                        }
                    }
                )
        if end_time:
            try:
                filters['end_time'] = datetime.fromisoformat(end_time)
            except ValueError:
                raise HTTPException(
                    status_code=400,
                    detail={
                        "error": {
                            "code": "INVALID_TIME_FORMAT",
                            "message": "end_time 格式无效，请使用 ISO 格式"
                        }
                    }
                )
        
        # 查询审计事件
        audit_service = AuditService()
        events = audit_service.query_events(
            filters=filters,
            limit=limit,
            offset=offset
        )
        
        logger.info(
            f"Admin '{session.username}' queried audit events: "
            f"{len(events)} results (filters: {filters})"
        )
        
        return [
            AuditEventResponse(
                event_id=event.event_id,
                timestamp=event.timestamp.isoformat(),
                event_type=event.event_type,
                username=event.username,
                ip_address=event.ip_address,
                details=event.details,
                result=event.result
            )
            for event in events
        ]
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error querying audit events: {e}")
        raise HTTPException(
            status_code=500,
            detail={
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": "查询审计事件时发生错误"
                }
            }
        )


@router.get("/export")
async def export_audit_events(
    username: Optional[str] = Query(None, description="按用户名筛选"),
    event_type: Optional[str] = Query(None, description="按事件类型筛选"),
    result: Optional[str] = Query(None, pattern="^(success|failure)$", description="按结果筛选"),
    start_time: Optional[str] = Query(None, description="开始时间（ISO格式）"),
    end_time: Optional[str] = Query(None, description="结束时间（ISO格式）"),
    format: str = Query("json", pattern="^(json|csv)$", description="导出格式（json 或 csv）"),
    session: Session = Depends(require_admin)
):
    """
    导出审计日志（管理员）
    
    需要管理员权限。导出审计日志为 JSON 或 CSV 格式。
    
    - **username**: 按用户名筛选（可选）
    - **event_type**: 按事件类型筛选（可选）
    - **result**: 按结果筛选（success 或 failure，可选）
    - **start_time**: 开始时间，ISO格式（可选）
    - **end_time**: 结束时间，ISO格式（可选）
    - **format**: 导出格式（json 或 csv，默认 json）
    """
    try:
        # 构建筛选条件
        filters = {}
        
        if username:
            filters['username'] = username
        if event_type:
            filters['event_type'] = event_type
        if result:
            filters['result'] = result
        if start_time:
            try:
                filters['start_time'] = datetime.fromisoformat(start_time)
            except ValueError:
                raise HTTPException(
                    status_code=400,
                    detail={
                        "error": {
                            "code": "INVALID_TIME_FORMAT",
                            "message": "start_time 格式无效，请使用 ISO 格式"
                        }
                    }
                )
        if end_time:
            try:
                filters['end_time'] = datetime.fromisoformat(end_time)
            except ValueError:
                raise HTTPException(
                    status_code=400,
                    detail={
                        "error": {
                            "code": "INVALID_TIME_FORMAT",
                            "message": "end_time 格式无效，请使用 ISO 格式"
                        }
                    }
                )
        
        # 导出审计事件
        audit_service = AuditService()
        export_data = audit_service.export_events(
            filters=filters,
            format=format
        )
        
        # 记录审计日志
        try:
            audit_service.log_event(
                event_type='export_audit_log',
                username=session.username,
                ip_address='',  # TODO: 从请求中获取
                details={
                    'format': format,
                    'filters': {k: str(v) for k, v in filters.items()}
                },
                result='success'
            )
        except Exception as e:
            logger.warning(f"Failed to log audit event: {e}")
        
        logger.info(
            f"Admin '{session.username}' exported audit log: "
            f"format={format}, filters={filters}"
        )
        
        # 设置响应头
        media_type = "application/json" if format == "json" else "text/csv"
        from datetime import timezone
        filename = f"audit_log_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.{format}"
        
        return Response(
            content=export_data,
            media_type=media_type,
            headers={
                "Content-Disposition": f"attachment; filename={filename}"
            }
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error exporting audit events: {e}")
        raise HTTPException(
            status_code=500,
            detail={
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": "导出审计日志时发生错误"
                }
            }
        )
