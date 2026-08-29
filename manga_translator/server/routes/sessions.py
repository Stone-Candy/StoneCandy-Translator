"""
Session Management Routes

This module provides API endpoints for session management with ownership-based access control.
"""

from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from manga_translator.server.core.session_security_service import SessionSecurityService

router = APIRouter(prefix="/sessions", tags=["sessions"])

# Initialize service
session_security_service = SessionSecurityService()


class CreateSessionRequest(BaseModel):
    metadata: Optional[dict] = None


class UpdateStatusRequest(BaseModel):
    status: str


async def get_current_user(
    x_session_token: Optional[str] = Header(None, alias="X-Session-Token")
):
    """Get current user from session token header."""
    if not x_session_token:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    # 验证token并获取用户信息
    from manga_translator.server.core.middleware import get_services
    _, session_service, _ = get_services()
    
    session = session_service.verify_token(x_session_token)
    if not session:
        raise HTTPException(status_code=401, detail="Invalid or expired session token")
    
    return {
        "user_id": session.username,
        "is_admin": session.role == "admin"
    }


@router.post("/")
async def create_session(
    request: CreateSessionRequest,
    current_user: dict = Depends(get_current_user)
):
    """Create a new session."""
    user_id = current_user.get("user_id")
    metadata = request.metadata or {}
    
    session = session_security_service.create_session(user_id, metadata)
    
    return JSONResponse(content=session.to_dict(), status_code=201)


@router.get("/")
async def list_sessions(
    all: bool = Query(False, description="Show all sessions (admin only)"),
    current_user: dict = Depends(get_current_user)
):
    """List sessions for the current user."""
    user_id = current_user.get("user_id")
    
    if all:
        sessions = session_security_service.get_all_sessions(user_id)
        if sessions is None:
            raise HTTPException(status_code=403, detail="Permission denied: Admin access required")
    else:
        sessions = session_security_service.get_user_sessions(user_id)
    
    return {"sessions": [s.to_dict() for s in sessions]}


@router.get("/{session_token}")
async def get_session(
    session_token: str,
    current_user: dict = Depends(get_current_user)
):
    """Get details of a specific session."""
    user_id = current_user.get("user_id")
    
    # Check ownership
    allowed, reason = session_security_service.check_session_ownership(
        session_token, user_id, "view"
    )
    
    if not allowed:
        raise HTTPException(status_code=403, detail=reason)
    
    session = session_security_service.repository.get_session(session_token)
    
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    return session.to_dict()


@router.delete("/{session_token}")
async def delete_session(
    session_token: str,
    current_user: dict = Depends(get_current_user)
):
    """Delete a session."""
    user_id = current_user.get("user_id")
    
    # Check ownership
    allowed, reason = session_security_service.check_session_ownership(
        session_token, user_id, "delete"
    )
    
    if not allowed:
        raise HTTPException(status_code=403, detail=reason)
    
    success, error = session_security_service.delete_session(session_token, user_id)
    
    if not success:
        raise HTTPException(status_code=400, detail=error)
    
    return {"message": "Session deleted successfully"}


@router.put("/{session_token}/status")
async def update_session_status(
    session_token: str,
    request: UpdateStatusRequest,
    current_user: dict = Depends(get_current_user)
):
    """Update session status."""
    user_id = current_user.get("user_id")
    
    # Check ownership
    allowed, reason = session_security_service.check_session_ownership(
        session_token, user_id, "edit"
    )
    
    if not allowed:
        raise HTTPException(status_code=403, detail=reason)
    
    if request.status not in ['active', 'completed', 'failed']:
        raise HTTPException(status_code=400, detail="Invalid status")
    
    success = session_security_service.update_session_status(session_token, request.status)
    
    if not success:
        raise HTTPException(status_code=404, detail="Session not found")
    
    return {"message": "Status updated successfully"}


@router.get("/access-log")
async def get_access_log(
    session_token: Optional[str] = Query(None),
    user_id: Optional[str] = Query(None),
    granted: Optional[bool] = Query(None),
    limit: int = Query(100),
    current_user: dict = Depends(get_current_user)
):
    """Get session access attempts (admin only)."""
    current_user_id = current_user.get("user_id")
    
    if not session_security_service._is_admin(current_user_id):
        raise HTTPException(status_code=403, detail="Permission denied: Admin access required")
    
    attempts = session_security_service.repository.get_access_attempts(
        session_token=session_token,
        user_id=user_id,
        granted=granted,
        limit=limit
    )
    
    return {"attempts": [a.to_dict() for a in attempts]}


@router.get("/access-log/unauthorized")
async def get_unauthorized_attempts(
    limit: int = Query(100),
    current_user: dict = Depends(get_current_user)
):
    """Get unauthorized access attempts (admin only)."""
    user_id = current_user.get("user_id")
    
    attempts = session_security_service.get_unauthorized_attempts(user_id, limit)
    
    if attempts is None:
        raise HTTPException(status_code=403, detail="Permission denied: Admin access required")
    
    return {"attempts": [a.to_dict() for a in attempts]}
