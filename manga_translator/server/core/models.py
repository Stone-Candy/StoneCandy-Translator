"""
数据模型

定义用户账号、权限、会话和审计事件的数据模型类。
"""

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


@dataclass
class UserPermissions:
    """用户权限数据模型"""
    # 翻译器权限（白名单 + 黑名单）
    allowed_translators: List[str] = field(default_factory=lambda: ["*"])
    denied_translators: List[str] = field(default_factory=list)

    # OCR 权限（白名单 + 黑名单）
    allowed_ocr: List[str] = field(default_factory=list)
    denied_ocr: List[str] = field(default_factory=list)

    # 上色器权限（白名单 + 黑名单）
    allowed_colorizers: List[str] = field(default_factory=list)
    denied_colorizers: List[str] = field(default_factory=list)

    # 渲染器权限（白名单 + 黑名单）
    allowed_renderers: List[str] = field(default_factory=list)
    denied_renderers: List[str] = field(default_factory=list)

    # 工作流权限（白名单 + 黑名单）
    allowed_workflows: List[str] = field(default_factory=list)
    denied_workflows: List[str] = field(default_factory=list)
    
    # 参数权限（白名单 + 黑名单）
    allowed_parameters: List[str] = field(default_factory=lambda: ["*"])
    denied_parameters: List[str] = field(default_factory=list)
    
    # 配额限制
    max_concurrent_tasks: int = 10
    daily_quota: int = -1  # -1 表示无限制
    
    # 文件操作权限
    can_upload_files: bool = True
    can_delete_files: bool = True
    
    # 离线翻译权限
    allow_offline_translation: bool = False  # 是否允许离线翻译（用户离线后继续处理任务）
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'UserPermissions':
        """从字典创建"""
        return cls(
            allowed_translators=data.get('allowed_translators', ["*"]),
            denied_translators=data.get('denied_translators', []),
            allowed_ocr=data.get('allowed_ocr', []),
            denied_ocr=data.get('denied_ocr', []),
            allowed_colorizers=data.get('allowed_colorizers', []),
            denied_colorizers=data.get('denied_colorizers', []),
            allowed_renderers=data.get('allowed_renderers', []),
            denied_renderers=data.get('denied_renderers', []),
            allowed_workflows=data.get('allowed_workflows', []),
            denied_workflows=data.get('denied_workflows', []),
            allowed_parameters=data.get('allowed_parameters', ["*"]),
            denied_parameters=data.get('denied_parameters', []),
            max_concurrent_tasks=data.get('max_concurrent_tasks', 10),
            daily_quota=data.get('daily_quota', -1),
            can_upload_files=data.get('can_upload_files', True),
            can_delete_files=data.get('can_delete_files', True),
            allow_offline_translation=data.get('allow_offline_translation', False)
        )


@dataclass
class UserAccount:
    """用户账号数据模型"""
    username: str
    password_hash: str
    role: str  # 'admin' 或 'user'
    permissions: UserPermissions
    created_at: datetime
    group: str = "default"  # 用户组名称
    last_login: Optional[datetime] = None
    is_active: bool = True
    must_change_password: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典（用于序列化）"""
        return {
            'username': self.username,
            'password_hash': self.password_hash,
            'role': self.role,
            'group': self.group,
            'permissions': self.permissions.to_dict(),
            'created_at': self.created_at.isoformat(),
            'last_login': self.last_login.isoformat() if self.last_login else None,
            'is_active': self.is_active,
            'must_change_password': self.must_change_password
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'UserAccount':
        """从字典创建（用于反序列化）"""
        return cls(
            username=data['username'],
            password_hash=data['password_hash'],
            role=data['role'],
            permissions=UserPermissions.from_dict(data['permissions']),
            created_at=datetime.fromisoformat(data['created_at']),
            group=data.get('group', 'default'),
            last_login=datetime.fromisoformat(data['last_login']) if data.get('last_login') else None,
            is_active=data.get('is_active', True),
            must_change_password=data.get('must_change_password', False)
        )


@dataclass
class Session:
    """会话数据模型"""
    session_id: str
    username: str
    role: str
    token: str
    created_at: datetime
    last_activity: datetime
    ip_address: str
    user_agent: str
    is_active: bool = True
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典（用于序列化）"""
        return {
            'session_id': self.session_id,
            'username': self.username,
            'role': self.role,
            'token': self.token,
            'created_at': self.created_at.isoformat(),
            'last_activity': self.last_activity.isoformat(),
            'ip_address': self.ip_address,
            'user_agent': self.user_agent,
            'is_active': self.is_active
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Session':
        """从字典创建（用于反序列化）"""
        return cls(
            session_id=data['session_id'],
            username=data['username'],
            role=data['role'],
            token=data['token'],
            created_at=datetime.fromisoformat(data['created_at']),
            last_activity=datetime.fromisoformat(data['last_activity']),
            ip_address=data['ip_address'],
            user_agent=data['user_agent'],
            is_active=data.get('is_active', True)
        )


@dataclass
class AuditEvent:
    """审计事件数据模型"""
    event_id: str
    timestamp: datetime
    event_type: str  # 'login', 'logout', 'create_task', 'permission_change', etc.
    username: str
    ip_address: str
    details: Dict[str, Any]
    result: str  # 'success' 或 'failure'
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典（用于序列化）"""
        return {
            'event_id': self.event_id,
            'timestamp': self.timestamp.isoformat(),
            'event_type': self.event_type,
            'username': self.username,
            'ip_address': self.ip_address,
            'details': self.details,
            'result': self.result
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'AuditEvent':
        """从字典创建（用于反序列化）"""
        return cls(
            event_id=data['event_id'],
            timestamp=datetime.fromisoformat(data['timestamp']),
            event_type=data['event_type'],
            username=data['username'],
            ip_address=data['ip_address'],
            details=data['details'],
            result=data['result']
        )
    
    def to_json_line(self) -> str:
        """转换为 JSON 行（用于日志文件）"""
        return json.dumps(self.to_dict(), ensure_ascii=False)


