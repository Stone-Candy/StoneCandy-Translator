"""
Session Security Models

This module defines data models for session/dialog security and ownership.
"""

import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Dict, Optional


@dataclass
class SessionOwnership:
    """
    Model representing session ownership binding.
    
    Attributes:
        session_token: Unique session identifier (UUID v4)
        user_id: ID of the user who owns this session
        created_at: Timestamp when session was created
        status: Session status (active, completed, failed)
        metadata: Additional session metadata
    """
    session_token: str
    user_id: str
    created_at: datetime
    status: str = "active"
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        # 返回前端期望的字段格式
        data = {
            'session_token': self.session_token,
            'user_id': self.user_id,
            'created_at': self.created_at.isoformat(),
            'status': self.status,
            # 前端兼容字段
            'username': self.user_id,
            'token': self.metadata.get('token', self.session_token),
            'ip': self.metadata.get('ip_address', ''),
            'user_agent': self.metadata.get('user_agent', ''),
            'is_active': self.status == 'active',
            'last_activity': self.metadata.get('last_activity', ''),
            'role': self.metadata.get('role', 'user'),
        }
        return data
    
    @classmethod
    def from_dict(cls, data: dict) -> 'SessionOwnership':
        """Create instance from dictionary."""
        data = data.copy()
        
        # 兼容旧格式数据 (session_id -> session_token, username -> user_id)
        if 'session_id' in data and 'session_token' not in data:
            data['session_token'] = data.pop('session_id')
        if 'username' in data and 'user_id' not in data:
            data['user_id'] = data.pop('username')
        
        # 处理 created_at 字段
        if isinstance(data.get('created_at'), str):
            data['created_at'] = datetime.fromisoformat(data['created_at'])
        
        # 处理 status 字段 (从 is_active 转换)
        if 'status' not in data:
            if data.get('is_active', True):
                data['status'] = 'active'
            else:
                data['status'] = 'inactive'
        
        # 将额外字段放入 metadata
        known_fields = {'session_token', 'user_id', 'created_at', 'status', 'metadata'}
        extra_fields = {k: v for k, v in data.items() if k not in known_fields}
        if extra_fields:
            metadata = data.get('metadata', {})
            metadata.update(extra_fields)
            data['metadata'] = metadata
        
        # 只保留模型需要的字段
        filtered_data = {k: v for k, v in data.items() if k in known_fields}
        
        return cls(**filtered_data)
    
    @staticmethod
    def generate_session_token() -> str:
        """
        Generate a secure, unpredictable session token using UUID v4.
        
        Returns:
            A UUID v4 string
        """
        return str(uuid.uuid4())


@dataclass
class SessionAccessAttempt:
    """
    Model representing a session access attempt for audit logging.
    
    Attributes:
        session_token: Session being accessed
        user_id: User attempting access
        timestamp: When the access was attempted
        action: Action being attempted (view, edit, delete, export)
        granted: Whether access was granted
        reason: Reason for denial if not granted
    """
    session_token: str
    user_id: str
    timestamp: datetime
    action: str
    granted: bool
    reason: Optional[str] = None
    
    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        data = asdict(self)
        data['timestamp'] = self.timestamp.isoformat()
        return data
    
    @classmethod
    def from_dict(cls, data: dict) -> 'SessionAccessAttempt':
        """Create instance from dictionary."""
        data = data.copy()
        if isinstance(data.get('timestamp'), str):
            data['timestamp'] = datetime.fromisoformat(data['timestamp'])
        return cls(**data)
